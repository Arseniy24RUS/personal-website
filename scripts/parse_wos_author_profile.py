#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re


def clean(value: str | None) -> str:
    return re.sub(r'\s+', ' ', (value or '').replace('\xa0', ' ')).strip()


def int_value(value: str | None):
    text = clean(value)
    m = re.search(r'-?\d+', text.replace(',', ''))
    return int(m.group(0)) if m else None


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_summary_items(soup: BeautifulSoup) -> dict:
    out: dict[str, dict] = {}
    for item in soup.select('.summary-item'):
        count = item.select_one('.summary-count')
        label = item.select_one('.summary-label')
        if not count or not label:
            continue
        key = clean(label.get_text(' '))
        raw = clean(count.get_text(' '))
        if key:
            out[key] = {'raw': raw, 'value': int_value(raw)}
    return out


def parse_core_metrics(soup: BeautifulSoup) -> dict:
    out: dict[str, dict] = {}
    for block in soup.select('.wat-author-metric-inline-block'):
        value = block.select_one('.wat-author-metric')
        label = block.select_one('.wat-author-metric-descriptor')
        sub = block.select_one('.wat-author-metric-sub-descriptor')
        if not value or not label:
            continue
        key = clean(label.get_text(' '))
        raw = clean(value.get_text(' '))
        if key:
            out[key] = {
                'raw': raw,
                'value': int_value(raw),
                'descriptor': key,
                'sub_descriptor': clean(sub.get_text(' ')) if sub else '',
            }
    return out


def metric_value(mapping: dict, *labels):
    for label in labels:
        if label in mapping and mapping[label].get('value') is not None:
            return mapping[label]['value']
    lowered = {k.lower(): v for k, v in mapping.items()}
    for label in labels:
        needle = label.lower()
        for key, value in lowered.items():
            if needle in key and value.get('value') is not None:
                return value['value']
    return None


def normalized_summary(summary_metrics: dict, core_metrics: dict) -> dict:
    return {
        'publications': metric_value(core_metrics, 'Publications') or metric_value(summary_metrics, 'Web of Science Core Collection publications', 'Publications indexed in Web of Science'),
        'citations': metric_value(core_metrics, 'Sum of Times Cited'),
        'h_index': metric_value(core_metrics, 'H-Index', 'H-index'),
        'total_documents': metric_value(summary_metrics, 'Total documents'),
        'indexed_publications': metric_value(summary_metrics, 'Publications indexed in Web of Science'),
        'core_collection_publications': metric_value(summary_metrics, 'Web of Science Core Collection publications'),
    }


def parse_record(record) -> dict:
    text_lines = [clean(x) for x in record.get_text('\n').split('\n')]
    parts = [x for x in text_lines if x]
    title = ''
    title_el = record.select_one('app-summary-title a, app-summary-title .title, .title-link, h3 a, h3')
    if title_el:
        title = clean(title_el.get_text(' '))
    if not title:
        candidates = [p for p in parts if len(p) > 18 and not p.isdigit()]
        title = candidates[1] if len(candidates) > 1 and candidates[0].lower() in {'article', 'review', 'proceedings paper'} else (candidates[0] if candidates else '')
    year = None
    for p in parts:
        m = re.search(r'\b((?:19|20)\d{2})\b', p)
        if m:
            year = int(m.group(1))
            break
    doi = None
    joined = ' '.join(parts)
    m = re.search(r'10\.\d{4,9}/[^\s]+', joined, flags=re.I)
    if m:
        doi = m.group(0).rstrip('.,;')
    record_id = None
    link = record.find('a', href=True)
    url = None
    if link:
        href = link['href']
        url = href if href.startswith('http') else 'https://www.webofscience.com' + href
        id_match = re.search(r'WOS:([A-Z0-9]+)', href)
        if id_match:
            record_id = 'WOS:' + id_match.group(1)
    metadata_raw = clean(' | '.join(parts[:80]))
    fp = hashlib.sha256('|'.join([title.lower(), str(year or ''), doi or '']).encode('utf-8')).hexdigest()[:16]
    return {
        'source': 'web_of_science_free_view_author_profile',
        'wos_uid': record_id,
        'title': title,
        'title_en': title if title and not re.search(r'[А-Яа-яЁё]', title) else '',
        'year': year,
        'doi': doi,
        'url': url,
        'metadata_raw': metadata_raw,
        'dedupe_fingerprint': fp,
        'sources': ['wos'],
    }


def parse_wos_author_profile_html(html: str, researcher_id: str = 'AAG-1530-2021') -> dict:
    soup = BeautifulSoup(html, 'html.parser')
    title = clean((soup.title.get_text(' ') if soup.title else ''))
    records = []
    for rec in soup.find_all('app-record'):
        parsed = parse_record(rec)
        if parsed.get('title'):
            records.append(parsed)
    summary_metrics = parse_summary_items(soup)
    core_metrics = parse_core_metrics(soup)
    payload = {
        'source': 'web_of_science_free_view_author_profile',
        'source_url': f'https://www.webofscience.com/wos/author/record/{researcher_id}',
        'researcher_id': researcher_id,
        'generated_at': now(),
        'page_title': title,
        'summary': normalized_summary(summary_metrics, core_metrics),
        'summary_metrics': summary_metrics,
        'core_collection_metrics': core_metrics,
        'records_count_on_page': len(records),
        'records': records,
    }
    return payload


def parse_file(path: str, researcher_id: str = 'AAG-1530-2021') -> dict:
    return parse_wos_author_profile_html(Path(path).read_text(encoding='utf-8', errors='replace'), researcher_id)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('html')
    ap.add_argument('--researcher-id', default='AAG-1530-2021')
    ap.add_argument('--out', default='data/wos/profile_metrics.json')
    args = ap.parse_args()
    data = parse_file(args.html, args.researcher_id)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'out': str(out), 'records': data.get('records_count_on_page'), 'researcher_id': data.get('researcher_id')}, ensure_ascii=False, indent=2))
