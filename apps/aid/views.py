"""HTTP layer: authorization, forms and rendering. Workflow lives in services.py."""
import csv
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Count
from django.http import FileResponse, HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.accounts.models import User
from . import services
from .forms import (ItemForm, ItemReviewForm, HelpRequestForm, DecisionForm,
                    ReservationForm, ReasonForm, ReservationCancelForm, TransferForm,
                    TransferReversalForm, TaskForm, TaskActionForm, VolunteerForm,
                    VolunteerDecisionForm, ReportForm, ClarificationForm, RequestEditForm)
from .models import (Item, Category, HelpRequest, Reservation, VolunteerTask,
                     Transfer, Notification, Favorite, AuditLog, VolunteerApplication)
from .permissions import coordinator_required, visible_items, visible_requests, visible_tasks, public_items


def paginate(request, queryset, size=12):
    return Paginator(queryset, size).get_page(request.GET.get('page'))


def try_operation(form, operation):
    try:
        return operation()
    except ValidationError as exc:
        form.add_error(None, exc)
    except IntegrityError:
        form.add_error(None, 'Запись уже изменена другим участником. Обновите страницу и проверьте состояние.')
    return None


def workflow_form(request, *, form, title, subtitle='', submit='Сохранить', back_url='dashboard', operation=None):
    if request.method == 'POST' and form.is_valid():
        result = try_operation(form, operation)
        if result is not None:
            messages.success(request, 'Изменения сохранены.')
            return redirect(result.get_absolute_url() if hasattr(result, 'get_absolute_url') else back_url)
    return render(request, 'aid/form.html', {'form': form, 'page_title': title, 'subtitle': subtitle, 'submit_label': submit, 'back_url': back_url, 'is_item_form': isinstance(form, ItemForm)})


def home(request):
    return render(request, 'aid/home.html', {
        'items': public_items().select_related('category')[:4],
        'categories': Category.objects.annotate(available_count=Count('items', filter=Q(items__status=Item.Status.AVAILABLE))).order_by('order', 'name'),
        'available_count': public_items().count(),
        'transfer_count': Transfer.objects.filter(reversed_at__isnull=True).count(),
        'volunteer_count': User.objects.filter(role=User.Role.VOLUNTEER, is_active=True).count(),
    })


def catalog(request):
    items = public_items().select_related('category')
    q = request.GET.get('q', '').strip()[:150]
    category = request.GET.get('category', '')
    district = request.GET.get('district', '')
    condition = request.GET.get('condition', '')
    placement = request.GET.get('placement', '')
    if placement in Item.Placement.values:
        items = items.filter(placement=placement)
    if q:
        items = items.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(size__icontains=q))
    if category:
        items = items.filter(category__slug=category)
    if district in User.District.values:
        items = items.filter(district=district)
    if condition in Item.Condition.values:
        items = items.filter(condition=condition)
    if request.GET.get('available') == '1':
        items = items.filter(status=Item.Status.AVAILABLE)
    sort = request.GET.get('sort', 'new')
    items = items.order_by('created_at' if sort == 'old' else 'title' if sort == 'title' else '-created_at')
    favorite_ids = set(request.user.favorites.values_list('item_id', flat=True)) if request.user.is_authenticated else set()
    return render(request, 'aid/catalog.html', {
        'page_obj': paginate(request, items), 'categories': Category.objects.all(),
        'districts': User.District.choices, 'conditions': Item.Condition.choices,
        'favorite_ids': favorite_ids, 'filters': {'q': q, 'category': category, 'district': district, 'condition': condition, 'sort': sort, 'placement': placement},
    })


def item_detail(request, pk):
    item = get_object_or_404(visible_items(request.user).select_related('category', 'donor'), pk=pk)
    own = request.user.is_authenticated and item.donor_id == request.user.pk
    staff = request.user.is_authenticated and request.user.is_coordinator
    reservation = item.reservations.filter(status=Reservation.Status.ACTIVE).select_related('request').first() if own or staff else None
    history = AuditLog.objects.filter(entity='item', object_id=item.pk)[:15] if own or staff else []
    point = None
    if item.latitude is not None and item.longitude is not None:
        point = {'latitude': float(item.latitude) if item.placement == 'street' else round(float(item.latitude), 3), 'longitude': float(item.longitude) if item.placement == 'street' else round(float(item.longitude), 3), 'approximate': item.placement != 'street'}
    return render(request, 'aid/item_detail.html', {
        'map_point': point,
        'item': item, 'own_item': own, 'staff_item': staff, 'reservation': reservation, 'history': history,
        'is_favorite': request.user.is_authenticated and Favorite.objects.filter(user=request.user, item=item).exists(),
        'can_edit': (own or staff) and item.status in [Item.Status.REVIEW, Item.Status.REJECTED, Item.Status.AVAILABLE],
        'can_withdraw': (own or staff) and item.status in [Item.Status.REVIEW, Item.Status.AVAILABLE, Item.Status.REJECTED],
    })


