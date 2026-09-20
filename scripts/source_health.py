"""Small, credential-free source reports and atomic last-good persistence."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def snapshot_time(path):
    """Legacy generated_at means rebuild time; use the actual capture filename."""
    match = re.search(r'(\d{8}T\d{6}Z)', str(path or ''))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def source_result(previous=None, *, status='error', count=0, reason=None, attempted_at=None):
    previous = previous or {}
    attempted_at = attempted_at or now()
    success = status == 'success'
    return {
        'status': status,
        'attempted_at': attempted_at,
        'last_success_at': attempted_at if success else previous.get('last_success_at'),
        'origin': 'live' if success else 'snapshot',
        'complete': success,
        'record_count': count,
        'reason': reason,
    }


def merge_records(previous, fresh, key):
    """Add/update verified records, never delete old ones or replace values by null."""
    result = {key(row): dict(row) for row in previous if key(row)}
    for row in fresh:
        identifier = key(row)
        if not identifier:
            continue
        old = result.get(identifier, {})
        sources = sorted(set(old.get('sources') or []) | set(row.get('sources') or []))
        result[identifier] = {**old, **{k: v for k, v in row.items() if v is not None and v != ''}}
        if sources:
            result[identifier]['sources'] = sources
    return list(result.values())
