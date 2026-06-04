#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import re

import enrich_publication_metadata as enrich

PUBLICATIONS_JSON = Path('data/public/publications.json')
REPORT_JSON = Path('data/audit/publication_reference_sanitizer_report.json')
BAD_ONE_LETTER = {'К', 'к', 'Ы', 'ы'}


def clean(value) -> str:
    return re.sub(r'\s+', ' ', str(value or '').replace('\xa0', ' ')).strip()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def valid_venue(value) -> bool:
    value = clean(value).strip('.;,')
    return len(value) >= 3 and value not in BAD_ONE_LETTER and not re.fullmatch(r'[A-ZА-ЯЁ]', value)


def valid_volume(value) -> bool:
    value = clean(value).strip('.;,()')
    if not value:
        return False
    if value in BAD_ONE_LETTER:
        return False
    if re.fullmatch(r'[А-Яа-яЁё]', value):
        return False
    return len(value) <= 30


def valid_issue(value) -> bool:
    value = clean(value).strip('.;,()')
    if not value:
        return False
    if value in BAD_ONE_LETTER:
        return False
    if re.fullmatch(r'[А-Яа-яЁё]', value):
        return False
    return len(value) <= 30


def valid_pages(value) -> bool:
    value = clean(value)
    if not value:
        return False
    value = re.sub(r'^[СC]\.?\s*', '', value)
    return bool(re.fullmatch(r'\d+\s*[-–—]?\s*\d*', value))


def bad_reference_text(value) -> bool:
    value = str(value or '')
    return bool(re.search(r'//\s*[КЫ]\.|—\s*Т\.\s*[КЫ]\.|,\s*[КЫ](?:\(|,|\.)|\s[КЫ]\s*//', value))


def sanitize_pub(pub: dict) -> list[dict]:
    changes: list[dict] = []
    for key in ['venue', 'venue_ru', 'venue_en', 'book_title']:
        if pub.get(key) and not valid_venue(pub.get(key)):
            changes.append({'field': key, 'old': pub.get(key), 'reason': 'invalid_venue'})
            pub[key] = ''
    for key in ['volume']:
        if pub.get(key) and not valid_volume(pub.get(key)):
            changes.append({'field': key, 'old': pub.get(key), 'reason': 'invalid_volume'})
            pub[key] = ''
    for key in ['issue']:
        if pub.get(key) and not valid_issue(pub.get(key)):
            changes.append({'field': key, 'old': pub.get(key), 'reason': 'invalid_issue'})
            pub[key] = ''
    for key in ['pages', 'page']:
        if pub.get(key) and not valid_pages(pub.get(key)):
            changes.append({'field': key, 'old': pub.get(key), 'reason': 'invalid_pages'})
            pub[key] = ''
    for key in ['gost_ru', 'apa_en']:
        if pub.get(key) and bad_reference_text(pub.get(key)):
            changes.append({'field': key, 'old': pub.get(key), 'reason': 'bad_reference_text'})
            pub[key] = ''
    return changes


def main() -> int:
    publications = enrich.read_json(PUBLICATIONS_JSON, [])
    if not isinstance(publications, list):
        raise SystemExit(f'{PUBLICATIONS_JSON} is missing or invalid')
    report = {
        'records': len(publications),
        'changed_records': 0,
        'field_changes': 0,
        'bad_references_before': 0,
        'bad_references_after': 0,
        'samples': [],
    }
    for pub in publications:
        before_bad = bad_reference_text(pub.get('gost_ru')) or bad_reference_text(pub.get('apa_en'))
        if before_bad:
            report['bad_references_before'] += 1
        changes = sanitize_pub(pub)
        if changes or before_bad:
            pub['gost_ru'] = enrich.format_gost(pub)
            pub['apa_en'] = enrich.format_apa(pub)
            # One more pass: if regenerated text is still suspicious, drop the
            # offending structural fields and regenerate a shorter safe reference.
            if bad_reference_text(pub.get('gost_ru')) or bad_reference_text(pub.get('apa_en')):
                for key in ['venue', 'venue_ru', 'venue_en', 'book_title', 'volume', 'issue']:
                    if pub.get(key):
                        changes.append({'field': key, 'old': pub.get(key), 'reason': 'second_pass_bad_reference_text'})
                        pub[key] = ''
                pub['gost_ru'] = enrich.format_gost(pub)
                pub['apa_en'] = enrich.format_apa(pub)
        after_bad = bad_reference_text(pub.get('gost_ru')) or bad_reference_text(pub.get('apa_en'))
        if after_bad:
            report['bad_references_after'] += 1
        if changes:
            report['changed_records'] += 1
            report['field_changes'] += len(changes)
            if len(report['samples']) < 20:
                report['samples'].append({
                    'title': pub.get('title_ru') or pub.get('title') or pub.get('title_en'),
                    'changes': changes,
                    'gost_ru': pub.get('gost_ru'),
                    'apa_en': pub.get('apa_en'),
                })
    write_json(PUBLICATIONS_JSON, publications)
    enrich.update_publications_tsv(publications)
    write_json(REPORT_JSON, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
