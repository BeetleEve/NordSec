"""Replace the typographic local fallback with the official public SVG logo.

The download URL is from the rendered home page at https://t-dobra.ru/.
Run manually or by bootstrap. A failed download preserves the local fallback.
"""
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

URL = 'https://t-dobra.ru/wp-content/themes/2026/assets/images/logo.svg'


def main():
    target = Path(__file__).resolve().parent.parent / 'static' / 'brand' / 'logo.svg'
    try:
        request = urllib.request.Request(URL, headers={'Cookie': 'beget=begetok'})
        with urllib.request.urlopen(request, timeout=10) as response:
            content = response.read(512_001)
        if len(content) > 512_000:
            raise ValueError('Неожиданный размер логотипа.')
        root = ET.fromstring(content)
        if not root.tag.endswith('svg') or b'<script' in content.lower():
            raise ValueError('Неожиданный формат логотипа.')
        target.write_bytes(content)
        print('Официальный логотип фонда сохранён.')
    except (OSError, ValueError, ET.ParseError) as exc:
        print('Сохранён локальный текстовый вариант. Загрузку официального логотипа можно повторить:', type(exc).__name__)


if __name__ == '__main__':
    main()
