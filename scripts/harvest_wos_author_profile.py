#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote
import base64
import json
import os
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_wos_author_profile import parse_wos_author_profile_html, parse_wosnx_ndjson, parse_file  # noqa: E402

RESEARCHER_ID = os.environ.get('WOS_RESEARCHER_ID', 'AAG-1530-2021')
URL = os.environ.get('WOS_PROFILE_URL', f'https://www.webofscience.com/wos/author/record/{RESEARCHER_ID}')
OUT = Path(os.environ.get('WOS_PROFILE_OUT', 'data/wos/profile_metrics.json'))
REPORT = Path(os.environ.get('WOS_HARVEST_REPORT', 'data/wos/harvest_report.json'))
SNAPSHOT_DIR = Path(os.environ.get('WOS_SNAPSHOT_DIR', 'data/snapshots/wos'))
ARTIFACT_DIR = Path(os.environ.get('WOS_ARTIFACT_DIR', 'artifacts/wos_live'))
WAIT_SEC = int(os.environ.get('WOS_BROWSER_WAIT_SEC', '120'))
MIN_RECORDS = int(os.environ.get('WOS_MIN_RECORDS', '10'))
WOS_RECORDS_COUNT = int(os.environ.get('WOS_RECORDS_COUNT', '50'))
WOS_COOKIE = os.environ.get('WOS_COOKIE', '').strip()
WOS_STORAGE_STATE_B64 = os.environ.get('WOS_STORAGE_STATE_B64', '').strip()


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', errors='replace')
    return str(path)


def latest_snapshot() -> Path | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob(f'author_profile_{RESEARCHER_ID}_*.html'))
    return files[-1] if files else None


def has_wos_payload(html: str) -> bool:
    text = html or ''
    return ('wat-author-metric' in text or 'summary-item' in text or 'app-record' in text) and 'Web of Science' in text


def records_count(data: dict | None) -> int:
    if not isinstance(data, dict):
        return 0
    records = data.get('records')
    return len(records) if isinstance(records, list) else 0


def summary_publications(data: dict | None) -> int:
    if not isinstance(data, dict):
        return 0
    try:
        return int(((data.get('summary') or {}).get('publications')) or data.get('records_count_on_page') or 0)
    except Exception:
        return 0


def normalized_count(data: dict | None) -> int:
    return max(records_count(data), summary_publications(data))


def expected_min_records(data: dict | None) -> int:
    expected = summary_publications(data)
    if expected > 0:
        return max(1, min(expected, MIN_RECORDS))
    return max(1, MIN_RECORDS)


def run_query_body(count: int = WOS_RECORDS_COUNT, first: int = 1) -> dict:
    return {
        'product': 'WOS',
        'searchMode': 'author_publications',
        'viewType': 'search',
        'serviceMode': 'summary',
        'search': {
            'mode': 'author_publications',
            'database': 'WOS',
            'authorId': {'type': 'rid', 'value': RESEARCHER_ID},
            'display': {'key': 'author', 'icon': 'author', 'params': {'name': os.environ.get('WOS_AUTHOR_DISPLAY_NAME', '') or 'Author'}},
            'searchOptions': {'collections': ['WOS'], 'publonCollections': [], 'nonIndexed': False},
            'analyzeConfig': 'profiles',
        },
        'retrieve': {
            'view': 'summary',
            'sort': 'date-descending',
            'jcr': True,
            'history': False,
            'count': count,
            'first': first,
            'analyzes': ['TP.Value.6', 'OA.Value.6', 'EARLY ACCESS.Value.6', 'DR.Value.6', 'ECR.Value.6', 'DX2NG.Value.101'],
            'locale': 'en',
        },
        'eventMode': None,
    }


