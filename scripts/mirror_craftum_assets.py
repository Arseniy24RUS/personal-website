#!/usr/bin/env python3
import hashlib
import json
import urllib.request
from pathlib import Path

manifest_path = Path("data/craftum/assets.json")
items = json.loads(manifest_path.read_text(encoding="utf-8"))
report = []

for item in items:
    local = Path(item["local"])
    local.parent.mkdir(parents=True, exist_ok=True)
    status = "skipped"
    sha256 = None
    size = None
    try:
        if not local.exists() or local.stat().st_size == 0:
            req = urllib.request.Request(item["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()
            local.write_bytes(data)
            status = "downloaded"
        else:
            data = local.read_bytes()
            status = "exists"
        sha256 = hashlib.sha256(data).hexdigest()
        size = len(data)
    except Exception as exc:
        status = "error"
        item["error"] = str(exc)
    report.append({**item, "status": status, "sha256": sha256, "size": size})

Path("data/craftum/assets.report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Processed {len(report)} Craftum assets")
