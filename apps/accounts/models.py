from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = 'member', 'Участник'
        VOLUNTEER = 'volunteer', 'Волонтёр'
        COORDINATOR = 'coordinator', 'Координатор'

    class District(models.TextChoices):
        CENTRAL = 'central', 'Центральный район'
        TALNAKH = 'talnakh', 'Талнах'
        KAYERKAN = 'kayerkan', 'Кайеркан'
        OGANER = 'oganer', 'Оганер'

    role = models.CharField('Роль', max_length=20, choices=Role.choices, default=Role.MEMBER)
    phone = models.CharField('Телефон', max_length=30, blank=True)
    district = models.CharField('Район', max_length=20, choices=District.choices, default=District.CENTRAL)
    consent_at = models.DateTimeField('Дата согласия на обработку данных', null=True, blank=True)

    @property
    def is_coordinator(self):
        return self.is_authenticated and (self.is_superuser or self.role == self.Role.COORDINATOR)

    @property
    def is_volunteer(self):
        return self.is_coordinator or self.role == self.Role.VOLUNTEER

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    class Meta:
        verbose_name = 'пользователь'
        verbose_name_plural = 'пользователи'
