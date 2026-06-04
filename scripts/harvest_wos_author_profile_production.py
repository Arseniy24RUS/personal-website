#!/usr/bin/env python3
"""Production wrapper for the Web of Science harvester.

The base harvester keeps persistence and fallbacks. This wrapper hardens the WoS
records route in three ways:
1. It sends a direct WOSNX request that mirrors the successful browser HAR.
2. If that direct request fails with an expired SID, it opens the profile in
   Playwright and runs the WOSNX request inside the live browser context, using
   the fresh SID and cookies created by the page itself.
3. It prevents a weak/empty WoS response from overwriting previously known
   metrics or records.
"""
from __future__ import annotations

from urllib.parse import quote
import json
import os

import harvest_wos_author_profile as base

USER_AGENT = os.environ.get(
    'WOS_USER_AGENT',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 YaBrowser/26.4.0.0 Safari/537.36',
)


def records_count(data) -> int:
    records = (data or {}).get('records') if isinstance(data, dict) else None
    return len(records) if isinstance(records, list) else 0


def _metric_value(data, section: str, *labels) -> int:
    mapping = (data or {}).get(section) if isinstance(data, dict) else None
    if not isinstance(mapping, dict):
        return 0
    for label in labels:
        item = mapping.get(label)
        if isinstance(item, dict) and item.get('value') not in (None, ''):
            try:
                return int(item.get('value'))
            except Exception:
                pass
    lowered = {str(k).lower(): v for k, v in mapping.items()}
    for label in labels:
        needle = str(label).lower()
        for key, item in lowered.items():
            if needle in key and isinstance(item, dict) and item.get('value') not in (None, ''):
                try:
                    return int(item.get('value'))
                except Exception:
                    pass
    return 0


def summary_publications(data) -> int:
    if not isinstance(data, dict):
        return 0
    for value in [
        ((data.get('summary') or {}).get('publications') if isinstance(data.get('summary'), dict) else None),
        data.get('records_count_on_page'),
        _metric_value(data, 'core_collection_metrics', 'Publications'),
        _metric_value(data, 'summary_metrics', 'Web of Science Core Collection publications', 'Publications indexed in Web of Science'),
    ]:
        try:
            if value not in (None, ''):
                return int(value)
        except Exception:
            pass
    return 0


def normalized_count(data) -> int:
    return max(records_count(data), summary_publications(data))


def preserve_best_records(candidate, previous, report):
    if not candidate:
        return previous
    prev_records = records_count(previous)
    cand_records = records_count(candidate)
    prev_strength = normalized_count(previous)
    cand_strength = normalized_count(candidate)
    if prev_records and cand_records < prev_records:
        merged = dict(candidate)
        merged['records'] = previous.get('records') or []
        merged['records_count_on_page'] = len(merged['records'])
        merged['records_preserved_from_previous'] = True
        report['warning'] = 'Live WoS payload had fewer records than previous normalized data; previous records were preserved while fresh metrics were kept.'
        return merged
    if prev_strength and cand_strength < prev_strength:
        report['warning'] = 'Live WoS payload was weaker than previous normalized data; previous WoS data was kept.'
        return previous
    return candidate


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
        if name == 'WOSSID' and any(c.name == 'WOSSID' for c in session.cookies):
            continue
        for domain in ('www.webofscience.com', 'webofscience.com', 'www.webofknowledge.com'):
            session.cookies.set(name, value, domain=domain, path='/')
            count += 1
    return count


def cleaned_search_from_storage(state):
    search, hits, search_id = base.search_state_from_storage(state)
    if search:
        search = dict(search)
        search.pop('id', None)
    return search, hits, search_id


def fallback_search():
    return {
        'mode': 'author_publications',
        'database': 'WOS',
        'authorId': {'type': 'rid', 'value': base.RESEARCHER_ID},
        'display': {'key': 'author', 'icon': 'author', 'params': {'name': os.environ.get('WOS_AUTHOR_DISPLAY_NAME', '') or base.RESEARCHER_ID}},
        'searchOptions': {'collections': ['WOS'], 'publonCollections': [], 'nonIndexed': False},
        'analyzeConfig': 'profiles',
    }


