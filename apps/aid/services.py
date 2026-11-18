"""Business operations. State transitions, locks, history and notifications live here.

Lock order for linked operations: item -> request -> reservation -> task.
Views and Django admin must not change workflow statuses directly.
"""
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.accounts.models import User
from .models import (Item, HelpRequest, Reservation, VolunteerTask, Transfer,
                     Notification, AuditLog, VolunteerApplication)


def require_coordinator(actor):
    if not actor.is_authenticated or not actor.is_coordinator:
        raise PermissionDenied('Эта операция доступна координатору.')


def audit(actor, obj, action, before=None, note=''):
    fields = set(before or {}) | {'status', 'location'}
    state = {k: str(getattr(obj, k)) for k in sorted(fields) if hasattr(obj, k)}
    AuditLog.objects.create(actor=actor, entity=obj._meta.model_name, object_id=obj.pk,
                            action=action, before=before or {}, after=state, note=note)


def notify(user, title, message, url=''):
    if user is not None:
        Notification.objects.create(recipient=user, title=title, message=message, url=url)


def notify_coordinators(title, message, url=''):
    recipients = User.objects.filter(is_active=True).filter(
        Q(role=User.Role.COORDINATOR) | Q(is_superuser=True))
    Notification.objects.bulk_create([Notification(recipient=u, title=title, message=message, url=url) for u in recipients])


@transaction.atomic
def submit_item(actor, form, on_behalf=False):
    obj = form.save(commit=False)
    obj.registered_by = actor
    obj.status = Item.Status.REVIEW
    obj.location = Item.Location.DONOR
    if on_behalf:
        require_coordinator(actor)
        obj.donor = None
    else:
        obj.donor = actor
    obj.save()
    audit(actor, obj, 'Предложение зарегистрировано')
    notify_coordinators('Новое предложение вещи', obj.title, obj.get_absolute_url())
    return obj


@transaction.atomic
def edit_item(actor, item_id, form):
    obj = Item.objects.select_for_update().get(pk=item_id)
    if not actor.is_coordinator and obj.donor_id != actor.pk:
        raise PermissionDenied
    if obj.status not in (Item.Status.REVIEW, Item.Status.REJECTED):
        raise ValidationError('Изменить можно предложение на проверке или отклонённое предложение.')
    previous = {name: str(getattr(obj, name)) for name in ['status', *form.Meta.fields]}
    for name in form.Meta.fields:
        if name in form.cleaned_data:
            value = form.cleaned_data[name]
            if name == 'photo' and value is False:
                value = ''
            setattr(obj, name, value)
    obj.status = Item.Status.REVIEW
    obj.review_reason = ''
    obj.reviewed_at = None
    obj.reviewed_by = None
    obj.accepted_at = None
    obj.save()
    audit(actor, obj, 'Предложение уточнено', previous)
    return obj


@transaction.atomic
def review_item(actor, item_id, action, reason='', location=None):
    require_coordinator(actor)
    item = Item.objects.select_for_update().get(pk=item_id)
    if item.status != Item.Status.REVIEW:
        raise ValidationError('Предложение уже рассмотрено. Обновите страницу.')
    if action not in ('approve', 'reject'):
        raise ValidationError('Неизвестное решение.')
    if action == 'reject' and not reason.strip():
        raise ValidationError('Укажите причину отказа.')
    previous = {'status': item.status, 'location': item.location}
    if action == 'approve':
        if location not in (Item.Location.DONOR, Item.Location.FUND):
            raise ValidationError('Укажите подтверждённое местонахождение вещи.')
        item.status = Item.Status.AVAILABLE
        item.location = location
        item.accepted_at = timezone.now()
    else:
        item.status = Item.Status.REJECTED
    item.review_reason = reason
    item.reviewed_by = actor
    item.reviewed_at = timezone.now()
    item.save()
    audit(actor, item, 'Вещь принята' if action == 'approve' else 'Предложение отклонено', previous, reason)
    notify(item.donor, 'Предложение рассмотрено', f'{item.title}: {item.get_status_display()}. {reason}', item.get_absolute_url())
    return item


