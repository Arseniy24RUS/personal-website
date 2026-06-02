#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_wos_author_profile import parse_wos_author_profile_html  # noqa: E402

RESEARCHER_ID = os.environ.get('WOS_RESEARCHER_ID', 'AAG-1530-2021')
PROFILE_URL = os.environ.get('WOS_PROFILE_URL', f'https://www.webofscience.com/wos/author/record/{RESEARCHER_ID}')
OUT = Path(os.environ.get('WOS_PROFILE_OUT', 'data/wos/profile_metrics_live_test.json'))
REPORT = Path(os.environ.get('WOS_HARVEST_REPORT', 'data/wos/live_test_report.json'))
ARTIFACT_DIR = Path(os.environ.get('WOS_TEST_ARTIFACT_DIR', 'artifacts/wos_debug'))
SNAPSHOT_DIR = Path(os.environ.get('WOS_SNAPSHOT_DIR', 'data/snapshots/wos'))
WAIT_SEC = int(os.environ.get('WOS_BROWSER_WAIT_SEC', '180'))
MIN_RECORDS = int(os.environ.get('WOS_MIN_RECORDS', '10'))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def clean(text: str | None) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', errors='replace')
    return str(path)


def write_json(path: Path, payload) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)


def html_markers(html: str) -> dict:
    text = html or ''
    return {
        'content_length': len(text.encode('utf-8', errors='replace')),
        'has_session_data': 'window.sessionData' in text,
        'has_free_view': 'Web of Science Free View' in text or 'AccessLevel":"FREE' in text,
        'has_summary_items': 'summary-item' in text,
        'has_metric_blocks': 'wat-author-metric' in text,
        'has_records': 'app-record' in text,
        'has_cookie_banner': 'onetrust' in text.lower(),
        'excerpt': clean(text[:1400]),
    }


def session_summary(page):
    try:
        return page.evaluate("""() => {
            const s = window.sessionData || null;
            if (!s) return null;
            return {
              accessLevel: s.BasicProperties && s.BasicProperties.AccessLevel,
              product: s.BasicProperties && s.BasicProperties.Product,
              customerName: s.BasicProperties && s.BasicProperties.CustomerName,
              sidPresent: !!(s.BasicProperties && s.BasicProperties.SID),
              authType: s.LoginData && s.LoginData.UserAuthType,
              sessionLength: s.LoginData && s.LoginData.SessionLength
            };
        }""")
    except Exception as exc:
        return {'error': repr(exc)}


def count_dom(page) -> dict:
    selectors = {
        'summary_items': '.summary-item',
        'metric_blocks': '.wat-author-metric-inline-block',
        'records': 'app-record',
        'spinners': 'mat-spinner, .wat-spinner, .spinner-lightbox',
        'cookie_accept_buttons': '#onetrust-accept-btn-handler',
    }
    out = {}
    for name, selector in selectors.items():
        try:
            out[name] = page.locator(selector).count()
        except Exception as exc:
            out[name] = f'error: {exc!r}'
    return out


def click_cookie_banner(page, report):
    for selector in ['#onetrust-accept-btn-handler', 'button:has-text("Accept All")', 'button:has-text("Accept")']:
        try:
            button = page.locator(selector).first
            if button.count() and button.is_visible(timeout=1000):
                button.click(timeout=3000)
                report.setdefault('actions', []).append({'action': 'cookie_banner_click', 'selector': selector})
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue
    return False