def storage_state_from_secret(report: dict | None = None) -> dict | None:
    if not WOS_STORAGE_STATE_B64:
        return None
    try:
        decoded = base64.b64decode(WOS_STORAGE_STATE_B64).decode('utf-8')
        data = json.loads(decoded)
        if report is not None:
            ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
            state_path = ARTIFACT_DIR / 'wos_input_storage_state.json'
            write_text(state_path, decoded)
            report.setdefault('input_state', {})['storage_state_secret_present'] = True
            report['input_state']['storage_state_path'] = str(state_path)
        return data
    except Exception as exc:
        if report is not None:
            report.setdefault('input_state', {})['storage_state_error'] = repr(exc)
        return None


def storage_state_path_from_secret(report: dict) -> str | None:
    data = storage_state_from_secret(report)
    if not data:
        return None
    return report.get('input_state', {}).get('storage_state_path')


def cookie_header_from_storage_state(state: dict | None) -> str:
    if not isinstance(state, dict):
        return ''
    cookies = []
    for cookie in state.get('cookies') or []:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get('domain') or '')
        if 'webofscience.com' not in domain and 'webofknowledge.com' not in domain and 'clarivate.com' not in domain:
            continue
        name = cookie.get('name')
        value = cookie.get('value')
        if name and value is not None:
            cookies.append(f'{name}={value}')
    return '; '.join(cookies)


def sid_from_storage_state(state: dict | None) -> str | None:
    if not isinstance(state, dict):
        return None
    for origin in state.get('origins') or []:
        if not isinstance(origin, dict):
            continue
        if 'webofscience.com' not in str(origin.get('origin') or ''):
            continue
        for item in origin.get('localStorage') or []:
            if item.get('name') != 'wos_sid':
                continue
            raw = item.get('value')
            try:
                sid = json.loads(raw)
            except Exception:
                sid = raw
            sid = str(sid or '').strip('"')
            if sid:
                return sid
    return None


def extract_sid(text: str | None = None, url: str | None = None, state: dict | None = None) -> str | None:
    for source in [url or '', text or '']:
        m = re.search(r'[?&]SID=([^&"\s]+)', source)
        if m:
            return m.group(1)
        m = re.search(r'"SID"\s*:\s*"([^"]+)"', source)
        if m:
            return m.group(1)
        m = re.search(r'"wos_sid"\s*:\s*"\\?"?([^"\\]+)', source)
        if m:
            return m.group(1)
    return sid_from_storage_state(state)


def carry_forward_metrics(candidate: dict, previous: dict | None) -> dict:
    if not isinstance(previous, dict):
        candidate.setdefault('summary', {})
        return candidate
    for key in ['summary', 'summary_metrics', 'core_collection_metrics', 'page_title', 'source_url', 'researcher_id']:
        if candidate.get(key) in (None, '', {}, []):
            value = previous.get(key)
            if value not in (None, '', {}, []):
                candidate[key] = value
    if not candidate.get('summary'):
        candidate['summary'] = previous.get('summary') or {}
    return candidate


