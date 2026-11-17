from django.core.exceptions import ValidationError
from django.urls import reverse
from apps.aid import services
from apps.aid.forms import HelpRequestForm
from apps.aid.models import HelpRequest
from .base import AidCase


class ItemRequestTests(AidCase):
    def setUp(self):
        self.client.force_login(self.recipient)
        self.data = {
            'category': self.category.pk, 'need': 'Нужна куртка',
            'recipient_name': 'Получатель', 'contact_phone': '+79000000000',
            'district': 'central', 'consent': 'on',
        }

    def test_form_without_selected_item_redirects_to_catalog(self):
        self.assertRedirects(self.client.get(reverse('request_create')), reverse('catalog'))

    def test_post_without_item_cannot_create_request(self):
        self.assertRedirects(self.client.post(reverse('request_create'), self.data), reverse('catalog'))
        self.assertFalse(HelpRequest.objects.exists())

    def test_member_cannot_bypass_selection_with_on_behalf_flag(self):
        response = self.client.post(reverse('request_create') + '?on_behalf=1', self.data)
        self.assertRedirects(response, reverse('catalog'))
        self.assertFalse(HelpRequest.objects.exists())

    def test_service_requires_selected_item_for_member(self):
        form = HelpRequestForm(self.data)
        self.assertTrue(form.is_valid(), form.errors)
        with self.assertRaises(ValidationError):
            services.submit_request(self.recipient, form)
        self.assertFalse(HelpRequest.objects.exists())

    def test_selected_item_is_saved_with_request(self):
        item = self.make_item()
        response = self.client.post(reverse('request_create') + f'?item={item.pk}', self.data)
        self.assertEqual(response.status_code, 302)
        obj = HelpRequest.objects.get()
        self.assertEqual(obj.preferred_item_id, item.pk)
        self.assertEqual(obj.recipient_id, self.recipient.pk)

    def test_coordinator_can_record_offline_request(self):
        self.client.force_login(self.coordinator)
        response = self.client.post(reverse('request_create') + '?on_behalf=1', self.data)
        self.assertEqual(response.status_code, 302)
        obj = HelpRequest.objects.get()
        self.assertEqual(obj.registered_by_id, self.coordinator.pk)
        self.assertIsNone(obj.recipient_id)
