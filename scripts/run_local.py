"""Local Windows bootstrap with a private PostgreSQL cluster.

No existing PostgreSQL service or user database is changed. Default local port: 55432.
Run `python main.py --demo` for fictional data, `python main.py` for an empty setup.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / '.runtime'


def execute(args, **kwargs):
    print('→', ' '.join(str(a) for a in args[:3]), flush=True)
    return subprocess.run([str(a) for a in args], cwd=ROOT, check=True, **kwargs)


def project_python():
    venv = ROOT / '.venv'
    python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        execute([sys.executable, '-m', 'venv', venv])
    return python


def find_postgres():
    configured = os.environ.get('PG_BIN')
    if configured:
        result = Path(configured)
        if not (result / ('pg_ctl.exe' if os.name == 'nt' else 'pg_ctl')).exists():
            raise RuntimeError('PG_BIN задан, но в нём нет pg_ctl.')
        return result
    if shutil.which('pg_ctl'):
        return Path(shutil.which('pg_ctl')).parent
    if os.name == 'nt':
        base = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'PostgreSQL'
        if base.exists():
            versions = sorted([p for p in base.iterdir() if p.is_dir() and p.name.isdigit()], key=lambda p: int(p.name), reverse=True)
            for version in versions:
                if (version / 'bin' / 'pg_ctl.exe').exists():
                    return version / 'bin'
    raise RuntimeError('Не найден PostgreSQL. Установите PostgreSQL 14+ или задайте PG_BIN, либо настройте существующую базу в .env.')


def local_env(demo):
    envfile = ROOT / '.env'
    if not envfile.exists():
        RUNTIME.mkdir(exist_ok=True)
        envfile.write_text(
            f'DJANGO_DEBUG=1\nDJANGO_SECRET_KEY={secrets.token_urlsafe(48)}\nDJANGO_ALLOWED_HOSTS=127.0.0.1,localhost\n'
            f'DB_NAME=nordsec\nDB_USER=nordsec\nDB_PASSWORD={secrets.token_urlsafe(24)}\nDB_HOST=127.0.0.1\nDB_PORT=55432\n'
            f'DB_SSLMODE=prefer\nNORDSEC_LOCAL_CLUSTER=1\nNORDSEC_DEMO={int(demo)}\n', encoding='utf-8')
    sys.path.insert(0, str(ROOT))
    from config.env import load_env
    load_env(envfile)
    if demo:
        if os.environ.get('NORDSEC_LOCAL_CLUSTER') != '1':
            raise RuntimeError('--demo разрешён только для отдельной локальной базы этого проекта.')
        os.environ['NORDSEC_DEMO'] = '1'
    return dict(os.environ, PYTHONIOENCODING='utf-8')


def start_database(env):
    """Only manages the cluster explicitly marked as local by this bootstrap."""
    if env.get('NORDSEC_LOCAL_CLUSTER') != '1':
        return None
    if env.get('DB_HOST') != '127.0.0.1' or env.get('DB_USER') != 'nordsec' or env.get('DB_NAME') != 'nordsec':
        raise RuntimeError('Параметры локального кластера изменены. Удалите NORDSEC_LOCAL_CLUSTER=1 из .env и настройте базу вручную.')
    pg = find_postgres()
    suffix = '.exe' if os.name == 'nt' else ''
    data = RUNTIME / 'postgres'
    control = pg / ('pg_ctl' + suffix)
    passwordfile = RUNTIME / 'postgres_password'
    RUNTIME.mkdir(exist_ok=True)
    if not (data / 'PG_VERSION').exists():
        if data.exists() and any(data.iterdir()):
            raise RuntimeError('Каталог .runtime/postgres не пуст и не содержит готовый кластер. Проверьте его вручную; данные не удалены.')
        passwordfile.write_text(env['DB_PASSWORD'] + '\n', encoding='utf-8')
        try:
            execute([pg / ('initdb' + suffix), '-D', data, '-U', 'nordsec', '--pwfile', passwordfile,
                     '--encoding=UTF8', '--locale=C', '--auth-host=scram-sha-256', '--auth-local=scram-sha-256'], env=env)
        finally:
            passwordfile.unlink(missing_ok=True)
    state = subprocess.run([str(control), '-D', str(data), 'status'], capture_output=True, cwd=ROOT)
    started = False
    if state.returncode != 0:
        execute([control, '-D', data, '-l', RUNTIME / 'postgres.log', '-o', f'-h 127.0.0.1 -p {int(env["DB_PORT"])}', '-w', 'start'], env=env)
        started = True
    pgenv = dict(env, PGPASSWORD=env['DB_PASSWORD'])
    # psql checks the exact local cluster before issuing a CREATE DATABASE.
    query = subprocess.run([str(pg / ('psql' + suffix)), '-h', '127.0.0.1', '-p', env['DB_PORT'], '-U', 'nordsec', '-d', 'postgres', '-tAc', "SELECT 1 FROM pg_database WHERE datname='nordsec'"], env=pgenv, capture_output=True, text=True, check=True)
    if query.stdout.strip() != '1':
        execute([pg / ('createdb' + suffix), '-h', '127.0.0.1', '-p', env['DB_PORT'], '-U', 'nordsec', 'nordsec'], env=pgenv)
    return (control, data) if started else None


def main():
    parser = argparse.ArgumentParser(description='Локальный запуск NordSec')
    parser.add_argument('--demo', action='store_true', help='Создать вымышленные данные в отдельной локальной базе')
    parser.add_argument('--test', action='store_true', help='Запустить тесты Django на PostgreSQL и завершить работу')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=8000)
    options = parser.parse_args()
    if not 1024 <= options.port <= 65535:
        parser.error('Порт должен быть в диапазоне 1024–65535.')
    database = None
    maintenance = None
    try:
        python = project_python()
        installed = subprocess.run([str(python), '-c', 'import django,psycopg,PIL,waitress,whitenoise; assert django.VERSION[:2] == (5, 2)'], capture_output=True).returncode == 0
        if not installed:
            execute([python, '-m', 'pip', 'install', '-r', ROOT / 'requirements.txt'])
        env = local_env(options.demo)
        database = start_database(env)
        execute([python, 'manage.py', 'migrate', '--noinput'], env=env)
        execute([python, 'manage.py', 'check'], env=env)
        if options.demo:
            execute([python, 'manage.py', 'seed_demo'], env=env)
        if options.test:
            execute([python, 'manage.py', 'test', 'apps', '--noinput', '--verbosity=2'], env=env)
            return
        if env.get('DJANGO_DEBUG') != '1':
            raise RuntimeError('main.py предназначен для локальной разработки с DJANGO_DEBUG=1. Рабочий запуск описан в docs/deployment.md.')
        maintenance = subprocess.Popen([str(python), 'manage.py', 'expire_reservations', '--loop'], cwd=ROOT, env=env)
        url = f'http://127.0.0.1:{options.port}'
        print(f'\nNordSec: {url}\nОстановить: Ctrl+C\n', flush=True)
        if not options.no_browser:
            timer = threading.Timer(2, lambda: webbrowser.open(url))
            timer.daemon = True
            timer.start()
        execute([python, 'manage.py', 'runserver', f'127.0.0.1:{options.port}', '--noreload'], env=env)
    except KeyboardInterrupt:
        print('\nОстановка NordSec…')
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        print(f'\nНе удалось запустить NordSec: {exc}\nПодробная инструкция: README.md', file=sys.stderr)
        raise SystemExit(1)
    finally:
        if maintenance and maintenance.poll() is None:
            maintenance.terminate()
            try:
                maintenance.wait(timeout=8)
            except subprocess.TimeoutExpired:
                maintenance.kill()
        if database:
            control, data = database
            subprocess.run([str(control), '-D', str(data), '-m', 'fast', '-w', 'stop'], cwd=ROOT, capture_output=True)


if __name__ == '__main__':
    main()
