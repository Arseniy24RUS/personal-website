#!/usr/bin/env python3
"""DOM-first production entrypoint for Web of Science profiles.

The primary source is the rendered Web of Science profile page. The harvester:
1. opens the public author profile;
2. if WoS leaves the browser on a transient Nextgen/transfer URL, returns to the
   public `/wos/author/record/<ResearcherID>` route rather than the fragile
   deep `/author_profile_page/claimed` route;
3. supports three browser modes: normal Playwright context, persistent local
   Chrome profile, or a browser already started with remote debugging;
4. waits for rendered `app-record` nodes and parses them from page.content();
5. detects Web of Science human-verification screens and preserves cached data;
6. saves screenshot/redacted HTML/browser diagnostics for failed live attempts;
7. never overwrites stronger previous WoS records with a weak/empty live result.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import re
from typing import Any

import harvest_wos_author_profile_production as prod

base = prod.base
USER_AGENT = os.environ.get('WOS_USER_AGENT', prod.USER_AGENT)
DOM_WAIT_SEC = int(os.environ.get('WOS_DOM_WAIT_SEC', str(max(base.WAIT_SEC, 180))))
PUBLIC_PROFILE_URL = os.environ.get(
    'WOS_STABLE_PROFILE_URL',
    f'https://www.webofscience.com/wos/author/record/{base.RESEARCHER_ID}',
)
# Optional only: diagnostics showed that directly forcing the claimed deep route
# can render "This page doesn't exist" in GitHub Actions. It is disabled by default.
OPTIONAL_CLAIMED_URL = os.environ.get('WOS_CLAIMED_PROFILE_URL', '').strip()
ROUTE_CANDIDATES = [PUBLIC_PROFILE_URL] + ([OPTIONAL_CLAIMED_URL] if OPTIONAL_CLAIMED_URL else [])
PERSISTENT_USER_DATA_DIR = os.environ.get('WOS_CHROME_USER_DATA_DIR', '').strip()
CDP_ENDPOINT = os.environ.get('WOS_CDP_ENDPOINT', '').strip()
KEEP_BROWSER_OPEN = os.environ.get('WOS_KEEP_BROWSER_OPEN', '').lower() in {'1', 'true', 'yes'}

HUMAN_VERIFICATION_PATTERNS = [
    ('unusual_activity', 'unusual activity coming from your institution'),
    ('verify_human', 'please verify you are human'),
    ('challenge_expired', 'the challenge has expired'),
    ('customer_support_challenge', "can't solve this? contact customer support"),
    ('captcha', 'captcha'),
    ('turing', 'turing'),
]


class BrowserHandle:
    def __init__(self, context, browser=None, mode: str = 'new_context'):
        self.context = context
        self.browser = browser
        self.mode = mode

    def close(self) -> None:
        if KEEP_BROWSER_OPEN:
            return
        try:
            self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass


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
    text = re.sub(r'[A-Z]{2,3}\d[A-Z0-9]{20,}', '[REDACTED_SID]', text)
    text = re.sub(r'("(?:SID|ReportingID|session|wos_sid|UserAuthID|AuthEnvID)"\s*:\s*")([^"]+)(")', r'\1[REDACTED]\3', text)
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


def human_verification_info(sample: str | None) -> dict | None:
    text = (sample or '').lower()
    hits = [code for code, pattern in HUMAN_VERIFICATION_PATTERNS if pattern in text]
    if not hits:
        return None
    return {
        'required': True,
        'signals': hits,
        'message': 'Web of Science is asking for human verification; live DOM records cannot be collected in this non-interactive run.',
    }


def cookie_names_from_header(value: str) -> list[str]:
    names = []
    for chunk in (value or '').split(';'):
        if '=' in chunk:
            name = chunk.split('=', 1)[0].strip()
            if name and name not in names:
                names.append(name)
    return names


def sanitize_headers(headers: dict[str, str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (headers or {}).items():
        lk = key.lower()
        if lk in {'cookie', 'authorization'}:
            out[lk + '_names'] = cookie_names_from_header(value) if lk == 'cookie' else '[REDACTED]'
        elif lk in {
            'user-agent', 'accept', 'accept-language', 'accept-encoding', 'sec-ch-ua',
            'sec-ch-ua-mobile', 'sec-ch-ua-platform', 'sec-fetch-site', 'sec-fetch-mode',
            'sec-fetch-user', 'sec-fetch-dest', 'upgrade-insecure-requests', 'priority',
            'content-type', 'origin', 'referer'
        }:
            out[lk] = value
    return out


def attach_network_probe(page, report: dict) -> None:
    events = []
    report['network_events_sample'] = events

    def add_event(kind: str, payload: dict) -> None:
        if len(events) >= 60:
            return
        url = payload.get('url') or ''
        if 'webofscience.com' not in url and 'webofknowledge.com' not in url and 'clarivate' not in url:
            return
        events.append({'kind': kind, **payload})

    def on_request(req):
        try:
            add_event('request', {
                'method': req.method,
                'resource_type': req.resource_type,
                'url': req.url[:500],
                'headers': sanitize_headers(req.headers),
            })
        except Exception:
            pass

    def on_response(resp):
        try:
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            add_event('response', {
                'status': resp.status,
                'url': resp.url[:500],
                'headers': {k: hdrs.get(k) for k in ['content-type', 'server', 'cf-ray', 'cf-cache-status', 'set-cookie'] if hdrs.get(k)},
            })
        except Exception:
            pass

    try:
        page.on('request', on_request)
        page.on('response', on_response)
    except Exception:
        pass


def selector_counts(page) -> dict:
    selectors = {
        'app_record': 'app-record',
        'summary_item': '.summary-item',
        'author_metric': '.wat-author-metric-inline-block',
        'app_author_profile': 'app-author-profile',
        'spinner': 'mat-progress-spinner, .cdx-spinner, .wat-spinner',
        'cookie_banner': '#onetrust-banner-sdk',
        'free_view_dialog': 'mat-dialog-container, .cdk-overlay-container',
    }
    out = {}
    for key, selector in selectors.items():
        try:
            out[key] = page.locator(selector).count()
        except Exception:
            out[key] = None
    return out


def body_text_sample(page, limit: int = 1600) -> str:
    try:
        return re.sub(r'\s+', ' ', page.locator('body').inner_text(timeout=3000))[:limit]
    except Exception:
        return ''


def browser_environment(page) -> dict:
    try:
        return page.evaluate(
            """async () => {
              const out = {
                userAgent: navigator.userAgent,
                webdriver: navigator.webdriver,
                platform: navigator.platform,
                languages: navigator.languages,
                language: navigator.language,
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                maxTouchPoints: navigator.maxTouchPoints,
                pluginsLength: navigator.plugins ? navigator.plugins.length : null,
                mimeTypesLength: navigator.mimeTypes ? navigator.mimeTypes.length : null,
                screen: {width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight, colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth},
                inner: {width: innerWidth, height: innerHeight, devicePixelRatio},
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                userAgentData: null,
                webgl: null,
              };
              try {
                if (navigator.userAgentData) {
                  out.userAgentData = {
                    brands: navigator.userAgentData.brands,
                    mobile: navigator.userAgentData.mobile,
                    platform: navigator.userAgentData.platform,
                    highEntropy: await navigator.userAgentData.getHighEntropyValues(['architecture','bitness','fullVersionList','model','platformVersion','uaFullVersion','wow64']).catch(e => null)
                  };
                }
              } catch(e) {}
              try {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                const dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
                if (gl && dbg) out.webgl = {vendor: gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL), renderer: gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)};
              } catch(e) {}
              return out;
            }"""
        )
    except Exception as exc:
        return {'error': repr(exc)}


def page_is_not_found(page) -> bool:
    sample = body_text_sample(page, 800).lower()
    return "this page doesn't exist" in sample or 'this page does not exist' in sample


def save_diagnostics(page, html: str | None, report: dict, label: str) -> None:
    base.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = base.ARTIFACT_DIR / f'wos_{base.RESEARCHER_ID}_{base.stamp()}_{label}'
    sample = body_text_sample(page)
    payload = {
        'label': label,
        'url': page.url,
        'title': None,
        'selector_counts': selector_counts(page),
        'content_length': len((html or '').encode('utf-8', errors='replace')),
        'human_verification': human_verification_info(sample),
        'browser_environment': browser_environment(page),
        'network_events_sample': report.get('network_events_sample', [])[-30:],
        'body_text_sample': sample,
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


def click_optional(page, selectors: list[str], report: dict, key: str) -> None:
    for selector in selectors:
        try:
            target = page.locator(selector).first
            if target.count() and target.is_visible(timeout=1000):
                target.click(timeout=2500)
                report[key] = selector
                return
        except Exception:
            pass


def dismiss_overlays(page, report: dict) -> None:
    click_optional(
        page,
        ['#onetrust-accept-btn-handler', 'button:has-text("Accept All")', 'button:has-text("Accept all")'],
        report,
        'cookie_banner_clicked',
    )
    click_optional(
        page,
        ['button:has-text("Got it")', 'button:has-text("Got It")', 'button:has-text("OK")'],
        report,
        'free_view_dialog_clicked',
    )


def navigate_candidate(page, report: dict, reason: str, candidate_url: str | None = None) -> None:
    target = candidate_url or ROUTE_CANDIDATES[0]
    current = page.url
    report.setdefault('route_forcing', []).append({'reason': reason, 'from': current, 'to': target})
    try:
        page.goto(target, wait_until='domcontentloaded', timeout=max(base.WAIT_SEC, 60) * 1000)
        dismiss_overlays(page, report)
    except Exception as exc:
        report.setdefault('route_forcing_errors', []).append({'reason': reason, 'target': target, 'error': repr(exc), 'current_url': page.url})


def recover_route_if_needed(page, report: dict, reason: str) -> None:
    # Do not force a fragile deep route by default. The successful saved page URL
    # is /wos/author/record/<RID>; the claimed route is only tried when explicitly
    # supplied through WOS_CLAIMED_PROFILE_URL.
    if is_transfer_url(page.url) or '/author/record/' not in page.url or page_is_not_found(page):
        navigate_candidate(page, report, reason, ROUTE_CANDIDATES[0])
    if page_is_not_found(page) and len(ROUTE_CANDIDATES) > 1:
        navigate_candidate(page, report, reason + '_optional_claimed', ROUTE_CANDIDATES[1])


def create_browser_context(p, report: dict) -> BrowserHandle:
    headless = os.environ.get('WOS_BROWSER_HEADLESS', 'false').lower() not in {'0', 'false', 'no'}
    channel = os.environ.get('WOS_BROWSER_CHANNEL', 'chrome').strip() or None
    common = {
        'locale': 'en-US',
        'timezone_id': 'Europe/Moscow',
        'viewport': {'width': 1440, 'height': 1400},
    }
    # In persistent/local modes, avoid forcing a synthetic UA unless the caller set
    # WOS_USER_AGENT explicitly. The goal is to use the local browser as-is.
    if os.environ.get('WOS_USER_AGENT') or not (PERSISTENT_USER_DATA_DIR or CDP_ENDPOINT):
        common['user_agent'] = USER_AGENT

    if CDP_ENDPOINT:
        browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
        context = browser.contexts[0] if browser.contexts else browser.new_context(**common)
        report['browser_mode'] = 'cdp_existing_browser'
        report['cdp_endpoint_present'] = True
        return BrowserHandle(context=context, browser=browser, mode='cdp')

    launch_args = ['--disable-dev-shm-usage', '--no-sandbox']
    launch_kwargs: dict[str, Any] = {'headless': headless, 'args': launch_args}
    if channel:
        launch_kwargs['channel'] = channel

    if PERSISTENT_USER_DATA_DIR:
        Path(PERSISTENT_USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
        try:
            context = p.chromium.launch_persistent_context(PERSISTENT_USER_DATA_DIR, **launch_kwargs, **common)
        except Exception as exc:
            report['persistent_context_launch_error'] = repr(exc)
            launch_kwargs.pop('channel', None)
            context = p.chromium.launch_persistent_context(PERSISTENT_USER_DATA_DIR, **launch_kwargs, **common)
            report['channel_fallback'] = 'bundled_chromium'
        report['browser_mode'] = 'persistent_context'
        report['persistent_user_data_dir_present'] = True
        return BrowserHandle(context=context, mode='persistent')

    try:
        browser = p.chromium.launch(**launch_kwargs)
    except Exception as exc:
        report['browser_launch_error'] = repr(exc)
        launch_kwargs.pop('channel', None)
        browser = p.chromium.launch(**launch_kwargs)
        report['channel_fallback'] = 'bundled_chromium'

    state_path = base.storage_state_path_from_secret(report)
    if state_path:
        common['storage_state'] = state_path
    context = browser.new_context(**common)
    if base.WOS_COOKIE:
        try:
            cookies = prod.cookie_header_to_playwright(base.WOS_COOKIE)
            context.add_cookies(cookies)
            report['input_state']['cookie_names'] = sorted({c['name'] for c in cookies})
            report['input_state']['cookie_domains_count'] = len(cookies)
        except Exception as exc:
            report['input_state']['cookie_add_error'] = repr(exc)
    report['browser_mode'] = 'new_context'
    return BrowserHandle(context=context, browser=browser, mode='new_context')


def browser_dom_first(previous):
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return None, {'status': 'playwright_import_failed', 'error': repr(exc)}, None

    report = {
        'route': 'browser_dom_first_public_profile_route',
        'url': base.URL,
        'public_profile_url': PUBLIC_PROFILE_URL,
        'optional_claimed_url': OPTIONAL_CLAIMED_URL or None,
        'dom_wait_sec': DOM_WAIT_SEC,
        'input_state': {
            'cookie_secret_present': bool(base.WOS_COOKIE),
            'storage_state_secret_present': bool(base.WOS_STORAGE_STATE_B64),
            'persistent_user_data_dir_env_present': bool(PERSISTENT_USER_DATA_DIR),
            'cdp_endpoint_env_present': bool(CDP_ENDPOINT),
        },
    }
    progress = []

    with sync_playwright() as p:
        handle = create_browser_context(p, report)
        context = handle.context
        page = context.new_page()
        attach_network_probe(page, report)
        try:
            page.goto(base.URL, wait_until='domcontentloaded', timeout=max(base.WAIT_SEC, 60) * 1000)
            report['browser_environment_initial'] = browser_environment(page)
            dismiss_overlays(page, report)
            recover_route_if_needed(page, report, 'after_initial_goto')
            try:
                page.wait_for_selector('app-record', timeout=45000)
            except Exception as exc:
                report['initial_app_record_wait'] = repr(exc)
                recover_route_if_needed(page, report, 'after_initial_app_record_timeout')

            html = ''
            best_dom = None
            for elapsed in range(0, DOM_WAIT_SEC + 1, 5):
                if elapsed:
                    page.wait_for_timeout(5000)
                if elapsed in {0, 15, 30, 60, 120}:
                    recover_route_if_needed(page, report, f'periodic_route_check_{elapsed}s')
                dismiss_overlays(page, report)
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
                sample = body_text_sample(page, 900)
                human = human_verification_info(sample)
                item = {
                    'elapsed_sec': elapsed,
                    'url': page.url,
                    'selector_counts': selector_counts(page),
                    'not_found': "This page doesn't exist" in sample,
                    'human_verification': human,
                    'parsed_records': dom_records,
                    'parsed_records_or_publications': prod.normalized_count(dom_data),
                    'content_length': len((html or '').encode('utf-8', errors='replace')),
                    'body_text_sample': sample,
                }
                progress.append(item)
                report['dom_progress_tail'] = progress[-8:]
                report['candidate_dom_records'] = dom_records
                report['candidate_dom_records_or_publications'] = prod.normalized_count(dom_data)
                if dom_records:
                    best_dom = dom_data
                if human and not dom_records:
                    report.update({
                        'status': 'human_verification_required',
                        'human_verification': human,
                        'elapsed_sec': elapsed,
                        'records': prod.records_count(best_dom),
                        'records_or_publications': prod.normalized_count(best_dom),
                        'final_url': page.url,
                        'content_length': len((html or '').encode('utf-8', errors='replace')),
                        'dom_progress_tail': progress[-8:],
                    })
                    save_diagnostics(page, html, report, 'human_verification_required')
                    handle.close()
                    return html or None, report, best_dom
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
                        'dom_progress_tail': progress[-8:],
                    })
                    save_diagnostics(page, html, report, 'success_dom_records')
                    handle.close()
                    return html, report, dom_data

            report.update({
                'status': 'no_records' if not best_dom else 'partial_records',
                'records': prod.records_count(best_dom),
                'records_or_publications': prod.normalized_count(best_dom),
                'final_url': page.url,
                'content_length': len((html or '').encode('utf-8', errors='replace')),
                'dom_progress_tail': progress[-8:],
            })
            save_diagnostics(page, html, report, 'failure_no_dom_records')
            handle.close()
            return html or None, report, best_dom
        except Exception as exc:
            html = safe_page_content(page)
            candidate = base.carry_forward_metrics(base.parse_wos_author_profile_html(html, base.RESEARCHER_ID), previous) if html else None
            report.update({
                'status': 'error',
                'error': repr(exc),
                'records': prod.records_count(candidate),
                'records_or_publications': prod.normalized_count(candidate),
                'dom_progress_tail': progress[-8:],
            })
            try:
                save_diagnostics(page, html, report, 'error')
            except Exception:
                pass
            handle.close()
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


def preserved_or_snapshot(previous, report: dict, source_label: str):
    candidate = best_saved_snapshot(previous, report)
    if candidate:
        report['used_source'] = source_label + '_saved_snapshot'
        return prod.preserve_best_records(candidate, previous, report)
    if previous:
        report['used_source'] = source_label + '_previous_normalized_json'
        return previous
    return None


def main() -> int:
    base.OUT.parent.mkdir(parents=True, exist_ok=True)
    base.REPORT.parent.mkdir(parents=True, exist_ok=True)
    base.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    base.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    previous = base.read_json(base.OUT, None)
    report: dict = {
        'generated_at': base.now(),
        'strategy': 'dom_first_public_profile_route',
        'previous_records': prod.records_count(previous),
        'previous_records_or_publications': prod.normalized_count(previous),
    }

    html, browser_report, live_data = browser_dom_first(previous)
    report['browser'] = browser_report

    if browser_report.get('status') == 'human_verification_required':
        report['human_verification_required'] = True
        data = preserved_or_snapshot(previous, report, 'human_verification')
        if data is None:
            report['used_source'] = 'none'
            report['error'] = 'Web of Science requires human verification and no saved WoS data is available.'
            base.write_json(base.REPORT, report)
            return 1
    elif live_data and prod.records_count(live_data):
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
        data = preserved_or_snapshot(previous, report, 'saved_snapshot')
        if data is None:
            report['used_source'] = 'none'
            report['error'] = 'No live Web of Science DOM records, no saved valid snapshot and no previous normalized JSON.'
            base.write_json(base.REPORT, report)
            return 1

    return write_result(data, report)


if __name__ == '__main__':
    raise SystemExit(main())
