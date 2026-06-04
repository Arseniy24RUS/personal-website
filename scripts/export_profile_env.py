#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os
import re

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

PROFILE_YAML = Path(os.environ.get('PROFILE_YAML', 'config/profile.yml'))
GITHUB_ENV = os.environ.get('GITHUB_ENV')


def load_profile() -> dict:
    text = PROFILE_YAML.read_text(encoding='utf-8') if PROFILE_YAML.exists() else ''
    if yaml:
        data = yaml.safe_load(text) or {}
        return data.get('profile') or {}
    # Minimal fallback for the current simple config/profile.yml structure.
    profile: dict = {'identifiers': {}}
    current = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        indent = len(line) - len(line.lstrip(' '))
        stripped = line.strip()
        if stripped == 'identifiers:':
            current = 'identifiers'
            continue
        if ':' not in stripped:
            continue
        key, value = stripped.split(':', 1)
        value = value.strip().strip('"\'')
        if indent >= 4 and current == 'identifiers':
            profile.setdefault('identifiers', {})[key] = value
        elif indent >= 2:
            profile[key] = value
    return profile


def safe(value) -> str:
    return str(value or '').strip()


def append_env(items: dict[str, str]) -> None:
    lines = []
    for key, value in items.items():
        # Newline-free values only; URLs are derived, not user free text.
        value = re.sub(r'[\r\n]+', ' ', value).strip()
        lines.append(f'{key}={value}')
    payload = '\n'.join(lines) + '\n'
    if GITHUB_ENV:
        with open(GITHUB_ENV, 'a', encoding='utf-8') as f:
            f.write(payload)
    print(payload, end='')


def main() -> int:
    profile = load_profile()
    ids = profile.get('identifiers') or {}
    elibrary_author_id = safe(ids.get('elibrary_authorid'))
    scopus_author_id = safe(ids.get('scopus_author_id'))
    wos_researcher_id = safe(ids.get('wos_researcher_id'))
    orcid = safe(ids.get('orcid'))
    values = {
        'PROFILE_SLUG': safe(profile.get('slug')),
        'DISPLAY_NAME_RU': safe(profile.get('display_name_ru')),
        'DISPLAY_NAME_EN': safe(profile.get('display_name_en')),
        'ELIBRARY_AUTHOR_ID': elibrary_author_id,
        'ELIBRARY_SPIN': safe(ids.get('elibrary_spin')),
        'ORCID_ID': orcid,
        'SCOPUS_AUTHOR_ID': scopus_author_id,
        'WOS_RESEARCHER_ID': wos_researcher_id,
        'GITHUB_USERNAME': safe(ids.get('github_username')),
    }
    if elibrary_author_id:
        values['ELIBRARY_PROFILE_URL'] = f'https://www.elibrary.ru/author_profile.asp?id={elibrary_author_id}'
        values['ELIBRARY_ITEMS_URL'] = f'https://elibrary.ru/author_items.asp?authorid={elibrary_author_id}&pubrole=100&show_refs=1&pubcat=risc'
    if wos_researcher_id:
        values['WOS_PROFILE_URL'] = f'https://www.webofscience.com/wos/author/record/{wos_researcher_id}'
    append_env(values)
    missing = [key for key in ['ELIBRARY_AUTHOR_ID', 'SCOPUS_AUTHOR_ID', 'WOS_RESEARCHER_ID', 'ORCID_ID'] if not values.get(key)]
    if missing:
        print('Profile identifiers missing: ' + ', '.join(missing))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