@transaction.atomic
def withdraw_item(actor, item_id, reason):
    item = Item.objects.select_for_update().get(pk=item_id)
    if not actor.is_coordinator and item.donor_id != actor.pk:
        raise PermissionDenied
    if item.status not in (Item.Status.REVIEW, Item.Status.AVAILABLE, Item.Status.REJECTED):
        raise ValidationError('Сначала нужно завершить или отменить действующий резерв через координатора.')
    previous = {'status': item.status}
    item.status = Item.Status.WITHDRAWN
    item.save(update_fields=['status', 'updated_at'])
    audit(actor, item, 'Вещь снята с передачи', previous, reason)
    return item


@transaction.atomic
def submit_request(actor, form, preferred_item=None, on_behalf=False):
    if not on_behalf and preferred_item is None:
        raise ValidationError('Выберите вещь в каталоге, чтобы отправить заявку.')
    obj = form.save(commit=False)
    obj.registered_by = actor
    if on_behalf:
        require_coordinator(actor)
        obj.recipient = None
    else:
        obj.recipient = actor
    if preferred_item:
        item = Item.objects.select_for_update().get(pk=preferred_item.pk)
        if item.status != Item.Status.AVAILABLE:
            raise ValidationError('Вещь уже недоступна. Выберите другую вещь в каталоге.')
        if item.donor_id == actor.pk:
            raise ValidationError('Нельзя подать обращение на собственную вещь.')
        obj.preferred_item = item
        obj.category = item.category
        if obj.recipient and HelpRequest.objects.filter(recipient=actor, preferred_item=item).exclude(
            status__in=[HelpRequest.Status.CANCELLED, HelpRequest.Status.REJECTED, HelpRequest.Status.COMPLETED]).exists():
            raise ValidationError('У вас уже есть активное обращение на эту вещь.')
    obj.status = HelpRequest.Status.NEW
    obj.save()
    audit(actor, obj, 'Обращение зарегистрировано')
    notify_coordinators('Новое обращение', f'Обращение №{obj.pk}', obj.get_absolute_url())
    return obj


@transaction.atomic
def edit_request(actor, request_id, form):
    obj = HelpRequest.objects.select_for_update().get(pk=request_id)
    if obj.recipient_id != actor.pk:
        raise PermissionDenied
    if obj.status not in (HelpRequest.Status.NEW, HelpRequest.Status.CLARIFICATION, HelpRequest.Status.REJECTED):
        raise ValidationError('Обращение уже согласовано. Для изменений свяжитесь с координатором.')
    before = {name: str(getattr(obj, name)) for name in ['status', *form.Meta.fields]}
    for name in form.Meta.fields:
        setattr(obj, name, form.cleaned_data[name])
    obj.status = HelpRequest.Status.NEW
    obj.decision_reason = ''
    obj.save()
    audit(actor, obj, 'Получатель изменил обращение', before)
    notify_coordinators('Обращение изменено', f'№{obj.pk}: проверьте обновлённые данные.', obj.get_absolute_url())
    return obj


@transaction.atomic
def decide_request(actor, request_id, action, reason='', staff_note=''):
    require_coordinator(actor)
    obj = HelpRequest.objects.select_for_update().get(pk=request_id)
    if obj.status not in (HelpRequest.Status.NEW, HelpRequest.Status.CLARIFICATION, HelpRequest.Status.APPROVED):
        raise ValidationError('Для обращения с резервом сначала используйте операции резерва.')
    mapping = {'approve': HelpRequest.Status.APPROVED, 'clarify': HelpRequest.Status.CLARIFICATION, 'reject': HelpRequest.Status.REJECTED}
    if action not in mapping:
        raise ValidationError('Неизвестное решение.')
    if action != 'approve' and not reason.strip():
        raise ValidationError('Напишите причину или вопрос получателю.')
    before = {'status': obj.status}
    obj.status = mapping[action]
    obj.coordinator = actor
    obj.decision_reason = reason
    obj.staff_note = staff_note
    obj.save()
    audit(actor, obj, 'Решение по обращению', before, reason)
    notify(obj.recipient, 'Обновление обращения', f'№{obj.pk}: {obj.get_status_display()}. {reason}', obj.get_absolute_url())
    return obj


