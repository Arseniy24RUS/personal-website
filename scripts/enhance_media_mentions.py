#!/usr/bin/env python3
from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
import html, json, re, time, urllib.request
try:
    import yaml
except Exception:
    yaml = None

OUT = Path('data/media')
CFG = Path('config/media_sources.yml')
OUT.mkdir(parents=True, exist_ok=True)
STATIC_EXT = re.compile(r'\.(css|js|mjs|map|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|eot|otf|pdf|docx?|xlsx?|pptx?|zip|rar|7z|mp3|mp4|avi|mov)(\?.*)?$', re.I)
BLOCK_PATH = re.compile(r'/(assets|asset|static|image_resp|images|img|css|js|fonts?|vendor|slick|slyder|caorusel|bootstrap)(/|$)', re.I)

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default

def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def read_cfg():
    if yaml is None or not CFG.exists():
        return {}
    return (yaml.safe_load(CFG.read_text(encoding='utf-8')) or {}).get('media_monitoring', {})

def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(s or '')).strip()

def host(url):
    h = urlparse(url or '').netloc.lower()
    return h[4:] if h.startswith('www.') else h

def is_static_url(url):
    p = urlparse(url or '')
    path = p.path or ''
    return bool(STATIC_EXT.search(path) or BLOCK_PATH.search(path))

