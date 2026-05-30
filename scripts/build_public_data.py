#!/usr/bin/env python3
from pathlib import Path
import csv
import json
import re
from datetime import datetime, timezone

try:
    import yaml
except Exception:
    yaml = None

ROOT = Path('.')
DATA = ROOT / 'data'
PUBLIC = DATA / 'public'
PUBLIC.mkdir(parents=True, exist_ok=True)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default


def read_profile():
    path = Path('config/profile.yml')
    if path.exists() and yaml is not None:
        return yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return {
        'profile': {
            'display_name_ru': 'Ситковский Арсений Михайлович',
            'display_name_en': 'Arseniy M. Sitkovskiy',
            'identifiers': {
                'elibrary_authorid': '1012909',
                'elibrary_spin': '9559-1803',
                'orcid': '0000-0002-8725-6580',
                'scopus_author_id': '57220956828',
                'wos_researcher_id': 'AAG-1530-2021',
                'github_username': 'Arseniy24RUS'
            }
        }
    }


def load_elibrary_publications():
    json_path = DATA / 'processed' / 'elibrary_publications.json'
    if json_path.exists():
        rows = read_json(json_path, [])
        for p in rows:
            p.setdefault('sources', ['elibrary'])
        return rows
    tsv_path = DATA / 'elibrary' / 'publications.tsv'
    rows = []
    if not tsv_path.exists():
        return rows
    with tsv_path.open('r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        for r in reader:
            if len(r) < 8:
                continue
            item = None
            if r[7] and 'id=' in r[7]:
                m = re.search(r'id=(\d+)', r[7])
                item = m.group(1) if m else None
            rows.append({
                'source': 'elibrary_rinc_tsv',
                'number': int(r[0]) if r[0].isdigit() else None,
                'elibrary_item_id': item,
                'year': int(r[1]) if r[1].isdigit() else None,
                'rinc_citations': int(r[2]) if r[2].isdigit() else 0,
                'title': r[3],
                'authors_raw': r[4],
                'venue': r[5] or None,
                'pages': r[6] or None,
                'url': r[7] or None,
                'sources': ['elibrary'],
            })
    return rows


def load_scopus(author_id):
    base = DATA / 'scopus'
    metrics = read_json(base / f'scopus_author_{author_id}_metrics.json', None)
    works = read_json(base / f'scopus_author_{author_id}_works.json', [])
    return metrics, works


def load_open_publications():
    payload = read_json(DATA / 'open' / 'open_publications.json', {})
    return payload.get('records', []) if isinstance(payload, dict) else []


def norm_title(s):
    return re.sub(r'[^a-zа-я0-9]+', ' ', (s or '').lower().replace('ё', 'е')).strip()


def norm_doi(doi):
    if not doi:
        return None
    doi = str(doi).strip().lower()
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)
    return doi or None


def add_source(target, source_name):
    target.setdefault('sources', ['elibrary'])
    if source_name not in target['sources']:
        target['sources'].append(source_name)


def index_records(records):
    by_item = {str(p.get('elibrary_item_id')): p for p in records if p.get('elibrary_item_id')}
    by_title = {norm_title(p.get('title')): p for p in records if p.get('title')}
    by_title_year = {(norm_title(p.get('title')), str(p.get('year') or '')): p for p in records if p.get('title')}
    by_doi = {norm_doi(p.get('doi')): p for p in records if norm_doi(p.get('doi'))}
    return by_item, by_title, by_title_year, by_doi


def merge_scopus(elib, scopus_works):
    curated = read_json(DATA / 'curation' / 'scopus_elibrary_map.json', {})
    by_item, by_title, by_title_year, by_doi = index_records(elib)
    queue = []

    for w in scopus_works or []:
        eid = w.get('eid')
        target = None
        match = curated.get(eid or '')
        if match:
            target = by_item.get(str(match.get('elibrary_item_id')))
        doi = norm_doi(w.get('doi'))
        if target is None and doi:
            target = by_doi.get(doi)
        if target is None:
            target = by_title.get(norm_title(w.get('title')))
        if target is None:
            target = by_title_year.get((norm_title(w.get('title')), str((w.get('year') or w.get('cover_date') or '')[:4])))
        if target is not None:
            add_source(target, 'scopus')
            target['scopus'] = {
                'eid': w.get('eid'),
                'scopus_id': w.get('scopus_id'),
                'doi': w.get('doi'),
                'title': w.get('title'),
                'source_title': w.get('journal_or_source') or w.get('source_title'),
                'cover_date': w.get('cover_date'),
                'cited_by_count': w.get('cited_by_count'),
                'subtype': w.get('subtype'),
                'openaccess': w.get('openaccess'),
                'match_type': (match or {}).get('match_type', 'automatic_doi_or_title_match'),
            }
            if doi and not target.get('doi'):
                target['doi'] = doi
        else:
            queue.append({
                'id': 'scopus_' + (w.get('eid') or str(len(queue)+1)).replace(':', '_'),
                'entity_type': 'publication',
                'action': 'review_scopus_publication',
                'confidence': 0.72,
                'reason': 'Scopus work was not matched to eLibrary snapshot or curated map',
                'candidate': w,
            })
    return elib, queue


