"""Create PostgreSQL custom-format backup plus uploaded files. No shell interpolation."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.env import load_env
from scripts.run_local import find_postgres


def main():
    parser = argparse.ArgumentParser(description='Резервная копия базы и фотографий NordSec')
    parser.add_argument('--output', type=Path, default=ROOT / 'backups')
    args = parser.parse_args()
    load_env(ROOT / '.env')
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = args.output / f'nordsec-{stamp}.dump'
    pg = find_postgres()
    executable = pg / ('pg_dump.exe' if os.name == 'nt' else 'pg_dump')
    env = dict(os.environ, PGPASSWORD=os.environ['DB_PASSWORD'])
    subprocess.run([str(executable), '-h', os.environ.get('DB_HOST', '127.0.0.1'), '-p', os.environ.get('DB_PORT', '5432'),
        '-U', os.environ.get('DB_USER', 'nordsec'), '-d', os.environ.get('DB_NAME', 'nordsec'), '-Fc', '-f', str(target)], check=True, env=env)
    with ZipFile(args.output / f'nordsec-media-{stamp}.zip', 'w', compression=ZIP_DEFLATED) as archive:
        for file in (ROOT / 'media').rglob('*'):
            if file.is_file():
                archive.write(file, file.relative_to(ROOT))
    print('Резервная копия создана:', target)
    print('Файл .env не включён. Сохраните его отдельно в защищённом месте.')


if __name__ == '__main__':
    main()
