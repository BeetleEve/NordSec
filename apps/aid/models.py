import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from apps.accounts.models import User


def photo_path(instance, filename):
    return f'items/{uuid.uuid4().hex}.jpg'


class Timestamped(models.Model):
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Изменено', auto_now=True)

    class Meta:
        abstract = True


class Category(models.Model):
    name = models.CharField('Название', max_length=80, unique=True)
    slug = models.SlugField('Код', unique=True)
    illustration = models.CharField('Иллюстрация', max_length=30, default='other')
    order = models.PositiveSmallIntegerField('Порядок', default=0)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'категория'
        verbose_name_plural = 'категории'

    def __str__(self):
        return self.name


class Item(Timestamped):
    class Status(models.TextChoices):
        REVIEW = 'review', 'На проверке'
        AVAILABLE = 'available', 'Доступна'
        RESERVED = 'reserved', 'В резерве'
        DELIVERED = 'delivered', 'Передана'
        WITHDRAWN = 'withdrawn', 'Снята с передачи'
        REJECTED = 'rejected', 'Не принята'

    class Condition(models.TextChoices):
        NEW = 'new', 'Новая'
        EXCELLENT = 'excellent', 'Отличное'
        GOOD = 'good', 'Хорошее'

    class Location(models.TextChoices):
        DONOR = 'donor', 'У жертвователя'
        FUND = 'fund', 'В пункте фонда'
        TRANSIT = 'transit', 'У волонтёра'
        RECIPIENT = 'recipient', 'У получателя'

    donor = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Жертвователь', on_delete=models.PROTECT, null=True, blank=True, related_name='donated_items')
    registered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='registered_items')
    donor_name = models.CharField('Имя жертвователя', max_length=150)
    contact_phone = models.CharField('Телефон для связи', max_length=30)
    title = models.CharField('Название вещи', max_length=140)
    category = models.ForeignKey(Category, verbose_name='Категория', on_delete=models.PROTECT, related_name='items')
    description = models.TextField('Описание', max_length=3000)
    condition = models.CharField('Состояние', max_length=20, choices=Condition.choices, default=Condition.GOOD)
    size = models.CharField('Размер / габариты', max_length=80, blank=True)
    district = models.CharField('Район', max_length=20, choices=User.District.choices)
    pickup_address = models.CharField('Точный адрес передачи', max_length=250)
    location = models.CharField('Местонахождение', max_length=20, choices=Location.choices, default=Location.DONOR)
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.REVIEW, db_index=True)
    photo = models.ImageField('Фото', upload_to=photo_path, blank=True)
    needs_transport = models.BooleanField('Нужна помощь с перевозкой', default=False)
    review_reason = models.TextField('Причина решения', max_length=1500, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='reviewed_items')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField('Дата принятия на учёт', null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'category', 'district'], name='item_catalog_idx')]
        verbose_name = 'вещь'
        verbose_name_plural = 'вещи'

    def get_absolute_url(self):
        return reverse('item_detail', args=[self.pk])

    def __str__(self):
        return self.title


