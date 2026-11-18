import re
from datetime import datetime, timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.urls import reverse
from apps.accounts.models import User


class AccountTests(TestCase):
    def test_registration_ignores_submitted_privileged_role(self):
        response=self.client.post(reverse('register'),{
            'username':'new-member','first_name':'Имя','last_name':'Фамилия','phone':'+7 900 000-00-00','district':'central',
            'password1':'Complex-pass-81020','password2':'Complex-pass-81020','consent':'on','role':'coordinator','is_superuser':'1',
        })
        self.assertEqual(response.status_code,302)
        user=User.objects.get(username='new-member')
        self.assertEqual(user.role,'member');self.assertFalse(user.is_superuser)
        self.assertIsNotNone(user.consent_at)

    def test_profile_cannot_escalate_role(self):
        user=User.objects.create_user('member',password='Example-pass-8120')
        self.client.force_login(user)
        self.client.post(reverse('profile'),{'first_name':'Имя','last_name':'Фамилия','phone':'+79000000000','district':'central','role':'coordinator'})
        user.refresh_from_db();self.assertEqual(user.role,'member')

    def test_login_throttles_failed_attempts(self):
        for _ in range(10):
            self.client.post(reverse('login'),{'username':'unknown','password':'invalid'})
        self.assertEqual(self.client.post(reverse('login'),{'username':'unknown','password':'invalid'}).status_code,429)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('reset-user', email='reset@example.test', password='Original-pass-88102')

    def test_reset_works_without_old_password_and_token_is_single_use(self):
        self.assertRedirects(self.client.post(reverse('password_reset'), {'email': self.user.email}), reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r'http://testserver(/\S+)', mail.outbox[0].body).group(1)
        response = self.client.get(link)
        self.assertEqual(response.status_code, 302)
        confirm_url = response.url
        self.assertTrue(self.client.get(confirm_url).context['validlink'])
        self.assertRedirects(self.client.post(confirm_url, {'new_password1': 'Changed-pass-88102', 'new_password2': 'Changed-pass-88102'}), reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Changed-pass-88102'))
        self.assertFalse(self.client.get(link).context['validlink'])

    def test_unknown_email_has_same_response_without_sending(self):
        self.assertRedirects(self.client.post(reverse('password_reset'), {'email': 'missing@example.test'}), reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_expired_link_is_rejected(self):
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        with patch.object(default_token_generator, '_now', return_value=datetime.now() + timedelta(hours=2)):
            response = self.client.get(reverse('password_reset_confirm', args=[uid, token]))
        self.assertFalse(response.context['validlink'])

    def test_reset_requests_are_throttled_even_for_logged_in_user(self):
        self.client.force_login(self.user)
        for _ in range(10):
            self.client.post(reverse('password_reset'), {'email': 'missing@example.test'})
        self.assertEqual(self.client.post(reverse('password_reset'), {'email': self.user.email}).status_code, 429)
        self.assertEqual(len(mail.outbox), 0)