@transaction.atomic
def clarify_request(actor, request_id, need, contact_phone, delivery_address):
    obj = HelpRequest.objects.select_for_update().get(pk=request_id)
    if obj.recipient_id != actor.pk:
        raise PermissionDenied
    if obj.status != HelpRequest.Status.CLARIFICATION:
        raise ValidationError('Сейчас уточнение не запрошено.')
    obj.need = need
    obj.contact_phone = contact_phone
    obj.delivery_address = delivery_address
    obj.status = HelpRequest.Status.NEW
    obj.save()
    audit(actor, obj, 'Получатель уточнил обращение', {'status': HelpRequest.Status.CLARIFICATION})
    notify_coordinators('Обращение уточнено', f'№{obj.pk}', obj.get_absolute_url())
    return obj


@transaction.atomic
def reserve(actor, request_id, item_id, expires_at, meeting_at=None, meeting_note=''):
    require_coordinator(actor)
    if expires_at <= timezone.now() or expires_at > timezone.now() + timedelta(days=30):
        raise ValidationError('Срок резерва должен быть в будущем, не более 30 дней.')
    if meeting_at and (meeting_at < timezone.now() or meeting_at > expires_at):
        raise ValidationError('Время встречи должно быть в будущем и до окончания резерва.')
    item = Item.objects.select_for_update().get(pk=item_id)
    obj = HelpRequest.objects.select_for_update().get(pk=request_id)
    if item.status != Item.Status.AVAILABLE or obj.status != HelpRequest.Status.APPROVED:
        raise ValidationError('Вещь недоступна или обращение ещё не одобрено. Обновите страницу.')
    if item.category_id != obj.category_id:
        raise ValidationError('Категория вещи должна соответствовать обращению.')
    if item.donor_id is not None and item.donor_id == obj.recipient_id:
        raise ValidationError('Жертвователь не может быть получателем собственной вещи.')
    if Reservation.objects.filter(item=item, status=Reservation.Status.ACTIVE).exists():
        raise ValidationError('Вещь уже зарезервирована другим координатором.')
    if Reservation.objects.filter(request=obj, status=Reservation.Status.ACTIVE).exists():
        raise ValidationError('Для обращения уже есть действующий резерв.')
    result = Reservation.objects.create(item=item, request=obj, created_by=actor, expires_at=expires_at, meeting_at=meeting_at, meeting_note=meeting_note)
    item.status = Item.Status.RESERVED
    item.save(update_fields=['status', 'updated_at'])
    obj.status = HelpRequest.Status.RESERVED
    obj.coordinator = actor
    obj.save(update_fields=['status', 'coordinator', 'updated_at'])
    audit(actor, item, 'Создан резерв', {'status': Item.Status.AVAILABLE}, f'Обращение №{obj.pk}')
    audit(actor, obj, 'Создан резерв', {'status': HelpRequest.Status.APPROVED}, f'Вещь №{item.pk}')
    notify(obj.recipient, 'Вещь зарезервирована для вас', f'{item.title}. {meeting_note}', obj.get_absolute_url())
    notify(item.donor, 'Согласуется передача вещи', item.title, item.get_absolute_url())
    return result


def _locked_reservation(reservation_id):
    ref = Reservation.objects.values('item_id', 'request_id').get(pk=reservation_id)
    item = Item.objects.select_for_update().get(pk=ref['item_id'])
    obj = HelpRequest.objects.select_for_update().get(pk=ref['request_id'])
    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
    return item, obj, reservation