def fetch(url):
    if is_static_url(url):
        return '', {'status':'skipped_static','url':url}
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 media-monitor/0.3','Accept':'text/html,application/xhtml+xml,*/*','Accept-Language':'ru-RU,ru;q=0.9,en;q=0.8'})
        with urllib.request.urlopen(req, timeout=18) as r:
            ctype = (r.headers.get('content-type') or '').lower()
            if ctype and not any(x in ctype for x in ['text/html','application/xhtml','text/plain']):
                return '', {'status':'skipped_content_type','url':url,'content_type':ctype}
            raw = r.read(); enc = r.headers.get_content_charset() or 'utf-8'
            return raw.decode(enc, errors='replace'), {'status':'ok','http_status':r.status,'url':url,'bytes':len(raw)}
    except Exception as e:
        return '', {'status':'error','url':url,'error':repr(e)[:220]}

def strip_tags(txt):
    txt = re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>', ' ', txt, flags=re.I)
    return clean(re.sub(r'<[^>]+>', ' ', txt))

def meta(html_text, url):
    def find_meta(name):
        m = re.search(r'<meta[^>]+(?:property|name)=["\']'+re.escape(name)+r'["\'][^>]+content=["\']([^"\']+)', html_text, re.I)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']'+re.escape(name)+r'["\']', html_text, re.I)
        return clean(m.group(1)) if m else None
    title = find_meta('og:title') or find_meta('twitter:title')
    if not title:
        m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html_text, re.I)
        title = clean(strip_tags(m.group(1))) if m else None
    if not title:
        m = re.search(r'<title[^>]*>([\s\S]*?)</title>', html_text, re.I)
        title = clean(m.group(1)) if m else None
    generic = ['ДЕМ.ИНФОРМ - первое демографическое информационное агентство России', url, 'Росбалт']
    if not title or title in generic or 'ДЕМ.ИНФОРМ' in title:
        slug = urlparse(url).path.strip('/').split('/')[-1]
        title = clean(slug.replace('-', ' ').replace('_', ' ')).capitalize() or url
    desc = find_meta('og:description') or find_meta('description') or strip_tags(html_text)[:320]
    image = find_meta('og:image') or find_meta('twitter:image')
    return {'title':title, 'description':desc, 'image':image, 'text':strip_tags(html_text)}

def terms(cfg, key, default):
    return [x.lower().replace('ё','е') for x in cfg.get(key, default)]

def score(m, cfg):
    text = (m.get('title','')+' '+m.get('description','')+' '+m.get('text','')).lower().replace('ё','е')
    ids = sum(1 for t in terms(cfg,'identity_terms',['ситковский','арсений ситковский','ситковский а.м.']) if t in text)
    ctx = sum(1 for t in terms(cfg,'context_terms',['демограф','фнисц','рудн','ран','ранхигс']) if t in text)
    return min(1.0, round((0.65 if ids else 0)+(0.15 if ids>1 else 0)+(0.15 if ctx else 0)+(0.05 if ctx>1 else 0),2))

def rid(url, title):
    import hashlib
    return hashlib.sha256((url+'|'+title).encode()).hexdigest()[:16]

def rec(url, m, cfg, source, source_name=None, force=False):
    c = 1.0 if force else score(m,cfg)
    return {'id':rid(url,m['title']),'source':source,'query':None,'title':m['title'],'url':url,'domain':host(url),'source_name':source_name or host(url),'published_at':None,'description':m.get('description') or '','image':m.get('image'),'confidence':c,'status':'published' if c>=float(cfg.get('auto_publish_threshold',0.75)) else 'low_confidence','force_publish':bool(force),'harvested_at':now()}

def links(html_text, base, allow, limit):
    rx = re.compile(allow) if allow else None
    out=[]
    for h in re.findall(r'href=["\']([^"\']+)', html_text, re.I):
        u = urljoin(base,h).split('#')[0]
        if host(u) != host(base) or is_static_url(u):
            continue
        if rx and not rx.search(u):
            continue
        if u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out

def institutional_scan(cfg, reports):
    found=[]
    for src in cfg.get('site_scan_sources') or []:
        frontier=list(src.get('start_urls') or []); seen=set(); allow=src.get('url_allow_regex')
        max_pages=min(int(src.get('max_pages') or 40), 60); max_depth=min(int(src.get('max_depth') or 1), 1)
        for _ in range(max_depth+1):
            nxt=[]
            for u in frontier:
                if u in seen or len(seen)>=max_pages or is_static_url(u):
                    continue
                seen.add(u); h, rep = fetch(u); reports.append(rep)
                if not h:
                    continue
                m = meta(h,u)
                if score(m,cfg) >= float(cfg.get('auto_publish_threshold',0.75)):
                    found.append(rec(u,m,cfg,'institutional_site_scan',src.get('name')))
                nxt.extend([x for x in links(h,u,allow,60) if x not in seen])
                time.sleep(0.02)
            frontier=nxt[:max_pages]
    return found

def dedupe(records):
    seen=set(); out=[]
    for r in sorted(records, key=lambda x:(x.get('confidence',0), x.get('harvested_at','')), reverse=True):
        if r.get('url') in seen:
            continue
        seen.add(r.get('url')); out.append(r)
    return out

def main():
    cfg=read_cfg(); reports=[]
    published=(read_json(OUT/'published.json', {'records':[]}).get('records') or [])
    low=(read_json(OUT/'rejected_or_low_confidence.json', {'records':[]}).get('records') or [])
    enhanced=[]
    for r in published:
        h, rep = fetch(r.get('url')); reports.append(rep)
        if h:
            m=meta(h,r.get('url'))
            r.update({'title':m['title'], 'description':m['description'], 'image':m.get('image') or r.get('image')})
        enhanced.append(r)
    found=institutional_scan(cfg,reports)
    all_pub=dedupe(enhanced+found)
    rejected=dedupe(low)
    write_json(OUT/'published.json', {'generated_at':now(),'records':all_pub})
    write_json(OUT/'news_mentions.json', {'generated_at':now(),'records':all_pub})
    write_json(OUT/'rejected_or_low_confidence.json', {'generated_at':now(),'records':rejected})
    write_json(OUT/'enhance_report.json', {'generated_at':now(),'published':len(all_pub),'rejected_or_low_confidence':len(rejected),'providers':reports})
    print(json.dumps({'published':len(all_pub),'low_confidence':len(rejected)}, ensure_ascii=False))
if __name__=='__main__':
    main()
