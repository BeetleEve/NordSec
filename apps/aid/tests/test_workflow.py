from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from apps.aid import services
from apps.aid.models import Item, HelpRequest, Reservation, VolunteerTask, Transfer, AuditLog, Notification
from .base import AidCase


class WorkflowTests(AidCase):
    def reserve(self, item=None, obj=None):
        return services.reserve(self.coordinator, (obj or self.make_request()).pk, (item or self.make_item()).pk, timezone.now()+timedelta(days=2))

    def test_reservation_updates_all_records_and_notifies(self):
        item, obj = self.make_item(), self.make_request()
        reservation = self.reserve(item,obj)
        item.refresh_from_db(); obj.refresh_from_db()
        self.assertEqual(item.status, Item.Status.RESERVED)
        self.assertEqual(obj.status, HelpRequest.Status.RESERVED)
        self.assertEqual(reservation.status, Reservation.Status.ACTIVE)
        self.assertTrue(Notification.objects.filter(recipient=self.recipient).exists())
        self.assertTrue(AuditLog.objects.filter(entity='item', object_id=item.pk).exists())

    def test_second_request_cannot_reserve_same_item(self):
        item = self.make_item()
        self.reserve(item)
        with self.assertRaises(ValidationError):
            self.reserve(item)
        self.assertEqual(Reservation.objects.filter(item=item,status='active').count(),1)

    def test_database_enforces_one_active_reservation_per_item(self):
        first=self.reserve()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Reservation.objects.create(item=first.item, request=self.make_request(), created_by=self.coordinator, expires_at=timezone.now()+timedelta(days=1))

    def test_database_enforces_one_active_reservation_per_request(self):
        first=self.reserve()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Reservation.objects.create(item=self.make_item(), request=first.request, created_by=self.coordinator, expires_at=timezone.now()+timedelta(days=1))

    def test_member_cannot_reserve(self):
        with self.assertRaises(PermissionDenied):
            services.reserve(self.recipient,self.make_request().pk,self.make_item().pk,timezone.now()+timedelta(days=1))

    def test_category_must_match(self):
        from apps.aid.models import Category
        category,_=Category.objects.get_or_create(slug='books',defaults={'name':'Книги'})
        with self.assertRaises(ValidationError):
            self.reserve(self.make_item(category=category))

    def test_cannot_reserve_own_donation(self):
        with self.assertRaises(ValidationError):
            self.reserve(self.make_item(donor=self.recipient))

    def test_reservation_requires_approved_request(self):
        with self.assertRaises(ValidationError):
            self.reserve(obj=self.make_request(status='new'))

    def test_past_deadline_is_rejected_without_changes(self):
        item,obj=self.make_item(),self.make_request()
        with self.assertRaises(ValidationError):
            services.reserve(self.coordinator,obj.pk,item.pk,timezone.now()-timedelta(seconds=1))
        item.refresh_from_db()
        self.assertEqual(item.status,'available')
        self.assertEqual(Reservation.objects.count(),0)

    def test_meeting_after_deadline_is_rejected(self):
        with self.assertRaises(ValidationError):
            services.reserve(self.coordinator,self.make_request().pk,self.make_item().pk,timezone.now()+timedelta(days=1),meeting_at=timezone.now()+timedelta(days=2))

    def test_declined_proposal_can_be_corrected_but_not_published_by_donor(self):
        item=self.make_item(status='review')
        services.review_item(self.coordinator,item.pk,'reject','Нужно уточнить состояние')
        item.refresh_from_db()
        self.assertEqual(item.status,'rejected')
        self.assertIsNone(item.accepted_at)

    def test_review_requires_coordinator_and_reason_for_rejection(self):
        item=self.make_item(status='review')
        with self.assertRaises(PermissionDenied):
            services.review_item(self.donor,item.pk,'approve',location='donor')
        with self.assertRaises(ValidationError):
            services.review_item(self.coordinator,item.pk,'reject')

    def test_accepted_at_records_approval_and_survives_withdrawal(self):
        item=self.make_item(status='review')
        services.review_item(self.coordinator,item.pk,'approve',location='fund')
        services.withdraw_item(self.donor,item.pk,'Изменились условия')
        item.refresh_from_db()
        self.assertIsNotNone(item.accepted_at)
        self.assertEqual(item.status,'withdrawn')

    def test_cancellation_releases_unmoved_item(self):
        reservation=self.reserve()
        services.cancel_reservation(self.coordinator,reservation.pk,'Встреча отменена')
        reservation.refresh_from_db(); reservation.item.refresh_from_db(); reservation.request.refresh_from_db()
        self.assertEqual(reservation.status,'cancelled')
        self.assertEqual(reservation.item.status,'available')
        self.assertEqual(reservation.request.status,'approved')

    def task(self,reservation,status='open'):
        return VolunteerTask.objects.create(reservation=reservation,title='Перенести вещь',description='Небольшая сумка',district='central',
            pickup_address='ЧАСТНЫЙ АДРЕС А',dropoff_address='ЧАСТНЫЙ АДРЕС Б',scheduled_at=timezone.now()+timedelta(hours=5),status=status)

    def test_volunteer_delivery_does_not_complete_transfer(self):
        reservation=self.reserve(); task=self.task(reservation)
        services.task_action(self.volunteer,task.pk,'accept')
        services.task_action(self.volunteer,task.pk,'start')
        services.task_action(self.volunteer,task.pk,'deliver','Лично передал получателю')
        reservation.item.refresh_from_db(); reservation.request.refresh_from_db()
        self.assertEqual(reservation.item.status,'reserved')
        self.assertEqual(reservation.item.location,'recipient')
        self.assertEqual(reservation.request.status,'reserved')
        self.assertFalse(Transfer.objects.exists())

    def test_unassigned_volunteer_cannot_change_task(self):
        reservation=self.reserve(); task=self.task(reservation)
        with self.assertRaises(PermissionDenied):
            services.task_action(self.other,task.pk,'accept')

    def test_second_volunteer_cannot_claim_accepted_task(self):
        reservation=self.reserve(); task=self.task(reservation)
        services.task_action(self.volunteer,task.pk,'accept')
        with self.assertRaises(ValidationError):
            services.task_action(self.coordinator,task.pk,'accept')

    def test_cannot_decline_after_pickup(self):
        reservation=self.reserve(); task=self.task(reservation)
        services.task_action(self.volunteer,task.pk,'accept');services.task_action(self.volunteer,task.pk,'start')
        with self.assertRaises(ValidationError):
            services.task_action(self.volunteer,task.pk,'decline','Не успеваю')

    def test_expired_reservation_releases_item_still_at_donor(self):
        reservation=self.reserve(); self.task(reservation)
        Reservation.objects.filter(pk=reservation.pk).update(expires_at=timezone.now()-timedelta(minutes=1))
        self.assertEqual(services.expire_reservations(),1)
        reservation.item.refresh_from_db()
        self.assertEqual(reservation.item.status,'available')

    def test_expired_reservation_keeps_item_in_transit_and_notifies_once(self):
        reservation=self.reserve(); task=self.task(reservation)
        services.task_action(self.volunteer,task.pk,'accept');services.task_action(self.volunteer,task.pk,'start')
        Reservation.objects.filter(pk=reservation.pk).update(expires_at=timezone.now()-timedelta(minutes=1))
        self.assertEqual(services.expire_reservations(),0)
        count=Notification.objects.filter(title='Просроченная передача требует проверки').count()
        services.expire_reservations()
        self.assertEqual(Notification.objects.filter(title='Просроченная передача требует проверки').count(),count)
        reservation.refresh_from_db();reservation.item.refresh_from_db()
        self.assertEqual(reservation.status,'active');self.assertEqual(reservation.item.status,'reserved')

    def test_cancellation_in_transit_requires_verified_return(self):
        reservation=self.reserve();task=self.task(reservation)
        services.task_action(self.volunteer,task.pk,'accept');services.task_action(self.volunteer,task.pk,'start')
        with self.assertRaises(ValidationError):
            services.cancel_reservation(self.coordinator,reservation.pk,'Не удалось доставить')
        services.cancel_reservation(self.coordinator,reservation.pk,'Возврат проверен',return_location='fund')
        reservation.item.refresh_from_db()
        self.assertEqual(reservation.item.location,'fund');self.assertEqual(reservation.item.status,'available')

    def test_confirmation_creates_single_transfer_and_completed_request(self):
        reservation=self.reserve()
        services.complete_transfer(self.coordinator,reservation.pk,timezone.now(),'Получатель подтвердил выдачу лично')
        with self.assertRaises(ValidationError):
            services.complete_transfer(self.coordinator,reservation.pk,timezone.now(),'Повтор')
        self.assertEqual(Transfer.objects.count(),1)
        reservation.request.refresh_from_db()
        self.assertEqual(reservation.request.status,'completed')

    def test_confirmation_refuses_unfinished_task(self):
        reservation=self.reserve();self.task(reservation)
        with self.assertRaises(ValidationError):
            services.complete_transfer(self.coordinator,reservation.pk,timezone.now(),'Позвонил получатель')

    def test_correction_preserves_transfer_but_excludes_it_from_report(self):
        reservation=self.reserve()
        transfer=services.complete_transfer(self.coordinator,reservation.pk,timezone.now(),'Выдача')
        services.reverse_transfer(self.coordinator,transfer.pk,'Отметка внесена ошибочно','donor')
        transfer.refresh_from_db();reservation.item.refresh_from_db()
        self.assertIsNotNone(transfer.reversed_at)
        self.assertEqual(Transfer.objects.filter(reversed_at__isnull=True).count(),0)
        self.assertEqual(reservation.item.status,'available')
        self.assertTrue(AuditLog.objects.filter(entity='transfer',action='Передача исправлена').exists())

    def test_member_cannot_cancel_someone_elses_request(self):
        obj=self.make_request()
        with self.assertRaises(PermissionDenied):
            services.cancel_request(self.other,obj.pk,'Отмена')

    def test_member_cancels_own_request_and_releases_reservation(self):
        reservation=self.reserve()
        services.cancel_request(self.recipient,reservation.request_id,'Больше не нужно')
        reservation.request.refresh_from_db();reservation.item.refresh_from_db()
        self.assertEqual(reservation.request.status,'cancelled')
        self.assertEqual(reservation.item.status,'available')