def _cancel_locked(actor, item, obj, reservation, reason, return_location='', expired=False):
    if reservation.status != Reservation.Status.ACTIVE:
        raise ValidationError('Резерв уже закрыт.')
    if not reason.strip():
        raise ValidationError('Укажите причину отмены.')
    task = VolunteerTask.objects.select_for_update().filter(reservation=reservation).first()
    physically_moved = item.location in (Item.Location.TRANSIT, Item.Location.RECIPIENT)
    if physically_moved and return_location not in (Item.Location.DONOR, Item.Location.FUND):
        raise ValidationError('Вещь уже перемещена. Сначала подтвердите её возврат жертвователю или в пункт фонда.')
    if return_location:
        if return_location not in (Item.Location.DONOR, Item.Location.FUND):
            raise ValidationError('Некорректное местонахождение возврата.')
        item.location = return_location
    if task:
        task.status = VolunteerTask.Status.CANCELLED
        task.result_note = reason
        task.save(update_fields=['status', 'result_note', 'updated_at'])
        notify(task.volunteer, 'Поручение отменено', reason, task.get_absolute_url())
        audit(actor, task, 'Поручение отменено', note=reason)
    reservation.status = Reservation.Status.EXPIRED if expired else Reservation.Status.CANCELLED
    reservation.cancellation_reason = reason
    reservation.save(update_fields=['status', 'cancellation_reason', 'updated_at'])
    item.status = Item.Status.AVAILABLE
    item.save(update_fields=['status', 'location', 'updated_at'])
    obj.status = HelpRequest.Status.APPROVED
    obj.save(update_fields=['status', 'updated_at'])
    audit(actor, reservation, 'Срок резерва истёк' if expired else 'Резерв отменён', {'status': Reservation.Status.ACTIVE}, reason)
    audit(actor, obj, 'Обращение возвращено к подбору', {'status': HelpRequest.Status.RESERVED})
    audit(actor, item, 'Вещь освобождена из резерва', {'status': Item.Status.RESERVED})
    notify(obj.recipient, 'Резерв закрыт', reason, obj.get_absolute_url())
    notify(item.donor, 'Резерв вещи закрыт', reason, item.get_absolute_url())


@transaction.atomic
def cancel_reservation(actor, reservation_id, reason, return_location=''):
    require_coordinator(actor)
    item, obj, reservation = _locked_reservation(reservation_id)
    _cancel_locked(actor, item, obj, reservation, reason, return_location)


@transaction.atomic
def cancel_request(actor, request_id, reason):
    if not reason.strip():
        raise ValidationError('Укажите причину отмены.')
    # An active reservation can be created between the initial read and locks;
    # retries are avoided by taking an item lock before the request when present.
    ref = Reservation.objects.filter(request_id=request_id, status=Reservation.Status.ACTIVE).first()
    if ref:
        item, obj, reservation = _locked_reservation(ref.pk)
    else:
        obj = HelpRequest.objects.select_for_update().get(pk=request_id)
        if Reservation.objects.filter(request=obj, status=Reservation.Status.ACTIVE).exists():
            raise ValidationError('Состояние изменилось. Обновите страницу и повторите отмену.')
    if not actor.is_coordinator and obj.recipient_id != actor.pk:
        raise PermissionDenied
    if obj.status in (HelpRequest.Status.COMPLETED, HelpRequest.Status.REJECTED, HelpRequest.Status.CANCELLED):
        raise ValidationError('Обращение уже закрыто.')
    if ref:
        _cancel_locked(actor, item, obj, reservation, reason)
    before = {'status': obj.status}
    obj.status = HelpRequest.Status.CANCELLED
    obj.save(update_fields=['status', 'updated_at'])
    audit(actor, obj, 'Обращение отменено', before, reason)
    notify_coordinators('Обращение отменено', f'№{obj.pk}', obj.get_absolute_url())
    return obj


@transaction.atomic
def create_task(actor, reservation_id, form):
    require_coordinator(actor)
    item, obj, reservation = _locked_reservation(reservation_id)
    if reservation.status != Reservation.Status.ACTIVE or reservation.expires_at <= timezone.now():
        raise ValidationError('Для поручения нужен действующий резерв.')
    if VolunteerTask.objects.filter(reservation=reservation).exists():
        raise ValidationError('Для этого резерва поручение уже создано.')
    task = form.save(commit=False)
    if task.scheduled_at > reservation.expires_at:
        raise ValidationError('Время доставки должно быть до окончания резерва.')
    task.reservation = reservation
    task.status = VolunteerTask.Status.OPEN
    task.district = item.district
    task.save()
    audit(actor, task, 'Создано поручение')
    return task


