from django.test import TestCase
from apps.accounts.models import User
from apps.aid.models import Category, Item, HelpRequest


class AidCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user('coord-test', password='Example-test-8102', role='moderator', first_name='Координатор')
        cls.donor = User.objects.create_user('donor-test', password='Example-test-8102', first_name='Жертвователь', phone='+7 900 000-00-01')
        cls.recipient = User.objects.create_user('recipient-test', password='Example-test-8102', first_name='Получатель', phone='+7 900 000-00-02')
        cls.other = User.objects.create_user('other-test', password='Example-test-8102')
        cls.volunteer = User.objects.create_user('volunteer-test', password='Example-test-8102', role='volunteer')
        cls.category, _ = Category.objects.get_or_create(slug='clothes', defaults={'name':'Одежда', 'illustration':'clothes'})

    def make_item(self, **kwargs):
        values = dict(donor=self.donor, registered_by=self.donor, donor_name='Жертвователь', contact_phone='+7 900 000-00-01',
            title='Зимняя куртка', category=self.category, description='Исправная чистая куртка', district='central', pickup_address='НЕПУБЛИЧНЫЙ АДРЕС 123', status=Item.Status.AVAILABLE)
        values.update(kwargs)
        return Item.objects.create(**values)

    def make_request(self, **kwargs):
        values = dict(recipient=self.recipient, registered_by=self.recipient, recipient_name='Получатель', contact_phone='+7 900 000-00-02',
            category=self.category, need='Нужна куртка размера M', district='central', status=HelpRequest.Status.APPROVED)
        values.update(kwargs)
        return HelpRequest.objects.create(**values)