def item_photo(request, pk):
    item = get_object_or_404(visible_items(request.user), pk=pk)
    if not item.photo:
        from django.http import Http404
        raise Http404
    response = FileResponse(item.photo.open('rb'), content_type='image/jpeg')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, max-age=0, no-store'
    return response


@login_required
def item_create(request):
    behalf = request.GET.get('on_behalf') == '1' and request.user.is_coordinator
    form = ItemForm(request.POST or None, request.FILES or None, initial={
        'donor_name': '' if behalf else request.user.display_name,
        'contact_phone': '' if behalf else request.user.phone, 'district': request.user.district,
        'placement': request.GET.get('placement') if request.GET.get('placement') in Item.Placement.values else Item.Placement.HOME,
    })
    return workflow_form(request, form=form, title='Разместить вещь',
                         subtitle='',
                         submit='Разместить вещь', operation=lambda: services.submit_item(request.user, form, behalf))


@login_required
def item_edit(request, pk):
    item = get_object_or_404(visible_items(request.user), pk=pk)
    if item.donor_id != request.user.pk and not request.user.is_coordinator:
        raise PermissionDenied
    if item.status not in (Item.Status.REVIEW, Item.Status.REJECTED, Item.Status.AVAILABLE):
        messages.error(request, 'Редактирование недоступно для текущего состояния вещи.')
        return redirect(item)
    form = ItemForm(request.POST or None, request.FILES or None, instance=item)
    return workflow_form(request, form=form, title='Редактировать объявление', submit='Сохранить изменения',
                         back_url=item.get_absolute_url(), operation=lambda: services.edit_item(request.user, pk, form))


@coordinator_required
def item_review(request, pk):
    item = get_object_or_404(Item, pk=pk)
    form = ItemReviewForm(request.POST or None)
    return workflow_form(request, form=form, title=f'Проверка: {item.title}',
                         subtitle='Проверьте фото, описание и допустимость публикации. Проверка не подтверждает наличие вещи на месте.',
                         back_url=item.get_absolute_url(), operation=lambda: services.review_item(request.user, pk, **form.cleaned_data))


@login_required
def item_withdraw(request, pk):
    item = get_object_or_404(visible_items(request.user), pk=pk)
    if item.donor_id != request.user.pk and not request.user.is_coordinator:
        raise PermissionDenied
    form = ReasonForm(request.POST or None)
    return workflow_form(request, form=form, title='Закрыть объявление', subtitle=item.title,
                         back_url=item.get_absolute_url(), operation=lambda: services.withdraw_item(request.user, pk, form.cleaned_data['reason']))


@login_required
@require_POST
def favorite_toggle(request, pk):
    item = get_object_or_404(visible_items(request.user), pk=pk)
    favorite, created = Favorite.objects.get_or_create(user=request.user, item=item)
    if not created:
        favorite.delete()
    return redirect(item)


@login_required
def favorites(request):
    items = visible_items(request.user).filter(favorite__user=request.user).select_related('category')
    return render(request, 'aid/favorites.html', {'page_obj': paginate(request, items)})


@login_required
def dashboard(request):
    context = {
        'own_items': Item.objects.filter(donor=request.user).select_related('category')[:6],
        'own_requests': request.user.help_requests.select_related('preferred_item__category', 'unselected_category', 'contact')[:6],
        'tasks': visible_tasks(request.user).exclude(status=VolunteerTask.Status.CANCELLED).select_related('reservation__item')[:4] if request.user.is_volunteer else [],
    }
    if request.user.is_coordinator:
        context.update({
            'pending_items': Item.objects.filter(status=Item.Status.REVIEW).count(),
            'pending_requests': HelpRequest.objects.filter(status__in=[HelpRequest.Status.NEW, HelpRequest.Status.CLARIFICATION]).count(),
            'active_reservations': Reservation.objects.filter(status=Reservation.Status.ACTIVE).count(),
            'unassigned_tasks': VolunteerTask.objects.filter(status=VolunteerTask.Status.OPEN).count(),
            'recent_requests': HelpRequest.objects.select_related('preferred_item__category', 'unselected_category', 'contact', 'coordinator')[:6],
            'expiring': Reservation.objects.filter(status=Reservation.Status.ACTIVE, expires_at__lte=timezone.now()+timedelta(days=1)).select_related('item', 'request')[:5],
        })
    return render(request, 'aid/dashboard.html', context)