def main() -> int:
    from playwright.sync_api import sync_playwright

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    t = stamp()
    har_path = ARTIFACT_DIR / f'wos_profile_{t}.har'
    headless = os.environ.get('WOS_BROWSER_HEADLESS', 'false').lower() not in {'0', 'false', 'no'}
    channel = os.environ.get('WOS_BROWSER_CHANNEL', 'chrome').strip() or None

    failures, responses, console = [], [], []
    report = {
        'generated_at': now(),
        'route': 'wos_free_view_profile_live_test',
        'researcher_id': RESEARCHER_ID,
        'profile_url': PROFILE_URL,
        'min_records': MIN_RECORDS,
        'browser': {'headless': headless, 'channel': channel},
        'artifacts': {'har_path': str(har_path)},
    }

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
            report['browser']['channel_fallback'] = 'bundled_chromium'

        context = browser.new_context(
            locale='en-US',
            timezone_id='Europe/Moscow',
            viewport={'width': 1440, 'height': 1200},
            record_har_path=str(har_path),
            record_har_content='embed',
        )
        page = context.new_page()
        page.on('requestfailed', lambda req: failures.append({'url': req.url, 'method': req.method, 'failure': req.failure} if len(failures) < 100 else None))
        page.on('response', lambda resp: responses.append({'url': resp.url, 'status': resp.status, 'content_type': resp.headers.get('content-type', '')} if len(responses) < 180 else None))
        page.on('console', lambda msg: console.append({'type': msg.type, 'text': msg.text[:500]} if len(console) < 120 else None))

        try:
            page.goto(PROFILE_URL, wait_until='domcontentloaded', timeout=max(45, WAIT_SEC) * 1000)
        except Exception as exc:
            report['goto_error'] = repr(exc)

        page.wait_for_timeout(2000)
        click_cookie_banner(page, report)

        first_html = page.content()
        report['first_checkpoint'] = {
            'url': page.url,
            'title': clean(page.title()),
            'dom_counts': count_dom(page),
            'session': session_summary(page),
            'markers': html_markers(first_html),
            'html_path': write_text(ARTIFACT_DIR / f'wos_profile_{t}_first.html', first_html),
        }
        try:
            screenshot = ARTIFACT_DIR / f'wos_profile_{t}_first.png'
            page.screenshot(path=str(screenshot), full_page=True, timeout=30000)
            report['first_checkpoint']['screenshot_path'] = str(screenshot)
        except Exception as exc:
            report['first_checkpoint']['screenshot_error'] = repr(exc)

        ready = False
        last_html = first_html
        timeline = []
        parsed = None
        for elapsed in range(0, WAIT_SEC + 1, 5):
            if elapsed:
                page.wait_for_timeout(5000)
            try:
                page.mouse.wheel(0, 1000)
            except Exception:
                pass
            last_html = page.content()
            parsed = parse_wos_author_profile_html(last_html, RESEARCHER_ID)
            records_count = len(parsed.get('records') or [])
            summary = parsed.get('summary') or {}
            point = {
                'elapsed_sec': elapsed,
                'url': page.url,
                'title': clean(page.title()),
                'dom_counts': count_dom(page),
                'records_count': records_count,
                'summary': summary,
                'markers': html_markers(last_html),
            }
            timeline.append(point)
            if records_count >= MIN_RECORDS and summary.get('publications') is not None and summary.get('h_index') is not None:
                ready = True
                report['ready_checkpoint'] = point
                break

        final_html_path = write_text(ARTIFACT_DIR / f'wos_profile_{t}_final.html', last_html)
        snapshot_path = write_text(SNAPSHOT_DIR / f'author_profile_{RESEARCHER_ID}_{t}_live_test.html', last_html)
        report['final_checkpoint'] = {
            'url': page.url,
            'title': clean(page.title()),
            'dom_counts': count_dom(page),
            'session': session_summary(page),
            'markers': html_markers(last_html),
            'html_path': final_html_path,
            'snapshot_path': snapshot_path,
        }
        try:
            screenshot = ARTIFACT_DIR / f'wos_profile_{t}_final.png'
            page.screenshot(path=str(screenshot), full_page=True, timeout=30000)
            report['final_checkpoint']['screenshot_path'] = str(screenshot)
        except Exception as exc:
            report['final_checkpoint']['screenshot_error'] = repr(exc)
        try:
            storage_path = ARTIFACT_DIR / f'wos_profile_{t}_storage_state.json'
            context.storage_state(path=str(storage_path))
            report['artifacts']['storage_state_path'] = str(storage_path)
        except Exception as exc:
            report['artifacts']['storage_state_error'] = repr(exc)
        context.close()
        browser.close()

    report['timeline'] = timeline[-12:]
    report['request_failures'] = [x for x in failures if x][-100:]
    report['responses'] = [x for x in responses if x][-180:]
    report['console_messages'] = [x for x in console if x][-120:]
    report['status'] = 'ok' if ready else 'not_ready'
    parsed = parsed or parse_wos_author_profile_html(last_html, RESEARCHER_ID)
    if ready:
        write_json(OUT, parsed)
        report['out'] = str(OUT)
    report['records'] = len(parsed.get('records') or [])
    report['summary'] = parsed.get('summary')
    write_json(REPORT, report)
    print(json.dumps({'status': report['status'], 'records': report['records'], 'summary': report['summary'], 'report': str(REPORT)}, ensure_ascii=False, indent=2))
    return 0 if ready else 2


if __name__ == '__main__':
    raise SystemExit(main())
