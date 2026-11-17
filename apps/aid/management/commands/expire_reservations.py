"""python manage.py expire_reservations [--loop]"""
import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone
from apps.aid.models import LoginAttempt
from apps.aid.services import expire_reservations


class Command(BaseCommand):
    help = 'Освободить просроченные резервы без перемещённых вещей; --loop запускает проверку каждые 60 секунд.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true')

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            released = expire_reservations()
            LoginAttempt.objects.filter(created_at__lt=timezone.now()-timedelta(days=1)).delete()
            if released or not options['loop']:
                self.stdout.write(f'Освобождено резервов: {released}')
            if not options['loop']:
                return
            time.sleep(60)
