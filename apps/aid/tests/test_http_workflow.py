"""Exercise submitted browser forms, not only the underlying service methods."""
from datetime import timedelta
from io import BytesIO
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from apps.aid import services
from apps.aid.forms import ItemForm
from apps.aid.models import Item, HelpRequest, Reservation, Transfer, AuditLog, VolunteerTask
from .base import AidCase


class BrowserFormWorkflowTests(AidCase):
    def test_report_date_inputs_use_browser_date_format(self):
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse('reports'))
        today = timezone.localdate()
        self.assertContains(response, f'value="{today.replace(day=1).isoformat()}"')
        self.assertContains(response, f'value="{today.isoformat()}"')

    def test_volunteer_buttons_through_post_forms(self):
        item, obj = self.make_item(), self.make_request()
        reservation = services.reserve(self.coordinator, obj.pk, item.pk, timezone.now() + timedelta(days=1))
        task = VolunteerTask.objects.create(reservation=reservation, title='Передать вещь',
            description='Учебное поручение', district='central', pickup_address='Адрес А',
            dropoff_address='Адрес Б', scheduled_at=timezone.now() + timedelta(hours=1))
        self.client.force_login(self.volunteer)
        url = task.get_absolute_url()
        for action in ['accept', 'start', 'deliver']:
            response = self.client.post(url, {'action': action, 'note': 'Получатель подтвердил доставку.'})
            self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, VolunteerTask.Status.DELIVERED)
        self.assertFalse(Transfer.objects.exists())
        self.client.force_login(self.coordinator)
        self.assertEqual(self.client.post(reverse('transfer_complete', args=[reservation.pk]), {
            'transferred_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
            'note': 'Получатель подтвердил.', 'confirmed': 'on',
        }).status_code, 302)
        self.assertEqual(Transfer.objects.count(), 1)

    def test_owner_listing_to_direct_contact_through_post_forms(self):
        self.client.force_login(self.donor)
        response = self.client.post(reverse('item_create'), {
            'placement': 'home', 'title': 'Куртка из формы', 'category': self.category.pk,
            'description': 'Чистая зимняя куртка без повреждений.', 'condition': 'good',
            'size': 'M', 'district': 'central', 'pickup_address': 'Тестовый адрес А',
            'donor_name': 'Автор', 'contact_phone': '+79000000000',
        })
        self.assertEqual(response.status_code, 302)
        item = Item.objects.get(title='Куртка из формы')
        self.assertEqual(item.status, Item.Status.AVAILABLE)
        self.client.logout()
        response = self.client.get(item.get_absolute_url())
        self.assertNotContains(response, '+79000000000')
        self.assertNotContains(response, 'Тестовый адрес А')
        self.client.force_login(self.recipient)
        response = self.client.get(reverse('item_contact', args=[item.pk]))
        self.assertContains(response, '+79000000000')
        self.assertFalse(HelpRequest.objects.exists())

    def test_invalid_selected_item_returns_404(self):
        self.client.force_login(self.recipient)
        for value in ['abc', '-1', '999999999999999999999999999', '١']:
            self.assertEqual(self.client.get(reverse('request_create'), {'item': value}).status_code, 404)

    def test_expired_unmoved_reservation_cannot_be_completed(self):
        from django.core.exceptions import ValidationError
        item, obj = self.make_item(), self.make_request()
        reservation = services.reserve(self.coordinator, obj.pk, item.pk, timezone.now() + timedelta(days=1))
        Reservation.objects.filter(pk=reservation.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            services.complete_transfer(self.coordinator, reservation.pk, timezone.now(), 'Выдача')
        self.assertFalse(Transfer.objects.exists())

    def test_photo_reencoded_and_metadata_removed(self):
        buffer = BytesIO()
        photo = Image.new('RGB', (20, 20), 'orange')
        exif = Image.Exif()
        exif[270] = 'Private image metadata'
        photo.save(buffer, 'JPEG', exif=exif)
        form = ItemForm(data={
            'title': 'Вещь', 'category': self.category.pk, 'description': 'Описание',
            'condition': 'good', 'district': 'central', 'pickup_address': 'Адрес',
            'donor_name': 'Имя', 'contact_phone': '+79000000000',
        }, files={'photo': SimpleUploadedFile('test.jpg', buffer.getvalue(), content_type='image/jpeg')})
        self.assertTrue(form.is_valid(), form.errors)
        cleaned = Image.open(form.cleaned_data['photo'])
        self.assertEqual(cleaned.format, 'JPEG')
        self.assertEqual(len(cleaned.getexif()), 0)

    def test_rejected_item_edit_records_changed_fields(self):
        item = self.make_item(status='rejected')
        form = ItemForm(data={
            'title': 'Уточнённая вещь', 'category': item.category_id, 'description': item.description,
            'condition': item.condition, 'district': item.district, 'pickup_address': item.pickup_address,
            'donor_name': item.donor_name, 'contact_phone': item.contact_phone,
        }, instance=item)
        self.assertTrue(form.is_valid(), form.errors)
        services.edit_item(self.donor, item.pk, form)
        entry = AuditLog.objects.get(entity='item', object_id=item.pk)
        self.assertNotEqual(entry.before['title'], entry.after['title'])
        self.assertEqual(entry.after['title'], 'Уточнённая вещь')
