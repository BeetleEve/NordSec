from io import StringIO
from django.core.management import call_command, CommandError
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.urls import reverse
from apps.accounts.models import User
from apps.aid import services
from apps.aid.forms import ItemForm
from apps.aid.models import Contact, HelpRequest, Item, VolunteerApplication
from .base import AidCase


class NormalizedWorkflowTests(AidCase):
    def test_identical_contacts_are_shared_but_edit_does_not_change_other_records(self):
        first = self.make_item()
        second = self.make_item()
        self.assertEqual(first.contact_id, second.contact_id)
        first.contact_phone = '+79005555555'
        first.save()
        second.refresh_from_db()
        self.assertNotEqual(first.contact_id, second.contact_id)
        self.assertEqual(second.contact_phone, '+7 900 000-00-01')

    def test_category_is_derived_from_item_and_cannot_have_two_sources(self):
        item = self.make_item()
        req = self.make_request(preferred_item=item)
        self.assertIsNone(req.unselected_category_id)
        self.assertEqual(req.category_id, item.category_id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            HelpRequest.objects.filter(pk=req.pk).update(unselected_category=self.category)

    def test_automatic_checks_apply_to_moderator_and_member(self):
        data = dict(title='Книга', category=self.category.pk, description='Книга в хорошем состоянии', condition='good', district='central', pickup_address='Адрес', donor_name='Автор', contact_phone='+79001234567')
        for actor, expected in [(self.coordinator, Item.Status.AVAILABLE), (self.donor, Item.Status.AVAILABLE)]:
            form = ItemForm(data)
            self.assertTrue(form.is_valid(), form.errors)
            obj = services.submit_item(actor, form)
            self.assertEqual(obj.status, expected)
            self.assertIsNone(obj.reviewed_by_id)

    def test_only_moderator_can_approve_volunteer(self):
        app = VolunteerApplication.objects.create(user=self.other, availability='Вечером', description='Доставка')
        with self.assertRaises(PermissionDenied):
            services.decide_volunteer(self.recipient, app.pk, 'approve')
        services.decide_volunteer(self.coordinator, app.pk, 'approve')
        self.other.refresh_from_db()
        self.assertEqual(self.other.role, User.Role.VOLUNTEER)

    def test_workspace_search_uses_normalized_contact(self):
        self.make_item()
        self.make_request()
        self.client.force_login(self.coordinator)
        for kind in ['items', 'requests']:
            response = self.client.get(reverse('workspace'), {'kind': kind, 'q': 'Получатель' if kind == 'requests' else 'Жертвователь'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['page_obj'].paginator.count, 1)

    def test_console_account_hashes_password_and_refuses_overwriting(self):
        output = StringIO()
        call_command('create_account', 'new-moderator', 'Strong-password-2026!', 'moderator', stdout=output)
        user = User.objects.get(username='new-moderator')
        self.assertTrue(user.is_moderator)
        self.assertTrue(user.check_password('Strong-password-2026!'))
        self.assertNotEqual(user.password, 'Strong-password-2026!')
        self.assertNotIn('Strong-password-2026!', output.getvalue())
        with self.assertRaises(CommandError):
            call_command('create_account', 'new-moderator', 'Other-password-2026!', 'member', stdout=output)
        user.refresh_from_db()
        self.assertTrue(user.is_moderator)
