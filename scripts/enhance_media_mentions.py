#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import time
import urllib.request

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None
try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

OUT = Path('data/media')
CFG = Path('config/media_sources.yml')
OUT.mkdir(parents=True, exist_ok=True)
STATIC_EXT = re.compile(r'\.(css|js|mjs|map|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|eot|otf|pdf|docx?|xlsx?|pptx?|zip|rar|7z|mp3|mp4|avi|mov)(\?.*)?$', re.I)
BLOCK_PATH = re.compile(r'/(assets|asset|static|image_resp|images|img|css|js|fonts?|vendor|slick|slyder|caorusel|bootstrap)(/|$)', re.I)
BLOCKED_URL_PATTERNS = [
    re.compile(r'admission\.rudn\.ru/staff/86110487-4a8f-11f0-b545-00155d0c0d4a', re.I),
    re.compile(r'fnisc\.ru/pers_about\.html\?id=2472', re.I),
    re.compile(r'isras\.ru/pers_about\.html\?id=2472', re.I),
    re.compile(r'fnisc\.ru/index\.php\?id=2472&page_id=1195', re.I),
    re.compile(r'fnisc\.ru/index\.php\?page_id=(44|2366|2483)', re.I),
    re.compile(r'rudn\.ru/about/struktura-rudn/.*/kafedra-gosudarstvennogo-i-municipalnogo-upravleniya', re.I),
]
BLOCKED_TITLES = {
    'список публикаций ситковского арсения михайловича',
    'ситковский арсений михайлович arseniy m. sitkovskiy',
    'кафедра государственного и муниципального управления',
}
NAVIGATION_JUNK = re.compile(r'Публикации молодых ученых|Поиск Информация|Противодействие корруп|Основные сведения Структура|Новости Минобрнауки РФ|slick|bootstrap|font-awesome|ДЕМ\.ИНФОРМ - первое демографическое информационное агентство России Главная', re.I)
KNOWN_OVERRIDES = {
    'https://www.rosbalt.ru/news/2026-01-31/obschestvo-superzrelosti-my-stremitelno-stareem-5543743': {
        'title_ru': 'Общество суперзрелости: мы стремительно стареем',
        'title_en': 'A super-mature society: we are ageing rapidly',
        'description_ru': 'Материал «Росбалта» о демографическом старении, изменении возрастной структуры населения и социальных последствиях этих процессов.',
        'description_en': 'A Rosbalt article on population ageing, shifts in the age structure and the social consequences of these processes.',
    },
    'https://deminform.ru/analytics/demograficheskoye-chudo-izrailya-mozhem-povtorit': {
        'title_ru': 'Демографическое чудо Израиля: можем повторить?',
        'title_en': 'Israel’s demographic miracle: can it be replicated?',
        'description_ru': 'Аналитический материал ДЕМ.ИНФОРМ о факторах высокой рождаемости в Израиле и применимости отдельных демографических практик в России.',
        'description_en': 'A DEM.INFORM analytical article on the drivers of high fertility in Israel and the applicability of selected demographic practices in Russia.',
    },
    'https://deminform.ru/analytics/semeynaya-ipoteka-2024-infrastrukturnoye-obespecheniye-mnogodetnoy-semyi': {
        'title_ru': 'Семейная ипотека 2024: инфраструктурное обеспечение многодетной семьи',
        'title_en': 'Family mortgage 2024: infrastructure support for large families',
        'description_ru': 'Аналитический материал ДЕМ.ИНФОРМ о семейной ипотеке, инфраструктурной обеспеченности и пространственных условиях жизни многодетных семей.',
        'description_en': 'A DEM.INFORM analytical article on family mortgages, infrastructure provision and spatial living conditions for large families.',
    },
    'https://deminform.ru/analytics/urbanizatsiya-protiv-rozhdayemosti-strategiya-prostranstvennogo-razvitiya-rossii-do-2030-goda': {
        'title_ru': 'Урбанизация против рождаемости: стратегия пространственного развития России до 2030 года',
        'title_en': 'Urbanisation versus fertility: Russia’s spatial development strategy to 2030',
        'description_ru': 'Аналитический материал ДЕМ.ИНФОРМ о взаимосвязи урбанизации, пространственного развития и демографической динамики.',
        'description_en': 'A DEM.INFORM analytical article on the links between urbanisation, spatial development and demographic dynamics.',
    },
    'https://deminform.ru/analytics/vliyaniye-gosudarstvennoy-politiki-aglomerirovaniya-na-dolgosrochnye-tendentsii-izmeneniya-chislennosti-naseleniya-rossii': {
        'title_ru': 'Влияние государственной политики агломерирования на долгосрочные тенденции изменения численности населения России',
        'title_en': 'The effect of agglomeration policy on long-term population trends in Russia',
        'description_ru': 'Аналитический материал ДЕМ.ИНФОРМ о долгосрочных демографических последствиях политики агломерирования и пространственной концентрации населения.',
        'description_en': 'A DEM.INFORM analytical article on the long-term demographic consequences of agglomeration policy and spatial population concentration.',
    },
}

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def clean(s): return re.sub(r'\s+', ' ', html.unescape(s or '').replace('\xa0',' ')).strip()
def canon(url):
    try: return urlparse(url or '')._replace(fragment='').geturl().rstrip('/')
    except Exception: return (url or '').split('#')[0].rstrip('/')