@login_required
def my_items(request):
    return render(request, 'aid/my_items.html', {'page_obj': paginate(request, Item.objects.filter(donor=request.user).select_related('category'))})


@login_required
def my_requests(request):
    return render(request, 'aid/requests.html', {'page_obj': paginate(request, request.user.help_requests.select_related('preferred_item__category', 'unselected_category', 'contact'))})


@login_required
def request_create(request):
    behalf = request.GET.get('on_behalf') == '1' and request.user.is_coordinator
    preferred = None
    if request.GET.get('item'):
        if not request.GET['item'].isascii() or not request.GET['item'].isdigit() or len(request.GET['item']) > 18:
            raise Http404
        preferred = get_object_or_404(Item, pk=request.GET['item'], status=Item.Status.AVAILABLE)
    if not preferred and not behalf:
        messages.info(request, 'Выберите вещь в каталоге, чтобы отправить заявку.')
        return redirect('catalog')
    if preferred:
        return redirect('item_contact', pk=preferred.pk)
    initial = {'recipient_name': '' if behalf else request.user.display_name,
               'contact_phone': '' if behalf else request.user.phone, 'district': request.user.district}
    if preferred:
        initial.update(category=preferred.category, need=f'Хочу получить: {preferred.title}.')
    form = HelpRequestForm(request.POST or None, initial=initial)
    if preferred:
        form.fields['category'].disabled = True
        form.fields['need'].label = 'Комментарий к заявке'
        form.fields['need'].help_text = 'Можно указать удобное время передачи или задать вопрос о вещи.'
    return workflow_form(request, form=form, title='Записать обращение' if behalf else 'Заявка на вещь',
                         subtitle=f'{preferred.title}. Укажите контакты, чтобы договориться о передаче.' if preferred else 'Запишите обращение человека, который связался с фондом.',
                         submit='Сохранить обращение' if behalf else 'Отправить заявку',
                         back_url=preferred.get_absolute_url() if preferred else 'workspace',
                         operation=lambda: services.submit_request(request.user, form, preferred, behalf))


@login_required
def request_detail(request, pk):
    obj = get_object_or_404(visible_requests(request.user).select_related('preferred_item__category', 'unselected_category', 'contact', 'recipient', 'coordinator'), pk=pk)
    reservation = obj.reservations.filter(status=Reservation.Status.ACTIVE).select_related('item').first()
    task = VolunteerTask.objects.filter(reservation=reservation).first() if reservation else None
    transfer = Transfer.objects.filter(reservation__request=obj, reversed_at__isnull=True).first()
    clarification = ClarificationForm(request.POST or None, instance=obj) if obj.status == HelpRequest.Status.CLARIFICATION and obj.recipient_id == request.user.pk else None
    if request.method == 'POST' and clarification and clarification.is_valid():
        result = try_operation(clarification, lambda: services.clarify_request(request.user, pk, **clarification.cleaned_data))
        if result:
            messages.success(request, 'Уточнение отправлено модератору.')
            return redirect(obj)
    return render(request, 'aid/request_detail.html', {'help_request': obj, 'reservation': reservation, 'task': task, 'transfer': transfer,
        'clarification_form': clarification, 'history': AuditLog.objects.filter(entity='helprequest', object_id=obj.pk)[:20],
        'can_edit': obj.recipient_id == request.user.pk and obj.status in (HelpRequest.Status.NEW, HelpRequest.Status.CLARIFICATION, HelpRequest.Status.REJECTED),
        'can_cancel': obj.status not in (HelpRequest.Status.COMPLETED, HelpRequest.Status.REJECTED, HelpRequest.Status.CANCELLED)})


