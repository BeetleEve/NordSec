"""Conservative automated checks; uncertain posts go to the moderator queue."""
import re
from django.utils import timezone
from datetime import timedelta
from .models import Item


def inspect_listing(item):
    text = f'{item.title} {item.description}'.casefold()
    flags = []
    if item.pk and item.signals.filter(kind='unsafe').count() >= 2 and not item.reviewed_by_id:
        flags.append('После жалоб нужна ручная проверка.')
    if re.search(r'закладк|наркот|мефедрон|героин|боеприпас|взрывчат|огнестрел', text):
        flags.append('Требуется проверка содержания.')
    if re.search(r'https?://|t\.me/|@[a-z0-9_]{4,}', text):
        flags.append('Внешние ссылки и контакты в описании требуют проверки.')
    if item.placement == Item.Placement.STREET and (not item.photo or item.latitude is None or item.longitude is None):
        flags.append('Для отметки на улице нужны фото и точка.')
    item.review_reason = ' '.join(flags)
    item.reviewed_by = None
    item.reviewed_at = timezone.now()
    item.status = Item.Status.REVIEW if flags else Item.Status.AVAILABLE
    if not flags:
        item.accepted_at = item.reviewed_at
    if item.placement == Item.Placement.STREET:
        item.expires_at = timezone.now() + timedelta(hours=6)
        item.last_seen_at = timezone.now()
    else:
        item.expires_at = None
    return flags
