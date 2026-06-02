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
WAIT_SEC = int(os.environ.get('WOS_BROWSER_WAIT_SEC', '90'))


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
    return ('wat-author-metric' in html or 'summary-item' in html) and ('Web of Science' in html or 'app-record' in html)


def fetch_live() -> tuple[str | None, dict]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return None, {'status': 'playwright_import_failed', 'error': repr(exc)}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-dev-shm-usage', '--no-sandbox'])
        context = browser.new_context(locale='en-US', timezone_id='Europe/Moscow', viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        report = {'status': 'started', 'url': URL}
        try:
            page.goto(URL, wait_until='domcontentloaded', timeout=max(WAIT_SEC, 45) * 1000)
            elapsed = 0
            html = ''
            while elapsed < WAIT_SEC:
                page.wait_for_timeout(3000)
                elapsed += 3
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
    html, report = fetch_live()
    report['generated_at'] = now()
    if html and has_wos_payload(html):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        snapshot = SNAPSHOT_DIR / f'author_profile_{RESEARCHER_ID}_{stamp}.html'
        snapshot.write_text(html, encoding='utf-8')
        data = parse_wos_author_profile_html(html, RESEARCHER_ID)
        report['used_source'] = 'live_wos_free_view'
        report['snapshot_path'] = str(snapshot)
    else:
        snapshot = latest_snapshot()
        if snapshot:
            data = parse_file(str(snapshot), RESEARCHER_ID)
            report['used_source'] = 'saved_snapshot'
            report['snapshot_path'] = str(snapshot)
        elif OUT.exists():
            data = json.loads(OUT.read_text(encoding='utf-8'))
            report['used_source'] = 'previous_normalized_json'
        else:
            report['used_source'] = 'none'
            report['error'] = 'No live Web of Science page, no saved snapshot and no previous normalized JSON.'
            write_json(REPORT, report)
            return 1
    write_json(OUT, data)
    write_json(REPORT, report)
    print(json.dumps({'out': str(OUT), 'used_source': report.get('used_source'), 'records': data.get('records_count_on_page')}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