def host(url):
    h=urlparse(url or '').netloc.lower(); return h[4:] if h.startswith('www.') else h
def is_static_url(url):
    p=urlparse(url or ''); return bool(STATIC_EXT.search(p.path or '') or BLOCK_PATH.search(p.path or ''))
def is_blocked_url(url): return any(rx.search(canon(url)) for rx in BLOCKED_URL_PATTERNS)
def is_blocked_title(title): return clean(title).lower().replace('ё','е') in BLOCKED_TITLES
def read_json(path, default):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception: return default
def write_json(path, data): Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
def read_cfg():
    if yaml is None or not CFG.exists(): return {}
    return (yaml.safe_load(CFG.read_text(encoding='utf-8')) or {}).get('media_monitoring', {})
def detect_lang(text): return 'ru' if re.search(r'[А-Яа-яЁё]', text or '') else 'en' if re.search(r'[A-Za-z]', text or '') else None

def localized_record_fields(title, description):
    title=clean(title); description=clean(description); fields={'title':title,'description':description}
    for base, val in [('title', title), ('description', description)]:
        lang=detect_lang(val)
        if lang: fields[f'{base}_{lang}']=val
    fields['language']=detect_lang(title) or detect_lang(description) or 'und'
    return fields

def apply_overrides(record):
    o=KNOWN_OVERRIDES.get(canon(record.get('url')))
    if not o: return record
    record.update(o); record['title']=o.get('title_ru') or record.get('title'); record['description']=o.get('description_ru') or record.get('description'); record['language']='ru'
    return record