@coordinator_required
def request_decide(request, pk):
    obj = get_object_or_404(HelpRequest, pk=pk)
    form = DecisionForm(request.POST or None, initial={'staff_note': obj.staff_note})
    return workflow_form(request, form=form, title=f'Рассмотреть обращение №{obj.pk}', back_url=obj.get_absolute_url(),
                         operation=lambda: services.decide_request(request.user, pk, **form.cleaned_data))


@login_required
def request_edit(request, pk):
    obj = get_object_or_404(HelpRequest, pk=pk, recipient=request.user)
    if obj.status not in (HelpRequest.Status.NEW, HelpRequest.Status.CLARIFICATION, HelpRequest.Status.REJECTED):
        messages.error(request, 'Обращение уже подтверждено. Для изменений свяжитесь с модератором.')
        return redirect(obj)
    form = RequestEditForm(request.POST or None, instance=obj)
    return workflow_form(request, form=form, title=f'Изменить обращение №{pk}',
                         subtitle=f'Выбранная вещь: {obj.preferred_item.title}.' if obj.preferred_item_id else '',
                         submit='Сохранить и отправить на рассмотрение', back_url=obj.get_absolute_url(),
                         operation=lambda: services.edit_request(request.user, pk, form))


@login_required
def request_cancel(request, pk):
    obj = get_object_or_404(visible_requests(request.user), pk=pk)
    form = ReasonForm(request.POST or None)
    return workflow_form(request, form=form, title=f'Отменить обращение №{pk}', back_url=obj.get_absolute_url(),
                         subtitle='Если вещь уже у волонтёра, сначала свяжитесь с модератором для обсуждения возврата.',
                         operation=lambda: services.cancel_request(request.user, pk, form.cleaned_data['reason']))


@coordinator_required
def request_reserve(request, pk):
    obj = get_object_or_404(HelpRequest, pk=pk)
    form = ReservationForm(request.POST or None, help_request=obj)
    def operation():
        values = dict(form.cleaned_data)
        item = values.pop('item')
        services.reserve(request.user, pk, item.pk, **values)
        return obj
    return workflow_form(request, form=form, title=f'Подобрать вещь: обращение №{pk}', back_url=obj.get_absolute_url(),
                         subtitle='Выберите доступную вещь нужной категории и укажите срок резерва.', operation=operation)


@coordinator_required
def reservation_cancel(request, pk):
    reservation = get_object_or_404(Reservation.objects.select_related('request', 'item'), pk=pk)
    form = ReservationCancelForm(request.POST or None)
    def operation():
        services.cancel_reservation(request.user, pk, **form.cleaned_data)
        return reservation.request
    return workflow_form(request, form=form, title='Отменить резерв', subtitle=f'{reservation.item.title}. Если вещь перемещена, сначала проверьте её возврат.',
                         back_url=reservation.request.get_absolute_url(), operation=operation)


@coordinator_required
def transfer_complete(request, pk):
    reservation = get_object_or_404(Reservation.objects.select_related('request'), pk=pk)
    form = TransferForm(request.POST or None)
    def operation():
        services.complete_transfer(request.user, pk, form.cleaned_data['transferred_at'], form.cleaned_data['note'])
        return reservation.request
    return workflow_form(request, form=form, title='Подтвердить фактическую передачу', subtitle='После подтверждения вещь закроется, а передача попадёт в отчёт.',
                         submit='Подтвердить получение', back_url=reservation.request.get_absolute_url(), operation=operation)


@coordinator_required
def transfer_reverse(request, pk):
    transfer = get_object_or_404(Transfer.objects.select_related('reservation__request'), pk=pk)
    form = TransferReversalForm(request.POST or None)
    def operation():
        services.reverse_transfer(request.user, pk, form.cleaned_data['reason'], form.cleaned_data['return_location'])
        return transfer.reservation.request
    return workflow_form(request, form=form, title='Исправить ошибочно подтверждённую передачу',
                         subtitle='Исходная запись сохранится в истории. Исправленная выдача исключается из отчёта.',
                         back_url=transfer.reservation.request.get_absolute_url(), operation=operation)


@coordinator_required
def task_create(request, pk):
    reservation = get_object_or_404(Reservation.objects.select_related('item', 'request'), pk=pk)
    form = TaskForm(request.POST or None, initial={
        'title': f'Передать: {reservation.item.title}',
        'pickup_address': reservation.item.pickup_address,
        'dropoff_address': reservation.request.delivery_address,
        'scheduled_at': reservation.meeting_at,
        'description': f'Нужно передать вещь: {reservation.item.title}. {reservation.item.size}',
    })
    return workflow_form(request, form=form, title='Создать поручение волонтёру',
                         back_url=reservation.request.get_absolute_url(), operation=lambda: services.create_task(request.user, pk, form))


