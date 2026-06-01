#!/usr/bin/env python3
"""Browser-based eLibrary harvester for delayed/JS-loaded public pages.

The ordinary urllib fetcher is intentionally kept as a cheap first/fallback
mechanism, but eLibrary can return a short intermediate loading page before the
real author profile/list appears. This script uses headless Chromium through
Playwright, waits for the real markers and then saves the same normalized JSON
outputs as the ordinary harvesters.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_elibrary_author_profile import parse_elibrary_author_profile_html  # noqa: E402
from parse_elibrary_author_items import parse_elibrary_author_items  # noqa: E402

AUTHOR_ID = os.environ.get('ELIBRARY_AUTHOR_ID', '1012909')
PROFILE_URL = os.environ.get('ELIBRARY_PROFILE_URL', f'https://www.elibrary.ru/author_profile.asp?id={AUTHOR_ID}')
ITEMS_URL = os.environ.get('ELIBRARY_ITEMS_URL', f'https://www.elibrary.ru/author_items.asp?authorid={AUTHOR_ID}&pubrole=100&show_refs=1&pubcat=risc')
PROFILE_OUT = Path(os.environ.get('ELIBRARY_PROFILE_OUT', 'data/elibrary/profile_metrics.json'))
ITEMS_OUT = Path(os.environ.get('ELIBRARY_ITEMS_OUT', 'data/processed/elibrary_publications.json'))
PROFILE_SNAPSHOT_DIR = Path(os.environ.get('ELIBRARY_PROFILE_SNAPSHOT_DIR', 'data/snapshots/elibrary/profile'))
ITEMS_SNAPSHOT_DIR = Path(os.environ.get('ELIBRARY_ITEMS_SNAPSHOT_DIR', 'data/snapshots/elibrary/items'))
REPORT = Path(os.environ.get('ELIBRARY_BROWSER_REPORT', 'data/elibrary/browser_fetch_report.json'))
WAIT_SEC = int(os.environ.get('ELIBRARY_BROWSER_WAIT_SEC', '95'))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def markers_for(kind: str) -> list[str]:
    if kind == 'profile':
        return ['ОБЩИЕ ПОКАЗАТЕЛИ', 'Индекс Хирша']
    return ['author_items', 'arw']


def has_markers(html: str, kind: str) -> bool:
    return all(marker in html for marker in markers_for(kind))


def fingerprint(html: str) -> dict:
    lowered = html.lower()
    return {
        'content_length': len(html.encode('utf-8', errors='replace')),
        'has_suspicious_ip_text': 'подозр' in lowered or 'suspicious' in lowered or 'ip_blocked' in lowered,
        'has_cookie_text': 'cookie' in lowered or 'cookies' in lowered,
        'excerpt': html[:700].replace('\n', ' '),
    }


def wait_for_real_page(page, url: str, kind: str) -> tuple[str, dict]:
    started = time.time()
    report = {'url': url, 'kind': kind, 'status': 'started'}
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=max(WAIT_SEC, 45) * 1000)
    except Exception as exc:
        report['goto_error'] = repr(exc)
    last_html = ''
    deadline = time.time() + WAIT_SEC
    while time.time() < deadline:
        try:
            # eLibrary often shows a short loader first; allow client-side JS and
            # redirects to finish. Reload once if the loader persists too long.
            page.wait_for_timeout(2000)
            last_html = page.content()
            if has_markers(last_html, kind):
                report.update({
                    'status': 'ready',
                    'elapsed_sec': round(time.time() - started, 3),
                    'final_url': page.url,
                    'title': page.title(),
                    'fingerprint': fingerprint(last_html),
                })
                return last_html, report
            if 20 < time.time() - started < 24:
                try:
                    page.reload(wait_until='domcontentloaded', timeout=45000)
                except Exception as exc:
                    report.setdefault('reload_errors', []).append(repr(exc))
        except Exception as exc:
            report.setdefault('loop_errors', []).append(repr(exc))
    report.update({
        'status': 'timeout_or_unready',
        'elapsed_sec': round(time.time() - started, 3),
        'final_url': getattr(page, 'url', ''),
        'fingerprint': fingerprint(last_html or ''),
    })
    return last_html, report


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        write_json(REPORT, {'generated_at': now(), 'status': 'playwright_import_failed', 'error': repr(exc)})
        print(f'Playwright import failed: {exc!r}', file=sys.stderr)
        return 1

    PROFILE_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ITEMS_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    report = {'generated_at': now(), 'wait_sec': WAIT_SEC, 'pages': {}}
    ok_profile = ok_items = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-dev-shm-usage', '--no-sandbox'])
        context = browser.new_context(
            locale='ru-RU',
            timezone_id='Europe/Moscow',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
            viewport={'width': 1366, 'height': 900},
        )
        page = context.new_page()
        try:
            page.goto(os.environ.get('ELIBRARY_PREFLIGHT_URL', 'https://www.elibrary.ru/defaultx.asp'), wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(5000)
        except Exception as exc:
            report['preflight_error'] = repr(exc)

        profile_html, profile_report = wait_for_real_page(page, PROFILE_URL, 'profile')
        report['pages']['profile'] = profile_report
        if has_markers(profile_html, 'profile'):
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            snapshot = PROFILE_SNAPSHOT_DIR / f'author_profile_{AUTHOR_ID}_{stamp}_browser.html'
            snapshot.write_text(profile_html, encoding='utf-8')
            data = parse_elibrary_author_profile_html(profile_html)
            PROFILE_OUT.parent.mkdir(parents=True, exist_ok=True)
            write_json(PROFILE_OUT, data)
            report['pages']['profile']['used_source'] = 'browser_live_elibrary'
            report['pages']['profile']['snapshot_path'] = str(snapshot)
            ok_profile = True

        items_html, items_report = wait_for_real_page(page, ITEMS_URL, 'items')
        report['pages']['items'] = items_report
        if has_markers(items_html, 'items'):
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            snapshot = ITEMS_SNAPSHOT_DIR / f'author_items_{AUTHOR_ID}_{stamp}_browser.html'
            snapshot.write_text(items_html, encoding='utf-8')
            data = parse_elibrary_author_items(str(snapshot))
            ITEMS_OUT.parent.mkdir(parents=True, exist_ok=True)
            write_json(ITEMS_OUT, data)
            report['pages']['items']['used_source'] = 'browser_live_elibrary'
            report['pages']['items']['snapshot_path'] = str(snapshot)
            report['pages']['items']['parsed_records'] = len(data)
            ok_items = True
        context.close()
        browser.close()

    report['status'] = 'ok' if ok_profile and ok_items else 'partial_or_failed'
    write_json(REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok_profile and ok_items else 2


if __name__ == '__main__':
    raise SystemExit(main())
