#!/usr/bin/env python3
"""Browser-based eLibrary harvester for delayed/JS-loaded public pages.

The ordinary urllib fetcher is intentionally kept as a cheap first/fallback
mechanism, but eLibrary can return a short intermediate loading page before the
real author profile/list appears. This script uses headless Chromium through
Playwright, waits for the real markers and then saves the same normalized JSON
outputs as the ordinary harvesters.

The author publication list is tried through several legitimate navigation
patterns: links discovered on the author profile, a minimal public
``author_items.asp?authorid=...`` URL, and the configured URL. This avoids
relying on one deep URL that can trigger an intermediate anti-robot page.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin
import json
import os
import re
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
DEBUG_DIR = Path(os.environ.get('ELIBRARY_DEBUG_DIR', 'artifacts/elibrary_debug'))
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


def has_captcha(html: str, url: str = '') -> bool:
    lowered = (html or '').lower()
    return (
        'page_captcha' in (url or '').lower()
        or 'тест тьюринга' in lowered
        or 'recaptcha' in lowered
        or 'g-recaptcha' in lowered
        or 'www.google.com/recaptcha' in lowered
    )


def fingerprint(html: str, url: str = '') -> dict:
    lowered = html.lower()
    return {
        'content_length': len(html.encode('utf-8', errors='replace')),
        'has_suspicious_ip_text': 'подозр' in lowered or 'suspicious' in lowered or 'ip_blocked' in lowered,
        'has_cookie_text': 'cookie' in lowered or 'cookies' in lowered,
        'has_captcha_text': has_captcha(html, url),
        'excerpt': html[:900].replace('\n', ' '),
    }


def save_debug(page, html: str, name: str) -> dict:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    base = DEBUG_DIR / f'{stamp}_{name}'
    html_path = base.with_suffix('.html')
    png_path = base.with_suffix('.png')
    html_path.write_text(html or '', encoding='utf-8')
    screenshot_ok = False
    try:
        page.screenshot(path=str(png_path), full_page=True)
        screenshot_ok = True
    except Exception:
        pass
    return {'html_path': str(html_path), 'screenshot_path': str(png_path) if screenshot_ok else None}


def wait_current_page(page, kind: str, *, started: float | None = None) -> tuple[str, dict]:
    started = started or time.time()
    report = {'kind': kind, 'status': 'started'}
    last_html = ''
    deadline = time.time() + WAIT_SEC
    while time.time() < deadline:
        try:
            page.wait_for_timeout(2000)
            last_html = page.content()
            current_url = getattr(page, 'url', '')
            if has_markers(last_html, kind):
                report.update({
                    'status': 'ready',
                    'elapsed_sec': round(time.time() - started, 3),
                    'final_url': current_url,
                    'title': page.title(),
                    'fingerprint': fingerprint(last_html, current_url),
                })
                return last_html, report
            if has_captcha(last_html, current_url):
                report.update({
                    'status': 'captcha',
                    'elapsed_sec': round(time.time() - started, 3),
                    'final_url': current_url,
                    'title': page.title(),
                    'fingerprint': fingerprint(last_html, current_url),
                })
                return last_html, report
            if 20 < time.time() - started < 24:
                try:
                    page.reload(wait_until='domcontentloaded', timeout=45000)
                except Exception as exc:
                    report.setdefault('reload_errors', []).append(repr(exc))
        except Exception as exc:
            report.setdefault('loop_errors', []).append(repr(exc))
    final_url = getattr(page, 'url', '')
    report.update({
        'status': 'timeout_or_unready',
        'elapsed_sec': round(time.time() - started, 3),
        'final_url': final_url,
        'fingerprint': fingerprint(last_html or '', final_url),
    })
    return last_html, report


def load_page(page, url: str, kind: str, *, referer: str | None = None) -> tuple[str, dict]:
    started = time.time()
    report = {'url': url, 'kind': kind, 'status': 'started'}
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=max(WAIT_SEC, 45) * 1000, referer=referer)
    except TypeError:
        # Older Playwright versions do not expose referer in Python; the normal
        # context still keeps cookies and the target can be loaded directly.
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=max(WAIT_SEC, 45) * 1000)
        except Exception as exc:
            report['goto_error'] = repr(exc)
    except Exception as exc:
        report['goto_error'] = repr(exc)
    html, wait_report = wait_current_page(page, kind, started=started)
    report.update(wait_report)
    report.setdefault('url', url)
    return html, report


def author_item_candidates(profile_page) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()

    def add(url: str, source: str, text: str = '') -> None:
        if not url:
            return
        absolute = urljoin('https://www.elibrary.ru/', url)
        if absolute in seen:
            return
        seen.add(absolute)
        candidates.append({'url': absolute, 'source': source, 'text': text[:120]})

    try:
        links = profile_page.eval_on_selector_all(
            'a[href*="author_items.asp"]',
            "els => els.map(a => ({href: a.getAttribute('href') || '', text: a.innerText || ''}))",
        )
        for link in links:
            add(link.get('href') or '', 'profile_link', link.get('text') or '')
    except Exception:
        pass

    add(f'https://www.elibrary.ru/author_items.asp?authorid={AUTHOR_ID}', 'minimal_authorid')
    add(f'https://www.elibrary.ru/author_items.asp?authorid={AUTHOR_ID}&pubrole=100', 'authorid_pubrole')
    add(f'https://www.elibrary.ru/author_items.asp?authorid={AUTHOR_ID}&pubrole=100&pubcat=risc', 'authorid_pubrole_pubcat')
    add(ITEMS_URL, 'configured_url')
    return candidates


def fetch_items(context, profile_page, report: dict) -> tuple[str, dict]:
    attempts = []
    last_html = ''
    selected_report = {'status': 'not_attempted'}
    for candidate in author_item_candidates(profile_page):
        page = context.new_page()
        html, attempt_report = load_page(page, candidate['url'], 'items', referer=PROFILE_URL)
        attempt_report['candidate_source'] = candidate['source']
        attempt_report['candidate_text'] = candidate.get('text', '')
        attempts.append(attempt_report)
        last_html = html
        selected_report = attempt_report
        if has_markers(html, 'items'):
            attempt_report['selected'] = True
            report['items_attempts'] = attempts
            return html, attempt_report
        page.close()
    report['items_attempts'] = attempts
    return last_html, selected_report


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

        profile_html, profile_report = load_page(page, PROFILE_URL, 'profile', referer='https://www.elibrary.ru/')
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
        else:
            report['pages']['profile']['debug'] = save_debug(page, profile_html, 'profile_unready')

        items_html, items_report = fetch_items(context, page, report)
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
        else:
            debug_page = context.new_page()
            try:
                debug_page.goto(items_report.get('final_url') or ITEMS_URL, wait_until='domcontentloaded', timeout=45000)
            except Exception:
                pass
            report['pages']['items']['debug'] = save_debug(debug_page, items_html, 'items_unready')
            debug_page.close()
        context.close()
        browser.close()

    if ok_profile and ok_items:
        report['status'] = 'ok'
        exit_code = 0
    elif ok_profile and any(attempt.get('status') == 'captcha' for attempt in report.get('items_attempts', [])):
        report['status'] = 'profile_ok_items_captcha'
        exit_code = 2
    else:
        report['status'] = 'partial_or_failed'
        exit_code = 2
    write_json(REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
