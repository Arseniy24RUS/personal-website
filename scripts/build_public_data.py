#!/usr/bin/env python3
from pathlib import Path
import csv, json, re
from datetime import datetime, timezone
try:
    import yaml
except Exception:
    yaml = None

DATA = Path('data')
PUBLIC = DATA / 'public'
PUBLIC.mkdir(parents=True, exist_ok=True)
MIN_ELIBRARY_RECORDS = 50


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default


def profile():
    if yaml and Path('config/profile.yml').exists():
        return (yaml.safe_load(Path('config/profile.yml').read_text(encoding='utf-8')) or {}).get('profile', {})
    return {'display_name_ru': 'Ситковский Арсений Михайлович', 'display_name_en': 'Arseniy M. Sitkovskiy', 'identifiers': {'scopus_author_id': '57220956828'}}


def nt(s):
    return re.sub(r'[^a-zа-я0-9]+', ' ', (s or '').lower().replace('ё', 'е')).strip()


def nd(doi):
    if not doi:
        return None
    return re.sub(r'^https?://(dx\.)?doi\.org/', '', str(doi).strip().lower()) or None


def has_cyrillic(s):
    return bool(re.search(r'[А-Яа-яЁё]', s or ''))


def has_latin(s):
    return bool(re.search(r'[A-Za-z]', s or ''))


def as_number(v):
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, dict):
        return as_number(v.get('value') if v.get('value') is not None else v.get('raw'))
    if v is None:
        return None
    m = re.search(r'-?\d+(?:\.\d+)?', str(v).replace('\xa0', ' ').replace(',', '.'))
    if not m:
        return None
    num = float(m.group(0))
    return int(num) if num.is_integer() else num


def metric_value(mapping, *labels):
    if not isinstance(mapping, dict):
        return None
    for label in labels:
        if label in mapping:
            v = as_number(mapping[label])
            if v is not None:
                return v
    lowered = {str(k).lower(): v for k, v in mapping.items()}
    for label in labels:
        key = str(label).lower()
        for k, v in lowered.items():
            if key in k:
                n = as_number(v)
                if n is not None:
                    return n
    return None


def set_lang_field(p, base, value, prefer=None):
    value = (value or '').strip() if isinstance(value, str) else value
    if not value:
        return
    lang = prefer
    if lang not in ('ru', 'en'):
        lang = 'ru' if has_cyrillic(value) else 'en' if has_latin(value) else None
    if lang:
        p.setdefault(f'{base}_{lang}', value)
    p.setdefault(base, value)


def enrich_localized_fields(p):
    set_lang_field(p, 'title', p.get('title'))
    set_lang_field(p, 'venue', p.get('venue'))
    sc = p.get('scopus') or {}
    if sc.get('title'):
        set_lang_field(p, 'title', sc.get('title'), 'en')
    if sc.get('journal_or_source') or sc.get('source_title'):
        set_lang_field(p, 'venue', sc.get('journal_or_source') or sc.get('source_title'), 'en')
    for r in p.get('open_sources') or []:
        if r.get('title'):
            set_lang_field(p, 'title', r.get('title'))
        if r.get('venue'):
            set_lang_field(p, 'venue', r.get('venue'))
    for r in p.get('wos_records') or []:
        if r.get('title_en') or r.get('title'):
            set_lang_field(p, 'title', r.get('title_en') or r.get('title'), 'en')
    p.setdefault('title_ru', p.get('title'))
    p.setdefault('venue_ru', p.get('venue'))


def addsrc(p, s):
    p.setdefault('sources', ['elibrary'])
    if s and s not in p['sources']:
        p['sources'].append(s)


def elib_key(p):
    if p.get('elibrary_item_id'):
        return ('elibrary', str(p.get('elibrary_item_id')))
    doi = nd(p.get('doi'))
    if doi:
        return ('doi', doi)
    return ('title_year', nt(p.get('title') or p.get('title_ru') or p.get('title_en')), str(p.get('year') or ''))


