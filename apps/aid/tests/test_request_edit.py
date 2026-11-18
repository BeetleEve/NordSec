from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from apps.aid import services
from apps.aid.forms import RequestEditForm
from apps.aid.models import AuditLog, HelpRequest, Notification
from .base import AidCase


class RequestEditTests(AidCase):
    def setUp(self):
        self.client.force_login(self.recipient)
        self.item = self.make_item()
        self.obj = self.make_request(status=HelpRequest.Status.NEW, preferred_item=self.item)
        self.url = reverse('request_edit', args=[self.obj.pk])
        self.data = dict(need='Заберу вечером', recipient_name='Получатель', contact_phone='+79001234567', district='central')

    def test_owner_can_edit_new_request_without_changing_item_or_owner(self):
        response = self.client.post(self.url, {**self.data, 'preferred_item': '999', 'status': 'completed', 'recipient': self.other.pk})
        self.assertRedirects(response, self.obj.get_absolute_url())
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.need, self.data['need'])
        self.assertEqual(self.obj.preferred_item_id, self.item.pk)
        self.assertEqual(self.obj.recipient_id, self.recipient.pk)
        self.assertEqual(self.obj.status, HelpRequest.Status.NEW)
        self.assertTrue(AuditLog.objects.filter(entity='helprequest', object_id=self.obj.pk).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.coordinator).exists())

    def test_other_user_cannot_read_or_edit(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 404)
        form = RequestEditForm(self.data, instance=self.obj)
        self.assertTrue(form.is_valid())
        with self.assertRaises(PermissionDenied):
            services.edit_request(self.other, self.obj.pk, form)

    def test_approved_or_reserved_request_is_locked_even_if_form_was_open(self):
        form = RequestEditForm(self.data, instance=self.obj)
        self.assertTrue(form.is_valid())
        for status in (HelpRequest.Status.APPROVED, HelpRequest.Status.RESERVED, HelpRequest.Status.COMPLETED, HelpRequest.Status.CANCELLED):
            HelpRequest.objects.filter(pk=self.obj.pk).update(status=status)
            with self.assertRaises(ValidationError):
                services.edit_request(self.recipient, self.obj.pk, form)
            self.assertRedirects(self.client.post(self.url, self.data), self.obj.get_absolute_url())
        self.obj.refresh_from_db()
        self.assertNotEqual(self.obj.need, self.data['need'])

    def test_clarification_and_rejection_return_to_review(self):
        for status in (HelpRequest.Status.CLARIFICATION, HelpRequest.Status.REJECTED):
            HelpRequest.objects.filter(pk=self.obj.pk).update(status=status, decision_reason='Уточните время')
            self.assertRedirects(self.client.post(self.url, self.data), self.obj.get_absolute_url())
            self.obj.refresh_from_db()
            self.assertEqual(self.obj.status, HelpRequest.Status.NEW)
            self.assertEqual(self.obj.decision_reason, '')

    def test_delivery_requires_address(self):
        response = self.client.post(self.url, {**self.data, 'needs_delivery': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('delivery_address', response.context['form'].errors)
        self.obj.refresh_from_db()
        self.assertFalse(self.obj.needs_delivery)