def fetch_direct_wosnx(previous: dict | None) -> tuple[dict | None, dict]:
    report = {
        'route': 'direct_wosnx_run_query_search',
        'input_state': {'cookie_secret_present': bool(WOS_COOKIE), 'storage_state_secret_present': bool(WOS_STORAGE_STATE_B64)},
    }
    try:
        import requests
    except Exception as exc:
        report['status'] = 'requests_import_failed'
        report['error'] = repr(exc)
        return None, report

    state = storage_state_from_secret()
    cookie_header = WOS_COOKIE or cookie_header_from_storage_state(state)
    headers = {
        'User-Agent': os.environ.get('WOS_USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 YaBrowser/26.4.0.0 Safari/537.36'),
        'Accept': 'application/x-ndjson',
        'Accept-Language': 'ru,en;q=0.9',
        'Origin': 'https://www.webofscience.com',
        'Referer': URL,
        'Content-Type': 'text/plain;charset=UTF-8',
    }
    if cookie_header:
        headers['Cookie'] = cookie_header
    session = requests.Session()
    session.headers.update(headers)

    sid = sid_from_storage_state(state)
    try:
        get_res = session.get(URL, timeout=45, allow_redirects=True)
        report['bootstrap_status'] = get_res.status_code
        report['bootstrap_url'] = get_res.url
        report['bootstrap_bytes'] = len((get_res.text or '').encode('utf-8', errors='replace'))
        sid = extract_sid(get_res.text, get_res.url, state) or sid
        # Preserve a diagnostically useful HTML snapshot when the bootstrap response is a real WoS page.
        if get_res.status_code == 200 and 'Web of Science' in (get_res.text or ''):
            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            snap = SNAPSHOT_DIR / f'author_profile_{RESEARCHER_ID}_{stamp()}_direct_bootstrap.html'
            snap.write_text(get_res.text, encoding='utf-8', errors='replace')
            report['bootstrap_snapshot_path'] = str(snap)
    except Exception as exc:
        report['bootstrap_error'] = repr(exc)

    if not sid:
        report['status'] = 'no_sid'
        return None, report
    report['sid_present'] = True
    body = run_query_body()
    api_url = f'https://www.webofscience.com/api/wosnx/core/runQuerySearch?SID={quote(sid, safe="")}'
    try:
        res = session.post(api_url, data=json.dumps(body, ensure_ascii=False), timeout=60)
        text = res.text or ''
        report['status_code'] = res.status_code
        report['content_type'] = res.headers.get('content-type', '')
        report['bytes'] = len(text.encode('utf-8', errors='replace'))
        if res.status_code != 200:
            report['status'] = 'api_http_error'
            report['excerpt'] = text[:600]
            return None, report
        data = parse_wosnx_ndjson(text, RESEARCHER_ID)
        data = carry_forward_metrics(data, previous)
        report['records'] = records_count(data)
        report['records_or_publications'] = normalized_count(data)
        report['search_info'] = data.get('search_info') or {}
        report['status'] = 'ok' if records_count(data) else 'api_without_records'
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        ndjson_path = ARTIFACT_DIR / f'wos_run_query_search_{stamp()}.ndjson'
        ndjson_path.write_text(text, encoding='utf-8', errors='replace')
        report['ndjson_path'] = str(ndjson_path)
        return data if records_count(data) else None, report
    except Exception as exc:
        report['status'] = 'api_error'
        report['error'] = repr(exc)
        return None, report


def combine_html_and_wosnx(html_data: dict | None, api_data: dict | None) -> dict | None:
    if html_data and api_data and records_count(api_data) >= records_count(html_data):
        combined = dict(html_data)
        combined['source'] = 'web_of_science_live_combined_html_and_wosnx'
        combined['records'] = api_data.get('records') or []
        combined['records_count_on_page'] = len(combined['records'])
        combined['wosnx_search_info'] = api_data.get('search_info') or {}
        combined['wosnx_analyze'] = api_data.get('analyze') or {}
        combined['wosnx_jcr'] = api_data.get('jcr') or {}
        combined['generated_at'] = now()
        return combined
    return html_data or api_data


def preserve_best_records(candidate: dict | None, previous: dict | None, report: dict) -> dict | None:
    if not candidate:
        return previous
    prev_count = records_count(previous)
    cand_count = records_count(candidate)
    if prev_count and cand_count < prev_count:
        merged = dict(candidate)
        merged['records'] = previous.get('records') or []
        merged['records_count_on_page'] = len(merged['records'])
        merged['records_preserved_from_previous'] = True
        report['warning'] = 'Live WoS payload had fewer records than previous normalized data; previous records were preserved while fresh metrics were kept.'
        return merged
    return candidate