def record_score(p):
    base_fields = ['title', 'title_ru', 'title_en', 'authors_raw', 'venue', 'venue_ru', 'venue_en', 'pages', 'doi', 'url', 'metadata_raw']
    score = sum(1 for key in base_fields if p.get(key))
    score += len(p.get('sources') or [])
    if p.get('source') and 'saved_html' in str(p.get('source')):
        score += 3
    if p.get('doi'):
        score += 2
    return score


def merge_publication_sets(*datasets):
    merged = {}
    for dataset in datasets:
        for original in dataset or []:
            if not isinstance(original, dict):
                continue
            p = dict(original)
            if not (p.get('title') or p.get('title_ru') or p.get('title_en') or p.get('elibrary_item_id')):
                continue
            p.setdefault('sources', ['elibrary'])
            if isinstance(p.get('sources'), str):
                p['sources'] = [s.strip() for s in p['sources'].split(',') if s.strip()]
            key = elib_key(p)
            if key not in merged:
                merged[key] = p
                continue
            a, b = merged[key], p
            if record_score(b) > record_score(a):
                a, b = b, a
            for k, v in b.items():
                if k in {'sources', 'open_sources', 'wos_records'}:
                    continue
                if (a.get(k) is None or a.get(k) == '' or a.get(k) == []) and v not in (None, '', []):
                    a[k] = v
            src = []
            for s in (a.get('sources') or []) + (b.get('sources') or []):
                if s and s not in src:
                    src.append(s)
            a['sources'] = src or ['elibrary']
            for list_key in ('open_sources', 'wos_records'):
                combined = []
                for item in (a.get(list_key) or []) + (b.get(list_key) or []):
                    if item not in combined:
                        combined.append(item)
                if combined:
                    a[list_key] = combined
            merged[key] = a
    rows = list(merged.values())
    for p in rows:
        enrich_localized_fields(p)
    rows.sort(key=lambda p: (-(int(p.get('year') or 0) if str(p.get('year') or '').isdigit() else 0), int(p.get('number') or 999999)))
    return rows


def load_elib_tsv():
    rows = []
    t = DATA / 'elibrary/publications.tsv'
    if not t.exists():
        return rows
    for r in csv.reader(t.open(encoding='utf-8'), delimiter='\t'):
        if len(r) < 8:
            continue
        m = re.search(r'id=(\d+)', r[7] or '')
        rec = {
            'source': 'elibrary_rinc_tsv',
            'number': int(r[0]) if r[0].isdigit() else None,
            'elibrary_item_id': m.group(1) if m else None,
            'year': int(r[1]) if r[1].isdigit() else None,
            'rinc_citations': int(r[2]) if r[2].isdigit() else 0,
            'title': r[3],
            'title_ru': r[3],
            'authors_raw': r[4],
            'venue': r[5] or None,
            'venue_ru': r[5] or None,
            'pages': r[6] or None,
            'doi': None,
            'url': r[7] or None,
            'sources': ['elibrary'],
        }
        enrich_localized_fields(rec)
        rows.append(rec)
    return rows


def load_existing_public_elib():
    rows = read_json(DATA / 'public/publications.json', [])
    out = []
    for p in rows if isinstance(rows, list) else []:
        src = p.get('sources') or []
        src_text = ','.join(src) if isinstance(src, list) else str(src)
        if p.get('elibrary_item_id') or 'elibrary' in src_text or 'eLibrary' in src_text or 'elibrary.ru' in str(p.get('url') or ''):
            out.append(p)
    return out


