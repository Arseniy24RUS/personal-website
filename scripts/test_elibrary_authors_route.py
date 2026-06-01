#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import json
import sys

sys.path.insert(0, 'scripts')
import harvest_elibrary_browser as h  # noqa: E402


def main() -> int:
    from playwright.sync_api import sync_playwright

    h.ITEMS_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    report = {'generated_at': h.now(), 'route': 'authors_search_only', 'pages': {}}
    ok = False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-dev-shm-usage', '--no-sandbox'])
        context = browser.new_context(
            locale='ru-RU',
            timezone_id='Europe/Moscow',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
            viewport={'width': 1366, 'height': 900},
        )
        html, page_report = h.fetch_items_via_authors_search(context, report)
        report['pages']['items'] = page_report
        if h.has_markers(html, 'items'):
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            snapshot = h.ITEMS_SNAPSHOT_DIR / f'author_items_{h.AUTHOR_ID}_{stamp}_authors_route.html'
            snapshot.write_text(html, encoding='utf-8')
            data = h.parse_elibrary_author_items(str(snapshot))
            h.write_json(h.ITEMS_OUT, data)
            report['pages']['items']['snapshot_path'] = str(snapshot)
            report['pages']['items']['parsed_records'] = len(data)
            ok = True
        else:
            debug_page = context.new_page()
            try:
                debug_page.set_content(html or '<html><body>No items page captured</body></html>')
            except Exception:
                pass
            report['pages']['items']['debug_final'] = h.save_debug(debug_page, html, 'authors_route_items_not_ready')
            debug_page.close()
        context.close()
        browser.close()
    report['status'] = 'ok' if ok else 'not_ready'
    h.write_json(h.REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
