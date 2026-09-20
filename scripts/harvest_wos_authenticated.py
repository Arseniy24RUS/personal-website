#!/usr/bin/env python3
"""Collect WoS through its ordinary ORCID login and rendered pagination.

No stale cookies, browser fingerprint overrides, access-control workarounds or
public session diagnostics. A snapshot fallback is reported as a failed live
attempt, not as a successful login.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from parse_wos_author_profile import parse_wos_author_profile_html
from provider_auth import AuthFailure, login_wos, assert_no_challenge, verify_browser_egress, visible, browser_initialization_diagnostics
from source_health import read_json, write_json, source_result, merge_records, now, snapshot_time

RESEARCHER_ID = os.environ.get('WOS_RESEARCHER_ID', 'AAG-1530-2021')
PROFILE_URL = f'https://www.webofscience.com/wos/author/record/{RESEARCHER_ID}'
OUT = Path(os.environ.get('WOS_PROFILE_OUT', 'data/wos/profile_metrics.json'))
REPORT = Path(os.environ.get('WOS_HARVEST_REPORT', 'data/wos/harvest_report.json'))
WAIT_SEC = int(os.environ.get('WOS_BROWSER_WAIT_SEC', '180'))


def record_key(record):
    return record.get('wos_uid') or record.get('doi') or (record.get('title'), record.get('year'))


def read_records(page, previous_keys=None):
    deadline = time.monotonic() + WAIT_SEC
    while time.monotonic() < deadline:
        assert_no_challenge(page)
        data = parse_wos_author_profile_html(page.content(), RESEARCHER_ID)
        records = data.get('records', [])
        if records and (not previous_keys or {record_key(r) for r in records} - previous_keys):
            return data
        page.wait_for_timeout(1000)
    raise AuthFailure('profile_records_not_ready')


def collect_profile(page, previous):
    data = read_records(page)
    records = data['records']
    expected = data.get('summary', {}).get('core_collection_publications')
    if expected is None:
        expected = data.get('summary', {}).get('publications')
    if expected is None:
        raise AuthFailure('profile_total_missing')
    for _ in range(1000):
        keys = {record_key(r) for r in records}
        next_button = visible(page, ['button[data-ta="next-page-button"]', 'button[aria-label*="Next Page"]'])
        if next_button is None or not next_button.is_enabled():
            break
        next_button.click()
        batch = read_records(page, keys)
        records = merge_records(records, batch['records'], record_key)
    else:
        raise AuthFailure('pagination_limit')
    if len(records) < int(expected):
        raise AuthFailure('incomplete_pagination')
    if any(data.get('summary', {}).get(key) is None for key in ('publications', 'citations', 'h_index')):
        raise AuthFailure('profile_metrics_missing')
    # Preserve withdrawn or temporarily hidden old works while refreshing new data.
    data['records'] = merge_records(previous.get('records', []), records, record_key)
    data['records_count_on_page'] = len(data['records'])
    data['source'] = 'web_of_science_authenticated_orcid'
    # Missing metrics are not genuine zero, and must not replace the last value.
    for field in ('summary', 'summary_metrics', 'core_collection_metrics'):
        data[field] = {**previous.get(field, {}), **{k: v for k, v in data.get(field, {}).items() if v is not None}}
    return data


def main():
    previous = read_json(OUT, {})
    previous_report = read_json(REPORT, {})
    stage = 'initialization'
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            launch = {'headless': os.environ.get('WOS_BROWSER_HEADLESS', 'true').lower() not in {'0', 'false', 'no'}, 'args': ['--disable-dev-shm-usage', '--no-sandbox']}
            if os.environ.get('WOS_BROWSER_CHANNEL'):
                launch['channel'] = os.environ['WOS_BROWSER_CHANNEL']
            browser = playwright.chromium.launch(**launch)
            context = browser.new_context(locale='en-US', timezone_id='Europe/Moscow', viewport={'width': 1440, 'height': 1100})
            stage = 'route_verification'
            verify_browser_egress(context)
            stage = 'login'
            page = login_wos(context, PROFILE_URL, WAIT_SEC)
            stage = 'profile'
            data = collect_profile(page, previous)
            context.close()
            browser.close()
        report = source_result(previous_report, status='success', count=len(data['records']))
        report['authentication'] = 'fresh_orcid_login'
        data['last_success_at'] = report['last_success_at']
        write_json(OUT, data)
    except AuthFailure as exc:
        report = source_result(previous_report, status='blocked', count=len(previous.get('records', [])), reason=exc.reason)
        report['stage'] = stage
        if getattr(exc, 'diagnostics', None):
            report['diagnostics'] = exc.diagnostics
    except Exception as exc:
        initialization = browser_initialization_diagnostics(exc) if stage == 'initialization' else None
        report = source_result(previous_report, status='error', count=len(previous.get('records', [])), reason=initialization['reason'] if initialization else type(exc).__name__)
        report['stage'] = stage
        if initialization:
            report['initialization'] = initialization
    if not report.get('last_success_at'):
        # Only actual record snapshots count; bootstrap HTML contains no works.
        snapshots = sorted(Path('data/snapshots/wos').glob(f'author_profile_{RESEARCHER_ID}_????????T??????Z.html'))
        report['last_success_at'] = previous.get('last_success_at') or snapshot_time(snapshots[-1] if snapshots else None)
    report['generated_at'] = now()
    write_json(REPORT, report)
    print(json.dumps(report))
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