def load_elib():
    processed = read_json(DATA / 'processed/elibrary_publications.json', [])
    if not isinstance(processed, list):
        processed = []
    for p in processed:
        p.setdefault('sources', ['elibrary'])
        enrich_localized_fields(p)
    tsv = load_elib_tsv()
    public_existing = load_existing_public_elib()
    merged = merge_publication_sets(tsv, public_existing, processed)
    best_count = max(len(processed), len(tsv), len(public_existing), len(merged))
    if best_count >= MIN_ELIBRARY_RECORDS and len(merged) < MIN_ELIBRARY_RECORDS:
        candidates = [x for x in [tsv, public_existing, processed] if len(x) >= MIN_ELIBRARY_RECORDS]
        return max(candidates, key=len) if candidates else merged
    return merged


def indexes(records):
    return ({str(p.get('elibrary_item_id')): p for p in records if p.get('elibrary_item_id')}, {nt(p.get('title')): p for p in records if p.get('title')}, {(nt(p.get('title')), str(p.get('year') or '')): p for p in records if p.get('title')}, {nd(p.get('doi')): p for p in records if nd(p.get('doi'))})


def merge_scopus(canon, works):
    curated = read_json(DATA / 'curation/scopus_elibrary_map.json', {})
    by_item, by_title, by_ty, by_doi = indexes(canon)
    added = 0
    for w in works or []:
        eid = w.get('eid'); doi = nd(w.get('doi')); target = None
        if eid in curated:
            target = by_item.get(str(curated[eid].get('elibrary_item_id')))
        if target is None and doi:
            target = by_doi.get(doi)
        if target is None:
            target = by_title.get(nt(w.get('title')))
        if target is None:
            target = by_ty.get((nt(w.get('title')), str(w.get('year') or w.get('cover_date') or '')[:4]))
        if target:
            addsrc(target, 'scopus'); target['scopus'] = w
            if doi and not target.get('doi'):
                target['doi'] = doi
            set_lang_field(target, 'title', w.get('title'), 'en')
            set_lang_field(target, 'venue', w.get('journal_or_source') or w.get('source_title'), 'en')
        else:
            rec = {'source': 'scopus_api_auto', 'number': None, 'elibrary_item_id': None, 'year': int(str(w.get('year') or w.get('cover_date') or '')[:4]) if str(w.get('year') or w.get('cover_date') or '')[:4].isdigit() else None, 'rinc_citations': 0, 'title': w.get('title'), 'authors_raw': w.get('creator') or '', 'venue': w.get('journal_or_source') or w.get('source_title'), 'pages': None, 'doi': doi, 'url': w.get('url') or (f"https://www.scopus.com/record/display.uri?eid={eid}" if eid else None), 'sources': ['scopus'], 'scopus': w, 'auto_accept_reason': 'author-scoped Scopus AU-ID record'}
            enrich_localized_fields(rec); canon.append(rec); added += 1
    return added


def merge_open(canon, records):
    curated = read_json(DATA / 'curation/open_elibrary_map.json', {})
    by_item, by_title, by_ty, by_doi = indexes(canon)
    enriched = added = 0
    for r in records or []:
        doi = nd(r.get('doi')); title = nt(r.get('title')); target = None
        if doi in curated:
            target = by_item.get(str(curated[doi].get('elibrary_item_id')))
        if target is None and ('title:' + title) in curated:
            target = by_item.get(str(curated['title:' + title].get('elibrary_item_id')))
        if target is None and doi:
            target = by_doi.get(doi)
        if target is None:
            target = by_ty.get((title, str(r.get('year') or ''))) or by_title.get(title)
        src = r.get('source') or 'open_api'
        if target:
            addsrc(target, src); target.setdefault('open_sources', []).append(r)
            if doi and not target.get('doi'):
                target['doi'] = doi
            if r.get('venue') and not target.get('venue'):
                target['venue'] = r.get('venue')
            set_lang_field(target, 'title', r.get('title'))
            set_lang_field(target, 'venue', r.get('venue'))
            enriched += 1
        else:
            rec = {'source': src + '_auto', 'number': None, 'elibrary_item_id': None, 'year': int(r.get('year')) if str(r.get('year') or '').isdigit() else None, 'rinc_citations': 0, 'title': r.get('title'), 'authors_raw': '', 'venue': r.get('venue'), 'pages': None, 'doi': doi, 'url': r.get('url') or r.get('landing_page_url'), 'sources': [src], 'open_sources': [r], 'auto_accept_reason': 'author-scoped ORCID/OpenAlex/Crossref record'}
            enrich_localized_fields(rec); canon.append(rec); added += 1
            if doi:
                by_doi[doi] = rec
            if title:
                by_title[title] = rec; by_ty[(title, str(rec.get('year') or ''))] = rec
    return enriched, added


