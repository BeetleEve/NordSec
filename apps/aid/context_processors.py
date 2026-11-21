from django.conf import settings
from .districts import DISTRICT_AREAS


def interface(request):
    return {
        'unread_count': request.user.notifications.filter(read_at__isnull=True).count() if request.user.is_authenticated else 0,
        'demo_mode': settings.NORDSEC_DEMO,
        'map_tile_url': settings.MAP_TILE_URL,
        'map_district_areas': DISTRICT_AREAS,
    }
