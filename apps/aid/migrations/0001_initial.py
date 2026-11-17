# Initial schema. Choice labels and defaults are frozen.
from django.db import migrations, models
from django.db.models import Q
from django.conf import settings
import apps.aid.models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField('Название', max_length=80, unique=True)),
                ('slug', models.SlugField('Код', unique=True)),
                ('illustration', models.CharField('Иллюстрация', max_length=30, default='other')),
                ('order', models.PositiveSmallIntegerField('Порядок', default=0))],
            options={'ordering': ['order', 'name'], 'verbose_name': 'категория', 'verbose_name_plural': 'категории'}
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField('Создано', auto_now_add=True)),
                ('updated_at', models.DateTimeField('Изменено', auto_now=True)),
                ('donor', models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Жертвователь', on_delete=models.PROTECT, null=True, blank=True, related_name='donated_items')),
                ('registered_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='registered_items')),
                ('donor_name', models.CharField('Имя жертвователя', max_length=150)),
                ('contact_phone', models.CharField('Телефон для связи', max_length=30)),
                ('title', models.CharField('Название вещи', max_length=140)),
                ('category', models.ForeignKey('aid.category', verbose_name='Категория', on_delete=models.PROTECT, related_name='items')),
                ('description', models.TextField('Описание', max_length=3000)),
                ('condition', models.CharField('Состояние', max_length=20, choices=[('new', 'Новая'), ('excellent', 'Отличное'), ('good', 'Хорошее')], default='good')),
                ('size', models.CharField('Размер / габариты', max_length=80, blank=True)),
                ('district', models.CharField('Район', max_length=20, choices=[('central', 'Центральный район'), ('talnakh', 'Талнах'), ('kayerkan', 'Кайеркан'), ('oganer', 'Оганер')])),
                ('pickup_address', models.CharField('Точный адрес передачи', max_length=250)),
                ('location', models.CharField('Местонахождение', max_length=20, choices=[('donor', 'У жертвователя'), ('fund', 'В пункте фонда'), ('transit', 'У волонтёра'), ('recipient', 'У получателя')], default='donor')),
                ('status', models.CharField('Статус', max_length=20, choices=[('review', 'На проверке'), ('available', 'Доступна'), ('reserved', 'В резерве'), ('delivered', 'Передана'), ('withdrawn', 'Снята с передачи'), ('rejected', 'Не принята')], default='review', db_index=True)),
                ('photo', models.ImageField('Фото', upload_to=apps.aid.models.photo_path, blank=True)),
                ('needs_transport', models.BooleanField('Нужна помощь с перевозкой', default=False)),
                ('review_reason', models.TextField('Причина решения', max_length=1500, blank=True)),
                ('reviewed_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='reviewed_items')),
                ('reviewed_at', models.DateTimeField(null=True, blank=True)),
                ('accepted_at', models.DateTimeField('Дата принятия на учёт', null=True, blank=True, db_index=True))],
            options={'ordering': ['-created_at'], 'indexes': [models.Index(fields=['status', 'category', 'district'], name='item_catalog_idx')], 'verbose_name': 'вещь', 'verbose_name_plural': 'вещи'}
        ),
        migrations.CreateModel(
            name='HelpRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField('Создано', auto_now_add=True)),
                ('updated_at', models.DateTimeField('Изменено', auto_now=True)),
                ('recipient', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='help_requests')),
                ('registered_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='registered_requests')),
                ('recipient_name', models.CharField('Имя получателя', max_length=150)),
                ('contact_phone', models.CharField('Телефон для связи', max_length=30)),
                ('preferred_item', models.ForeignKey('aid.item', verbose_name='Выбранная вещь', on_delete=models.PROTECT, null=True, blank=True, related_name='requests')),
                ('category', models.ForeignKey('aid.category', verbose_name='Категория', on_delete=models.PROTECT)),
                ('need', models.TextField('Какая помощь нужна', max_length=3000)),
                ('district', models.CharField('Район', max_length=20, choices=[('central', 'Центральный район'), ('talnakh', 'Талнах'), ('kayerkan', 'Кайеркан'), ('oganer', 'Оганер')])),
                ('delivery_address', models.CharField('Адрес для согласования передачи', max_length=250, blank=True)),
                ('needs_delivery', models.BooleanField('Нужна помощь с доставкой', default=False)),
                ('status', models.CharField('Статус', max_length=20, choices=[('new', 'На рассмотрении'), ('clarification', 'Нужно уточнение'), ('approved', 'Одобрено'), ('reserved', 'Вещь зарезервирована'), ('completed', 'Помощь получена'), ('rejected', 'Отказано'), ('cancelled', 'Отменено')], default='new', db_index=True)),
                ('coordinator', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='assigned_requests')),
                ('decision_reason', models.TextField('Ответ получателю', max_length=1500, blank=True)),
                ('staff_note', models.TextField('Служебный комментарий', max_length=2000, blank=True))],
            options={'ordering': ['-created_at'], 'verbose_name': 'обращение', 'verbose_name_plural': 'обращения'}
        ),
        migrations.CreateModel(
            name='Reservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField('Создано', auto_now_add=True)),
                ('updated_at', models.DateTimeField('Изменено', auto_now=True)),
                ('item', models.ForeignKey('aid.item', on_delete=models.PROTECT, related_name='reservations')),
                ('request', models.ForeignKey('aid.helprequest', on_delete=models.PROTECT, related_name='reservations')),
                ('created_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
                ('status', models.CharField(max_length=20, choices=[('active', 'Действует'), ('fulfilled', 'Передача подтверждена'), ('cancelled', 'Отменён'), ('expired', 'Истёк')], default='active')),
                ('expires_at', models.DateTimeField('Действует до')),
                ('meeting_at', models.DateTimeField('Время передачи', null=True, blank=True)),
                ('meeting_note', models.CharField('Условия передачи', max_length=500, blank=True)),
                ('cancellation_reason', models.TextField(max_length=1500, blank=True)),
                ('overdue_notified', models.BooleanField(default=False))],
            options={'ordering': ['-created_at'], 'constraints': [models.UniqueConstraint(fields=['item'], condition=Q(status='active'), name='one_active_reservation_per_item'), models.UniqueConstraint(fields=['request'], condition=Q(status='active'), name='one_active_reservation_per_request')]}
        ),
        migrations.CreateModel(
            name='VolunteerTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField('Создано', auto_now_add=True)),
                ('updated_at', models.DateTimeField('Изменено', auto_now=True)),
                ('reservation', models.OneToOneField('aid.reservation', on_delete=models.PROTECT, related_name='task')),
                ('volunteer', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='volunteer_tasks')),
                ('title', models.CharField('Поручение', max_length=160)),
                ('description', models.TextField('Что нужно сделать', max_length=2000)),
                ('district', models.CharField('Район', max_length=20, choices=[('central', 'Центральный район'), ('talnakh', 'Талнах'), ('kayerkan', 'Кайеркан'), ('oganer', 'Оганер')])),
                ('pickup_address', models.CharField('Откуда забрать', max_length=250)),
                ('dropoff_address', models.CharField('Куда доставить', max_length=250)),
                ('scheduled_at', models.DateTimeField('Согласованное время')),
                ('status', models.CharField(max_length=20, choices=[('open', 'Ищем волонтёра'), ('accepted', 'Принято волонтёром'), ('in_progress', 'В пути'), ('delivered', 'Доставлено, ждёт подтверждения'), ('cancelled', 'Отменено')], default='open', db_index=True)),
                ('result_note', models.TextField('Результат / причина отказа', max_length=1500, blank=True))],
            options={'ordering': ['scheduled_at'], 'verbose_name': 'поручение', 'verbose_name_plural': 'поручения'}
        ),
        migrations.CreateModel(
            name='Transfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reservation', models.OneToOneField('aid.reservation', on_delete=models.PROTECT, related_name='transfer')),
                ('confirmed_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='confirmed_transfers')),
                ('transferred_at', models.DateTimeField('Фактическое время передачи', db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('confirmation_note', models.TextField('Подтверждение получения', max_length=1500)),
                ('reversed_at', models.DateTimeField(null=True, blank=True)),
                ('reversed_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='reversed_transfers')),
                ('reversal_reason', models.TextField(max_length=1500, blank=True))],
            options={'ordering': ['-transferred_at'], 'verbose_name': 'передача', 'verbose_name_plural': 'передачи'}
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recipient', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')),
                ('title', models.CharField(max_length=150)),
                ('message', models.TextField(max_length=1500)),
                ('url', models.CharField(max_length=250, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('read_at', models.DateTimeField(null=True, blank=True))],
            options={'ordering': ['-created_at']}
        ),
        migrations.CreateModel(
            name='Favorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')),
                ('item', models.ForeignKey('aid.item', on_delete=models.CASCADE))],
            options={'constraints': [models.UniqueConstraint(fields=['user', 'item'], name='unique_favorite')]}
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('actor', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)),
                ('entity', models.CharField(max_length=30)),
                ('object_id', models.PositiveBigIntegerField()),
                ('action', models.CharField(max_length=120)),
                ('before', models.JSONField(default=dict)),
                ('after', models.JSONField(default=dict)),
                ('note', models.TextField(max_length=2000, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True))],
            options={'ordering': ['-created_at'], 'verbose_name': 'событие', 'verbose_name_plural': 'журнал событий'}
        ),
        migrations.CreateModel(
            name='VolunteerApplication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField('Создано', auto_now_add=True)),
                ('updated_at', models.DateTimeField('Изменено', auto_now=True)),
                ('user', models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='volunteer_application')),
                ('availability', models.CharField('Когда удобно помогать', max_length=300)),
                ('has_vehicle', models.BooleanField('Есть автомобиль', default=False)),
                ('description', models.TextField('Какую помощь готовы оказывать', max_length=1500)),
                ('status', models.CharField(max_length=20, choices=[('new', 'На рассмотрении'), ('approved', 'Одобрено'), ('rejected', 'Отклонено')], default='new')),
                ('decision_reason', models.TextField(max_length=1500, blank=True))],
            options={}
        ),
        migrations.CreateModel(
            name='LoginAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=64, db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True))],
            options={}
        )
    ]
