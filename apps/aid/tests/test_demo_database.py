from datetime import timedelta
from io import StringIO
from pathlib import Path
import shutil
import tempfile
from django.conf import settings
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.accounts.models import User
from apps.aid.models import Item, HelpRequest, Reservation, Transfer


class BundledDemoDatabaseTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='nordsec-demo-test-')
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        (root / 'demo').mkdir()
        for name in ['manifest.json', 'nordsec_demo.json']:
            shutil.copyfile(settings.BASE_DIR / 'demo' / name, root / 'demo' / name)
        self.override = override_settings(BASE_DIR=root, DEBUG=True, NORDSEC_DEMO=True)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_fixture_imports_and_keeps_reservations_current(self):
        call_command('load_demo', stdout=StringIO())
        self.assertEqual(User.objects.count(), 4)
        self.assertEqual(Item.objects.count(), 13)
        self.assertEqual(HelpRequest.objects.count(), 3)
        self.assertEqual(Transfer.objects.count(), 1)
        self.assertTrue(User.objects.get(username='coordinator').check_password('NordSecDemo2026!'))
        active = Reservation.objects.get(status='active')
        self.assertGreater(active.expires_at, timezone.now() + timedelta(days=2))
        self.assertGreater(active.task.scheduled_at, timezone.now())
        self.assertTrue((settings.BASE_DIR / '.runtime' / 'demo_accounts.txt').is_file())

    def test_existing_user_is_preserved(self):
        user = User.objects.create_user('existing', password='Existing-password-281')
        with self.assertRaises(CommandError):
            call_command('load_demo', stdout=StringIO())
        call_command('load_demo', if_empty=True, stdout=StringIO())
        self.assertEqual(User.objects.count(), 1)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Existing-password-281'))
        self.assertFalse(Item.objects.exists())

    def test_production_mode_refuses_demo_import(self):
        with override_settings(DEBUG=False), self.assertRaises(CommandError):
            call_command('load_demo', stdout=StringIO())
        with override_settings(NORDSEC_DEMO=False), self.assertRaises(CommandError):
            call_command('load_demo', stdout=StringIO())
        self.assertFalse(User.objects.exists())
