from django.test import TestCase
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
