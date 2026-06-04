#!/usr/bin/env python3
"""DOM-first production entrypoint for Web of Science profiles.

WoS Free View can render the author profile records directly into the page as
`app-record` nodes. The safest path is therefore:
1. open the public Researcher Profile page in a real browser context;
2. wait for the rendered `app-record` DOM;
3. parse those records directly from page.content();
4. only then fall back to the WOSNX endpoint diagnostics.
"""
from __future__ import annotations

import os

import harvest_wos_author_profile_production as prod

base = prod.base
USER_AGENT = prod.USER_AGENT


def safe_page_content(page) -> str:
    try:
        return page.content()
    except Exception:
        try:
            page.wait_for_load_state('domcontentloaded', timeout=5000)
            return page.content()
        except Exception:
            return ''


def good_dom_records(data: dict | None) -> bool:
    return prod.records_count(data) >= max(1, min(prod.summary_publications(data) or 10, 10))


def browser_dom_first(previous):
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return None, {'status': 'playwright_import_failed', 'error': repr(exc)}, None

    report = {
        'route': 'browser_dom_first_then_wosnx',
        'url': base.URL,
        'input_state': {
            'cookie_secret_present': bool(base.WOS_COOKIE),
            'storage_state_secret_present': bool(base.WOS_STORAGE_STATE_B64),
        },
    }
    api_reports = []
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
            'viewport': {'width': 1440, 'height': 1100},
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
            page.goto(base.URL, wait_until='domcontentloaded', timeout=max(base.WAIT_SEC, 45) * 1000)
            html = ''
            best_dom = None
            best_api = None
            try:
                page.wait_for_selector('app-record', timeout=20000)
            except Exception as exc:
                report['initial_app_record_wait'] = repr(exc)

            for elapsed in range(0, base.WAIT_SEC + 1, 3):
                if elapsed:
                    page.wait_for_timeout(3000)
                try:
                    page.mouse.wheel(0, 1200)
                except Exception:
                    pass

                html = safe_page_content(page)
                if html:
                    dom_data = base.carry_forward_metrics(base.parse_wos_author_profile_html(html, base.RESEARCHER_ID), previous)
                    dom_records = prod.records_count(dom_data)
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
                            'api_reports': api_reports[-12:],
                        })
                        context.close(); browser.close()
                        return html, report, dom_data

                # Fallback diagnostic: use the live page to make the WOSNX call with
                # its fresh SID/cookies. This is not the primary path anymore.
                try:
                    state_info = prod.extract_browser_state(page)
                    sid = state_info.get('sid')
                    body = prod.run_query_body(None, state_info.get('search'), state_info.get('hits'))
                    if sid:
                        fetch_result = page.evaluate(
                            """async ({sid, body}) => {
                              const res = await fetch('/api/wosnx/core/runQuerySearch?SID=' + encodeURIComponent(sid), {
                                method: 'POST', credentials: 'include',
                                headers: {'Accept': 'application/x-ndjson', 'Content-Type': 'text/plain;charset=UTF-8'},
                                body: JSON.stringify(body)
                              });
                              return {status: res.status, contentType: res.headers.get('content-type') || '', text: await res.text()};
                            }""",
                            {'sid': sid, 'body': body},
                        )
                        text = fetch_result.get('text') or ''
                        api_data = base.carry_forward_metrics(base.parse_wosnx_ndjson(text, base.RESEARCHER_ID), previous)
                        item = {
                            'elapsed_sec': elapsed,
                            'sid_present': True,
                            'search_id': state_info.get('searchId'),
                            'request_count': (body.get('retrieve') or {}).get('count'),
                            'status': fetch_result.get('status'),
                            'content_type': fetch_result.get('contentType'),
                            'bytes': len(text.encode('utf-8', errors='replace')),
                            'excerpt': text[:800],
                            'records': prod.records_count(api_data),
                            'records_or_publications': prod.normalized_count(api_data),
                        }
                        api_reports.append(item)
                        if prod.records_count(api_data):
                            best_api = api_data
                            report.update({
                                'status': 'ok',
                                'used_subroute': 'browser_context_wosnx_fetch',
                                'elapsed_sec': elapsed,
                                'records': prod.records_count(api_data),
                                'records_or_publications': prod.normalized_count(api_data),
                                'final_url': page.url,
                                'api_reports': api_reports[-12:],
                            })
                            context.close(); browser.close()
                            return html, report, api_data
                except Exception as exc:
                    api_reports.append({'elapsed_sec': elapsed, 'error': repr(exc)})

            fallback = best_dom or best_api
            report.update({
                'status': 'no_records' if not fallback else 'partial_records',
                'records': prod.records_count(fallback),
                'records_or_publications': prod.normalized_count(fallback),
                'api_reports': api_reports[-12:],
                'final_url': page.url,
                'content_length': len((html or '').encode('utf-8', errors='replace')),
            })
            context.close(); browser.close()
            return html or None, report, fallback
        except Exception as exc:
            html = safe_page_content(page)
            candidate = base.carry_forward_metrics(base.parse_wos_author_profile_html(html, base.RESEARCHER_ID), previous) if html else None
            report.update({'status': 'error', 'error': repr(exc), 'records': prod.records_count(candidate), 'records_or_publications': prod.normalized_count(candidate), 'api_reports': api_reports[-12:]})
            context.close(); browser.close()
            return html or None, report, candidate


def main() -> int:
    prod.base.fetch_live_browser = browser_dom_first
    prod.browser_wosnx = browser_dom_first
    return prod.main()


if __name__ == '__main__':
    raise SystemExit(main())
