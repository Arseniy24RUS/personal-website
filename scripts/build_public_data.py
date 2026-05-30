#!/usr/bin/env python3
from pathlib import Path
import csv
import json
import re
from datetime import datetime, timezone

ROOT = Path('.')
DATA = ROOT / 'data'
PUBLIC = DATA / 'public'
PUBLIC.mkdir(parents=True, exist_ok=True)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default


def load_elibrary_publications():
    json_path = DATA / 'processed' / 'elibrary_publications.json'
    if json_path.exists():
        return read_json(json_path, [])
    tsv_path = DATA / 'elibrary' / 'publications.tsv'
    rows = []
    if not tsv_path.exists():
        return rows
    with tsv_path.open('r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        for r in reader:
            if len(r) < 8:
                continue
            rows.append({
                'source': 'elibrary_rinc_tsv',
                'number': int(r[0]) if r[0].isdigit() else None,
                'year': int(r[1]) if r[1].isdigit() else None,
                'rinc_citations': int(r[2]) if r[2].isdigit() else 0,
                'title': r[3],
                'authors_raw': r[4],
                'venue': r[5] or None,
                'pages': r[6] or None,
                'url': r[7] or None,
            })
    return rows


def load_scopus(author_id='57220956828'):
    base = DATA / 'scopus'
    metrics = read_json(base / f'scopus_author_{author_id}_metrics.json', None)
    works = read_json(base / f'scopus_author_{author_id}_works.json', [])
    return metrics, works


def norm_title(s):
    return re.sub(r'[^a-zа-я0-9]+', ' ', (s or '').lower()).strip()


def build_admin_queue(elib, scopus_works):
    existing = {norm_title(p.get('title')) for p in elib if p.get('title')}
    queue = []
    for w in scopus_works or []:
        title = w.get('title') or ''
        nt = norm_title(title)
        if not nt:
            continue
        if nt not in existing:
            queue.append({
                'id': 'scopus_' + (w.get('eid') or str(len(queue)+1)).replace(':', '_'),
                'entity_type': 'publication',
                'action': 'review_scopus_publication',
                'confidence': 0.72,
                'reason': 'Scopus work was not matched exactly to eLibrary title snapshot',
                'candidate': w,
            })
    return queue


def main():
    elib = load_elibrary_publications()
    scopus_metrics, scopus_works = load_scopus()
    admin_queue = build_admin_queue(elib, scopus_works)
    metrics = read_json(DATA / 'elibrary' / 'metrics.json', {})
    public_profile = {
        'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'name_ru': 'Ситковский Арсений Михайлович',
        'name_en': 'Arseniy M. Sitkovskiy',
        'identifiers': {
            'elibrary_authorid': '1012909',
            'elibrary_spin': '9559-1803',
            'orcid': '0000-0002-8725-6580',
            'scopus_author_id': '57220956828',
            'wos_researcher_id': 'AAG-1530-2021',
            'github': 'Arseniy24RUS'
        },
        'elibrary_metrics': metrics,
        'scopus_metrics': scopus_metrics,
        'admin_queue_size': len(admin_queue),
    }
    (PUBLIC / 'profile.json').write_text(json.dumps(public_profile, ensure_ascii=False, indent=2), encoding='utf-8')
    (PUBLIC / 'publications.json').write_text(json.dumps(elib, ensure_ascii=False, indent=2), encoding='utf-8')
    (DATA / 'admin_queue').mkdir(parents=True, exist_ok=True)
    (DATA / 'admin_queue' / 'publications.json').write_text(json.dumps(admin_queue, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Built public data: {len(elib)} eLibrary publications, {len(scopus_works or [])} Scopus works, {len(admin_queue)} queue items')


if __name__ == '__main__':
    main()
