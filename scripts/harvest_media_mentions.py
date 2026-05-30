#!/usr/bin/env python3
"""Free, API-less media mention harvester for a static scientist portfolio.

The script uses public RSS search feeds, primarily Google News RSS. It is not a
replacement for a professional media-monitoring API, but it is a useful free
baseline for GitHub Actions.

Outputs:
  data/media/news_mentions.json
  data/media/harvest_report.json
  data/admin_queue/media_mentions.json
  data/admin_queue/media_mentions.csv
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

ROOT = Path('.')
PROFILE = Path(os.environ.get('PROFILE_YAML', 'config/profile.yml'))
OUT = ROOT / 'data' / 'media'
QUEUE = ROOT / 'data' / 'admin_queue'
OUT.mkdir(parents=True, exist_ok=True)
QUEUE.mkdir(parents=True, exist_ok=True)

DEFAULT_QUERIES = [
    '"Ситковский Арсений"',
    '"Ситковский А.М."',
    '"Арсений Ситковский"',
    '"Arseniy Sitkovskiy"',
    '"Arseniy M. Sitkovskiy"',
]

STOP_DOMAINS = {
    'elibrary.ru', 'orcid.org', 'scopus.com', 'webofscience.com', 'github.com',
    'researchgate.net', 'scholar.google.com', 'cyberleninka.ru'
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_profile():
    if yaml is None or not PROFILE.exists():
        return {}
    return yaml.safe_load(PROFILE.read_text(encoding='utf-8')) or {}


def profile_queries():
    prof = (read_profile().get('profile') or {})
    names = [prof.get('display_name_ru'), prof.get('display_name_en')]
    queries = list(DEFAULT_QUERIES)
    for name in names:
        if name:
            queries.append('"' + str(name).strip() + '"')
    # Deduplicate preserving order.
    seen = set(); out = []
    for q in queries:
        if q not in seen:
            seen.add(q); out.append(q)
    return out


def rss_url(query: str, lang='ru', country='RU') -> str:
    params = {
        'q': query,
        'hl': lang,
        'gl': country,
        'ceid': f'{country}:{lang}',
    }
    return 'https://news.google.com/rss/search?' + urlencode(params)


def fetch_text(url: str):
    headers = {
        'User-Agent': 'Mozilla/5.0 scientist-portfolio-media-harvester/0.1',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
            enc = resp.headers.get_content_charset() or 'utf-8'
            return raw.decode(enc, errors='replace'), {'status': 'ok', 'http_status': resp.status, 'url': url, 'bytes': len(raw)}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:800]
        return None, {'status': 'http_error', 'http_status': exc.code, 'url': url, 'error_excerpt': body}
    except Exception as exc:
        return None, {'status': 'error', 'url': url, 'error': repr(exc)}


def unwrap_google_news_link(link: str) -> str:
    # Google News RSS often wraps links; keep the original if no obvious url parameter exists.
    if not link:
        return link
    qs = parse_qs(urlparse(link).query)
    for key in ['url', 'u']:
        if key in qs and qs[key]:
            return unquote(qs[key][0])
    return link


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith('www.') else host
    except Exception:
        return ''


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return value


def confidence(title: str, description: str, query: str, link: str) -> float:
    text = (title + ' ' + description).lower().replace('ё', 'е')
    score = 0.0
    if 'ситковск' in text:
        score += 0.45
    if 'арсени' in text or 'arseniy' in text or 'arseny' in text:
        score += 0.35
    if any(w in text for w in ['демограф', 'демографи', 'demograph', 'рудн', 'фнисц', 'fnisc', 'ruden', 'rudn']):
        score += 0.15
    if domain_of(link) in STOP_DOMAINS:
        score -= 0.3
    return max(0.0, min(1.0, round(score, 2)))


def parse_rss(xml_text: str, query: str):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall('.//item'):
        title = html.unescape((item.findtext('title') or '').strip())
        link = unwrap_google_news_link((item.findtext('link') or '').strip())
        desc = html.unescape(re.sub('<[^>]+>', ' ', item.findtext('description') or '')).strip()
        pub_date = parse_date(item.findtext('pubDate'))
        source_node = item.find('source')
        source_name = source_node.text.strip() if source_node is not None and source_node.text else None
        domain = domain_of(link)
        if domain in STOP_DOMAINS:
            continue
        conf = confidence(title, desc, query, link)
        if conf < 0.45:
            continue
        mention_id = hashlib.sha256((title + '|' + link).encode('utf-8')).hexdigest()[:16]
        items.append({
            'id': mention_id,
            'source': 'google_news_rss',
            'query': query,
            'title': title,
            'url': link,
            'domain': domain,
            'source_name': source_name,
            'published_at': pub_date,
            'description': desc,
            'confidence': conf,
            'status': 'auto_candidate',
            'harvested_at': now(),
        })
    return items


def dedupe(records):
    seen = set(); out = []
    for r in sorted(records, key=lambda x: (x.get('published_at') or '', x.get('confidence') or 0), reverse=True):
        key = r.get('url') or r.get('id')
        if key in seen:
            continue
        seen.add(key); out.append(r)
    return out


def write_queue(records):
    queue_items = []
    for r in records:
        queue_items.append({
            'id': 'media_' + r['id'],
            'entity_type': 'media_mention',
            'action': 'review_media_mention',
            'confidence': r.get('confidence'),
            'reason': 'Free RSS search candidate; requires human confirmation before public display',
            'candidate': r,
        })
    (QUEUE / 'media_mentions.json').write_text(json.dumps(queue_items, ensure_ascii=False, indent=2), encoding='utf-8')
    with (QUEUE / 'media_mentions.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id','confidence','title','source_name','domain','published_at','url','query'])
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k) for k in ['id','confidence','title','source_name','domain','published_at','url','query']})
    return queue_items


def main() -> int:
    records = []
    provider_reports = []
    for query in profile_queries():
        for lang, country in [('ru','RU'), ('en','US')]:
            url = rss_url(query, lang=lang, country=country)
            text, report = fetch_text(url)
            provider_reports.append(report)
            if text:
                try:
                    records.extend(parse_rss(text, query))
                except Exception as exc:
                    provider_reports.append({'status': 'parse_error', 'url': url, 'error': repr(exc)})
            time.sleep(0.2)
    records = dedupe(records)
    queue = write_queue(records)
    (OUT / 'news_mentions.json').write_text(json.dumps({'generated_at': now(), 'records': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'harvest_report.json').write_text(json.dumps({'generated_at': now(), 'queries': profile_queries(), 'providers': provider_reports, 'records': len(records), 'queue_items': len(queue)}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'media_mentions': len(records), 'queue_items': len(queue)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
