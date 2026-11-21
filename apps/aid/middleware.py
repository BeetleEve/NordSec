"""Request audit without form bodies, query strings, passwords or session tokens."""
import json
import logging
from django.utils import timezone

logger = logging.getLogger('nordsec.requests')


class RequestAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        status = 500
        try:
            response = self.get_response(request)
            status = response.status_code
            return response
        finally:
            user = getattr(request, 'user', None)
            logger.info(json.dumps({
                'time': timezone.now().isoformat(), 'method': request.method,
                'path': request.path, 'status': status,
                'user_id': user.pk if user and user.is_authenticated else None,
                'ip': request.META.get('REMOTE_ADDR', ''),
            }, ensure_ascii=False))
