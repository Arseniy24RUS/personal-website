#!/usr/bin/env python3
"""
Harvest Scopus author/publication data for a portfolio site.

The script intentionally reads credentials from environment variables, because
GitHub Pages is static and any key placed into browser-side JavaScript becomes public.

Required:
  SCOPUS_API_KEY

Optional:
  SCOPUS_INST_TOKEN
  SCOPUS_AUTHOR_ID (default: 57220956828)
  SCOPUS_OUT_DIR (default: data/scopus)

Outputs:
  scopus_author_<id>_raw.json
  scopus_author_<id>_works.json
  scopus_author_<id>_metrics.json
  scopus_author_<id>_access_report.json
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

API_BASE = "https://api.elsevier.com"

def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def request_json(path: str, api_key: str, inst_token: str | None = None, params: Dict[str, Any] | None = None) -> Tuple[Dict[str, Any], Dict[str, str]]:
    params = params or {}
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    headers = {
        "Accept": "application/json",
        "X-ELS-APIKey": api_key,
        "User-Agent": "scientist-portfolio-harvester/0.1",
    }
    if inst_token:
        headers["X-ELS-Insttoken"] = inst_token
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            response_headers = {k: v for k, v in resp.headers.items()}
            return json.loads(body), response_headers
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except Exception:
            payload = {"error": body}
        payload["_http_status"] = e.code
        payload["_url_path"] = path
        payload["_params"] = params
        payload["_headers"] = dict(e.headers.items())
        return payload, dict(e.headers.items())

def safe_int(x: Any) -> int:
    try:
        return int(x)
    except Exception:
        return 0

def flatten_author_profile(author_json: Dict[str, Any]) -> Dict[str, Any]:
    root = author_json.get("author-retrieval-response")
    if isinstance(root, list):
        root = root[0] if root else {}
    if not isinstance(root, dict):
        root = {}
    coredata = root.get("coredata") or {}
    profile = root.get("author-profile") or {}
    preferred = profile.get("preferred-name") or {}
    return {
        "scopus_author_id": coredata.get("dc:identifier", "").replace("AUTHOR_ID:", "") or None,
        "eid": coredata.get("eid"),
        "name": " ".join([preferred.get("given-name", ""), preferred.get("surname", "")]).strip() or coredata.get("dc:title"),
        "document_count": safe_int(coredata.get("document-count")),
        "cited_by_count": safe_int(coredata.get("cited-by-count")),
        "citation_count": safe_int(coredata.get("citation-count")),
        "coauthor_count": safe_int(coredata.get("coauthor-count")),
        "raw_coredata": coredata,
    }

def fetch_author(api_key: str, author_id: str, inst_token: str | None = None) -> Tuple[Dict[str, Any], Dict[str, str]]:
    # ENHANCED may depend on entitlements; STANDARD fallback is attempted by caller if needed.
    return request_json(f"/content/author/author_id/{author_id}", api_key, inst_token, {"view": "ENHANCED"})

def fetch_author_standard(api_key: str, author_id: str, inst_token: str | None = None) -> Tuple[Dict[str, Any], Dict[str, str]]:
    return request_json(f"/content/author/author_id/{author_id}", api_key, inst_token, {"view": "STANDARD"})

def fetch_works(api_key: str, author_id: str, inst_token: str | None = None, count: int = 25) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, str]]]:
    entries: List[Dict[str, Any]] = []
    headers_seen: List[Dict[str, str]] = []
    start = 0
    first_payload: Dict[str, Any] = {}
    fields = ",".join([
        "dc:title",
        "dc:creator",
        "prism:publicationName",
        "prism:coverDate",
        "prism:doi",
        "citedby-count",
        "eid",
        "dc:identifier",
        "prism:aggregationType",
        "subtypeDescription",
        "openaccess",
    ])
    while True:
        payload, headers = request_json(
            "/content/search/scopus",
            api_key,
            inst_token,
            {
                "query": f"AU-ID({author_id})",
                "count": count,
                "start": start,
                "view": "STANDARD",
                "field": fields,
            },
        )
        headers_seen.append(headers)
        if start == 0:
            first_payload = payload
        if payload.get("_http_status"):
            break
        search = payload.get("search-results") or {}
        batch = search.get("entry") or []
        if isinstance(batch, dict):
            batch = [batch]
        entries.extend(batch)
        total = safe_int(search.get("opensearch:totalResults"))
        start_index = safe_int(search.get("opensearch:startIndex"))
        items_per_page = safe_int(search.get("opensearch:itemsPerPage")) or count
        if not batch or len(entries) >= total:
            break
        start = start_index + items_per_page
        time.sleep(0.2)
    return entries, first_payload, headers_seen

def compute_h_index(citations: List[int]) -> int:
    citations = sorted([safe_int(c) for c in citations], reverse=True)
    h = 0
    for i, c in enumerate(citations, start=1):
        if c >= i:
            h = i
        else:
            break
    return h

def normalize_work(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source": "scopus_api",
        "eid": entry.get("eid"),
        "scopus_id": (entry.get("dc:identifier") or "").replace("SCOPUS_ID:", "") or None,
        "title": entry.get("dc:title"),
        "creator": entry.get("dc:creator"),
        "journal_or_source": entry.get("prism:publicationName"),
        "cover_date": entry.get("prism:coverDate"),
        "year": (entry.get("prism:coverDate") or "")[:4] or None,
        "doi": entry.get("prism:doi"),
        "cited_by_count": safe_int(entry.get("citedby-count")),
        "aggregation_type": entry.get("prism:aggregationType"),
        "subtype": entry.get("subtypeDescription"),
        "openaccess": entry.get("openaccess"),
        "url": next((l.get("@href") for l in entry.get("link", []) if l.get("@ref") == "scopus"), None) if isinstance(entry.get("link"), list) else None,
        "raw": entry,
    }

def main() -> int:
    api_key = os.environ.get("SCOPUS_API_KEY", "").strip()
    inst_token = os.environ.get("SCOPUS_INST_TOKEN", "").strip() or None
    author_id = os.environ.get("SCOPUS_AUTHOR_ID", "57220956828").strip()
    out_dir = Path(os.environ.get("SCOPUS_OUT_DIR", "data/scopus"))
    out_dir.mkdir(parents=True, exist_ok=True)

    if not api_key:
        print("ERROR: SCOPUS_API_KEY is not set", file=sys.stderr)
        return 2

    author_payload, author_headers = fetch_author(api_key, author_id, inst_token)
    # Fallback: if ENHANCED is not allowed, try STANDARD.
    if author_payload.get("_http_status") in {401, 403}:
        std_payload, std_headers = fetch_author_standard(api_key, author_id, inst_token)
        if not std_payload.get("_http_status"):
            author_payload, author_headers = std_payload, std_headers

    works_entries, search_payload, search_headers = fetch_works(api_key, author_id, inst_token)
    works = [normalize_work(e) for e in works_entries]
    citations = [w["cited_by_count"] for w in works]

    profile = flatten_author_profile(author_payload) if not author_payload.get("_http_status") else {}
    metrics = {
        "source": "scopus_api",
        "generated_at": now_utc(),
        "scopus_author_id": author_id,
        "author_profile_status": author_payload.get("_http_status", 200),
        "search_status": search_payload.get("_http_status", 200),
        "profile": profile,
        "works_count_from_search": len(works),
        "citation_sum_from_search": sum(citations),
        "h_index_recomputed_from_retrieved_works": compute_h_index(citations),
        "note": "Recomputed h-index uses works retrieved by Scopus Search. If access is incomplete, prefer official author profile metrics when available.",
    }

    access_report = {
        "generated_at": now_utc(),
        "author_headers": {k: author_headers.get(k) for k in author_headers if k.lower().startswith("x-") or k.lower() in {"content-type"}},
        "search_headers": [
            {k: h.get(k) for k in h if k.lower().startswith("x-") or k.lower() in {"content-type"}}
            for h in search_headers
        ],
        "author_error": author_payload if author_payload.get("_http_status") else None,
        "search_error": search_payload if search_payload.get("_http_status") else None,
    }

    prefix = out_dir / f"scopus_author_{author_id}"
    (prefix.with_name(prefix.name + "_raw.json")).write_text(json.dumps({
        "author_payload": author_payload,
        "search_first_payload": search_payload,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (prefix.with_name(prefix.name + "_works.json")).write_text(json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")
    (prefix.with_name(prefix.name + "_metrics.json")).write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (prefix.with_name(prefix.name + "_access_report.json")).write_text(json.dumps(access_report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if not (author_payload.get("_http_status") or search_payload.get("_http_status")) else 1

if __name__ == "__main__":
    raise SystemExit(main())