def merge_open_sources(canonical, open_records):
    _, by_title, by_title_year, by_doi = index_records(canonical)
    queue = []
    enriched = 0
    for r in open_records or []:
        doi = norm_doi(r.get('doi'))
        title_key = norm_title(r.get('title'))
        year_key = str(r.get('year') or '')
        target = by_doi.get(doi) if doi else None
        if target is None and title_key:
            target = by_title_year.get((title_key, year_key)) or by_title.get(title_key)
        if target:
            source = r.get('source') or 'open_api'
            add_source(target, source)
            target.setdefault('open_sources', []).append({
                'source': source,
                'doi': r.get('doi'),
                'title': r.get('title'),
                'year': r.get('year'),
                'url': r.get('url') or r.get('landing_page_url'),
                'venue': r.get('venue'),
                'cited_by_count': r.get('cited_by_count') or r.get('is_referenced_by_count'),
                'is_oa': r.get('is_oa'),
                'oa_status': r.get('oa_status'),
            })
            if doi and not target.get('doi'):
                target['doi'] = doi
            if r.get('venue') and not target.get('venue'):
                target['venue'] = r.get('venue')
            enriched += 1
        else:
            queue.append({
                'id': 'open_' + (doi or re.sub(r'\W+', '_', title_key)[:60] or str(len(queue)+1)),
                'entity_type': 'publication',
                'action': 'review_open_publication',
                'confidence': 0.65 if doi else 0.45,
                'reason': 'Open bibliographic record from ORCID/OpenAlex/Crossref was not matched to canonical eLibrary/Scopus list',
                'candidate': r,
            })
    return canonical, queue, enriched


def write_tsv(publications):
    path = PUBLIC / 'publications.tsv'
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['number','year','rinc_citations','scopus_citations','title','authors','venue','pages','doi','url','sources'])
        for p in publications:
            writer.writerow([
                p.get('number'), p.get('year'), p.get('rinc_citations', 0),
                (p.get('scopus') or {}).get('cited_by_count', ''),
                p.get('title'), p.get('authors_raw'), p.get('venue'), p.get('pages', ''), p.get('doi', ''), p.get('url'), ','.join(p.get('sources', []))
            ])


def write_admin_queue_csv(queue):
    path = DATA / 'admin_queue' / 'publications.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id','entity_type','action','confidence','reason','title','year','doi','source'])
        writer.writeheader()
        for item in queue:
            c = item.get('candidate') or {}
            writer.writerow({
                'id': item.get('id'),
                'entity_type': item.get('entity_type'),
                'action': item.get('action'),
                'confidence': item.get('confidence'),
                'reason': item.get('reason'),
                'title': c.get('title'),
                'year': c.get('year'),
                'doi': c.get('doi'),
                'source': c.get('source'),
            })


def main():
    profile = read_profile().get('profile', {})
    ids = profile.get('identifiers', {})
    scopus_author_id = ids.get('scopus_author_id', '57220956828')
    elib = load_elibrary_publications()
    scopus_metrics, scopus_works = load_scopus(scopus_author_id)
    canonical, scopus_queue = merge_scopus(elib, scopus_works)
    open_records = load_open_publications()
    canonical, open_queue, open_enriched = merge_open_sources(canonical, open_records)
    admin_queue = scopus_queue + open_queue

    elibrary_publication_metrics = read_json(DATA / 'elibrary' / 'metrics.json', {})
    elibrary_profile_metrics = read_json(DATA / 'elibrary' / 'profile_metrics.json', {})
    wos_profile_metrics = read_json(DATA / 'wos' / 'profile_metrics.json', {})
    open_report = read_json(DATA / 'open' / 'harvest_report.json', {})
    public_profile = {
        'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'name_ru': profile.get('display_name_ru', 'Ситковский Арсений Михайлович'),
        'name_en': profile.get('display_name_en', 'Arseniy M. Sitkovskiy'),
        'identifiers': ids,
        'elibrary_metrics': elibrary_publication_metrics,
        'elibrary_profile_metrics': elibrary_profile_metrics,
        'wos_profile_metrics': wos_profile_metrics,
        'scopus_metrics': scopus_metrics,
        'open_sources_report': open_report,
        'canonical_publications_count': len(canonical),
        'scopus_enriched_publications_count': sum(1 for p in canonical if 'scopus' in p.get('sources', [])),
        'open_sources_records_count': len(open_records),
        'open_sources_enriched_publications_count': open_enriched,
        'admin_queue_size': len(admin_queue),
    }
    (PUBLIC / 'profile.json').write_text(json.dumps(public_profile, ensure_ascii=False, indent=2), encoding='utf-8')
    (PUBLIC / 'publications.json').write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding='utf-8')
    write_tsv(canonical)
    (DATA / 'admin_queue').mkdir(parents=True, exist_ok=True)
    (DATA / 'admin_queue' / 'publications.json').write_text(json.dumps(admin_queue, ensure_ascii=False, indent=2), encoding='utf-8')
    write_admin_queue_csv(admin_queue)
    print(f'Built public data: {len(canonical)} canonical publications, {len(scopus_works or [])} Scopus works, {len(open_records)} open records, {len(admin_queue)} queue items')


if __name__ == '__main__':
    main()
