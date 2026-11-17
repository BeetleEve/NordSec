from django.conf import settings


def interface(request):
    return {
        'unread_count': request.user.notifications.filter(read_at__isnull=True).count() if request.user.is_authenticated else 0,
        'demo_mode': settings.NORDSEC_DEMO,
    }