@transaction.atomic
def task_action(actor, task_id, action, note=''):
    if not actor.is_authenticated or not actor.is_volunteer:
        raise PermissionDenied
    ref = VolunteerTask.objects.values('reservation_id').get(pk=task_id)
    item, obj, reservation = _locked_reservation(ref['reservation_id'])
    task = VolunteerTask.objects.select_for_update().get(pk=task_id)
    if reservation.status != Reservation.Status.ACTIVE:
        raise ValidationError('Резерв уже закрыт.')
    previous = {'status': task.status}
    if action == 'accept':
        if task.status != VolunteerTask.Status.OPEN or task.volunteer_id:
            raise ValidationError('Поручение уже принято. Обновите страницу.')
        if reservation.expires_at <= timezone.now():
            raise ValidationError('Срок резерва истёк. Свяжитесь с координатором.')
        task.volunteer = actor
        task.status = VolunteerTask.Status.ACCEPTED
    else:
        if task.volunteer_id != actor.pk and not actor.is_coordinator:
            raise PermissionDenied
        if action == 'decline':
            if task.status != VolunteerTask.Status.ACCEPTED:
                raise ValidationError('После получения вещи отмена возможна только через координатора с фиксацией возврата.')
            if not note.strip():
                raise ValidationError('Укажите причину отказа.')
            task.volunteer = None
            task.status = VolunteerTask.Status.OPEN
        elif action == 'start':
            if task.status != VolunteerTask.Status.ACCEPTED or reservation.expires_at <= timezone.now():
                raise ValidationError('Поручение не принято или срок резерва истёк.')
            task.status = VolunteerTask.Status.IN_PROGRESS
            item.location = Item.Location.TRANSIT
            item.save(update_fields=['location', 'updated_at'])
        elif action == 'deliver':
            if task.status != VolunteerTask.Status.IN_PROGRESS:
                raise ValidationError('Сначала нужно отметить получение вещи у жертвователя.')
            if not note.strip():
                raise ValidationError('Укажите, кому передана вещь и как подтверждена доставка.')
            task.status = VolunteerTask.Status.DELIVERED
            item.location = Item.Location.RECIPIENT
            item.save(update_fields=['location', 'updated_at'])
        else:
            raise ValidationError('Неизвестная операция.')
    task.result_note = note
    task.save()
    audit(actor, task, 'Изменено поручение', previous, note)
    notify_coordinators('Обновление поручения', f'{task.title}: {task.get_status_display()}', task.get_absolute_url())
    return task


@transaction.atomic
def complete_transfer(actor, reservation_id, transferred_at, note):
    require_coordinator(actor)
    item, obj, reservation = _locked_reservation(reservation_id)
    if reservation.status != Reservation.Status.ACTIVE:
        raise ValidationError('Передача уже подтверждена или резерв закрыт.')
    if reservation.expires_at <= timezone.now() and item.location not in (Item.Location.TRANSIT, Item.Location.RECIPIENT):
        raise ValidationError('Срок резерва истёк. Сначала закройте резерв и согласуйте новый срок передачи.')
    # Browser datetime controls have minute precision. A confirmation made in
    # the reservation's first minute must remain valid after that truncation.
    if transferred_at > timezone.now() or transferred_at < reservation.created_at.replace(second=0, microsecond=0):
        raise ValidationError('Фактическая передача должна быть после создания резерва и не в будущем.')
    if not note.strip():
        raise ValidationError('Укажите основание подтверждения получения.')
    task = VolunteerTask.objects.select_for_update().filter(reservation=reservation).first()
    if task and task.status != VolunteerTask.Status.DELIVERED:
        raise ValidationError('Дождитесь отметки волонтёра о доставке либо отмените поручение и согласуйте прямую передачу.')
    result = Transfer.objects.create(reservation=reservation, confirmed_by=actor, transferred_at=transferred_at, confirmation_note=note)
    reservation.status = Reservation.Status.FULFILLED
    reservation.save(update_fields=['status', 'updated_at'])
    item.status = Item.Status.DELIVERED
    item.location = Item.Location.RECIPIENT
    item.save(update_fields=['status', 'location', 'updated_at'])
    obj.status = HelpRequest.Status.COMPLETED
    obj.save(update_fields=['status', 'updated_at'])
    audit(actor, item, 'Передача подтверждена', {'status': Item.Status.RESERVED}, note)
    audit(actor, obj, 'Помощь предоставлена', {'status': HelpRequest.Status.RESERVED}, note)
    audit(actor, result, 'Создана запись передачи', note=note)
    notify(obj.recipient, 'Получение помощи подтверждено', item.title, obj.get_absolute_url())
    notify(item.donor, 'Ваша вещь передана', item.title, item.get_absolute_url())
    return result


