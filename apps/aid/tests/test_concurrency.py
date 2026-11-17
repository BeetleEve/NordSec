from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from django.core.exceptions import ValidationError
from django.db import connection, close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.aid.models import Category, Item, HelpRequest, Reservation
from apps.aid import services


class ConcurrentReservationTests(TransactionTestCase):
    """Uses real PostgreSQL row locks; intentionally not SQLite-compatible."""
    def test_two_coordinators_racing_for_one_item(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Нужен PostgreSQL для проверки блокировок.')
        coordinators=[User.objects.create_user(f'coord-{i}',role='coordinator') for i in range(2)]
        donor=User.objects.create_user('donor-concurrent')
        recipients=[User.objects.create_user(f'recipient-{i}') for i in range(2)]
        category,_=Category.objects.get_or_create(slug='clothes',defaults={'name':'Одежда'})
        item=Item.objects.create(donor=donor,registered_by=donor,donor_name='Тест',contact_phone='+79000000000',title='Куртка',category=category,description='Тест',district='central',pickup_address='Тест',status='available')
        requests=[HelpRequest.objects.create(recipient=u,registered_by=u,recipient_name='Тест',contact_phone='+79000000000',category=category,need='Тест',district='central',status='approved') for u in recipients]
        barrier=Barrier(2)
        def worker(index):
            close_old_connections()
            try:
                actor=User.objects.get(pk=coordinators[index].pk)
                barrier.wait(timeout=10)
                services.reserve(actor,requests[index].pk,item.pk,timezone.now()+timedelta(days=1))
                return 'reserved'
            except ValidationError:
                return 'unavailable'
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(worker,range(2)))
        self.assertCountEqual(outcomes,['reserved','unavailable'])
        self.assertEqual(Reservation.objects.filter(item=item,status='active').count(),1)