def volunteers(request):
    application = VolunteerApplication.objects.filter(user=request.user).first() if request.user.is_authenticated else None
    return render(request, 'aid/volunteers.html', {'application': application})


@login_required
def volunteer_apply(request):
    existing = VolunteerApplication.objects.filter(user=request.user).first()
    if request.user.is_volunteer or (existing and existing.status == VolunteerApplication.Status.APPROVED):
        return redirect('volunteers')
    form = VolunteerForm(request.POST or None, instance=existing)
    def operation():
        with transaction.atomic():
            app = form.save(commit=False)
            app.user = request.user
            app.status = VolunteerApplication.Status.APPROVED
            app.decision_reason = ''
            app.save()
            if request.user.role == User.Role.MEMBER:
                request.user.role = User.Role.VOLUNTEER
                request.user.save(update_fields=['role'])
            services.audit(request.user, app, 'Участник включил помощь с вещами')

        return 'volunteers'
    if request.method == 'POST' and form.is_valid():
        result = try_operation(form, operation)
        if result:
            messages.success(request, 'Вы можете помогать другим участникам.')
            return redirect('volunteers')
    return render(request, 'aid/form.html', {'form': form, 'page_title': 'Стать волонтёром', 'submit_label': 'Отправить заявку', 'back_url': 'volunteers'})


@coordinator_required
def volunteer_decide(request, pk):
    app = get_object_or_404(VolunteerApplication.objects.select_related('user'), pk=pk)
    form = VolunteerDecisionForm(request.POST or None)
    def operation():
        services.decide_volunteer(request.user, pk, **form.cleaned_data)
        return True
    return workflow_form(request, form=form, title=f'Заявка волонтёра: {app.user.display_name}',
                         subtitle=f'{app.availability}. {app.description}', back_url='workspace', operation=operation)


@login_required
def task_list(request):
    if not request.user.is_volunteer:
        return redirect('volunteers')
    tasks = visible_tasks(request.user).select_related('reservation__item__category', 'volunteer')
    mode = request.GET.get('mode', 'open')
    if mode == 'mine':
        tasks = tasks.filter(volunteer=request.user)
    elif mode == 'all' and request.user.is_coordinator:
        pass
    else:
        tasks = tasks.filter(status=VolunteerTask.Status.OPEN, reservation__status=Reservation.Status.ACTIVE, reservation__expires_at__gt=timezone.now())
    return render(request, 'aid/tasks.html', {'page_obj': paginate(request, tasks), 'mode': mode})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(visible_tasks(request.user).select_related('reservation__item', 'reservation__request', 'volunteer'), pk=pk)
    form = TaskActionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        result = try_operation(form, lambda: services.task_action(request.user, pk, **form.cleaned_data))
        if result:
            messages.success(request, 'Статус поручения обновлён.')
            return redirect(task)
    return render(request, 'aid/task_detail.html', {'task': task, 'form': form,
        'show_contacts': request.user.is_coordinator or task.volunteer_id == request.user.pk,
        'can_act': request.user.is_coordinator or task.volunteer_id == request.user.pk,
        'history': AuditLog.objects.filter(entity='volunteertask', object_id=task.pk)[:20] if request.user.is_coordinator or task.volunteer_id == request.user.pk else []})


@coordinator_required
def workspace(request):
    kind = request.GET.get('kind', 'items')
    status = request.GET.get('status', '')
    q = request.GET.get('q', '').strip()[:150]
    if kind == 'items':
        queryset = Item.objects.select_related('category')
        choices = Item.Status.choices
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(contact__name__icontains=q))
    elif kind == 'volunteers':
        queryset = VolunteerApplication.objects.select_related('user')
        choices = VolunteerApplication.Status.choices
        if q:
            queryset = queryset.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q))
    else:
        kind = 'requests'
        queryset = HelpRequest.objects.select_related('preferred_item__category', 'unselected_category', 'contact', 'coordinator')
        choices = HelpRequest.Status.choices
        if q:
            queryset = queryset.filter(Q(contact__name__icontains=q) | Q(need__icontains=q))
    if status in dict(choices):
        queryset = queryset.filter(status=status)
    return render(request, 'aid/workspace.html', {'kind': kind, 'status': status, 'q': q, 'status_choices': choices, 'page_obj': paginate(request, queryset, 15)})


