"""Small .env reader. Existing process environment always takes priority."""
import os
from pathlib import Path


def load_env(path: Path):
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


def flag(name, default=False):
    return os.environ.get(name, str(int(default))).lower() in ('1', 'true', 'yes')