def cookie_header_to_playwright(raw: str) -> list[dict]:
    cookies = []
    domains = ['.webofscience.com', 'www.webofscience.com', '.webofknowledge.com', 'www.webofknowledge.com', '.clarivate.com']
    for chunk in raw.split(';'):
        if '=' not in chunk:
            continue
        name, value = chunk.split('=', 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        for domain in domains:
            cookies.append({'name': name, 'value': value, 'domain': domain, 'path': '/', 'secure': True, 'sameSite': 'Lax'})
    return cookies


def fetch_live_browser() -> tuple[str | None, dict, dict | None]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return None, {'status': 'playwright_import_failed', 'error': repr(exc)}, None

    headless = os.environ.get('WOS_BROWSER_HEADLESS', 'true').lower() not in {'0', 'false', 'no'}
    channel = os.environ.get('WOS_BROWSER_CHANNEL', '').strip() or None
    ua = os.environ.get('WOS_USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 YaBrowser/26.4.0.0 Safari/537.36')
    api_candidates: list[dict] = []
    api_reports: list[dict] = []

    def capture_wosnx_response(resp):
        url = resp.url
        if '/api/wosnx/core/runQuerySearch' not in url:
            return
        item = {'url': url, 'status': resp.status, 'content_type': resp.headers.get('content-type', '')}
        try:
            text = resp.text()
            item['text_bytes'] = len(text.encode('utf-8', errors='replace'))
            if resp.status == 200 and ('application/x-ndjson' in item['content_type'] or 'json' in item['content_type'] or text.startswith('{')):
                data = parse_wosnx_ndjson(text, RESEARCHER_ID)
                item['records'] = records_count(data)
                item['search_info'] = data.get('search_info') or {}
                if records_count(data):
                    api_candidates.append(data)
        except Exception as exc:
            item['error'] = repr(exc)
        api_reports.append(item)

    with sync_playwright() as p:
        launch_kwargs = {'headless': headless, 'args': ['--disable-dev-shm-usage', '--no-sandbox']}
        if channel:
            launch_kwargs['channel'] = channel
        report = {
            'status': 'started',
            'url': URL,
            'headless': headless,
            'channel': channel,
            'input_state': {'cookie_secret_present': bool(WOS_COOKIE), 'storage_state_secret_present': bool(WOS_STORAGE_STATE_B64)},
        }
        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception as exc:
            report['browser_launch_error'] = repr(exc)
            launch_kwargs.pop('channel', None)
            browser = p.chromium.launch(**launch_kwargs)
            report['channel_fallback'] = 'bundled_chromium'
        state_path = storage_state_path_from_secret(report)
        context_kwargs = {'locale': 'en-US', 'timezone_id': 'Europe/Moscow', 'user_agent': ua, 'viewport': {'width': 1440, 'height': 1100}}
        if state_path:
            context_kwargs['storage_state'] = state_path
        context = browser.new_context(**context_kwargs)
        if WOS_COOKIE:
            try:
                cookies = cookie_header_to_playwright(WOS_COOKIE)
                context.add_cookies(cookies)
                report['input_state']['cookie_names'] = sorted({c['name'] for c in cookies})
                report['input_state']['cookie_domains_count'] = len(cookies)
            except Exception as exc:
                report['input_state']['cookie_add_error'] = repr(exc)
        page = context.new_page()
        page.on('response', capture_wosnx_response)
        try:
            page.goto(URL, wait_until='domcontentloaded', timeout=max(WAIT_SEC, 45) * 1000)
            elapsed = 0
            html = ''
            best = None
            # If WoS lands on the old transfer URL, force the actual Angular route once more.
            if 'mode=Nextgen' in page.url or '/wos/?' in page.url:
                try:
                    page.goto(f'https://www.webofscience.com/wos/author/record/{RESEARCHER_ID}/author_profile_page/claimed', wait_until='domcontentloaded', timeout=45000)
                except Exception:
                    pass
            while elapsed < WAIT_SEC:
                page.wait_for_timeout(3000)
                elapsed += 3
                try:
                    page.mouse.wheel(0, 900)
                except Exception:
                    pass
                html = page.content()
                html_candidate = parse_wos_author_profile_html(html, RESEARCHER_ID)
                api_candidate = max(api_candidates, key=records_count) if api_candidates else None
                best = combine_html_and_wosnx(html_candidate, api_candidate)
                report['candidate_records'] = records_count(best)
                report['candidate_records_or_publications'] = normalized_count(best)
                if records_count(best) >= expected_min_records(best):
                    report.update({'status': 'ok', 'elapsed_sec': elapsed, 'final_url': page.url, 'title': page.title(), 'content_length': len(html.encode('utf-8', errors='replace')), 'api_reports': api_reports[-12:]})
                    context.close(); browser.close()
                    return html, report, best
            report.update({'status': 'timeout_or_unready', 'final_url': page.url, 'title': page.title(), 'content_length': len(html.encode('utf-8', errors='replace')), 'api_reports': api_reports[-12:]})
            context.close(); browser.close()
            return html, report, best
        except Exception as exc:
            try:
                html = page.content()
                report['content_length'] = len(html.encode('utf-8', errors='replace'))
            except Exception:
                html = ''
            api_candidate = max(api_candidates, key=records_count) if api_candidates else None
            html_candidate = parse_wos_author_profile_html(html, RESEARCHER_ID) if html else None
            best = combine_html_and_wosnx(html_candidate, api_candidate)
            report.update({'status': 'error', 'error': repr(exc), 'api_reports': api_reports[-12:]})
            context.close(); browser.close()
            return html or None, report, best


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    previous = read_json(OUT, None)
    report: dict = {'generated_at': now(), 'previous_records': records_count(previous), 'previous_records_or_publications': normalized_count(previous)}

    direct_data, direct_report = fetch_direct_wosnx(previous)
    report['direct_wosnx'] = direct_report
    data = None
    html = None

    if direct_data and records_count(direct_data) >= expected_min_records(previous or direct_data):
        report['used_source'] = 'direct_wosnx_run_query_search'
        data = preserve_best_records(direct_data, previous, report)
    else:
        html, browser_report, live_data = fetch_live_browser()
        report['browser'] = browser_report
        if live_data and records_count(live_data):
            if html and has_wos_payload(html):
                snapshot = SNAPSHOT_DIR / f'author_profile_{RESEARCHER_ID}_{stamp()}.html'
                snapshot.write_text(html, encoding='utf-8')
                report['snapshot_path'] = str(snapshot)
            report['used_source'] = live_data.get('source') or 'live_wos_free_view'
            data = preserve_best_records(carry_forward_metrics(live_data, previous), previous, report)
        elif html and has_wos_payload(html):
            snapshot = SNAPSHOT_DIR / f'author_profile_{RESEARCHER_ID}_{stamp()}.html'
            snapshot.write_text(html, encoding='utf-8')
            candidate = carry_forward_metrics(parse_wos_author_profile_html(html, RESEARCHER_ID), previous)
            report['used_source'] = 'live_wos_free_view_html_only'
            report['snapshot_path'] = str(snapshot)
            report['candidate_records'] = records_count(candidate)
            report['candidate_records_or_publications'] = normalized_count(candidate)
            data = preserve_best_records(candidate, previous, report)
        else:
            snapshot = latest_snapshot()
            if snapshot:
                candidate = carry_forward_metrics(parse_file(str(snapshot), RESEARCHER_ID), previous)
                report['used_source'] = 'saved_snapshot'
                report['snapshot_path'] = str(snapshot)
                report['candidate_records'] = records_count(candidate)
                report['candidate_records_or_publications'] = normalized_count(candidate)
                data = preserve_best_records(candidate, previous, report)
            elif previous:
                data = previous
                report['used_source'] = 'previous_normalized_json'
            else:
                report['used_source'] = 'none'
                report['error'] = 'No live Web of Science page, no saved snapshot and no previous normalized JSON.'
                write_json(REPORT, report)
                return 1

    write_json(OUT, data)
    report['written_records'] = records_count(data)
    report['written_records_or_publications'] = normalized_count(data)
    write_json(REPORT, report)
    print(json.dumps({'out': str(OUT), 'used_source': report.get('used_source'), 'records': records_count(data), 'records_or_publications': normalized_count(data), 'input_state': (report.get('direct_wosnx') or report.get('browser') or {}).get('input_state')}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
