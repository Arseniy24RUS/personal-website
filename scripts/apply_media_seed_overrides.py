#!/usr/bin/env python3
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
import csv, hashlib, json, re
try:
    import yaml
except Exception:
    yaml = None

CFG = Path('config/media_sources.yml')
OUT = Path('data/media')
QUEUE = Path('data/admin_queue')
OUT.mkdir(parents=True, exist_ok=True)
QUEUE.mkdir(parents=True, exist_ok=True)

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def read_json(path, default):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception: return default

def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def read_cfg():
    if yaml is None or not CFG.exists(): return {}
    return (yaml.safe_load(CFG.read_text(encoding='utf-8')) or {}).get('media_monitoring', {})

def domain(url):
    h = urlparse(url or '').netloc.lower()
    return h[4:] if h.startswith('www.') else h

def title_from_url(url):
    slug = urlparse(url).path.strip('/').split('/')[-1]
    slug = re.sub(r'\.(pdf|html?|php)$', '', slug, flags=re.I)
    return re.sub(r'\s+', ' ', slug.replace('-', ' ').replace('_', ' ')).strip().capitalize() or url

def rid(url, title):
    return hashlib.sha256((str(title)+'|'+str(url)).encode('utf-8')).hexdigest()[:16]

def seed_record(seed):
    url = seed.get('url')
    title = seed.get('title') or title_from_url(url)
    return {
        'id': rid(url, title),
        'source': seed.get('source_type') or 'known_media_seed',
        'query': None,
        'title': title,
        'url': url,
        'domain': domain(url),
        'source_name': seed.get('source_name') or domain(url),
        'published_at': seed.get('date') or seed.get('published_at'),
        'description': seed.get('description') or seed.get('context') or '',
        'image': seed.get('image'),
        'confidence': 1.0 if seed.get('force_publish', True) else float(seed.get('confidence', 0.85)),
        'status': 'published',
        'force_publish': bool(seed.get('force_publish', True)),
        'seed_metadata_locked': bool(seed.get('title') or seed.get('description') or seed.get('date')),
        'harvested_at': now(),
    }

def main():
    cfg = read_cfg()
    current = (read_json(OUT / 'published.json', {'records': []}).get('records') or [])
    by_url = {r.get('url'): r for r in current if r.get('url')}
    added = updated = 0
    for seed in cfg.get('seed_urls') or []:
        if not seed.get('url') or not seed.get('force_publish', False):
            continue
        rec = seed_record(seed)
        if rec['url'] in by_url:
            old = by_url[rec['url']]
            if rec.get('seed_metadata_locked'):
                old.update({k: rec[k] for k in ['title','description','published_at','source_name','confidence','status','force_publish','seed_metadata_locked']})
                if rec.get('image'):
                    old['image'] = rec['image']
                updated += 1
        else:
            by_url[rec['url']] = rec
            added += 1
    records = sorted(by_url.values(), key=lambda r: (str(r.get('published_at') or ''), str(r.get('title') or '')), reverse=True)
    write_json(OUT / 'published.json', {'generated_at': now(), 'records': records})
    write_json(OUT / 'news_mentions.json', {'generated_at': now(), 'records': records})
    (QUEUE / 'media_mentions.json').write_text('[]\n', encoding='utf-8')
    with (QUEUE / 'media_mentions.csv').open('w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerow(['id','confidence','title','source_name','domain','published_at','url','query'])
    print(json.dumps({'seed_records_total': len([s for s in cfg.get('seed_urls') or [] if s.get('force_publish')]), 'added': added, 'updated': updated, 'published': len(records)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
