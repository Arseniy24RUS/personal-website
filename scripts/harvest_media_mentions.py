#!/usr/bin/env python3
"""Free automated media mention harvester for a static scientist portfolio.

The algorithm combines several zero-cost channels:

1. Known seed URLs from config/media_sources.yml.
2. Google News RSS searches by exact name variants.
3. Optional sitemap scanning for selected media/project domains.
4. Optional public Telegram channel-page scanning through t.me/s/<channel>.

Unlike earlier versions, this script does not create a manual queue. It writes:

  data/media/published.json
  data/media/rejected_or_low_confidence.json
  data/media/harvest_report.json
  data/admin_queue/media_mentions.json   # always [] for compatibility
  data/admin_queue/media_mentions.csv    # header only for compatibility

The static site should display only data/media/published.json.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse, parse_qs, unquote
import csv
import email.utils
import hashlib
import html
import json
import os
import re
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

try:
    import yaml
except Exception:
    yaml = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

ROOT = Path('.')
PROFILE = Path(os.environ.get('PROFILE_YAML', 'config/profile.yml'))
CONFIG = Path(os.environ.get('MEDIA_SOURCES_YAML', 'config/media_sources.yml'))
OUT = ROOT / 'data' / 'media'
QUEUE = ROOT / 'data' / 'admin_queue'
OUT.mkdir(parents=True, exist_ok=True)
QUEUE.mkdir(parents=True, exist_ok=True)

DEFAULT_QUERIES = [
    '"Ситковский Арсений"',
    '"Ситковский А.М."',
    '"Арсений Ситковский"',
    '"Ситковский Арсений Михайлович"',
    '"Arseniy Sitkovskiy"',
    '"Arseniy M. Sitkovskiy"',
]

DEFAULT_IDENTITY_TERMS = [
    'ситковский', 'арсений ситковский', 'ситковский а. м.', 'ситковский а.м.',
    'ситковский арсений', 'arseniy sitkovskiy', 'arseniy m. sitkovskiy'
]

DEFAULT_CONTEXT_TERMS = [
    'демограф', 'демография', 'рождаемость', 'старение', 'фнисц', 'рудн', 'ран',
    'пространственное развитие', 'агломерац', 'расселение', 'семейная ипотека'
]

STOP_DOMAINS = {
    'elibrary.ru', 'orcid.org', 'scopus.com', 'webofscience.com', 'github.com',
    'researchgate.net', 'scholar.google.com', 'cyberleninka.ru'
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_yaml(path: Path) -> dict:
    if yaml is None or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def read_profile() -> dict:
    return read_yaml(PROFILE)


def media_cfg() -> dict:
    return read_yaml(CONFIG).get('media_monitoring', {})


def cfg_queries(cfg: dict) -> list[str]:
    prof = (read_profile().get('profile') or {})
    queries = list(cfg.get('queries') or DEFAULT_QUERIES)
    for name in [prof.get('display_name_ru'), prof.get('display_name_en')]:
        if name:
            queries.append('"' + str(name).strip() + '"')
    seen = set(); out = []
    for q in queries:
        if q not in seen:
            seen.add(q); out.append(q)
    return out


def identity_terms(cfg: dict) -> list[str]:
    terms = list(cfg.get('identity_terms') or DEFAULT_IDENTITY_TERMS)
    prof = (read_profile().get('profile') or {})
    for name in [prof.get('display_name_ru'), prof.get('display_name_en')]:
        if name:
            terms.append(str(name).lower())
    return [t.lower().replace('ё', 'е') for t in terms]


def context_terms(cfg: dict) -> list[str]:
    return [t.lower().replace('ё', 'е') for t in (cfg.get('context_terms') or DEFAULT_CONTEXT_TERMS)]


def clean_url(url: str) -> str:
    url = (url or '').strip().replace(' ', '_')
    url = url.replace('utm_source=perplexity', '').replace('utm source=perplexity', '')
    url = url.rstrip('?&')
    return url


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith('www.') else host
    except Exception:
        return ''


def fetch_text(url: str, accept='text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'):
    headers = {
        'User-Agent': 'Mozilla/5.0 scientist-portfolio-media-harvester/0.2',
        'Accept': accept,
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    }
    req = urllib.request.Request(url, headers=headers)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
            enc = resp.headers.get_content_charset() or 'utf-8'
            return raw.decode(enc, errors='replace'), {
                'status': 'ok', 'http_status': resp.status, 'url': url,
                'bytes': len(raw), 'elapsed_sec': round(time.time() - started, 3)
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:1000]
        return None, {'status': 'http_error', 'http_status': exc.code, 'url': url, 'error_excerpt': body}
    except Exception as exc:
        return None, {'status': 'error', 'url': url, 'error': repr(exc)}


def textify_html(html_text: str) -> str:
    if not html_text:
        return ''
    if BeautifulSoup:
        soup = BeautifulSoup(html_text, 'html.parser')
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        return re.sub(r'\s+', ' ', soup.get_text(' ')).strip()
    return re.sub(r'<[^>]+>', ' ', html_text)


def meta_from_html(html_text: str) -> dict:
    if not BeautifulSoup:
        title = re.search(r'<title[^>]*>(.*?)</title>', html_text or '', re.I | re.S)
        return {'title': html.unescape(title.group(1)).strip() if title else None}
    soup = BeautifulSoup(html_text or '', 'html.parser')
    def meta(*names):
        for name in names:
            tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                return html.unescape(tag['content']).strip()
        return None
    title = meta('og:title', 'twitter:title') or (soup.title.get_text(' ').strip() if soup.title else None)
    desc = meta('og:description', 'twitter:description', 'description')
    image = meta('og:image', 'twitter:image')
    return {'title': title, 'description': desc, 'image': image}


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return value


def score_record(text: str, title: str, url: str, cfg: dict, force_publish=False) -> float:
    if force_publish:
        return 1.0
    body = (title + ' ' + text).lower().replace('ё', 'е')
    score = 0.0
    id_hits = sum(1 for t in identity_terms(cfg) if t and t in body)
    ctx_hits = sum(1 for t in context_terms(cfg) if t and t in body)
    if id_hits:
        score += 0.55
    if id_hits >= 2:
        score += 0.15
    if ctx_hits:
        score += 0.2
    if ctx_hits >= 2:
        score += 0.05
    if domain_of(url) in STOP_DOMAINS:
        score -= 0.35
    return max(0.0, min(1.0, round(score, 2)))


def make_record(url: str, *, source: str, cfg: dict, force_publish=False, query=None, source_name=None) -> tuple[dict | None, dict]:
    url = clean_url(url)
    html_text, report = fetch_text(url)
    if not html_text:
        if force_publish:
            title = urlparse(url).path.strip('/').split('/')[-1].replace('-', ' ') or url
            rec = build_record(url, source, title, '', cfg, force_publish=True, query=query, source_name=source_name)
            return rec, report
        return None, report
    meta = meta_from_html(html_text)
    text = textify_html(html_text)
    title = meta.get('title') or url
    desc = meta.get('description') or text[:280]
    rec = build_record(url, source, title, desc, cfg, text=text, image=meta.get('image'), force_publish=force_publish, query=query, source_name=source_name)
    return rec, report


def build_record(url, source, title, desc, cfg, *, text='', image=None, force_publish=False, query=None, source_name=None):
    conf = score_record(text or desc, title, url, cfg, force_publish=force_publish)
    rec_id = hashlib.sha256((title + '|' + url).encode('utf-8')).hexdigest()[:16]
    return {
        'id': rec_id,
        'source': source,
        'query': query,
        'title': html.unescape(title or '').strip(),
        'url': url,
        'domain': domain_of(url),
        'source_name': source_name or domain_of(url),
        'published_at': None,
        'description': html.unescape(desc or '').strip(),
        'image': image,
        'confidence': conf,
        'status': 'published' if conf >= float(cfg.get('auto_publish_threshold', 0.75)) else 'low_confidence',
        'force_publish': bool(force_publish),
        'harvested_at': now(),
    }


def rss_url(query: str, lang='ru', country='RU') -> str:
    return 'https://news.google.com/rss/search?' + urlencode({'q': query, 'hl': lang, 'gl': country, 'ceid': f'{country}:{lang}'})


def unwrap_google_news_link(link: str) -> str:
    if not link:
        return link
    qs = parse_qs(urlparse(link).query)
    for key in ['url', 'u']:
        if key in qs and qs[key]:
            return unquote(qs[key][0])
    return link


def parse_rss(xml_text: str, query: str, cfg: dict):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall('.//item'):
        title = html.unescape((item.findtext('title') or '').strip())
        link = unwrap_google_news_link((item.findtext('link') or '').strip())
        desc = html.unescape(re.sub('<[^>]+>', ' ', item.findtext('description') or '')).strip()
        pub_date = parse_date(item.findtext('pubDate'))
        source_node = item.find('source')
        source_name = source_node.text.strip() if source_node is not None and source_node.text else None
        if domain_of(link) in STOP_DOMAINS:
            continue
        rec = build_record(link, 'google_news_rss', title, desc, cfg, text=desc, query=query, source_name=source_name)
        rec['published_at'] = pub_date
        items.append(rec)
    return items


def fetch_google_news(cfg: dict):
    records, reports = [], []
    for query in cfg_queries(cfg):
        for lang, country in [('ru', 'RU'), ('en', 'US')]:
            url = rss_url(query, lang=lang, country=country)
            text, report = fetch_text(url, accept='application/rss+xml,application/xml,text/xml,*/*')
            reports.append(report)
            if text:
                try:
                    records.extend(parse_rss(text, query, cfg))
                except Exception as exc:
                    reports.append({'status': 'parse_error', 'url': url, 'error': repr(exc)})
            time.sleep(0.2)
    return records, reports


def fetch_sitemap_urls(sitemap_url: str, limit: int, allow_regex: str | None):
    text, report = fetch_text(sitemap_url, accept='application/xml,text/xml,*/*')
    urls = []
    if text:
        try:
            root = ET.fromstring(text)
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            locs = [x.text for x in root.findall('.//sm:loc', ns) if x.text] or [x.text for x in root.findall('.//loc') if x.text]
            rx = re.compile(allow_regex) if allow_regex else None
            for loc in locs:
                if rx is None or rx.search(loc):
                    urls.append(loc)
                if len(urls) >= limit:
                    break
        except Exception as exc:
            report['parse_error'] = repr(exc)
    return urls, report


def fetch_sitemaps(cfg: dict):
    records, reports = [], []
    for src in cfg.get('sitemap_sources') or []:
        urls, rep = fetch_sitemap_urls(src.get('sitemap_url'), int(src.get('max_urls') or 200), src.get('url_allow_regex'))
        reports.append(rep)
        for url in urls:
            rec, report = make_record(url, source='sitemap_scan', cfg=cfg, force_publish=False, source_name=src.get('name'))
            reports.append(report)
            if rec:
                records.append(rec)
            time.sleep(0.1)
    return records, reports


def fetch_seed_urls(cfg: dict):
    records, reports = [], []
    for seed in cfg.get('seed_urls') or []:
        rec, report = make_record(seed.get('url'), source=seed.get('source_type') or 'known_seed', cfg=cfg, force_publish=bool(seed.get('force_publish')))
        reports.append(report)
        if rec:
            records.append(rec)
        time.sleep(0.15)
    return records, reports


def fetch_telegram(cfg: dict):
    records, reports = [], []
    for ch in cfg.get('telegram_channels') or []:
        channel = ch.get('channel')
        if not channel:
            continue
        url = f'https://t.me/s/{channel}'
        text, report = fetch_text(url)
        reports.append(report)
        if not text or not BeautifulSoup:
            continue
        soup = BeautifulSoup(text, 'html.parser')
        posts = soup.select('.tgme_widget_message')[:int(ch.get('max_latest_posts') or 50)]
        for post in posts:
            post_url = post.get('data-post')
            href = f'https://t.me/{post_url}' if post_url else url
            body = re.sub(r'\s+', ' ', post.get_text(' ')).strip()
            title = body[:110] or href
            rec = build_record(href, 'telegram_channel_scan', title, body[:400], cfg, text=body, source_name=channel)
            records.append(rec)
    return records, reports


def dedupe(records):
    seen, out = set(), []
    for r in sorted(records, key=lambda x: (x.get('status') == 'published', x.get('confidence') or 0, x.get('published_at') or ''), reverse=True):
        key = r.get('url') or r.get('id')
        if key in seen:
            continue
        seen.add(key); out.append(r)
    return out


def main() -> int:
    cfg = media_cfg()
    records, provider_reports = [], []
    for func in [fetch_seed_urls, fetch_google_news, fetch_telegram, fetch_sitemaps]:
        try:
            recs, reps = func(cfg)
            records.extend(recs); provider_reports.extend(reps)
        except Exception as exc:
            provider_reports.append({'status': 'collector_error', 'collector': func.__name__, 'error': repr(exc)})
    records = dedupe(records)
    threshold = float(cfg.get('auto_publish_threshold', 0.75))
    published = [r for r in records if r.get('confidence', 0) >= threshold or r.get('force_publish')]
    rejected = [r for r in records if r not in published]
    (OUT / 'published.json').write_text(json.dumps({'generated_at': now(), 'records': published}, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'news_mentions.json').write_text(json.dumps({'generated_at': now(), 'records': published}, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'rejected_or_low_confidence.json').write_text(json.dumps({'generated_at': now(), 'records': rejected}, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'harvest_report.json').write_text(json.dumps({'generated_at': now(), 'published': len(published), 'rejected_or_low_confidence': len(rejected), 'providers': provider_reports}, ensure_ascii=False, indent=2), encoding='utf-8')
    (QUEUE / 'media_mentions.json').write_text('[]\n', encoding='utf-8')
    with (QUEUE / 'media_mentions.csv').open('w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerow(['id', 'confidence', 'title', 'source_name', 'domain', 'published_at', 'url', 'query'])
    print(json.dumps({'published_media_mentions': len(published), 'low_confidence': len(rejected)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
