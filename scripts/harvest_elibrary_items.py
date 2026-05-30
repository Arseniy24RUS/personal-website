#!/usr/bin/env python3
"""Fetch and parse public eLibrary author publication list.

The script is designed for a reusable static-first scientist portfolio.
It tries to fetch the public eLibrary author_items page and parse it. If live
fetching is blocked, it falls back to the latest saved HTML snapshot or leaves
previous normalized data intact.

Outputs:
  data/processed/elibrary_publications.json
  data/elibrary/items_fetch_report.json
  data/snapshots/elibrary/items/*.html when live fetch succeeds
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_elibrary_author_items import parse_elibrary_author_items  # noqa: E402

AUTHOR_ID = os.environ.get("ELIBRARY_AUTHOR_ID", "1012909")
URL = os.environ.get(
    "ELIBRARY_ITEMS_URL",
    f"https://www.elibrary.ru/author_items.asp?authorid={AUTHOR_ID}&pubrole=100&show_refs=1&pubcat=risc",
)
OUT = Path(os.environ.get("ELIBRARY_ITEMS_OUT", "data/processed/elibrary_publications.json"))
REPORT = Path(os.environ.get("ELIBRARY_ITEMS_REPORT", "data/elibrary/items_fetch_report.json"))
SNAPSHOT_DIR = Path(os.environ.get("ELIBRARY_ITEMS_SNAPSHOT_DIR", "data/snapshots/elibrary/items"))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_live() -> tuple[str | None, dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 personal-website-harvester/0.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Referer": "https://www.elibrary.ru/",
    }
    req = urllib.request.Request(URL, headers=headers, method="GET")
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
            enc = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(enc, errors="replace"), {
                "status": "ok",
                "http_status": resp.status,
                "elapsed_sec": round(time.time() - started, 3),
                "content_length": len(raw),
                "url": URL,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1200]
        return None, {
            "status": "http_error",
            "http_status": exc.code,
            "elapsed_sec": round(time.time() - started, 3),
            "url": URL,
            "error_excerpt": body,
        }
    except Exception as exc:
        return None, {
            "status": "error",
            "elapsed_sec": round(time.time() - started, 3),
            "url": URL,
            "error": repr(exc),
        }


def latest_snapshot() -> Path | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob("*.html"))
    return files[-1] if files else None


def parse_snapshot(path: Path):
    return parse_elibrary_author_items(str(path))


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    html, report = fetch_live()
    report["generated_at"] = now()

    if html and "author_items" in html and "arw" in html:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot = SNAPSHOT_DIR / f"author_items_{AUTHOR_ID}_{stamp}.html"
        snapshot.write_text(html, encoding="utf-8")
        data = parse_snapshot(snapshot)
        report["used_source"] = "live_elibrary"
        report["snapshot_path"] = str(snapshot)
    else:
        fallback = latest_snapshot()
        if fallback:
            data = parse_snapshot(fallback)
            report["used_source"] = "saved_snapshot"
            report["snapshot_path"] = str(fallback)
        elif OUT.exists():
            data = json.loads(OUT.read_text(encoding="utf-8"))
            report["used_source"] = "previous_normalized_json"
        else:
            report["used_source"] = "none"
            report["error"] = "No live eLibrary items, no saved HTML snapshot, and no previous normalized JSON."
            REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    report["parsed_records"] = len(data)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(OUT), "used_source": report.get("used_source"), "records": len(data)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
