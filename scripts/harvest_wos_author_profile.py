#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_wos_author_profile import parse_wos_author_profile_html, parse_file  # noqa: E402

RESEARCHER_ID = os.environ.get('WOS_RESEARCHER_ID', 'AAG-1530-2021')
URL = os.environ.get('WOS_PROFILE_URL', f'https://www.webofscience.com/wos/author/record/{RESEARCHER_ID}')
OUT = Path(os.environ.get('WOS_PROFILE_OUT', 'data/wos/profile_metrics.json'))
REPORT = Path(os.environ.get('WOS_HARVEST_REPORT', 'data/wos/harvest_report.json'))
SNAPSHOT_DIR = Path(os.environ.get('WOS_SNAPSHOT_DIR', 'data/snapshots/wos'))
WAIT_SEC = int(os.environ.get('WOS_BROWSER_WAIT_SEC', '120'))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def latest_snapshot() -> Path | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob(f'author_profile_{RESEARCHER_ID}_*.html'))
    return files[-1] if files else None


def has_wos_payload(html: str) -> bool:
    text = html or ''
    return ('wat-author-metric' in text or 'summary-item' in text) and ('Web of Science' in text or 'app-record' in text)


def normalized_count(data: dict) -> int:
    if not isinstance(data, dict):
        return 0
    if isinstance(data.get('records'), list) and data['records']:
        return len(data['records'])
    if data.get('records_count_on_page'):
        return int(data.get('records_count_on_page') or 0)
    return int(((data.get('summary') or {}).get('publications')) or 0)


def fetch_live() -> tuple[str | None, dict]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return None, {'status': 'playwright_import_failed', 'error': repr(exc)}
    headless = os.environ.get('WOS_BROWSER_HEADLESS', 'true').lower() not in {'0', 'false', 'no'}
    ua = os.environ.get('WOS_USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=['--disable-dev-shm-usage', '--no-sandbox'])
        context = browser.new_context(locale='en-US', timezone_id='Europe/Moscow', user_agent=ua, viewport={'width': 1440, 'height': 1100})
        page = context.new_page()
        report = {'status': 'started', 'url': URL, 'headless': headless}
        try:
            page.goto(URL, wait_until='domcontentloaded', timeout=max(WAIT_SEC, 45) * 1000)
            elapsed = 0
            html = ''
            while elapsed < WAIT_SEC:
                page.wait_for_timeout(3000)
                elapsed += 3
                try:
                    page.mouse.wheel(0, 900)
                except Exception:
                    pass
                html = page.content()
                if has_wos_payload(html):
                    report.update({'status': 'ok', 'elapsed_sec': elapsed, 'final_url': page.url, 'title': page.title(), 'content_length': len(html.encode('utf-8', errors='replace'))})
                    context.close(); browser.close()
                    return html, report
            report.update({'status': 'timeout_or_unready', 'final_url': page.url, 'title': page.title(), 'content_length': len(html.encode('utf-8', errors='replace'))})
            context.close(); browser.close()
            return html, report
        except Exception as exc:
            try:
                html = page.content()
                report['content_length'] = len(html.encode('utf-8', errors='replace'))
            except Exception:
                html = ''
            report.update({'status': 'error', 'error': repr(exc)})
            context.close(); browser.close()
            return html or None, report


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else None
    previous_count = normalized_count(previous or {})
    html, report = fetch_live()
    report['generated_at'] = now()
    report['previous_records_or_publications'] = previous_count
    data = None
    if html and has_wos_payload(html):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        snapshot = SNAPSHOT_DIR / f'author_profile_{RESEARCHER_ID}_{stamp}.html'
        snapshot.write_text(html, encoding='utf-8')
        candidate = parse_wos_author_profile_html(html, RESEARCHER_ID)
        candidate_count = normalized_count(candidate)
        report['used_source'] = 'live_wos_free_view'
        report['snapshot_path'] = str(snapshot)
        report['candidate_records_or_publications'] = candidate_count
        data = candidate if candidate_count >= previous_count else previous
        if data is previous:
            report['warning'] = 'Live WoS payload was weaker than previous normalized data; previous data was kept.'
    else:
        snapshot = latest_snapshot()
        if snapshot:
            candidate = parse_file(str(snapshot), RESEARCHER_ID)
            candidate_count = normalized_count(candidate)
            report['used_source'] = 'saved_snapshot'
            report['snapshot_path'] = str(snapshot)
            report['candidate_records_or_publications'] = candidate_count
            data = candidate if candidate_count >= previous_count else previous
            if data is previous:
                report['warning'] = 'Saved WoS snapshot was weaker than previous normalized data; previous data was kept.'
        elif previous:
            data = previous
            report['used_source'] = 'previous_normalized_json'
        else:
            report['used_source'] = 'none'
            report['error'] = 'No live Web of Science page, no saved snapshot and no previous normalized JSON.'
            write_json(REPORT, report)
            return 1
    write_json(OUT, data)
    report['written_records_or_publications'] = normalized_count(data)
    write_json(REPORT, report)
    print(json.dumps({'out': str(OUT), 'used_source': report.get('used_source'), 'records_or_publications': normalized_count(data)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
