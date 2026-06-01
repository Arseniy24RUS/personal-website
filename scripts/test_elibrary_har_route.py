#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, 'scripts')
from parse_elibrary_author_items import parse_elibrary_author_items  # noqa: E402

AUTHOR_ID = os.environ.get('ELIBRARY_AUTHOR_ID', '1012909')
AUTHOR_NAME = os.environ.get('ELIBRARY_AUTHOR_SEARCH_NAME', 'Ситковский Арсений Михайлович')
BASE = 'https://www.elibrary.ru'
DEFAULT_URL = BASE + '/defaultx.asp'
AUTHORS_URL = BASE + '/authors.asp'
ITEMS_OUT = Path(os.environ.get('ELIBRARY_ITEMS_OUT', 'data/processed/elibrary_publications.json'))
REPORT = Path(os.environ.get('ELIBRARY_BROWSER_REPORT', 'data/elibrary/browser_fetch_report.json'))
DEBUG_DIR = Path(os.environ.get('ELIBRARY_DEBUG_DIR', 'artifacts/elibrary_debug'))
SNAPSHOT_DIR = Path(os.environ.get('ELIBRARY_ITEMS_SNAPSHOT_DIR', 'data/snapshots/elibrary/items'))
WAIT_MS = int(os.environ.get('ELIBRARY_BROWSER_WAIT_SEC', '130')) * 1000


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def cookie_objects(header: str) -> list[dict]:
    out = []
    for part in (header or '').split(';'):
        if '=' not in part:
            continue
        name, value = part.split('=', 1)
        name = name.strip(); value = value.strip()
        if not name:
            continue
        for domain in ['.elibrary.ru', 'www.elibrary.ru', 'elibrary.ru']:
            out.append({'name': name, 'value': value, 'domain': domain, 'path': '/', 'secure': True, 'httpOnly': False, 'sameSite': 'Lax'})
    return out


def is_items(html: str) -> bool:
    return 'author_items' in html and 'arw' in html


def challenge(html: str, url: str) -> bool:
    low = (html or '').lower()
    return 'тест тьюринга' in low or 'page_captcha' in (url or '').lower() or 'recaptcha' in low


def page_info(page, html: str) -> dict:
    return {'url': page.url, 'title': page.title(), 'bytes': len((html or '').encode('utf-8', 'replace')), 'has_items': is_items(html or ''), 'has_challenge': challenge(html or '', page.url), 'excerpt': (html or '')[:900].replace('\n', ' ')}


def debug(page, html: str, name: str) -> dict:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    base = DEBUG_DIR / f'{stamp}_{name}'
    hp = base.with_suffix('.html')
    sp = base.with_suffix('.png')
    hp.write_text(html or '', encoding='utf-8')
    ok = False
    try:
        page.screenshot(path=str(sp), full_page=True)
        ok = True
    except Exception:
        pass
    return {'html_path': str(hp), 'screenshot_path': str(sp) if ok else None}


def wait_items(page) -> tuple[str, dict]:
    end = page.context._timeout_settings.timeout() or WAIT_MS
    # Avoid using private timeout value if Playwright changes it.
    deadline = WAIT_MS
    elapsed = 0
    html = ''
    while elapsed < deadline:
        page.wait_for_timeout(2000)
        elapsed += 2000
        html = page.content()
        if is_items(html) or challenge(html, page.url):
            info = page_info(page, html); info['elapsed_ms'] = elapsed
            return html, info
    info = page_info(page, html); info['elapsed_ms'] = elapsed; info['status'] = 'timeout'
    return html, info


