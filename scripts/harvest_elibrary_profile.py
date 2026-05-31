#!/usr/bin/env python3
"""Fetch and parse public eLibrary author profile metrics.

The script is designed for GitHub Actions. It first tries to fetch the public
profile page. If eLibrary blocks live access, it can fall back to the latest
saved HTML snapshot from data/snapshots/elibrary/profile/.

Outputs:
  data/elibrary/profile_metrics.json
  data/elibrary/profile_metrics_fetch_report.json
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

# Import parser from the neighbouring script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_elibrary_author_profile import parse_elibrary_author_profile_html, parse_file  # noqa: E402

AUTHOR_ID = os.environ.get("ELIBRARY_AUTHOR_ID", "1012909")
URL = os.environ.get(
    "ELIBRARY_PROFILE_URL",
    f"https://www.elibrary.ru/author_profile.asp?id={AUTHOR_ID}",
)
OUT = Path(os.environ.get("ELIBRARY_PROFILE_OUT", "data/elibrary/profile_metrics.json"))
REPORT = Path(os.environ.get("ELIBRARY_PROFILE_REPORT", "data/elibrary/profile_metrics_fetch_report.json"))
SNAPSHOT_DIR = Path(os.environ.get("ELIBRARY_PROFILE_SNAPSHOT_DIR", "data/snapshots/elibrary/profile"))


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
    opener = urllib.request.build_opener()
    proxy_url = os.environ.get("ELIBRARY_PROXY_URL")
    if proxy_url:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    started = time.time()
    try:
        with opener.open(req, timeout=45) as resp:
            raw = resp.read()
            enc = resp.headers.get_content_charset() or "utf-8"
            text = raw.decode(enc, errors="replace")
            return text, {
                "status": "ok",
                "http_status": resp.status,
                "elapsed_sec": round(time.time() - started, 3),
                "content_length": len(raw),
                "url": URL,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
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


def latest_saved_snapshot() -> Path | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob("*.html"))
    return files[-1] if files else None


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    html, report = fetch_live()
    report["generated_at"] = now()

    if html:
        report["html_fingerprint"] = {"has_metrics": "ОБЩИЕ ПОКАЗАТЕЛИ" in html, "has_h_index": "Индекс Хирша" in html, "has_suspicious_ip_text": "подозр" in html.lower() or "suspicious" in html.lower()}

    if html and "ОБЩИЕ ПОКАЗАТЕЛИ" in html and "Индекс Хирша" in html:
        data = parse_elibrary_author_profile_html(html)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = SNAPSHOT_DIR / f"author_profile_{AUTHOR_ID}_{stamp}.html"
        snapshot_path.write_text(html, encoding="utf-8")
        report["used_source"] = "live_elibrary"
        report["snapshot_path"] = str(snapshot_path)
    else:
        fallback = latest_saved_snapshot()
        if fallback:
            data = parse_file(str(fallback))
            report["used_source"] = "saved_snapshot"
            report["snapshot_path"] = str(fallback)
        else:
            # Keep the previous normalized snapshot if present.
            if OUT.exists():
                report["used_source"] = "previous_normalized_json"
                data = json.loads(OUT.read_text(encoding="utf-8"))
            else:
                report["used_source"] = "none"
                report["error"] = "No live profile, no saved HTML snapshot, and no previous normalized JSON."
                REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                return 1

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(OUT), "used_source": report.get("used_source"), "summary": data.get("summary")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
