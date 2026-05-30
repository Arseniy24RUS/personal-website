#!/usr/bin/env python3
"""Harvest open bibliographic sources for a static scientist portfolio.

Inputs:
  config/profile.yml with identifiers.orcid and optional display names.

Outputs:
  data/open/orcid_works.json
  data/open/openalex_author.json
  data/open/openalex_works.json
  data/open/crossref_works.json
  data/open/open_publications.json
  data/open/harvest_report.json

The script is deliberately best-effort: every source is saved independently and
one failing provider must not break the whole GitHub Pages refresh workflow.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode, quote
import json
import os
import re
import time
import urllib.request
import urllib.error

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path('.')
OUT = ROOT / 'data' / 'open'
OUT.mkdir(parents=True, exist_ok=True)
PROFILE = Path(os.environ.get('PROFILE_YAML', 'config/profile.yml'))
CONTACT = os.environ.get('OPENALEX_MAILTO', 'omnistat@yandex.ru')


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_profile():
    if not PROFILE.exists() or yaml is None:
        return {}
    return yaml.safe_load(PROFILE.read_text(encoding='utf-8')) or {}


def get_json(url, headers=None, timeout=45):
    headers = headers or {}
    headers.setdefault('User-Agent', 'scientist-portfolio-harvester/0.2 (mailto:omnistat@yandex.ru)')
    headers.setdefault('Accept', 'application/json')
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            return json.loads(raw), {'status': 'ok', 'http_status': resp.status, 'url': url}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:1200]
        return None, {'status': 'http_error', 'http_status': exc.code, 'url': url, 'error_excerpt': body}
    except Exception as exc:
        return None, {'status': 'error', 'url': url, 'error': repr(exc)}


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def normalize_title(s):
    return re.sub(r'\s+', ' ', (s or '').strip())


def doi_norm(doi):
    if not doi:
        return None
    doi = str(doi).strip()
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.I)
    return doi.lower() or None


def normalize_orcid_works(payload, orcid):
    out = []
    for group in (payload or {}).get('group', []) or []:
        summaries = group.get('work-summary') or []
        for w in summaries:
            title = (((w.get('title') or {}).get('title') or {}).get('value'))
            pdate = w.get('publication-date') or {}
            year = ((pdate.get('year') or {}).get('value'))
            ext = ((w.get('external-ids') or {}).get('external-id')) or []
            doi = None
            for e in ext:
                if (e.get('external-id-type') or '').lower() == 'doi':
                    doi = e.get('external-id-value')
                    break
            out.append({
                'source': 'orcid_public_api',
                'orcid': orcid,
                'title': normalize_title(title),
                'year': int(year) if str(year or '').isdigit() else None,
                'doi': doi_norm(doi),
                'type': w.get('type'),
                'url': (w.get('url') or {}).get('value'),
                'put_code': w.get('put-code'),
                'raw': w,
            })
    return out


def normalize_openalex_works(payload):
    out = []
    for w in (payload or {}).get('results', []) or []:
        loc = w.get('primary_location') or {}
        source = loc.get('source') or {}
        out.append({
            'source': 'openalex_api',
            'openalex_id': w.get('id'),
            'title': normalize_title(w.get('display_name')),
            'year': w.get('publication_year'),
            'doi': doi_norm(w.get('doi')),
            'url': w.get('id'),
            'landing_page_url': loc.get('landing_page_url'),
            'pdf_url': ((loc.get('pdf_url') or '') or None),
            'venue': source.get('display_name'),
            'cited_by_count': w.get('cited_by_count'),
            'is_oa': (w.get('open_access') or {}).get('is_oa'),
            'oa_status': (w.get('open_access') or {}).get('oa_status'),
            'raw': w,
        })
    return out


def normalize_crossref_works(payload):
    out = []
    for w in ((payload or {}).get('message') or {}).get('items', []) or []:
        title = (w.get('title') or [None])[0]
        pub = (w.get('container-title') or [None])[0]
        year = None
        for key in ['published-print', 'published-online', 'published', 'created']:
            parts = (((w.get(key) or {}).get('date-parts') or [[None]])[0])
            if parts and parts[0]:
                year = parts[0]
                break
        out.append({
            'source': 'crossref_api',
            'title': normalize_title(title),
            'year': year,
            'doi': doi_norm(w.get('DOI')),
            'url': w.get('URL'),
            'venue': pub,
            'type': w.get('type'),
            'publisher': w.get('publisher'),
            'is_referenced_by_count': w.get('is-referenced-by-count'),
            'raw': w,
        })
    return out


def main():
    profile = read_profile()
    ids = ((profile.get('profile') or {}).get('identifiers') or {}) if profile else {}
    orcid = ids.get('orcid') or os.environ.get('ORCID_ID')
    report = {'generated_at': now(), 'providers': {}}
    all_records = []

    if orcid:
        url = f'https://pub.orcid.org/v3.0/{orcid}/works'
        payload, rep = get_json(url, {'Accept': 'application/json'})
        report['providers']['orcid'] = rep
        if payload:
            save(OUT / 'orcid_works.json', payload)
            all_records.extend(normalize_orcid_works(payload, orcid))

        # OpenAlex author by ORCID: try ORCID singleton URL first, then works filter.
        oa_author_url = 'https://api.openalex.org/authors/' + quote('https://orcid.org/' + orcid, safe='') + '?' + urlencode({'mailto': CONTACT})
        oa_author, rep = get_json(oa_author_url)
        report['providers']['openalex_author'] = rep
        if oa_author:
            save(OUT / 'openalex_author.json', oa_author)
            openalex_author_id = oa_author.get('id')
            if openalex_author_id:
                filt = 'authorships.author.id:' + openalex_author_id
                oa_works_url = 'https://api.openalex.org/works?' + urlencode({'filter': filt, 'per-page': 200, 'sort': 'publication_date:desc', 'mailto': CONTACT})
                oa_works, rep2 = get_json(oa_works_url)
                report['providers']['openalex_works'] = rep2
                if oa_works:
                    save(OUT / 'openalex_works.json', oa_works)
                    all_records.extend(normalize_openalex_works(oa_works))
        else:
            filt = 'authorships.author.orcid:' + orcid
            oa_works_url = 'https://api.openalex.org/works?' + urlencode({'filter': filt, 'per-page': 200, 'sort': 'publication_date:desc', 'mailto': CONTACT})
            oa_works, rep2 = get_json(oa_works_url)
            report['providers']['openalex_works'] = rep2
            if oa_works:
                save(OUT / 'openalex_works.json', oa_works)
                all_records.extend(normalize_openalex_works(oa_works))

        cr_url = 'https://api.crossref.org/works?' + urlencode({'filter': 'orcid:' + orcid, 'rows': 100, 'sort': 'published', 'order': 'desc', 'mailto': CONTACT})
        cr, rep = get_json(cr_url)
        report['providers']['crossref'] = rep
        if cr:
            save(OUT / 'crossref_works.json', cr)
            all_records.extend(normalize_crossref_works(cr))

    # lightweight dedupe inside open-source pool
    deduped = []
    seen = set()
    for r in all_records:
        key = ('doi', r.get('doi')) if r.get('doi') else ('title_year', (normalize_title(r.get('title')).lower(), r.get('year')))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    save(OUT / 'open_publications.json', {'generated_at': now(), 'records': deduped})
    report['records_total_before_dedupe'] = len(all_records)
    report['records_total_after_dedupe'] = len(deduped)
    save(OUT / 'harvest_report.json', report)
    print(json.dumps({'open_records': len(deduped), 'providers': report['providers']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
