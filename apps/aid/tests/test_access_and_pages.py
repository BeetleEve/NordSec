from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from apps.aid.models import Item, VolunteerTask, Notification
from apps.aid import services
from .base import AidCase


class AccessAndPageTests(AidCase):
    def test_public_pages_render(self):
        for name in ['home','catalog','about','privacy','volunteers','login','register']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code,200)

    def test_private_pages_require_login(self):
        for name in ['dashboard','my_items','my_requests','notifications','profile','reports','workspace']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code,302)

    def test_member_cannot_view_reports_or_workspace(self):
        self.client.force_login(self.recipient)
        for name in ['reports','workspace','audit_log']:
            self.assertEqual(self.client.get(reverse(name)).status_code,403)

    def test_coordinator_pages_render(self):
        self.client.force_login(self.coordinator)
        for name in ['dashboard','workspace','reports','audit_log','task_list','item_create','request_create','profile']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code,200)

    def test_member_pages_render(self):
        self.client.force_login(self.recipient)
        for name in ['dashboard','my_items','my_requests','favorites','notifications','profile','item_create','request_create','volunteer_apply']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code,200)

    def test_public_item_does_not_expose_contacts(self):
        item=self.make_item()
        response=self.client.get(item.get_absolute_url())
        self.assertContains(response,item.title)
        self.assertNotContains(response,item.pickup_address)
        self.assertNotContains(response,item.contact_phone)

    def test_pending_item_is_not_public(self):
        item=self.make_item(status='review')
        self.assertEqual(self.client.get(item.get_absolute_url()).status_code,404)
        self.client.force_login(self.donor)
        self.assertEqual(self.client.get(item.get_absolute_url()).status_code,200)

    def test_other_member_cannot_view_request(self):
        obj=self.make_request()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(obj.get_absolute_url()).status_code,404)

    def test_recipient_cannot_see_staff_note(self):
        obj=self.make_request(staff_note='СЕКРЕТНЫЙ СЛУЖЕБНЫЙ КОММЕНТАРИЙ')
        self.client.force_login(self.recipient)
        response=self.client.get(obj.get_absolute_url())
        self.assertNotContains(response,obj.staff_note)

    def test_task_contacts_only_visible_after_acceptance(self):
        item,obj=self.make_item(),self.make_request()
        reservation=services.reserve(self.coordinator,obj.pk,item.pk,timezone.now()+timedelta(days=2))
        task=VolunteerTask.objects.create(reservation=reservation,title='Перенести вещь',description='Небольшая сумка',district='central',pickup_address='СЕКРЕТНЫЙ АДРЕС А',dropoff_address='СЕКРЕТНЫЙ АДРЕС Б',scheduled_at=timezone.now()+timedelta(days=1))
        self.client.force_login(self.volunteer)
        self.assertNotContains(self.client.get(task.get_absolute_url()),task.pickup_address)
        services.task_action(self.volunteer,task.pk,'accept')
        self.assertContains(self.client.get(task.get_absolute_url()),task.pickup_address)

    def test_logout_requires_post(self):
        self.client.force_login(self.recipient)
        self.assertEqual(self.client.get(reverse('logout')).status_code,405)

    def test_report_rejects_inverted_dates(self):
        self.client.force_login(self.coordinator)
        response=self.client.get(reverse('reports'),{'start':'2026-12-01','end':'2026-01-01'})
        self.assertContains(response,'Дата начала должна быть')
        self.assertNotIn('transfer_count',response.context)

    def test_filters_search_title_and_size(self):
        self.make_item(title='Куртка особенная',size='Размер XXL')
        self.make_item(title='Другая вещь')
        response=self.client.get(reverse('catalog'),{'q':'XXL'})
        self.assertContains(response,'Куртка особенная')
        self.assertNotContains(response,'Другая вещь')

    def test_read_notifications_only_changes_own_records(self):
        mine=Notification.objects.create(recipient=self.recipient,title='Для меня',message='Тест')
        other=Notification.objects.create(recipient=self.other,title='Для другого',message='Тест')
        self.client.force_login(self.recipient)
        self.client.post(reverse('notifications_read'))
        mine.refresh_from_db();other.refresh_from_db()
        self.assertIsNotNone(mine.read_at);self.assertIsNone(other.read_at)

    def test_favorite_does_not_create_reservation(self):
        from apps.aid.models import Reservation,Favorite
        item=self.make_item();self.client.force_login(self.recipient)
        self.client.post(reverse('favorite_toggle',args=[item.pk]))
        self.assertTrue(Favorite.objects.filter(user=self.recipient,item=item).exists())
        self.assertFalse(Reservation.objects.exists())

    def test_get_review_does_not_change_item(self):
        item=self.make_item(status='review');self.client.force_login(self.coordinator)
        response=self.client.get(reverse('item_review',args=[item.pk]))
        self.assertEqual(response.status_code,200)
        item.refresh_from_db();self.assertEqual(item.status,'review')
