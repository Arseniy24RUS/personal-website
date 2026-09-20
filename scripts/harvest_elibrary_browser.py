#!/usr/bin/env python3
"""Authenticated eLibrary profile, all list pages and item details in one context."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

from parse_elibrary_author_profile import parse_elibrary_author_profile_html
from parse_elibrary_author_items import parse_elibrary_author_items
from harvest_elibrary_item_details import parse_detail_html, needs_details, item_id_from_pub
from provider_auth import AuthFailure, login_elibrary, assert_no_challenge, elibrary_authenticated, verify_browser_egress, browser_initialization_diagnostics
from source_health import read_json, write_json, source_result, merge_records, now, snapshot_time

AUTHOR_ID = os.environ.get('ELIBRARY_AUTHOR_ID', '1012909')
PROFILE_URL = f'https://elibrary.ru/author_profile.asp?id={AUTHOR_ID}'
ITEMS_URL = f'https://elibrary.ru/author_items.asp?authorid={AUTHOR_ID}&pubrole=100&show_refs=1&pubcat=risc'
PROFILE_OUT = Path(os.environ.get('ELIBRARY_PROFILE_OUT', 'data/elibrary/profile_metrics.json'))
ITEMS_OUT = Path(os.environ.get('ELIBRARY_ITEMS_OUT', 'data/processed/elibrary_publications.json'))
DETAILS_OUT = Path(os.environ.get('ELIBRARY_ITEM_DETAILS_OUT', 'data/elibrary/item_details.json'))
REPORT = Path(os.environ.get('ELIBRARY_BROWSER_REPORT', 'data/elibrary/browser_fetch_report.json'))
WAIT_SEC = int(os.environ.get('ELIBRARY_BROWSER_WAIT_SEC', '90'))


def wait_ready(page, selector):
    deadline = time.monotonic() + WAIT_SEC
    while time.monotonic() < deadline:
        assert_no_challenge(page)
        if page.locator(selector).count():
            if not elibrary_authenticated(page):
                raise AuthFailure('session_expired')
            return page.content()
        page.wait_for_timeout(1000)
    raise AuthFailure('page_structure_changed')


def list_total(html):
    text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
    match = re.search(r'Всего найдено\s+([\d\s]+)\s+публикац', text, re.I)
    return int(re.sub(r'\s+', '', match.group(1))) if match else None


def parse_items(html, temp):
    path = Path(temp) / 'items.html'
    path.write_text(html, encoding='utf-8')
    return parse_elibrary_author_items(str(path))


def collect_items(page, temp):
    page.goto(ITEMS_URL, wait_until='domcontentloaded', timeout=90000)
    result = []
    seen = set()
    total = None
    for number in range(1, 1001):
        html = wait_ready(page, 'tr[id^="arw"]')
        batch = parse_items(html, temp)
        if not batch:
            raise AuthFailure('empty_publication_list')
        current = {row['elibrary_item_id'] for row in batch}
        if not current - seen:
            raise AuthFailure('pagination_loop')
        seen.update(current)
        result = merge_records(result, batch, lambda row: row.get('elibrary_item_id'))
        total = list_total(html) if total is None else total
        if total is None:
            raise AuthFailure('publication_total_missing')
        if len(result) >= total:
            return result
        # The site's own paging form preserves the author, category and filters.
        available = page.evaluate("() => typeof goto_page === 'function' && !!document.querySelector('[name=pagenum]')")
        if not available:
            raise AuthFailure('pagination_control_changed')
        page.evaluate('(n) => goto_page(n)', number + 1)
        page.wait_for_load_state('domcontentloaded', timeout=90000)
        page.wait_for_timeout(1200)
    raise AuthFailure('pagination_limit')


def collect_details(page, records, previous):
    payload = previous if isinstance(previous, dict) and 'items' in previous else {'items': {}}
    cached = payload['items']
    # Retry missing fields; valid old entries are never removed when an item fails.
    todo = [row for row in records if needs_details(row, cached)]
    limit = int(os.environ.get('ELIBRARY_ITEM_DETAILS_LIMIT', '100'))
    failed = 0
    completed = 0
    for row in todo[:limit]:
        item_id = item_id_from_pub(row)
        try:
            response = page.goto(f'https://elibrary.ru/item.asp?id={item_id}', wait_until='domcontentloaded', timeout=90000)
            assert_no_challenge(page)
            if not response or response.status != 200 or not elibrary_authenticated(page):
                raise AuthFailure('item_unavailable')
            html = page.content()
            # Check bibliographic evidence rather than accept a 200 login page.
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.select_one('#title, .bigtext, meta[name="citation_title"]')
            if not title or len(soup.get_text(' ', strip=True)) < 500:
                raise AuthFailure('item_structure_changed')
            parsed = parse_detail_html(html)
            # Authentication/session sidebars must never appear in published data.
            parsed.pop('raw_text_excerpt', None)
            old = cached.get(item_id, {}).get('parsed', {})
            optional = ('venue', 'publisher', 'volume', 'issue', 'pages', 'doi', 'isbn', 'issn')
            cached[item_id] = {'fetched_at': now(), 'status': 'success', 'observed_absent_fields': [key for key in optional if not parsed.get(key)], 'url': f'https://elibrary.ru/item.asp?id={item_id}', 'parsed': {**old, **{k: v for k, v in parsed.items() if v is not None and v != ''}}}
            completed += 1
        except AuthFailure as exc:
            failed += 1
            if exc.reason in {'session_expired', 'human_verification_required', 'mfa_required', 'ip_blocked'}:
                break
        except Exception:
            failed += 1
        page.wait_for_timeout(int(float(os.environ.get('ELIBRARY_ITEM_DETAILS_DELAY_SEC', '1.5')) * 1000))
    payload.update({'generated_at': now(), 'schema': 'elibrary_item_details/v1'})
    return payload, {'fetched': completed, 'failed': failed, 'pending': max(0, len(todo) - completed)}


def main():
    previous_report = read_json(REPORT, {})
    previous_items = read_json(ITEMS_OUT, [])
    previous_profile = read_json(PROFILE_OUT, {})
    count = len(previous_items)
    stage = 'initialization'
    try:
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory(prefix='elibrary-', dir=os.environ.get('RUNNER_TEMP')) as temp:
            with sync_playwright() as playwright:
                launch = {'headless': os.environ.get('ELIBRARY_BROWSER_HEADLESS', 'true').lower() not in {'false', '0', 'no'}, 'args': ['--disable-dev-shm-usage', '--no-sandbox']}
                if os.environ.get('ELIBRARY_BROWSER_CHANNEL'):
                    launch['channel'] = os.environ['ELIBRARY_BROWSER_CHANNEL']
                browser = playwright.chromium.launch(**launch)
                context = browser.new_context(locale='ru-RU', timezone_id='Europe/Moscow', viewport={'width': 1366, 'height': 900})
                stage = 'route_verification'
                verify_browser_egress(context)
                stage = 'login'
                page = login_elibrary(context)
                stage = 'profile'
                page.goto(PROFILE_URL, wait_until='domcontentloaded', timeout=90000)
                deadline = time.monotonic() + WAIT_SEC
                while time.monotonic() < deadline:
                    assert_no_challenge(page)
                    html = page.content()
                    if 'ОБЩИЕ ПОКАЗАТЕЛИ' in html and 'Индекс Хирша' in html:
                        break
                    page.wait_for_timeout(1000)
                if not elibrary_authenticated(page) or 'ОБЩИЕ ПОКАЗАТЕЛИ' not in html:
                    raise AuthFailure('profile_not_authenticated_or_changed')
                address = urlparse(page.url)
                if not address.path.endswith('/author_profile.asp') or parse_qs(address.query).get('id') != [AUTHOR_ID]:
                    raise AuthFailure('wrong_author_profile')
                profile = parse_elibrary_author_profile_html(html)
                required = ('publications_rinc', 'citations_rinc', 'h_index_rinc', 'publications_elibrary', 'citations_elibrary', 'h_index_elibrary')
                if any(profile.get('summary', {}).get(key) is None for key in required):
                    raise AuthFailure('profile_metrics_missing')
                stage = 'publications'
                fresh = collect_items(page, temp)
                records = merge_records(previous_items, fresh, lambda row: row.get('elibrary_item_id'))
                for record in records:
                    if record.get('elibrary_item_id') in {row['elibrary_item_id'] for row in fresh}:
                        record['source'] = 'elibrary_authenticated_browser'
                stage = 'item_details'
                details, details_report = collect_details(page, records, read_json(DETAILS_OUT, {}))
                context.close()
                browser.close()
        count = len(records)
        state = source_result(previous_report, status='success', count=count)
        profile['last_success_at'] = state['last_success_at']
        write_json(PROFILE_OUT, profile)
        write_json(ITEMS_OUT, records)
        write_json(DETAILS_OUT, details)
        report = {**state, 'generated_at': now(), 'authentication': 'fresh_password_login', 'details': details_report, 'target_author_id': AUTHOR_ID}
    except AuthFailure as exc:
        report = source_result(previous_report, status='blocked', count=count, reason=exc.reason)
        report['stage'] = stage
        if getattr(exc, 'diagnostics', None):
            report['diagnostics'] = exc.diagnostics
    except Exception as exc:
        initialization = browser_initialization_diagnostics(exc) if stage == 'initialization' else None
        report = source_result(previous_report, status='error', count=count, reason=initialization['reason'] if initialization else type(exc).__name__)
        report['stage'] = stage
        if initialization:
            report['initialization'] = initialization
    if not report.get('last_success_at'):
        legacy_report = read_json('data/elibrary/profile_metrics_fetch_report.json', {})
        report['last_success_at'] = previous_profile.get('last_success_at') or snapshot_time(legacy_report.get('snapshot_path'))
    write_json(REPORT, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
