#!/usr/bin/env python3
"""Production wrapper for the Web of Science harvester.

This wrapper keeps the browser fallback from harvest_wos_author_profile.py, but
replaces only the direct WOSNX request with a version that mirrors the successful
browser HAR more closely:
- reuse the saved author-publications search from storage_state;
- remove the transient localStorage search id from the request body;
- request 10 records, matching Free View;
- load cookies into a requests cookie jar instead of freezing a Cookie header;
- keep WOSSID aligned with the SID used in the WOSNX URL.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
import json
import os

import harvest_wos_author_profile as base


def add_storage_cookies(session, state) -> int:
    count = 0
    if not isinstance(state, dict):
        return 0
    for cookie in state.get('cookies') or []:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get('domain') or '')
        if not any(host in domain for host in ('webofscience.com', 'webofknowledge.com', 'clarivate.com')):
            continue
        name = cookie.get('name')
        value = cookie.get('value')
        if not name or value is None:
            continue
        session.cookies.set(str(name), str(value), domain=domain.lstrip('.'), path=cookie.get('path') or '/')
        count += 1
    return count


def add_cookie_header(session, raw: str) -> int:
    count = 0
    for chunk in (raw or '').split(';'):
        if '=' not in chunk:
            continue
        name, value = chunk.split('=', 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        # Do not overwrite WOSSID from storage_state; it is paired with wos_sid.
        if name == 'WOSSID' and any(c.name == 'WOSSID' for c in session.cookies):
            continue
        for domain in ('www.webofscience.com', 'webofscience.com', 'www.webofknowledge.com'):
            session.cookies.set(name, value, domain=domain, path='/')
            count += 1
    return count


def run_query_body(state):
    search, hits, search_id = base.search_state_from_storage(state)
    if search:
        search = dict(search)
        search.pop('id', None)
    else:
        search = {
            'mode': 'author_publications',
            'database': 'WOS',
            'authorId': {'type': 'rid', 'value': base.RESEARCHER_ID},
            'display': {'key': 'author', 'icon': 'author', 'params': {'name': os.environ.get('WOS_AUTHOR_DISPLAY_NAME', '') or base.RESEARCHER_ID}},
            'searchOptions': {'collections': ['WOS'], 'publonCollections': [], 'nonIndexed': False},
            'analyzeConfig': 'profiles',
        }
    try:
        available = int((hits or {}).get('available') or (hits or {}).get('found') or 0)
    except Exception:
        available = 0
    count = max(1, min(available or 10, 10))
    return {
        'product': 'WOS',
        'searchMode': 'author_publications',
        'viewType': 'search',
        'serviceMode': 'summary',
        'search': search,
        'retrieve': {
            'view': 'summary',
            'sort': 'date-descending',
            'jcr': True,
            'history': False,
            'count': count,
            'first': 1,
            'analyzes': ['TP.Value.6', 'OA.Value.6', 'EARLY ACCESS.Value.6', 'DR.Value.6', 'ECR.Value.6', 'DX2NG.Value.101'],
            'locale': 'en',
        },
        'eventMode': None,
    }


def direct_wosnx(previous):
    report = {
        'route': 'direct_wosnx_run_query_search_har_compatible',
        'input_state': {
            'cookie_secret_present': bool(base.WOS_COOKIE),
            'storage_state_secret_present': bool(base.WOS_STORAGE_STATE_B64),
        },
    }
    try:
        import requests
    except Exception as exc:
        report.update({'status': 'requests_import_failed', 'error': repr(exc)})
        return None, report

    state = base.storage_state_from_secret()
    search, hits, search_id = base.search_state_from_storage(state)
    if search_id:
        report['storage_search_id'] = search_id
        report['storage_search_hits'] = hits or {}
        report['storage_search_display_name'] = (((search or {}).get('display') or {}).get('params') or {}).get('name')

    session = requests.Session()
    session.headers.update({
        'User-Agent': os.environ.get('WOS_USER_AGENT', base.USER_AGENT if hasattr(base, 'USER_AGENT') else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 YaBrowser/26.4.0.0 Safari/537.36'),
        'Accept': 'application/x-ndjson',
        'Accept-Language': 'ru,en;q=0.9',
        'Origin': 'https://www.webofscience.com',
        'Referer': base.URL,
        'Content-Type': 'text/plain;charset=UTF-8',
    })
    report['cookies_from_storage_count'] = add_storage_cookies(session, state)
    report['cookies_from_secret_header_count'] = add_cookie_header(session, base.WOS_COOKIE)

    sid = base.sid_from_storage_state(state)
    try:
        bootstrap = session.get(base.URL, timeout=45, allow_redirects=True)
        text = bootstrap.text or ''
        report['bootstrap_status'] = bootstrap.status_code
        report['bootstrap_url'] = bootstrap.url
        report['bootstrap_bytes'] = len(text.encode('utf-8', errors='replace'))
        sid = base.extract_sid(text, bootstrap.url, state) or sid
        if sid:
            session.cookies.set('WOSSID', sid, domain='www.webofscience.com', path='/')
            session.cookies.set('WOSSID', sid, domain='webofscience.com', path='/')
        if bootstrap.status_code == 200 and 'window.sessionData' in text:
            base.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            snapshot = base.SNAPSHOT_DIR / f'author_profile_{base.RESEARCHER_ID}_{base.stamp()}_direct_bootstrap.html'
            snapshot.write_text(text, encoding='utf-8', errors='replace')
            report['bootstrap_snapshot_path'] = str(snapshot)
    except Exception as exc:
        report['bootstrap_error'] = repr(exc)

    if not sid:
        report['status'] = 'no_sid'
        return None, report

    body = run_query_body(state)
    body_text = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    report['sid_present'] = True
    report['request_count'] = (body.get('retrieve') or {}).get('count')
    report['request_display_name'] = (((body.get('search') or {}).get('display') or {}).get('params') or {}).get('name')
    report['request_author_id'] = (((body.get('search') or {}).get('authorId') or {}).get('value') if isinstance((body.get('search') or {}).get('authorId'), dict) else None)
    report['request_has_search_id'] = 'id' in (body.get('search') or {})
    report['request_body_bytes'] = len(body_text.encode('utf-8'))
    api_url = f'https://www.webofscience.com/api/wosnx/core/runQuerySearch?SID={quote(sid, safe="")}'

    try:
        response = session.post(api_url, data=body_text, timeout=60)
        text = response.text or ''
        report['status_code'] = response.status_code
        report['content_type'] = response.headers.get('content-type', '')
        report['bytes'] = len(text.encode('utf-8', errors='replace'))
        report['excerpt'] = text[:1200]
        base.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        ndjson_path = base.ARTIFACT_DIR / f'wos_run_query_search_{base.stamp()}.ndjson'
        ndjson_path.write_text(text, encoding='utf-8', errors='replace')
        report['ndjson_path'] = str(ndjson_path)
        if response.status_code != 200:
            report['status'] = 'api_http_error'
            return None, report
        data = base.carry_forward_metrics(base.parse_wosnx_ndjson(text, base.RESEARCHER_ID), previous)
        report['records'] = base.records_count(data)
        report['records_or_publications'] = base.normalized_count(data)
        report['search_info'] = data.get('search_info') or {}
        report['status'] = 'ok' if base.records_count(data) else 'api_without_records'
        return data if base.records_count(data) else None, report
    except Exception as exc:
        report.update({'status': 'api_error', 'error': repr(exc)})
        return None, report


def main() -> int:
    base.run_query_body = run_query_body
    base.fetch_direct_wosnx = direct_wosnx
    return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
