#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from elibrary_fetch import fetch_elibrary_page  # noqa: E402

AUTHOR_ID = os.environ.get('ELIBRARY_AUTHOR_ID', '1012909')
PROFILE_URL = os.environ.get('ELIBRARY_PROFILE_URL', f'https://www.elibrary.ru/author_profile.asp?id={AUTHOR_ID}')
ITEMS_URL = os.environ.get('ELIBRARY_ITEMS_URL', f'https://www.elibrary.ru/author_items.asp?authorid={AUTHOR_ID}&pubrole=100&show_refs=1&pubcat=risc')


def probe(name: str, url: str, must_have: list[str]) -> dict:
    html, report = fetch_elibrary_page(url)
    if html:
        out = Path(f'elibrary_{name}_probe.html')
        out.write_text(html, encoding='utf-8')
        report['probe_path'] = str(out)
        report['probe_bytes_utf8'] = len(html.encode('utf-8', errors='replace'))
        report['checks'] = {token: (token in html) for token in must_have}
        lowered = html.lower()
        report['checks']['ip_blocked_or_suspicious'] = ('ip_blocked' in lowered) or ('подозр' in lowered) or ('suspicious' in lowered)
        report['checks']['cookie_warning'] = ('cookie' in lowered or 'cookies' in lowered) and len(html.encode('utf-8', errors='replace')) < 2000
        report['excerpt'] = html[:700].replace('\n', ' ')
    else:
        report['checks'] = {token: False for token in must_have}
        report['checks']['ip_blocked_or_suspicious'] = False
        report['checks']['cookie_warning'] = False
    return report


def main() -> int:
    profile = probe('profile', PROFILE_URL, ['ОБЩИЕ ПОКАЗАТЕЛИ', 'Индекс Хирша'])
    items = probe('items', ITEMS_URL, ['author_items', 'arw'])
    payload = {'profile': profile, 'items': items}
    Path('elibrary_probe_report.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    profile_ok = all(profile.get('checks', {}).get(x) for x in ['ОБЩИЕ ПОКАЗАТЕЛИ', 'Индекс Хирша'])
    items_ok = all(items.get('checks', {}).get(x) for x in ['author_items', 'arw'])
    blocked = profile.get('checks', {}).get('ip_blocked_or_suspicious') or items.get('checks', {}).get('ip_blocked_or_suspicious')
    cookie_warning = profile.get('checks', {}).get('cookie_warning') or items.get('checks', {}).get('cookie_warning')
    if profile_ok and items_ok and not blocked and not cookie_warning:
        return 0
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
