"""Import the bundled fictional database into an empty development installation."""
import json
from pathlib import Path
import tempfile
from django.apps import apps
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from apps.accounts.models import User
from apps.aid.models import Item, HelpRequest


class Command(BaseCommand):
    help = 'Загрузить приложенную демонстрационную базу. Только DEBUG=1, NORDSEC_DEMO=1 и пустая база.'

    def add_arguments(self, parser):
        parser.add_argument('--if-empty', action='store_true', help='Сохранить существующие записи и пропустить импорт, если база заполнена.')

    def handle(self, *args, **options):
        if not settings.DEBUG or not settings.NORDSEC_DEMO:
            raise CommandError('Загрузка демонстрации разрешена только при DJANGO_DEBUG=1 и NORDSEC_DEMO=1.')
        if User.objects.exists() or Item.objects.exists() or HelpRequest.objects.exists():
            if options['if_empty']:
                self.stdout.write('База уже заполнена. Импорт пропущен; существующие записи сохранены.')
                return
            raise CommandError('База содержит пользователей или рабочие записи. Используйте отдельную пустую базу.')

        directory = settings.BASE_DIR / 'demo'
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        records = json.loads((directory / 'nordsec_demo.json').read_text(encoding='utf-8'))
        # A checked-in SQL snapshot keeps its original dates; this portable
        # fixture instead preserves intervals relative to the time of import.
        offset = timezone.now() - parse_datetime(manifest['exported_at'])
        for record in records:
            model = apps.get_model(record['model'])
            for name, value in record['fields'].items():
                if value and isinstance(model._meta.get_field(name), models.DateTimeField):
                    record['fields'][name] = (parse_datetime(value) + offset).isoformat()

        with tempfile.TemporaryDirectory(prefix='nordsec-demo-') as temporary:
            fixture = Path(temporary) / 'demo.json'
            fixture.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
            with transaction.atomic():
                call_command('loaddata', str(fixture), verbosity=0)

        marker = settings.BASE_DIR / '.runtime' / 'demo_accounts.txt'
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('Публичные учебные аккаунты. Не использовать в рабочей установке.\n\n' +
                          '\n'.join(f'{name}: NordSecDemo2026!' for name in
                                    ('coordinator', 'volunteer', 'donor', 'recipient')) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('Демонстрационная база загружена. Пароль четырёх учебных аккаунтов: NordSecDemo2026!'))
