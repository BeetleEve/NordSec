import json
import hashlib
import math
import time
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from django.conf import settings
from django.core.cache import caches
from django.db import connection, transaction, models
from django.db.models import Case, When, F
from django.db.models.functions import Round
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_GET
from .models import Item
from .permissions import public_items


@require_GET
def markers(request):
    items = public_items().exclude(latitude__isnull=True).select_related('category').annotate(public_latitude=Case(When(placement='street', then=F('latitude')), default=Round('latitude', 3), output_field=models.DecimalField(max_digits=9, decimal_places=6)), public_longitude=Case(When(placement='street', then=F('longitude')), default=Round('longitude', 3), output_field=models.DecimalField(max_digits=9, decimal_places=6)))
    if request.GET.get('placement') in Item.Placement.values:
        items = items.filter(placement=request.GET['placement'])
    if request.GET.get('category'):
        items = items.filter(category__slug=request.GET['category'][:80])
    bounds = request.GET.get('bounds')
    if bounds:
        try:
            west, south, east, north = [float(n) for n in bounds.split(',')]
            if not all(math.isfinite(v) for v in (west, south, east, north)) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Некорректная область карты.'}, status=400)
        # Slight margin avoids leaking exact private coordinates through boundary probes.
        items = items.filter(public_latitude__gte=south, public_latitude__lte=north, public_longitude__gte=west, public_longitude__lte=east)
    result = []
    for item in items[:200]:
        street = item.placement == Item.Placement.STREET
        lat = float(item.public_latitude)
        lon = float(item.public_longitude)
        if bounds and not (west <= lon <= east and south <= lat <= north):
            continue
        result.append({'id': item.pk, 'title': item.title, 'url': item.get_absolute_url(), 'latitude': lat, 'longitude': lon, 'placement': item.placement, 'category': item.category.name, 'place': item.pickup_address if street else item.get_district_display(), 'expires_at': item.expires_at.isoformat() if item.expires_at else None, 'approximate': not street})
    response = JsonResponse({'items': result, 'limit': 200})
    response['Cache-Control'] = 'no-store'
    return response


@require_GET
def find_address(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 3 or len(q) > 180:
        return JsonResponse({'error': 'Введите адрес, от 3 до 180 символов.'}, status=400)
    cache = caches['geocoding']
    key = 'address:' + hashlib.sha256(q.casefold().encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return JsonResponse({'results': cached})
    try:
        with transaction.atomic():
            # PostgreSQL lock plus persisted cache keeps the application-wide provider limit across workers.
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_try_advisory_xact_lock(7340261)')
                acquired = cursor.fetchone()[0]
            if not acquired:
                return JsonResponse({'error': 'Поиск занят. Повторите через пару секунд.'}, status=429)
            last = cache.get('last-request', 0)
            if time.time()-last < 1.1:
                return JsonResponse({'error': 'Повторите поиск через пару секунд.'}, status=429)
            cache.set('last-request', time.time(), 60)
            url = settings.MAP_GEOCODER_URL + '?' + urlencode({'q': q, 'format': 'jsonv2', 'limit': 5, 'accept-language': 'ru'})
            req = Request(url, headers={'User-Agent': 'NordSec/1.0 (+https://github.com/BeetleEve/NordSec)'})
            with urlopen(req, timeout=6) as response:
                data = json.loads(response.read(100000))
            results = [{'latitude': float(row['lat']), 'longitude': float(row['lon']), 'label': row['display_name']} for row in data[:5]]
            cache.set(key, results, 86400)
            return JsonResponse({'results': results})
    except (OSError, ValueError, KeyError, TypeError):
        return JsonResponse({'error': 'Поиск адреса недоступен. Поставьте метку на карте.'}, status=503)


@require_GET
def tile(request, z, x, y):
    # Only requested visible tiles are loaded; there is no prefetch or bulk/offline download.
    if z > 19 or x >= 2**z or y >= 2**z:
        raise Http404
    cache = caches['map_tiles']
    key = f'v2:{z}:{x}:{y}'
    cached = cache.get(key)
    if cached is None:
        upstream = settings.MAP_TILE_UPSTREAM_URL.format(z=z, x=x, y=y)
        req = Request(upstream, headers={'User-Agent': 'NordSec/1.0 (+https://github.com/BeetleEve/NordSec)'})
        try:
            with urlopen(req, timeout=8) as response:
                data = response.read(1500000)
                if not data.startswith(b'\x89PNG'):
                    raise ValueError('Invalid tile')
                import re
                age = re.search(r'max-age=(\d+)', response.headers.get('Cache-Control', ''))
                ttl = max(1, int(age.group(1))) if age else 604800
        except (OSError, ValueError):
            return HttpResponse(status=503)
        cached = {'data': data, 'until': time.time()+ttl}
        cache.set(key, cached, ttl)
    remaining = max(1, int(cached['until']-time.time()))
    result = HttpResponse(cached['data'], content_type='image/png')
    result['Cache-Control'] = f'public, max-age={remaining}'
    return result