@transaction.atomic
def reverse_transfer(actor, transfer_id, reason, return_location):
    require_coordinator(actor)
    ref = Transfer.objects.values('reservation_id').get(pk=transfer_id)
    item, obj, reservation = _locked_reservation(ref['reservation_id'])
    transfer = Transfer.objects.select_for_update().get(pk=transfer_id)
    if transfer.reversed_at:
        raise ValidationError('Эта запись уже исправлена.')
    if not reason.strip() or return_location not in (Item.Location.DONOR, Item.Location.FUND):
        raise ValidationError('Нужны причина исправления и подтверждённое местонахождение вещи.')
    if item.status != Item.Status.DELIVERED:
        raise ValidationError('Текущее состояние вещи не позволяет исправить эту передачу.')
    transfer.reversed_at = timezone.now()
    transfer.reversed_by = actor
    transfer.reversal_reason = reason
    transfer.save(update_fields=['reversed_at', 'reversed_by', 'reversal_reason'])
    reservation.status = Reservation.Status.CANCELLED
    reservation.cancellation_reason = reason
    reservation.save(update_fields=['status', 'cancellation_reason', 'updated_at'])
    item.status = Item.Status.AVAILABLE
    item.location = return_location
    item.save(update_fields=['status', 'location', 'updated_at'])
    obj.status = HelpRequest.Status.APPROVED
    obj.save(update_fields=['status', 'updated_at'])
    audit(actor, transfer, 'Передача исправлена', note=reason)
    audit(actor, item, 'Вещь возвращена в учёт', {'status': Item.Status.DELIVERED}, reason)
    audit(actor, obj, 'Обращение возвращено к подбору', {'status': HelpRequest.Status.COMPLETED}, reason)
    notify(obj.recipient, 'Запись передачи исправлена', reason, obj.get_absolute_url())
    return transfer


@transaction.atomic
def decide_volunteer(actor, application_id, action, reason=''):
    require_coordinator(actor)
    app = VolunteerApplication.objects.select_for_update().get(pk=application_id)
    if app.status != VolunteerApplication.Status.NEW:
        raise ValidationError('Заявка уже рассмотрена.')
    if action not in ('approve', 'reject'):
        raise ValidationError('Неизвестное решение.')
    if action == 'reject' and not reason.strip():
        raise ValidationError('Укажите причину.')
    user = User.objects.select_for_update().get(pk=app.user_id)
    if action == 'approve':
        app.status = VolunteerApplication.Status.APPROVED
        if user.role == User.Role.MEMBER:
            user.role = User.Role.VOLUNTEER
            user.save(update_fields=['role'])
    else:
        app.status = VolunteerApplication.Status.REJECTED
    app.decision_reason = reason
    app.save()
    audit(actor, app, 'Рассмотрена заявка волонтёра', note=reason)
    notify(user, 'Заявка волонтёра рассмотрена', app.get_status_display() + '. ' + reason, '/volunteers/')
    return app


def expire_reservations():
    """Safely release only items that have not physically left donor/fund."""
    ids = Reservation.objects.filter(status=Reservation.Status.ACTIVE, expires_at__lt=timezone.now()).values_list('pk', flat=True)
    released = 0
    for pk in list(ids):
        with transaction.atomic():
            item, obj, reservation = _locked_reservation(pk)
            if reservation.status != Reservation.Status.ACTIVE or reservation.expires_at >= timezone.now():
                continue
            if item.location in (Item.Location.TRANSIT, Item.Location.RECIPIENT):
                if not reservation.overdue_notified:
                    reservation.overdue_notified = True
                    reservation.save(update_fields=['overdue_notified', 'updated_at'])
                    notify_coordinators('Просроченная передача требует проверки', f'{item.title}, обращение №{obj.pk}. Резерв сохранён: вещь уже перемещена.', obj.get_absolute_url())
                    audit(None, reservation, 'Просрочка: ожидается проверка местонахождения')
                continue
            _cancel_locked(None, item, obj, reservation, 'Истёк согласованный срок резерва.', expired=True)
            released += 1
    return released
