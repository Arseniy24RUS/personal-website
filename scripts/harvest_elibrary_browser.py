#!/usr/bin/env python3
"""Browser-based eLibrary harvester for delayed/JS-loaded public pages.

The ordinary urllib fetcher is intentionally kept as a cheap first/fallback
mechanism, but eLibrary can return a short intermediate loading page before the
real author profile/list appears. This script uses headless Chromium through
Playwright, waits for the real markers and then saves the same normalized JSON
outputs as the ordinary harvesters.

The author publication list is fetched through the same legitimate navigation
path used by a human researcher: defaultx.asp -> authors.asp -> fill the
surname/name field -> press Search -> click the publication-count link for the
matched author. Direct author_items URLs are used only as a fallback.
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
AUTHOR_SEARCH_NAME = os.environ.get('ELIBRARY_AUTHOR_SEARCH_NAME', 'Ситковский Арсений Михайлович')
AUTHORS_URL = os.environ.get('ELIBRARY_AUTHORS_URL', 'https://www.elibrary.ru/authors.asp')
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


def normalize_url(value: str) -> str:
    if not value:
        return ''
    value = value.strip()
    if value.lower().startswith('javascript:'):
        return ''
    return urljoin('https://www.elibrary.ru/', value)


def fill_author_search_form(page, report: dict) -> bool:
    started = time.time()
    page.goto(AUTHORS_URL, wait_until='domcontentloaded', timeout=max(WAIT_SEC, 45) * 1000, referer='https://www.elibrary.ru/defaultx.asp')
    page.wait_for_timeout(2500)
    fill_info = page.evaluate(
        """
        (value) => {
          const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
          const inputs = Array.from(document.querySelectorAll('input'))
            .filter(el => {
              const type = (el.getAttribute('type') || 'text').toLowerCase();
              return !el.disabled && visible(el) && ['text', 'search', ''].includes(type);
            });
          function contextText(el) {
            let node = el;
            const parts = [];
            for (let i = 0; i < 5 && node; i += 1) {
              parts.push(node.innerText || node.textContent || '');
              node = node.parentElement;
            }
            return parts.join(' ');
          }
          const ranked = inputs.map((input, idx) => {
            const ctx = contextText(input);
            const attrs = [input.name, input.id, input.placeholder, input.title, input.className].join(' ');
            let score = 0;
            if (/Фамилия/i.test(ctx)) score += 100;
            if (/автор|author|surname|family|fio|name|ftext|f_name/i.test(attrs)) score += 20;
            return {input, idx, score, ctx, attrs};
          }).sort((a,b) => b.score - a.score || a.idx - b.idx);
          const chosen = ranked.length ? ranked[0].input : null;
          if (!chosen) return {ok: false, reason: 'no_visible_text_input', inputs: inputs.length};
          chosen.focus();
          chosen.value = value;
          chosen.dispatchEvent(new Event('input', {bubbles: true}));
          chosen.dispatchEvent(new Event('change', {bubbles: true}));
          window.__elibrary_author_search_input = chosen;
          return {
            ok: true,
            name: chosen.getAttribute('name') || '',
            id: chosen.id || '',
            inputs: inputs.length,
            score: ranked[0].score,
            row: ranked[0].ctx.slice(0, 500),
            attrs: ranked[0].attrs,
            outerHTML: chosen.outerHTML.slice(0, 500)
          };
        }
        """,
        AUTHOR_SEARCH_NAME,
    )
    report['fill_author_search'] = fill_info
    if not fill_info or not fill_info.get('ok'):
        report['elapsed_sec'] = round(time.time() - started, 3)
        return False
    click_info = page.evaluate(
        """
        () => {
          const input = window.__elibrary_author_search_input;
          const root = input && input.form ? input.form : document;
          const controls = Array.from(root.querySelectorAll('input, button, a, img'));
          const searchControl = controls.find(el => {
            const text = [
              el.value || '',
              el.innerText || '',
              el.textContent || '',
              el.title || '',
              el.alt || '',
              el.getAttribute('onclick') || ''
            ].join(' ');
            return /Поиск|Найти|Search/i.test(text);
          });
          if (searchControl) {
            searchControl.click();
            return {
              ok: true,
              tag: searchControl.tagName,
              type: searchControl.getAttribute('type') || '',
              value: searchControl.value || '',
              text: (searchControl.innerText || searchControl.textContent || searchControl.title || searchControl.alt || '').slice(0, 120)
            };
          }
          if (input && input.form) {
            input.form.submit();
            return {ok: true, submitted_form: true};
          }
          return {ok: false, reason: 'search_button_not_found'};
        }
        """
    )
    report['click_author_search'] = click_info
    if not click_info or not click_info.get('ok'):
        try:
            page.keyboard.press('Enter')
            report['enter_fallback'] = True
        except Exception as exc:
            report['enter_fallback_error'] = repr(exc)
    try:
        page.wait_for_load_state('domcontentloaded', timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(8000)
    report['elapsed_sec'] = round(time.time() - started, 3)
    report['final_url'] = page.url
    return True


def collect_author_result_links(page) -> list[dict]:
    try:
        return page.eval_on_selector_all(
            'a[href], a[onclick], input[onclick], button[onclick], img[onclick]',
            """
            (els) => els.map(el => {
              const row = el.closest('tr') ? el.closest('tr').innerText : '';
              return {
                href: el.getAttribute('href') || '',
                abs: el.href || '',
                onclick: el.getAttribute('onclick') || '',
                text: (el.innerText || el.textContent || el.value || el.title || el.alt || '').trim(),
                row
              };
            })
            """,
        )
    except Exception:
        return []


def extract_author_items_url(link: dict) -> str:
    href = link.get('abs') or link.get('href') or ''
    onclick = link.get('onclick') or ''
    combined = href + ' ' + onclick
    if AUTHOR_ID not in combined and f'id={AUTHOR_ID}' not in combined:
        return ''
    if 'author_items.asp' in href:
        return normalize_url(href)
    if 'author_items.asp' in onclick:
        match = re.search(r"author_items\.asp\?[^'\"\s)]+", onclick)
        if match:
            return normalize_url(match.group(0))
    return ''


def fetch_items_via_authors_search(context, report: dict) -> tuple[str, dict]:
    page = context.new_page()
    started = time.time()
    search_report: dict = {
        'source': 'authors_search_path',
        'authors_url': AUTHORS_URL,
        'search_name': AUTHOR_SEARCH_NAME,
        'status': 'started',
    }
    try:
        if not fill_author_search_form(page, search_report):
            html = page.content()
            search_report.update({
                'status': 'form_fill_failed',
                'elapsed_sec': round(time.time() - started, 3),
                'fingerprint': fingerprint(html, page.url),
                'debug': save_debug(page, html, 'authors_search_form_fill_failed'),
            })
            report['authors_search_path'] = search_report
            return html, search_report

        links: list[dict] = []
        deadline = time.time() + WAIT_SEC
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            html = page.content()
            if has_captcha(html, page.url):
                search_report.update({
                    'status': 'captcha',
                    'elapsed_sec': round(time.time() - started, 3),
                    'final_url': page.url,
                    'fingerprint': fingerprint(html, page.url),
                    'debug': save_debug(page, html, 'authors_search_captcha'),
                })
                report['authors_search_path'] = search_report
                return html, search_report
            links = collect_author_result_links(page)
            item_links = [(link, extract_author_items_url(link)) for link in links]
            item_links = [(link, url) for link, url in item_links if url]
            if item_links:
                break
        search_report['result_links_total'] = len(links)
        search_report['result_links_sample'] = [{
            'href': (link.get('href') or '')[:220],
            'onclick': (link.get('onclick') or '')[:220],
            'text': (link.get('text') or '')[:120],
            'row': (link.get('row') or '')[:300],
            'items_url': extract_author_items_url(link),
        } for link in links[:30]]
        item_links = [(link, extract_author_items_url(link)) for link in links]
        item_links = [(link, url) for link, url in item_links if url]
        if not item_links:
            html = page.content()
            search_report.update({
                'status': 'author_items_link_not_found',
                'elapsed_sec': round(time.time() - started, 3),
                'final_url': page.url,
                'fingerprint': fingerprint(html, page.url),
                'debug': save_debug(page, html, 'authors_search_no_items_link'),
            })
            report['authors_search_path'] = search_report
            return html, search_report

        selected_link, target_url = item_links[0]
        search_report['selected_author_items_url'] = target_url
        search_report['selected_author_items_text'] = selected_link.get('text') or ''
        search_report['selected_author_row'] = (selected_link.get('row') or '')[:500]
        try:
            selector = f'a[href*="author_items.asp"][href*="{AUTHOR_ID}"]'
            if page.locator(selector).count() > 0:
                page.locator(selector).first().click(timeout=15000)
                page.wait_for_load_state('domcontentloaded', timeout=60000)
            else:
                page.goto(target_url, wait_until='domcontentloaded', timeout=max(WAIT_SEC, 45) * 1000, referer=AUTHORS_URL)
        except Exception as exc:
            search_report['click_items_link_error'] = repr(exc)
            page.goto(target_url, wait_until='domcontentloaded', timeout=max(WAIT_SEC, 45) * 1000, referer=AUTHORS_URL)
        html, wait_report = wait_current_page(page, 'items', started=started)
        search_report.update(wait_report)
        search_report.setdefault('final_url', page.url)
        if not has_markers(html, 'items'):
            search_report['debug'] = save_debug(page, html, 'authors_search_items_unready')
        report['authors_search_path'] = search_report
        return html, search_report
    except Exception as exc:
        html = ''
        try:
            html = page.content()
        except Exception:
            pass
        search_report.update({
            'status': 'error',
            'error': repr(exc),
            'elapsed_sec': round(time.time() - started, 3),
            'fingerprint': fingerprint(html, getattr(page, 'url', '')),
            'debug': save_debug(page, html, 'authors_search_error'),
        })
        report['authors_search_path'] = search_report
        return html, search_report
    finally:
        try:
            page.close()
        except Exception:
            pass


def author_item_candidates(profile_page) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()

    def add(url: str, source: str, text: str = '') -> None:
        if not url:
            return
        absolute = normalize_url(url)
        if not absolute or absolute in seen:
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
    html, search_report = fetch_items_via_authors_search(context, report)
    attempts.append(search_report)
    if has_markers(html, 'items'):
        search_report['selected'] = True
        report['items_attempts'] = attempts
        return html, search_report
    last_html = html
    selected_report = search_report

    for candidate in author_item_candidates(profile_page):
        page = context.new_page()
        html, attempt_report = load_page(page, candidate['url'], 'items', referer=AUTHORS_URL)
        attempt_report['candidate_source'] = candidate['source']
        attempt_report['candidate_text'] = candidate.get('text', '')
        attempts.append(attempt_report)
        last_html = html
        selected_report = attempt_report
        if has_markers(html, 'items'):
            attempt_report['selected'] = True
            report['items_attempts'] = attempts
            page.close()
            return html, attempt_report
        if attempt_report.get('status') == 'captcha':
            attempt_report['debug'] = save_debug(page, html, f'items_captcha_{candidate["source"]}')
            page.close()
            break
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
                debug_page.set_content(items_html or '<html><body>No items HTML captured</body></html>')
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
    elif ok_profile and report.get('pages', {}).get('items', {}).get('status') == 'captcha':
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
