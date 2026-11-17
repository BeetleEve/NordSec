"""Database-backed login rate limit; shared across application processes."""
import hashlib
from datetime import timedelta
from django.http import HttpResponse
from django.utils import timezone


class LoginThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != '/account/login/' or request.method != 'POST':
            return self.get_response(request)
        from apps.aid.models import LoginAttempt
        # Never trust a forwarded address supplied by the client.
        key = hashlib.sha256((request.META.get('REMOTE_ADDR', '') + ':' + request.POST.get('username', '').casefold()).encode()).hexdigest()
        since = timezone.now() - timedelta(minutes=15)
        if LoginAttempt.objects.filter(key=key, created_at__gte=since).count() >= 10:
            response = HttpResponse('Слишком много попыток входа. Повторите через 15 минут.', status=429, content_type='text/plain; charset=utf-8')
            response['Retry-After'] = '900'
            return response
        response = self.get_response(request)
        if request.user.is_authenticated:
            LoginAttempt.objects.filter(key=key).delete()
        else:
            LoginAttempt.objects.create(key=key)
        return response