def merge_wos(canon, records):
    by_item, by_title, by_ty, by_doi = indexes(canon)
    enriched = added = 0
    for r in records or []:
        doi = nd(r.get('doi')); title = nt(r.get('title_en') or r.get('title')); target = None
        if doi:
            target = by_doi.get(doi)
        if target is None:
            target = by_ty.get((title, str(r.get('year') or ''))) or by_title.get(title)
        if target:
            addsrc(target, 'wos'); target.setdefault('wos_records', []).append(r)
            if doi and not target.get('doi'):
                target['doi'] = doi
            set_lang_field(target, 'title', r.get('title_en') or r.get('title'), 'en')
            enriched += 1
        else:
            rec = {'source': 'wos_free_view_auto', 'number': None, 'elibrary_item_id': None, 'year': r.get('year'), 'rinc_citations': 0, 'title': r.get('title_en') or r.get('title'), 'authors_raw': '', 'venue': None, 'pages': None, 'doi': doi, 'url': r.get('url'), 'sources': ['wos'], 'wos_records': [r], 'auto_accept_reason': 'author-scoped Web of Science ResearcherID record'}
            enrich_localized_fields(rec); canon.append(rec); added += 1
            if doi:
                by_doi[doi] = rec
            if title:
                by_title[title] = rec; by_ty[(title, str(rec.get('year') or ''))] = rec
    return enriched, added


