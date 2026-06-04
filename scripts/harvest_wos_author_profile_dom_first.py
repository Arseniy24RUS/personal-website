#!/usr/bin/env python3
"""DOM-first production entrypoint for Web of Science profiles.

The primary source is the rendered Web of Science profile page. The harvester:
1. opens the public author profile;
2. forces the stable `/author_profile_page/claimed` route if WoS leaves the
   browser on the transient Nextgen/transfer URL;
3. waits for rendered `app-record` nodes and parses them from page.content();
4. saves a screenshot and a redacted HTML diagnostic when live DOM records are
   not available;
5. never overwrites stronger previous WoS records with a weak/empty live result.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import re

import harvest_wos_author_profile_production as prod

base = prod.base
USER_AGENT = prod.USER_AGENT
DOM_WAIT_SEC = int(os.environ.get('WOS_DOM_WAIT_SEC', str(max(base.WAIT_SEC, 180))))
CLAIMED_URL = os.environ.get(
    'WOS_CLAIMED_PROFILE_URL',
    f'https://www.webofscience.com/wos/author/record/{base.RESEARCHER_ID}/author_profile_page/claimed',
)


def safe_page_content(page) -> str:
    try:
        return page.content()
    except Exception:
        try:
            page.wait_for_load_state('domcontentloaded', timeout=5000)
            return page.content()
        except Exception:
            return ''


def redacted_html(html: str | None) -> str:
    text = html or ''
    # The saved diagnostic should show page structure, not session material.
    text = re.sub(
        r'window\.sessionData\s*=\s*\{.*?\};\s*\n\s*window\.debugTimestamp',
        'window.sessionData = {"redacted": true};\n        window.debugTimestamp',
        text,
        flags=re.S,
    )
    text = re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[REDACTED_EMAIL]', text)
    text = re.sub(r'EUW[A-Za-z0-9]{8,}', '[REDACTED_SID]', text)
    return text


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', errors='replace')
    return str(path)


def write_json(path: Path, payload) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)


def good_dom_records(data: dict | None) -> bool:
    return prod.records_count(data) >= max(1, min(prod.summary_publications(data) or 10, 10))


def is_transfer_url(url: str | None) -> bool:
    url = str(url or '')
    return 'mode=Nextgen' in url or 'action=transfer' in url or '/wos/?' in url


def selector_counts(page) -> dict:
    selectors = {
        'app_record': 'app-record',
        'summary_item': '.summary-item',
        'author_metric': '.wat-author-metric-inline-block',
        'app_author_profile': 'app-author-profile',
        'spinner': 'mat-progress-spinner, .cdx-spinner, .wat-spinner',
        'cookie_banner': '#onetrust-banner-sdk',
    }
    out = {}
    for key, selector in selectors.items():
        try:
            out[key] = page.locator(selector).count()
        except Exception:
            out[key] = None
    return out


def body_text_sample(page) -> str:
    try:
        return re.sub(r'\s+', ' ', page.locator('body').inner_text(timeout=3000))[:1600]
    except Exception:
        return ''


def save_diagnostics(page, html: str | None, report: dict, label: str) -> None:
    base.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = base.ARTIFACT_DIR / f'wos_{base.RESEARCHER_ID}_{base.stamp()}_{label}'
    payload = {
        'label': label,
        'url': page.url,
        'title': None,
        'selector_counts': selector_counts(page),
        'content_length': len((html or '').encode('utf-8', errors='replace')),
        'body_text_sample': body_text_sample(page),
    }
    try:
        payload['title'] = page.title()
    except Exception:
        pass
    try:
        screenshot = prefix.with_suffix('.png')
        page.screenshot(path=str(screenshot), full_page=True, timeout=15000)
        payload['screenshot_path'] = str(screenshot)
    except Exception as exc:
        payload['screenshot_error'] = repr(exc)
    if html:
        payload['html_path'] = write_text(prefix.with_suffix('.html'), redacted_html(html))
    payload['json_path'] = write_json(prefix.with_suffix('.json'), payload)
    report.setdefault('diagnostic_artifacts', []).append(payload)


def dismiss_cookie_banner(page, report: dict) -> None:
    for selector in ['#onetrust-accept-btn-handler', 'button:has-text("Accept All")', 'button:has-text("Accept all")']:
        try:
            button = page.locator(selector).first
            if button.count() and button.is_visible(timeout=1000):
                button.click(timeout=2000)
                report['cookie_banner_clicked'] = selector
                return
        except Exception:
            pass


def force_claimed_route_if_needed(page, report: dict, reason: str) -> None:
    current = page.url
    if is_transfer_url(current) or '/author/record/' not in current or reason == 'force':
        report.setdefault('route_forcing', []).append({'reason': reason, 'from': current, 'to': CLAIMED_URL})
        try:
            page.goto(CLAIMED_URL, wait_until='domcontentloaded', timeout=max(base.WAIT_SEC, 60) * 1000)
        except Exception as exc:
            report.setdefault('route_forcing_errors', []).append({'reason': reason, 'error': repr(exc), 'current_url': page.url})


def browser_dom_first(previous):
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return None, {'status': 'playwright_import_failed', 'error': repr(exc)}, None

    report = {
        'route': 'browser_dom_first_claimed_route',
        'url': base.URL,
        'claimed_url': CLAIMED_URL,
        'dom_wait_sec': DOM_WAIT_SEC,
        'input_state': {
            'cookie_secret_present': bool(base.WOS_COOKIE),
            'storage_state_secret_present': bool(base.WOS_STORAGE_STATE_B64),
        },
    }
    progress = []
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

        context_kwargs = {
            'locale': 'en-US',
            'timezone_id': 'Europe/Moscow',
            'user_agent': USER_AGENT,
            'viewport': {'width': 1440, 'height': 1400},
        }
        state_path = base.storage_state_path_from_secret(report)
        if state_path:
            context_kwargs['storage_state'] = state_path
        context = browser.new_context(**context_kwargs)
        if base.WOS_COOKIE:
            try:
                cookies = prod.cookie_header_to_playwright(base.WOS_COOKIE)
                context.add_cookies(cookies)
                report['input_state']['cookie_names'] = sorted({c['name'] for c in cookies})
                report['input_state']['cookie_domains_count'] = len(cookies)
            except Exception as exc:
                report['input_state']['cookie_add_error'] = repr(exc)

        page = context.new_page()
        try:
            page.goto(base.URL, wait_until='domcontentloaded', timeout=max(base.WAIT_SEC, 60) * 1000)
            dismiss_cookie_banner(page, report)
            force_claimed_route_if_needed(page, report, 'after_initial_goto')
            try:
                page.wait_for_selector('app-record', timeout=45000)
            except Exception as exc:
                report['initial_app_record_wait'] = repr(exc)
                force_claimed_route_if_needed(page, report, 'after_initial_app_record_timeout')

            html = ''
            best_dom = None
            for elapsed in range(0, DOM_WAIT_SEC + 1, 5):
                if elapsed:
                    page.wait_for_timeout(5000)
                if elapsed in {0, 15, 30, 60} and is_transfer_url(page.url):
                    force_claimed_route_if_needed(page, report, f'transfer_url_at_{elapsed}s')
                try:
                    page.mouse.wheel(0, 1400)
                except Exception:
                    pass
                try:
                    page.wait_for_load_state('networkidle', timeout=2500)
                except Exception:
                    pass

                html = safe_page_content(page)
                dom_data = base.carry_forward_metrics(base.parse_wos_author_profile_html(html, base.RESEARCHER_ID), previous) if html else None
                dom_records = prod.records_count(dom_data)
                counts = selector_counts(page)
                item = {
                    'elapsed_sec': elapsed,
                    'url': page.url,
                    'selector_counts': counts,
                    'parsed_records': dom_records,
                    'parsed_records_or_publications': prod.normalized_count(dom_data),
                    'content_length': len((html or '').encode('utf-8', errors='replace')),
                }
                progress.append(item)
                report['dom_progress_tail'] = progress[-12:]
                report['candidate_dom_records'] = dom_records
                report['candidate_dom_records_or_publications'] = prod.normalized_count(dom_data)
                if dom_records:
                    best_dom = dom_data
                if good_dom_records(dom_data):
                    report.update({
                        'status': 'ok',
                        'used_subroute': 'rendered_dom_app_records',
                        'elapsed_sec': elapsed,
                        'records': dom_records,
                        'records_or_publications': prod.normalized_count(dom_data),
                        'final_url': page.url,
                        'title': page.title(),
                        'content_length': len(html.encode('utf-8', errors='replace')),
                        'dom_progress_tail': progress[-12:],
                    })
                    save_diagnostics(page, html, report, 'success_dom_records')
                    context.close(); browser.close()
                    return html, report, dom_data

            report.update({
                'status': 'no_records' if not best_dom else 'partial_records',
                'records': prod.records_count(best_dom),
                'records_or_publications': prod.normalized_count(best_dom),
                'final_url': page.url,
                'content_length': len((html or '').encode('utf-8', errors='replace')),
                'dom_progress_tail': progress[-12:],
            })
            save_diagnostics(page, html, report, 'failure_no_dom_records')
            context.close(); browser.close()
            return html or None, report, best_dom
        except Exception as exc:
            html = safe_page_content(page)
            candidate = base.carry_forward_metrics(base.parse_wos_author_profile_html(html, base.RESEARCHER_ID), previous) if html else None
            report.update({
                'status': 'error',
                'error': repr(exc),
                'records': prod.records_count(candidate),
                'records_or_publications': prod.normalized_count(candidate),
                'dom_progress_tail': progress[-12:],
            })
            try:
                save_diagnostics(page, html, report, 'error')
            except Exception:
                pass
            context.close(); browser.close()
            return html or None, report, candidate


def save_valid_snapshot(html: str | None, subroute: str, report: dict) -> None:
    if not html or not base.has_wos_payload(html):
        return
    data = base.parse_wos_author_profile_html(html, base.RESEARCHER_ID)
    if not prod.records_count(data) and not prod.normalized_count(data):
        report.setdefault('skipped_snapshots', []).append({'subroute': subroute, 'reason': 'weak_html_without_records_or_metrics'})
        return
    base.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = base.SNAPSHOT_DIR / f'author_profile_{base.RESEARCHER_ID}_{base.stamp()}_{subroute}.html'
    path.write_text(html, encoding='utf-8', errors='replace')
    report['snapshot_path'] = str(path)


def best_saved_snapshot(previous, report: dict):
    if not base.SNAPSHOT_DIR.exists():
        return None
    skipped = []
    for snapshot in sorted(base.SNAPSHOT_DIR.glob(f'author_profile_{base.RESEARCHER_ID}_*.html'), reverse=True):
        try:
            data = base.carry_forward_metrics(base.parse_file(str(snapshot), base.RESEARCHER_ID), previous)
            if prod.records_count(data) or prod.normalized_count(data):
                report['snapshot_path'] = str(snapshot)
                return data
            skipped.append(str(snapshot))
        except Exception:
            skipped.append(str(snapshot))
    if skipped:
        report['skipped_empty_snapshots_sample'] = skipped[:8]
    return None


def write_result(data, report: dict) -> int:
    base.write_json(base.OUT, data)
    report['written_records'] = prod.records_count(data)
    report['written_records_or_publications'] = prod.normalized_count(data)
    base.write_json(base.REPORT, report)
    print(json.dumps({
        'out': str(base.OUT),
        'used_source': report.get('used_source'),
        'records': prod.records_count(data),
        'records_or_publications': prod.normalized_count(data),
        'diagnostic_artifacts': (report.get('browser') or {}).get('diagnostic_artifacts'),
    }, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    base.OUT.parent.mkdir(parents=True, exist_ok=True)
    base.REPORT.parent.mkdir(parents=True, exist_ok=True)
    base.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    base.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    previous = base.read_json(base.OUT, None)
    report: dict = {
        'generated_at': base.now(),
        'strategy': 'dom_first_claimed_route',
        'previous_records': prod.records_count(previous),
        'previous_records_or_publications': prod.normalized_count(previous),
    }

    html, browser_report, live_data = browser_dom_first(previous)
    report['browser'] = browser_report

    if live_data and prod.records_count(live_data):
        report['used_source'] = live_data.get('source') or 'live_wos_rendered_dom'
        save_valid_snapshot(html, browser_report.get('used_subroute') or 'dom_first', report)
        data = prod.preserve_best_records(live_data, previous, report)
    elif html and base.has_wos_payload(html):
        candidate = base.carry_forward_metrics(base.parse_wos_author_profile_html(html, base.RESEARCHER_ID), previous)
        report['used_source'] = 'live_wos_dom_metrics_only'
        report['candidate_records'] = prod.records_count(candidate)
        report['candidate_records_or_publications'] = prod.normalized_count(candidate)
        save_valid_snapshot(html, 'dom_metrics_only', report)
        data = prod.preserve_best_records(candidate, previous, report)
    else:
        candidate = best_saved_snapshot(previous, report)
        if candidate:
            report['used_source'] = 'saved_snapshot'
            data = prod.preserve_best_records(candidate, previous, report)
        elif previous:
            report['used_source'] = 'previous_normalized_json'
            data = previous
        else:
            report['used_source'] = 'none'
            report['error'] = 'No live Web of Science DOM records, no saved valid snapshot and no previous normalized JSON.'
            base.write_json(base.REPORT, report)
            return 1

    return write_result(data, report)


if __name__ == '__main__':
    raise SystemExit(main())
