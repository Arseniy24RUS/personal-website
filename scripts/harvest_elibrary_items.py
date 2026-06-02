#!/usr/bin/env python3
"""Fetch and parse public eLibrary author publication list.

The script first tries a cookie-aware live fetch. In GitHub Actions it can be
routed through the repository OpenVPN step or through ELIBRARY_PROXY_URL.

Important invariant: this script must never replace a fuller historical corpus
with a partial/failed eLibrary response. Scientific publications are append-only
for the portfolio: a temporary eLibrary outage or database glitch is not a
reason to remove works from the website.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_elibrary_author_items import parse_elibrary_author_items  # noqa: E402
from elibrary_fetch import fetch_elibrary_page  # noqa: E402

AUTHOR_ID = os.environ.get("ELIBRARY_AUTHOR_ID", "1012909")
URL = os.environ.get(
    "ELIBRARY_ITEMS_URL",
    f"https://www.elibrary.ru/author_items.asp?authorid={AUTHOR_ID}&pubrole=100&show_refs=1&pubcat=risc",
)
OUT = Path(os.environ.get("ELIBRARY_ITEMS_OUT", "data/processed/elibrary_publications.json"))
REPORT = Path(os.environ.get("ELIBRARY_ITEMS_REPORT", "data/elibrary/items_fetch_report.json"))
SNAPSHOT_DIR = Path(os.environ.get("ELIBRARY_ITEMS_SNAPSHOT_DIR", "data/snapshots/elibrary/items"))
MIN_RECORDS = int(os.environ.get("ELIBRARY_MIN_RECORDS", "50"))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_live() -> tuple[str | None, dict]:
    return fetch_elibrary_page(URL)


def latest_snapshot() -> Path | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob("*.html"))
    return files[-1] if files else None


def parse_snapshot(path: Path):
    return parse_elibrary_author_items(str(path))


def read_existing_records() -> list:
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def write_report(report: dict) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    html, report = fetch_live()
    report["generated_at"] = now()
    report["min_records"] = MIN_RECORDS

    if html:
        lowered = html.lower()
        report["html_fingerprint"] = {
            **(report.get("html_fingerprint") or {}),
            "has_author_items": "author_items" in html,
            "has_rows": "arw" in html,
            "has_suspicious_ip_text": "подозр" in lowered or "suspicious" in lowered or "ip_blocked" in lowered,
            "has_cookie_text": "cookie" in lowered or "cookies" in lowered,
        }

    data = None
    if html and "author_items" in html and "arw" in html:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot = SNAPSHOT_DIR / f"author_items_{AUTHOR_ID}_{stamp}.html"
        snapshot.write_text(html, encoding="utf-8")
        candidate = parse_snapshot(snapshot)
        report["used_source"] = "live_elibrary"
        report["snapshot_path"] = str(snapshot)
        report["parsed_records"] = len(candidate)
        if len(candidate) >= MIN_RECORDS:
            data = candidate
        else:
            report["warning"] = f"Live eLibrary returned only {len(candidate)} records; existing corpus will not be overwritten."
    else:
        fallback = latest_snapshot()
        if fallback:
            candidate = parse_snapshot(fallback)
            report["used_source"] = "saved_snapshot"
            report["snapshot_path"] = str(fallback)
            report["parsed_records"] = len(candidate)
            if len(candidate) >= MIN_RECORDS:
                data = candidate
            else:
                report["warning"] = f"Saved eLibrary snapshot has only {len(candidate)} records; existing corpus will not be overwritten."
        elif OUT.exists():
            existing = read_existing_records()
            report["used_source"] = "previous_normalized_json"
            report["parsed_records"] = len(existing)
            report["warning"] = "No usable live/snapshot data; previous normalized JSON left unchanged."
            write_report(report)
            print(json.dumps({"out": str(OUT), "used_source": report.get("used_source"), "records": len(existing), "unchanged": True}, ensure_ascii=False, indent=2))
            return 0 if len(existing) >= MIN_RECORDS else 2
        else:
            report["used_source"] = "none"
            report["error"] = "No live eLibrary items, no saved HTML snapshot, and no previous normalized JSON."
            write_report(report)
            return 1

    if data is None:
        existing = read_existing_records()
        report["existing_records"] = len(existing)
        write_report(report)
        print(json.dumps({"out": str(OUT), "used_source": report.get("used_source"), "records": report.get("parsed_records"), "existing_records": len(existing), "unchanged": True}, ensure_ascii=False, indent=2))
        return 0 if len(existing) >= MIN_RECORDS else 2

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    report["written_records"] = len(data)
    write_report(report)
    print(json.dumps({"out": str(OUT), "used_source": report.get("used_source"), "records": len(data)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
