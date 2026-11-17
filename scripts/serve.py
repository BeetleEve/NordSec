"""Run the WSGI application behind a configured HTTPS reverse proxy."""
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description='Сервер NordSec для рабочей установки')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()
    from django.conf import settings
    from config.env import flag
    from waitress import serve
    if settings.DEBUG or settings.NORDSEC_DEMO:
        parser.error('Рабочая установка требует DJANGO_DEBUG=0 и NORDSEC_DEMO=0.')
    if not flag('NORDSEC_BEHIND_HTTPS_PROXY'):
        parser.error('Настройте HTTPS-прокси и NORDSEC_BEHIND_HTTPS_PROXY=1. Локальная демонстрация: python main.py.')
    # The proxy must terminate TLS. Only the loopback address is exposed here;
    # untrusted forwarded client headers are deliberately not accepted.
    serve(application, host='127.0.0.1', port=args.port, threads=8,
          url_scheme='https', max_request_body_size=7 * 1024 * 1024)


if __name__ == '__main__':
    main()
