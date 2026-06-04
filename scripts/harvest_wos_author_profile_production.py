#!/usr/bin/env python3
"""Production wrapper for the Web of Science harvester.

The base harvester contains the browser fallback and persistence logic. This wrapper
keeps that logic, but forces the direct WOSNX request to match the successful
browser HAR more closely:
- reuse the saved author-publications search from storage_state;
- remove the transient localStorage search id from the request body;
- request 10 records, which matches the Free View profile page;
- prefer storage_state cookies for the WOSSID/SID pair and append extra cookies after.
"""
from __future__ import annotations

import os
import json

import harvest_wos_author_profile as base


def merged_cookie_header(state):
    chunks = []
    seen = set()
    # Storage-state cookies are paired with wos_sid/localStorage, so they must win
    # over a separately pasted Cookie header when names overlap.
    for raw in [base.cookie_header_from_storage_state(state), os.environ.get('WOS_COOKIE', '').strip()]:
        for part in (raw or '').split(';'):
            part = part.strip()
            if not part or '=' not in part:
                continue
            name = part.split('=', 1)[0].strip()
            if name in seen:
                continue
            seen.add(name)
            chunks.append(part)
    return '; '.join(chunks)


def run_query_body(state):
    search, hits, _search_id = base.search_state_from_storage(state)
    if search:
        search = dict(search)
        # The working HAR request does not include this transient storage id inside
        # the search object. Keeping it can turn the request into a cache lookup
        # that returns only searchInfo without records.
        search.pop('id', None)
    else:
        search = {
            'mode': 'author_publications',
            'database': 'WOS',
            'authorId': {'type': 'rid', 'value': base.RESEARCHER_ID},
            'display': {'key': 'author', 'icon': 'author', 'params': {'name': os.environ.get('WOS_AUTHOR_DISPLAY_NAME', '') or base.RESEARCHER_ID}},
            'searchOptions': {'collections': ['WOS'], 'publonCollections': [], 'nonIndexed': False},
            'analyzeConfig': 'profiles',
        }
    try:
        available = int((hits or {}).get('available') or (hits or {}).get('found') or 0)
    except Exception:
        available = 0
    count = max(1, min(available or 10, 10))
    return {
        'product': 'WOS',
        'searchMode': 'author_publications',
        'viewType': 'search',
        'serviceMode': 'summary',
        'search': search,
        'retrieve': {
            'view': 'summary',
            'sort': 'date-descending',
            'jcr': True,
            'history': False,
            'count': count,
            'first': 1,
            'analyzes': ['TP.Value.6', 'OA.Value.6', 'EARLY ACCESS.Value.6', 'DR.Value.6', 'ECR.Value.6', 'DX2NG.Value.101'],
            'locale': 'en',
        },
        'eventMode': None,
    }


def main() -> int:
    base.merged_cookie_header = merged_cookie_header
    base.run_query_body = run_query_body
    return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