def fetch(url):
    if is_static_url(url) or is_blocked_url(url): return '', {'status':'skipped','url':url}
    try:
        req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 media-monitor/0.5','Accept':'text/html,application/xhtml+xml,*/*','Accept-Language':'ru-RU,ru;q=0.9,en;q=0.8'})
        with urllib.request.urlopen(req, timeout=22) as r:
            ctype=(r.headers.get('content-type') or '').lower()
            if ctype and not any(x in ctype for x in ['text/html','application/xhtml','text/plain']): return '', {'status':'skipped_content_type','url':url,'content_type':ctype}
            raw=r.read(); enc=r.headers.get_content_charset() or 'utf-8'
            return raw.decode(enc, errors='replace'), {'status':'ok','http_status':r.status,'url':url,'bytes':len(raw)}
    except Exception as e: return '', {'status':'error','url':url,'error':repr(e)[:220]}

def strip_tags(txt):
    if BeautifulSoup:
        soup=BeautifulSoup(txt or '', 'html.parser')
        for tag in soup(['script','style','noscript']): tag.decompose()
        return clean(soup.get_text(' '))
    txt=re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>',' ',txt or '',flags=re.I)
    return clean(re.sub(r'<[^>]+>',' ',txt))

def meta(html_text, url):
    if not BeautifulSoup:
        text=strip_tags(html_text); return {'title':url,'description':text[:320],'image':None,'text':text}
    soup=BeautifulSoup(html_text or '', 'html.parser')
    def m(name):
        tag=soup.find('meta', attrs={'property':name}) or soup.find('meta', attrs={'name':name})
        return clean(tag.get('content')) if tag and tag.get('content') else None
    title=m('og:title') or m('twitter:title')
    if not title or title in {'Росбалт','ФНИСЦ РАН','ДЕМ.ИНФОРМ - первое демографическое информационное агентство России'}:
        h=soup.select_one('article h1, main h1, h1'); title=clean(h.get_text(' ')) if h else None
    if not title and soup.title: title=clean(soup.title.get_text(' '))
    if not title or title in {url, 'Росбалт'}:
        slug=urlparse(url).path.strip('/').split('/')[-1]; title=clean(slug.replace('-',' ').replace('_',' ')).capitalize() or url
    desc=m('og:description') or m('twitter:description') or m('description')
    if not desc or NAVIGATION_JUNK.search(desc):
        p=soup.select_one('article p, main p, .article p, .content p'); desc=clean(p.get_text(' ')) if p else None
    text=strip_tags(html_text)
    if not desc: desc=text[:320]
    image=m('og:image') or m('twitter:image') or m('vk:image')
    if not image:
        for sel in ['article img','main img','.article img','.content img','img']:
            img=soup.select_one(sel)
            if img:
                cand=img.get('src') or img.get('data-src') or img.get('data-original')
                if cand and not re.search(r'logo|icon|sprite|avatar', cand, re.I): image=cand; break
    if image: image=urljoin(url, image)
    return {'title':clean(title),'description':clean(desc),'image':image,'text':text}

def terms(cfg,key,default): return [x.lower().replace('ё','е') for x in cfg.get(key, default)]
def score(m,cfg):
    text=(m.get('title','')+' '+m.get('description','')+' '+m.get('text','')).lower().replace('ё','е')
    ids=sum(1 for t in terms(cfg,'identity_terms',['ситковский','арсений ситковский','ситковский а.м.']) if t in text)
    ctx=sum(1 for t in terms(cfg,'context_terms',['демограф','фнисц','рудн','ран','ранхигс']) if t in text)
    return min(1.0, round((0.65 if ids else 0)+(0.15 if ids>1 else 0)+(0.15 if ctx else 0)+(0.05 if ctx>1 else 0),2))
def rid(url,title): return hashlib.sha256((canon(url)+'|'+title).encode()).hexdigest()[:16]

def rec(url,m,cfg,source,source_name=None,force=False):
    c=1.0 if force else score(m,cfg); record={'id':rid(url,m['title']),'source':source,'query':None,'url':url,'domain':host(url),'source_name':source_name or host(url),'published_at':None,'image':m.get('image'),'confidence':c,'status':'published' if c>=float(cfg.get('auto_publish_threshold',0.75)) else 'low_confidence','force_publish':bool(force),'harvested_at':now()}
    record.update(localized_record_fields(m.get('title') or '', m.get('description') or ''))
    return apply_overrides(record)

def links(html_text, base, allow, limit):
    rx=re.compile(allow) if allow else None; out=[]
    for h in re.findall(r'href=["\']([^"\']+)', html_text, re.I):
        u=urljoin(base,h).split('#')[0]
        if host(u)!=host(base) or is_static_url(u) or is_blocked_url(u): continue
        if rx and not rx.search(u): continue
        if u not in out: out.append(u)
        if len(out)>=limit: break
    return out

def institutional_scan(cfg,reports):
    found=[]
    for src in cfg.get('site_scan_sources') or []:
        frontier=list(src.get('start_urls') or []); seen=set(); allow=src.get('url_allow_regex')
        max_pages=min(int(src.get('max_pages') or 40),60); max_depth=min(int(src.get('max_depth') or 1),1)
        for _ in range(max_depth+1):
            nxt=[]
            for u in frontier:
                if u in seen or len(seen)>=max_pages or is_static_url(u) or is_blocked_url(u): continue
                seen.add(u); h,rep=fetch(u); reports.append(rep)
                if not h: continue
                m=meta(h,u)
                if not NAVIGATION_JUNK.search(m.get('description') or '') and score(m,cfg)>=float(cfg.get('auto_publish_threshold',0.75)):
                    found.append(rec(u,m,cfg,'institutional_site_scan',src.get('name')))
                nxt.extend([x for x in links(h,u,allow,60) if x not in seen]); time.sleep(0.02)
            frontier=nxt[:max_pages]
    return found

def dedupe(records):
    seen=set(); out=[]
    for r in records:
        if not r or is_blocked_url(r.get('url')): continue
        r=apply_overrides(r); key=canon(r.get('url'))
        if not key or key in seen: continue
        if is_blocked_title(r.get('title') or r.get('title_ru') or ''): continue
        if r.get('source')=='institutional_site_scan' and (r.get('title') in {'ФНИСЦ РАН','РУДН'} or NAVIGATION_JUNK.search(r.get('description') or '')): continue
        seen.add(key); out.append(r)
    out.sort(key=lambda x:(x.get('published_at') or x.get('harvested_at') or ''), reverse=True)
    return out

def main():
    cfg=read_cfg(); reports=[]; published=(read_json(OUT/'published.json', {'records':[]}).get('records') or []); low=(read_json(OUT/'rejected_or_low_confidence.json', {'records':[]}).get('records') or [])
    enhanced=[]
    for r in published:
        if is_blocked_url(r.get('url')): continue
        h,rep=fetch(r.get('url')); reports.append(rep)
        if h:
            m=meta(h,r.get('url'))
            r.update(localized_record_fields(m.get('title') or r.get('title') or '', m.get('description') or r.get('description') or ''))
            if m.get('image'): r['image']=m.get('image')
        enhanced.append(apply_overrides(r))
    found=institutional_scan(cfg,reports)
    all_pub=dedupe(enhanced+found); rejected=dedupe(low)
    write_json(OUT/'published.json', {'generated_at':now(),'records':all_pub}); write_json(OUT/'news_mentions.json', {'generated_at':now(),'records':all_pub}); write_json(OUT/'rejected_or_low_confidence.json', {'generated_at':now(),'records':rejected}); write_json(OUT/'enhance_report.json', {'generated_at':now(),'published':len(all_pub),'rejected_or_low_confidence':len(rejected),'providers':reports})
    print(json.dumps({'published':len(all_pub),'low_confidence':len(rejected)}, ensure_ascii=False))
if __name__=='__main__': main()