def build_scientometrics(canon, elib_profile, scopus_metrics, wos_profile):
    gm = (elib_profile or {}).get('general_metrics') or {}
    wos_summary = (wos_profile or {}).get('summary') or {}
    sm = scopus_metrics or {}
    data = {
        'rinc': {'label_ru': 'РИНЦ', 'label_en': 'RSCI', 'source': 'eLibrary/РИНЦ', 'publications': metric_value(gm, 'Число публикаций в РИНЦ') or sum(1 for p in canon if 'elibrary' in p.get('sources', [])), 'citations': metric_value(gm, 'Число цитирований из публикаций, входящих в РИНЦ'), 'h_index': metric_value(gm, 'Индекс Хирша по публикациям в РИНЦ') or metric_value(gm, 'Индекс Хирша по всем публикациям')},
        'scopus': {'label_ru': 'Scopus', 'label_en': 'Scopus', 'source': 'Scopus API/search snapshot', 'publications': as_number(sm.get('documents_count')) or as_number(sm.get('document_count')) or as_number(sm.get('works_count_from_search')), 'citations': as_number(sm.get('cited_by_count')) or as_number(sm.get('citation_count')) or as_number(sm.get('citation_sum_from_search')), 'h_index': as_number(sm.get('h_index')) or as_number(sm.get('h_index_recomputed_from_retrieved_works'))},
        'wos': {'label_ru': 'Web of Science', 'label_en': 'Web of Science', 'source': 'Web of Science Researcher Profile', 'publications': as_number(wos_summary.get('publications')), 'citations': as_number(wos_summary.get('citations')), 'h_index': as_number(wos_summary.get('h_index'))}
    }
    return {'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(), 'columns': ['rinc', 'scopus', 'wos'], 'rows': [{'key': 'publications', 'label_ru': 'Количество публикаций', 'label_en': 'Publications'}, {'key': 'citations', 'label_ru': 'Количество цитирований', 'label_en': 'Citations'}, {'key': 'h_index', 'label_ru': 'H-индекс (Хирш)', 'label_en': 'H-index'}], 'sources': data}


def write_tsv(pubs):
    with (PUBLIC / 'publications.tsv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['number', 'year', 'rinc_citations', 'scopus_citations', 'title', 'title_ru', 'title_en', 'authors', 'venue', 'venue_ru', 'venue_en', 'pages', 'doi', 'url', 'sources'])
        for p in pubs:
            enrich_localized_fields(p)
            w.writerow([p.get('number'), p.get('year'), p.get('rinc_citations', 0), (p.get('scopus') or {}).get('cited_by_count', ''), p.get('title'), p.get('title_ru', ''), p.get('title_en', ''), p.get('authors_raw'), p.get('venue'), p.get('venue_ru', ''), p.get('venue_en', ''), p.get('pages', ''), p.get('doi', ''), p.get('url'), ','.join(p.get('sources', []))])


def empty_queue():
    q = DATA / 'admin_queue'; q.mkdir(parents=True, exist_ok=True)
    (q / 'publications.json').write_text('[]\n', encoding='utf-8')
    with (q / 'publications.csv').open('w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerow(['id', 'entity_type', 'action', 'confidence', 'reason', 'title', 'year', 'doi', 'source'])


def main():
    prof = profile(); ids = prof.get('identifiers', {}); sid = ids.get('scopus_author_id', '57220956828')
    canon = load_elib()
    scopus_metrics = read_json(DATA / f'scopus/scopus_author_{sid}_metrics.json', None)
    scopus_works = read_json(DATA / f'scopus/scopus_author_{sid}_works.json', [])
    scopus_added = merge_scopus(canon, scopus_works)
    open_records = (read_json(DATA / 'open/open_publications.json', {}) or {}).get('records', [])
    open_enriched, open_added = merge_open(canon, open_records)
    wos_profile = read_json(DATA / 'wos/profile_metrics.json', {})
    wos_records = (wos_profile or {}).get('records', [])
    wos_enriched, wos_added = merge_wos(canon, wos_records)
    elib_profile = read_json(DATA / 'elibrary/profile_metrics.json', {})
    for p in canon:
        enrich_localized_fields(p)
    scientometrics = build_scientometrics(canon, elib_profile, scopus_metrics, wos_profile)
    public_profile = {'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(), 'name_ru': prof.get('display_name_ru', ''), 'name_en': prof.get('display_name_en', ''), 'identifiers': ids, 'elibrary_metrics': read_json(DATA / 'elibrary/metrics.json', {}), 'elibrary_profile_metrics': elib_profile, 'wos_profile_metrics': wos_profile, 'scopus_metrics': scopus_metrics, 'scientometrics': scientometrics, 'open_sources_report': read_json(DATA / 'open/harvest_report.json', {}), 'canonical_publications_count': len(canon), 'scopus_enriched_publications_count': sum(1 for p in canon if 'scopus' in p.get('sources', [])), 'scopus_auto_added_publications_count': scopus_added, 'open_sources_records_count': len(open_records), 'open_sources_enriched_publications_count': open_enriched, 'open_sources_auto_added_publications_count': open_added, 'wos_records_count': len(wos_records), 'wos_enriched_publications_count': wos_enriched, 'wos_auto_added_publications_count': wos_added, 'admin_queue_size': 0}
    (PUBLIC / 'profile.json').write_text(json.dumps(public_profile, ensure_ascii=False, indent=2), encoding='utf-8')
    (PUBLIC / 'publications.json').write_text(json.dumps(canon, ensure_ascii=False, indent=2), encoding='utf-8')
    write_tsv(canon); empty_queue()
    print(f'Built public data: {len(canon)} canonical publications; queue disabled')


if __name__ == '__main__':
    main()