def run_query_body(state=None, search_override=None, hits_override=None):
    search, hits, _search_id = cleaned_search_from_storage(state)
    if search_override:
        search = dict(search_override)
        search.pop('id', None)
        hits = hits_override or hits
    if not search:
        search = fallback_search()
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
        'input_state': {'cookie_secret_present': bool(base.WOS_COOKIE), 'storage_state_secret_present': bool(base.WOS_STORAGE_STATE_B64)},
    }
    try:
        import requests
    except Exception as exc:
        report.update({'status': 'requests_import_failed', 'error': repr(exc)})
        return None, report

    state = base.storage_state_from_secret()
    search, hits, search_id = cleaned_search_from_storage(state)
    if search_id:
        report['storage_search_id'] = search_id
        report['storage_search_hits'] = hits or {}
        report['storage_search_display_name'] = (((search or {}).get('display') or {}).get('params') or {}).get('name')

    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
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

    try:
        response = session.post(f'https://www.webofscience.com/api/wosnx/core/runQuerySearch?SID={quote(sid, safe="")}', data=body_text, timeout=60)
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
        report['records'] = records_count(data)
        report['records_or_publications'] = normalized_count(data)
        report['search_info'] = data.get('search_info') or {}
        report['status'] = 'ok' if records_count(data) else 'api_without_records'
        return data if records_count(data) else None, report
    except Exception as exc:
        report.update({'status': 'api_error', 'error': repr(exc)})
        return None, report