def fill_and_submit_authors(page, report: dict) -> None:
    page.goto(DEFAULT_URL, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(3000)
    report['default'] = page_info(page, page.content())
    page.goto(AUTHORS_URL, wait_until='domcontentloaded', timeout=60000, referer=DEFAULT_URL)
    page.wait_for_timeout(3000)
    report['authors_before'] = page_info(page, page.content())
    if report['authors_before']['has_challenge']:
        report['authors_before']['debug'] = debug(page, page.content(), 'authors_before_challenge')
        return
    result = page.evaluate("""(q) => {
      const input = Array.from(document.querySelectorAll('input')).find(i => (i.name || '').toLowerCase() === 'surname')
        || Array.from(document.querySelectorAll('input')).find(i => /Фамилия/i.test((i.closest('tr') ? i.closest('tr').innerText : '') || ''));
      if (!input) return {ok:false, reason:'surname_input_not_found', inputs: document.querySelectorAll('input').length};
      input.value = q;
      input.dispatchEvent(new Event('input', {bubbles:true}));
      input.dispatchEvent(new Event('change', {bubbles:true}));
      const form = input.form || document.querySelector('form');
      if (!form) return {ok:false, reason:'form_not_found'};
      const set = (name, value) => { let el = form.querySelector(`[name="${name}"]`); if (!el) { el = document.createElement('input'); el.type='hidden'; el.name=name; form.appendChild(el); } el.value=value; };
      set('authors_all',''); set('pagenum',''); set('authorbox_name',''); set('selid',''); set('orgid',''); set('orgadminid',''); set('townid',''); set('regionid',''); set('codetype','SPIN'); set('codevalue',''); set('countryid',''); set('town',''); set('orgname',''); set('authorboxid',''); set('rubriccode',''); set('metrics','1'); set('sortorder','2'); set('order','0'); set('hid1012909','Ситковский А М');
      form.method='POST'; form.action='authors.asp'; form.submit();
      return {ok:true, form_action: form.action, input_name: input.name || ''};
    }""", AUTHOR_NAME)
    report['submit_result'] = result
    try:
        page.wait_for_load_state('domcontentloaded', timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(5000)
    report['authors_after'] = page_info(page, page.content())
    if report['authors_after']['has_challenge']:
        report['authors_after']['debug'] = debug(page, page.content(), 'authors_after_challenge')


def main() -> int:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    report = {'generated_at': now(), 'route': 'har_authors_post_popup', 'cookie_present': bool(os.environ.get('ELIBRARY_COOKIE'))}
    ok = False
    with sync_playwright() as p:
        headless = os.environ.get('ELIBRARY_BROWSER_HEADLESS', 'true').lower() not in {'0', 'false', 'no'}
        ua = os.environ.get('ELIBRARY_USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 YaBrowser/26.4.0.0 Safari/537.36')
        browser = p.chromium.launch(headless=headless, args=['--disable-dev-shm-usage', '--no-sandbox'])
        context = browser.new_context(locale='ru-RU', timezone_id='Europe/Moscow', user_agent=ua, viewport={'width': 1366, 'height': 900})
        cookies = cookie_objects(os.environ.get('ELIBRARY_COOKIE', ''))
        if cookies:
            context.add_cookies(cookies)
            report['cookies_loaded'] = sorted({c['name'] for c in cookies})
        page = context.new_page()
        fill_and_submit_authors(page, report)
        html = page.content()
        if not challenge(html, page.url):
            loc = page.locator(f'a[href*="author_items.asp"][href*="{AUTHOR_ID}"]').first()
            report['author_items_link_count'] = page.locator(f'a[href*="author_items.asp"][href*="{AUTHOR_ID}"]').count()
            if report['author_items_link_count']:
                try:
                    with context.expect_page(timeout=7000) as popup_info:
                        loc.click(timeout=15000)
                    target = popup_info.value
                    target.wait_for_load_state('domcontentloaded', timeout=60000)
                    report['opened_as'] = 'popup'
                except PlaywrightTimeoutError:
                    target = page
                    report['opened_as'] = 'same_page_or_no_popup'
                except Exception as exc:
                    report['click_error'] = repr(exc)
                    target = page
                html, info = wait_items(target)
                report['items_page'] = info
                if is_items(html):
                    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                    snapshot = SNAPSHOT_DIR / f'author_items_{AUTHOR_ID}_{stamp}_popup.html'
                    snapshot.write_text(html, encoding='utf-8')
                    records = parse_elibrary_author_items(str(snapshot))
                    write_json(ITEMS_OUT, records)
                    report['snapshot_path'] = str(snapshot)
                    report['records'] = len(records)
                    ok = True
                else:
                    report['items_debug'] = debug(target, html, 'items_popup_not_ready')
            else:
                report['no_link_debug'] = debug(page, html, 'authors_no_items_link')
        else:
            report['initial_challenge_debug'] = debug(page, html, 'authors_route_challenge')
        context.close(); browser.close()
    report['status'] = 'ok' if ok else 'not_ready'
    write_json(REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