@login_required
def notifications(request):
    return render(request, 'aid/notifications.html', {'page_obj': paginate(request, request.user.notifications.all(), 20)})


@login_required
@require_POST
def notifications_read(request):
    request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    messages.success(request, 'Все уведомления отмечены прочитанными.')
    return redirect('notifications')


def csv_safe(value):
    text = str(value or '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text


@coordinator_required
def reports(request):
    today = timezone.localdate()
    form = ReportForm(request.GET if request.GET else None, initial={'start': today.replace(day=1), 'end': today})
    if request.GET:
        valid = form.is_valid()
        start, end = (form.cleaned_data.get('start'), form.cleaned_data.get('end')) if valid else (None, None)
    else:
        valid, start, end = True, today.replace(day=1), today
    if not valid:
        return render(request, 'aid/reports.html', {'form': form, 'invalid': True})
    transfers = Transfer.objects.filter(transferred_at__date__range=(start, end), reversed_at__isnull=True).select_related(
        'reservation__item__category', 'reservation__request', 'confirmed_by')
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="nordsec-{start}-{end}.csv"'
        response['Cache-Control'] = 'no-store'
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Передача', 'Дата', 'Вещь / неделимый комплект', 'Категория', 'Обращение', 'Подтвердил'])
        for t in transfers:
            writer.writerow([t.pk, timezone.localtime(t.transferred_at).strftime('%d.%m.%Y %H:%M'),
                csv_safe(t.reservation.item.title), csv_safe(t.reservation.item.category.name), t.reservation.request_id, csv_safe(t.confirmed_by.display_name)])
        services.audit(request.user, transfers.first() or request.user, 'Экспорт отчёта', note=f'{start} — {end}; записей: {transfers.count()}')
        return response
    return render(request, 'aid/reports.html', {
        'form': form, 'start': start, 'end': end, 'transfers': transfers[:100], 'transfer_count': transfers.count(),
        'proposal_count': Item.objects.filter(created_at__date__range=(start, end)).count(),
        'accepted_count': Item.objects.filter(accepted_at__date__range=(start, end)).count(),
        'request_count': HelpRequest.objects.filter(created_at__date__range=(start, end)).count(),
        'by_category': transfers.values('reservation__item__category__name').annotate(total=Count('pk')).order_by('-total'),
    })


@coordinator_required
def audit_log(request):
    events = AuditLog.objects.select_related('actor')
    q = request.GET.get('q', '').strip()[:100]
    if q:
        events = events.filter(Q(action__icontains=q) | Q(note__icontains=q))
    return render(request, 'aid/audit.html', {'page_obj': paginate(request, events, 25), 'q': q})


def about(request):
    return render(request, 'aid/about.html')


def privacy(request):
    return render(request, 'aid/privacy.html')


def error403(request, exception=None):
    return render(request, 'errors/error.html', {'code': '403', 'heading': 'Нет доступа', 'description': 'Эта страница доступна участнику обращения или уполномоченному сотруднику.'}, status=403)


def error404(request, exception=None):
    return render(request, 'errors/error.html', {'code': '404', 'heading': 'Страница не найдена', 'description': 'Возможно, запись недоступна или ссылка устарела.'}, status=404)


def error500(request):
    return render(request, 'errors/error.html', {'code': '500', 'heading': 'Не удалось открыть страницу', 'description': 'Попробуйте позже. Если вы отправляли форму, проверьте запись в личном кабинете перед повторной отправкой.'}, status=500)


@login_required
def item_contact(request, pk):
    item = get_object_or_404(visible_items(request.user).select_related('contact', 'donor'), pk=pk)
    if item.placement == Item.Placement.STREET:
        return redirect(item)
    if item.status != Item.Status.AVAILABLE:
        messages.info(request, 'Это объявление уже закрыто.')
        return redirect(item)
    response = render(request, 'aid/item_contact.html', {'item': item})
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_POST
def item_signal(request, pk):
    from .models import ItemSignal
    obj = get_object_or_404(visible_items(request.user), pk=pk)
    kind = request.POST.get('kind')
    try:
        services.signal_item(request.user, obj.pk, kind)
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    else:
        messages.success(request, 'Отметка сохранена. Спасибо за обновление.')
    return redirect('catalog')