def cookie_header_to_playwright(raw: str) -> list[dict]:
    cookies = []
    for chunk in (raw or '').split(';'):
        if '=' not in chunk:
            continue
        name, value = chunk.split('=', 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        for domain in ['.webofscience.com', 'www.webofscience.com', '.webofknowledge.com', 'www.webofknowledge.com', '.clarivate.com']:
            cookies.append({'name': name, 'value': value, 'domain': domain, 'path': '/', 'secure': True, 'sameSite': 'Lax'})
    return cookies


def extract_browser_state(page):
    return page.evaluate(
        """({rid}) => {
          const result = {url: location.href, sid: null, sessionDataSid: null, search: null, hits: null, searchId: null};
          try { result.sessionDataSid = window.sessionData?.BasicProperties?.SID || window.sessionData?.Products?.Portal?.ProductProperties?.SID || null; } catch(e) {}
          try { result.sid = new URL(location.href).searchParams.get('SID') || result.sessionDataSid || JSON.parse(localStorage.getItem('wos_sid') || 'null'); } catch(e) { result.sid = result.sessionDataSid; }
          let best = null;
          for (let i = 0; i < localStorage.length; i++) {
            const name = localStorage.key(i);
            if (!name || !name.startsWith('wos_search_') || name.startsWith('wos_search_hits_')) continue;
            try {
              const search = JSON.parse(localStorage.getItem(name));
              if (!search || !search.authorId || search.authorId.value !== rid) continue;
              const id = search.id || name.replace('wos_search_', '');
              let hits = {};
              try { hits = JSON.parse(localStorage.getItem('wos_search_hits_' + id) || '{}'); } catch(e) {}
              const available = Number(hits.available || hits.found || 0);
              if (!best || available > best.available) best = {available, search, hits, id};
            } catch(e) {}
          }
          if (best) { result.search = best.search; result.hits = best.hits; result.searchId = best.id; }
          return result;
        }""",
        {'rid': base.RESEARCHER_ID},
    )


def browser_wosnx(previous):
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return None, {'status': 'playwright_import_failed', 'error': repr(exc)}, None

    report = {
        'route': 'browser_context_wosnx_fetch',
        'url': base.URL,
        'input_state': {'cookie_secret_present': bool(base.WOS_COOKIE), 'storage_state_secret_present': bool(base.WOS_STORAGE_STATE_B64)},
    }
    api_reports = []
    headless = os.environ.get('WOS_BROWSER_HEADLESS', 'false').lower() not in {'0', 'false', 'no'}
    channel = os.environ.get('WOS_BROWSER_CHANNEL', 'chrome').strip() or None

    with sync_playwright() as p:
        launch_kwargs = {'headless': headless, 'args': ['--disable-dev-shm-usage', '--no-sandbox']}
        if channel:
            launch_kwargs['channel'] = channel
        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception as exc:
            report['browser_launch_error'] = repr(exc)
            launch_kwargs.pop('channel', None)
            browser = p.chromium.launch(**launch_kwargs)
            report['channel_fallback'] = 'bundled_chromium'

        context_kwargs = {'locale': 'en-US', 'timezone_id': 'Europe/Moscow', 'user_agent': USER_AGENT, 'viewport': {'width': 1440, 'height': 1100}}
        state_path = base.storage_state_path_from_secret(report)
        if state_path:
            context_kwargs['storage_state'] = state_path
        context = browser.new_context(**context_kwargs)
        if base.WOS_COOKIE:
            try:
                cookies = cookie_header_to_playwright(base.WOS_COOKIE)
                context.add_cookies(cookies)
                report['input_state']['cookie_names'] = sorted({c['name'] for c in cookies})
                report['input_state']['cookie_domains_count'] = len(cookies)
            except Exception as exc:
                report['input_state']['cookie_add_error'] = repr(exc)

        page = context.new_page()
        try:
            page.goto(base.URL, wait_until='domcontentloaded', timeout=max(base.WAIT_SEC, 45) * 1000)
            html = ''
            best_data = None
            for elapsed in range(0, base.WAIT_SEC + 1, 3):
                if elapsed:
                    page.wait_for_timeout(3000)
                try:
                    page.mouse.wheel(0, 900)
                except Exception:
                    pass
                state_info = extract_browser_state(page)
                sid = state_info.get('sid')
                body = run_query_body(None, state_info.get('search'), state_info.get('hits'))
                if sid:
                    try:
                        fetch_result = page.evaluate(
                            """async ({sid, body}) => {
                              const res = await fetch('/api/wosnx/core/runQuerySearch?SID=' + encodeURIComponent(sid), {
                                method: 'POST', credentials: 'include',
                                headers: {'Accept': 'application/x-ndjson', 'Content-Type': 'text/plain;charset=UTF-8'},
                                body: JSON.stringify(body)
                              });
                              return {status: res.status, contentType: res.headers.get('content-type') || '', text: await res.text()};
                            }""",
                            {'sid': sid, 'body': body},
                        )
                        text = fetch_result.get('text') or ''
                        item = {
                            'elapsed_sec': elapsed,
                            'sid_present': True,
                            'search_id': state_info.get('searchId'),
                            'request_count': (body.get('retrieve') or {}).get('count'),
                            'status': fetch_result.get('status'),
                            'content_type': fetch_result.get('contentType'),
                            'bytes': len(text.encode('utf-8', errors='replace')),
                            'excerpt': text[:800],
                        }
                        data = base.carry_forward_metrics(base.parse_wosnx_ndjson(text, base.RESEARCHER_ID), previous)
                        item['records'] = records_count(data)
                        item['records_or_publications'] = normalized_count(data)
                        api_reports.append(item)
                        if records_count(data):
                            best_data = data
                            break
                    except Exception as exc:
                        api_reports.append({'elapsed_sec': elapsed, 'sid_present': True, 'error': repr(exc)})
                if not html:
                    try:
                        html = page.content()
                    except Exception:
                        html = ''
            if not html:
                try:
                    html = page.content()
                except Exception:
                    html = ''
            if best_data:
                report.update({'status': 'ok', 'records': records_count(best_data), 'records_or_publications': normalized_count(best_data), 'api_reports': api_reports[-12:], 'final_url': page.url})
                context.close(); browser.close()
                return html, report, best_data
            html_candidate = base.carry_forward_metrics(base.parse_wos_author_profile_html(html, base.RESEARCHER_ID), previous) if html else None
            report.update({'status': 'no_records', 'candidate_records': records_count(html_candidate), 'candidate_records_or_publications': normalized_count(html_candidate), 'api_reports': api_reports[-12:], 'final_url': page.url, 'content_length': len(html.encode('utf-8', errors='replace'))})
            context.close(); browser.close()
            return html, report, html_candidate
        except Exception as exc:
            try:
                html = page.content()
            except Exception:
                html = ''
            report.update({'status': 'error', 'error': repr(exc), 'api_reports': api_reports[-12:]})
            context.close(); browser.close()
            return html or None, report, None


def main() -> int:
    base.records_count = records_count
    base.summary_publications = summary_publications
    base.normalized_count = normalized_count
    base.preserve_best_records = preserve_best_records
    base.run_query_body = run_query_body
    base.fetch_direct_wosnx = direct_wosnx
    base.fetch_live_browser = browser_wosnx
    return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
