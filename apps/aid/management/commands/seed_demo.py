"""Fictional demo only. Does not reset or replace existing business data."""
import secrets
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.accounts.models import User
from apps.aid.models import Item, Category, HelpRequest, VolunteerTask
from apps.aid import services


class Command(BaseCommand):
    help = 'Создать вымышленный пример работы. Нужны DJANGO_DEBUG=1 и NORDSEC_DEMO=1.'

    def handle(self, *args, **options):
        if not settings.DEBUG or not settings.NORDSEC_DEMO:
            raise CommandError('Демонстрационные данные разрешены только в локальном режиме NORDSEC_DEMO=1.')
        marker = settings.BASE_DIR / '.runtime' / 'demo_accounts.txt'
        if Item.objects.exists() or HelpRequest.objects.exists():
            if marker.exists():
                self.stdout.write('Демонстрация уже создана. Существующие записи сохранены.')
                return
            raise CommandError('База уже содержит вещи или обращения. Демонстрация не добавлена: используйте отдельную базу.')
        if User.objects.filter(username__in=['coordinator', 'volunteer', 'donor', 'recipient']).exists():
            raise CommandError('Демонстрационные логины уже заняты. Используйте отдельную пустую базу.')
        password = secrets.token_urlsafe(12)
        with transaction.atomic():
            coordinator = User.objects.create_user('coordinator', password=password, first_name='Анна', last_name='Координатор', role=User.Role.COORDINATOR, phone='+7 900 000-00-01', consent_at=timezone.now())
            volunteer = User.objects.create_user('volunteer', password=password, first_name='Михаил', last_name='Волонтёр', role=User.Role.VOLUNTEER, phone='+7 900 000-00-02', consent_at=timezone.now())
            donor = User.objects.create_user('donor', password=password, first_name='Елена', last_name='Жертвователь', phone='+7 900 000-00-03', consent_at=timezone.now())
            recipient = User.objects.create_user('recipient', password=password, first_name='Мария', last_name='Получатель', phone='+7 900 000-00-04', consent_at=timezone.now())
            examples = [
                ('Зимняя куртка', 'clothes', 'Размер M', 'excellent', 'central', 'Тёплая куртка без повреждений. Чистая, молнии и кнопки исправны.'),
                ('Плюшевый медведь', 'children', '35 см', 'excellent', 'talnakh', 'Мягкая игрушка. После стирки, без повреждений.'),
                ('Набор кружек', 'home', 'Комплект из 4 шт.', 'new', 'central', 'Четыре одинаковые керамические кружки. Передаются одним неделимым комплектом.'),
                ('Деревянный стул', 'furniture', '45 × 45 × 85 см', 'good', 'kayerkan', 'Устойчивый деревянный стул. Небольшие следы использования, крепления исправны.'),
                ('Детские книги', 'books', 'Набор для 6–8 лет', 'good', 'oganer', 'Книги с рассказами и иллюстрациями. Передаются одним комплектом.'),
                ('Коробка для хранения', 'other', '40 × 30 см', 'excellent', 'central', 'Прочная коробка с крышкой, без повреждений.'),
                ('Тёплый свитер', 'clothes', 'Размер L', 'good', 'talnakh', 'Мягкий свитер, без пятен и дыр. Выстиран.'),
                ('Детский конструктор', 'children', 'Возраст 5+', 'good', 'central', 'Крупные детали в коробке. Острые и повреждённые детали отсутствуют.'),
                ('Книги для школьника', 'books', 'Комплект из 3 книг', 'excellent', 'kayerkan', 'Художественные книги для школьного чтения, комплект неделимый.'),
                ('Небольшая тумба', 'furniture', '40 × 35 × 50 см', 'good', 'central', 'Тумба с одной полкой. Нужна помощь с переносом.'),
                ('Настольная игра', 'children', 'Возраст 8+', 'excellent', 'oganer', 'Настольная игра, все детали на месте.'),
                ('Набор кухонных мисок', 'home', 'Комплект из 3 шт.', 'new', 'talnakh', 'Миски из нержавеющей стали. Передаются комплектом.'),
            ]
            items = []
            for title, slug, size, condition, district, description in examples:
                category = Category.objects.get(slug=slug)
                item = Item.objects.create(donor=donor, registered_by=donor, donor_name=donor.display_name, contact_phone=donor.phone,
                    title=title, category=category, description=description, size=size, condition=condition, district=district,
                    pickup_address='Демонстрационный адрес, дом 1', status=Item.Status.AVAILABLE, reviewed_by=coordinator,
                    reviewed_at=timezone.now(), accepted_at=timezone.now(), needs_transport=slug == 'furniture')
                services.audit(coordinator, item, 'Демонстрационная вещь принята на учёт')
                items.append(item)
            Item.objects.create(donor=donor, registered_by=donor, donor_name=donor.display_name, contact_phone=donor.phone,
                title='Школьный рюкзак', category=Category.objects.get(slug='children'), description='Нужно проверить предложение жертвователя.',
                condition=Item.Condition.GOOD, district='central', pickup_address='Демонстрационный адрес, дом 1')
            for item in items[:3]:
                obj = HelpRequest.objects.create(recipient=recipient, registered_by=recipient, recipient_name=recipient.display_name,
                    contact_phone=recipient.phone, preferred_item=item, category=item.category, need=f'Нужна вещь: {item.title}. Вымышленное демонстрационное обращение.',
                    district='central', delivery_address='Демонстрационный адрес, дом 2', needs_delivery=True)
                services.audit(recipient, obj, 'Демонстрационное обращение создано')
                if item == items[1]:
                    services.decide_request(coordinator, obj.pk, 'approve', 'Можно подобрать вещь.')
                    reservation = services.reserve(coordinator, obj.pk, item.pk, timezone.now()+timedelta(days=3), meeting_at=timezone.now()+timedelta(days=1), meeting_note='Время подтверждается координатором.')
                    VolunteerTask.objects.create(reservation=reservation, title='Передать игрушку получателю', description='Забрать мягкую игрушку и передать получателю. Небольшая сумка.', district='central',
                        pickup_address='Демонстрационный адрес, дом 1', dropoff_address='Демонстрационный адрес, дом 2', scheduled_at=timezone.now()+timedelta(days=1))
                elif item == items[2]:
                    services.decide_request(coordinator, obj.pk, 'approve')
                    reservation = services.reserve(coordinator, obj.pk, item.pk, timezone.now()+timedelta(days=1))
                    services.complete_transfer(coordinator, reservation.pk, timezone.now(), 'Вымышленная передача для демонстрации отчёта.')
        marker.parent.mkdir(exist_ok=True)
        marker.write_text('Демонстрационные аккаунты NordSec. Не использовать в рабочей установке.\n\n'
            + '\n'.join(f'{name}: {password}' for name in ('coordinator', 'volunteer', 'donor', 'recipient')) + '\n', encoding='utf-8')
        self.stdout.write(f'Демонстрация создана. Логины и случайный пароль: {marker}')