class HelpRequest(Timestamped):
    class Status(models.TextChoices):
        NEW = 'new', 'На рассмотрении'
        CLARIFICATION = 'clarification', 'Нужно уточнение'
        APPROVED = 'approved', 'Одобрено'
        RESERVED = 'reserved', 'Вещь зарезервирована'
        COMPLETED = 'completed', 'Помощь получена'
        REJECTED = 'rejected', 'Отказано'
        CANCELLED = 'cancelled', 'Отменено'

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='help_requests')
    registered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='registered_requests')
    recipient_name = models.CharField('Имя получателя', max_length=150)
    contact_phone = models.CharField('Телефон для связи', max_length=30)
    preferred_item = models.ForeignKey(Item, verbose_name='Выбранная вещь', on_delete=models.PROTECT, null=True, blank=True, related_name='requests')
    category = models.ForeignKey(Category, verbose_name='Категория', on_delete=models.PROTECT)
    need = models.TextField('Какая помощь нужна', max_length=3000)
    district = models.CharField('Район', max_length=20, choices=User.District.choices)
    delivery_address = models.CharField('Адрес для согласования передачи', max_length=250, blank=True)
    needs_delivery = models.BooleanField('Нужна помощь с доставкой', default=False)
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    coordinator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='assigned_requests')
    decision_reason = models.TextField('Ответ получателю', max_length=1500, blank=True)
    staff_note = models.TextField('Служебный комментарий', max_length=2000, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'обращение'
        verbose_name_plural = 'обращения'

    def __str__(self):
        return f'Обращение №{self.pk}'

    def get_absolute_url(self):
        return reverse('request_detail', args=[self.pk])


class Reservation(Timestamped):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Действует'
        FULFILLED = 'fulfilled', 'Передача подтверждена'
        CANCELLED = 'cancelled', 'Отменён'
        EXPIRED = 'expired', 'Истёк'

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='reservations')
    request = models.ForeignKey(HelpRequest, on_delete=models.PROTECT, related_name='reservations')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField('Действует до')
    meeting_at = models.DateTimeField('Время передачи', null=True, blank=True)
    meeting_note = models.CharField('Условия передачи', max_length=500, blank=True)
    cancellation_reason = models.TextField(max_length=1500, blank=True)
    overdue_notified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['item'], condition=Q(status='active'), name='one_active_reservation_per_item'),
            models.UniqueConstraint(fields=['request'], condition=Q(status='active'), name='one_active_reservation_per_request'),
        ]


class VolunteerTask(Timestamped):
    class Status(models.TextChoices):
        OPEN = 'open', 'Ищем волонтёра'
        ACCEPTED = 'accepted', 'Принято волонтёром'
        IN_PROGRESS = 'in_progress', 'В пути'
        DELIVERED = 'delivered', 'Доставлено, ждёт подтверждения'
        CANCELLED = 'cancelled', 'Отменено'

    reservation = models.OneToOneField(Reservation, on_delete=models.PROTECT, related_name='task')
    volunteer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='volunteer_tasks')
    title = models.CharField('Поручение', max_length=160)
    description = models.TextField('Что нужно сделать', max_length=2000)
    district = models.CharField('Район', max_length=20, choices=User.District.choices)
    pickup_address = models.CharField('Откуда забрать', max_length=250)
    dropoff_address = models.CharField('Куда доставить', max_length=250)
    scheduled_at = models.DateTimeField('Согласованное время')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    result_note = models.TextField('Результат / причина отказа', max_length=1500, blank=True)

    class Meta:
        ordering = ['scheduled_at']
        verbose_name = 'поручение'
        verbose_name_plural = 'поручения'

    def get_absolute_url(self):
        return reverse('task_detail', args=[self.pk])


class Transfer(models.Model):
    reservation = models.OneToOneField(Reservation, on_delete=models.PROTECT, related_name='transfer')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='confirmed_transfers')
    transferred_at = models.DateTimeField('Фактическое время передачи', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmation_note = models.TextField('Подтверждение получения', max_length=1500)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='reversed_transfers')
    reversal_reason = models.TextField(max_length=1500, blank=True)

    class Meta:
        ordering = ['-transferred_at']
        verbose_name = 'передача'
        verbose_name_plural = 'передачи'


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField(max_length=1500)
    url = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    item = models.ForeignKey(Item, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'item'], name='unique_favorite')]


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    entity = models.CharField(max_length=30)
    object_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=120)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    note = models.TextField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'событие'
        verbose_name_plural = 'журнал событий'


class VolunteerApplication(Timestamped):
    class Status(models.TextChoices):
        NEW = 'new', 'На рассмотрении'
        APPROVED = 'approved', 'Одобрено'
        REJECTED = 'rejected', 'Отклонено'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='volunteer_application')
    availability = models.CharField('Когда удобно помогать', max_length=300)
    has_vehicle = models.BooleanField('Есть автомобиль', default=False)
    description = models.TextField('Какую помощь готовы оказывать', max_length=1500)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    decision_reason = models.TextField(max_length=1500, blank=True)


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
