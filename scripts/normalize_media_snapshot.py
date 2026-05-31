#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import argparse
import json
import re
import subprocess
import sys

OUT = Path('data/media')
PUBLISHED = OUT / 'published.json'
NEWS = OUT / 'news_mentions.json'
REJECTED = OUT / 'rejected_or_low_confidence.json'

BLOCKED = [
    re.compile(r'admission\.rudn\.ru/staff/86110487-4a8f-11f0-b545-00155d0c0d4a', re.I),
    re.compile(r'fnisc\.ru/pers_about\.html\?id=2472', re.I),
    re.compile(r'fnisc\.ru/index\.php\?page_id=(44|2366|2483)', re.I),
]

JUNK = re.compile(
    r'Публикации молодых ученых|Поиск Информация|Противодействие корруп|'
    r'Основные сведения Структура|Новости Минобрнауки РФ|slick|bootstrap|font-awesome',
    re.I,
)

OVERRIDES = {
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


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_records(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        return payload.get('records') or []
    except Exception:
        return []


def write_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'generated_at': now(), 'records': records}, ensure_ascii=False, indent=2), encoding='utf-8')


def canonical(url: str | None) -> str:
    if not url:
        return ''
    try:
        p = urlparse(str(url).strip())
        return p._replace(fragment='').geturl().rstrip('/')
    except Exception:
        return str(url).split('#')[0].rstrip('/')


def blocked(record: dict) -> bool:
    u = canonical(record.get('url'))
    if not u or any(rx.search(u) for rx in BLOCKED):
        return True
    if re.search(r'\.(css|js|mjs|map|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|pdf)(\?.*)?$', u, re.I):
        return True
    title = str(record.get('title') or record.get('title_ru') or '')
    desc = str(record.get('description') or record.get('description_ru') or '')
    if record.get('source') == 'institutional_site_scan' and (title.strip() in {'ФНИСЦ РАН', 'РУДН'} or JUNK.search(desc)):
        return True
    return False


def override(record: dict) -> dict:
    info = OVERRIDES.get(canonical(record.get('url')))
    if not info:
        return record
    record.update(info)
    record['title'] = info.get('title_ru') or record.get('title')
    record['description'] = info.get('description_ru') or record.get('description')
    record['language'] = 'ru'
    return record


def merge(*groups: list[dict]) -> list[dict]:
    out, seen = [], set()
    for group in groups:
        for rec in group:
            if not rec:
                continue
            rec = override(dict(rec))
            key = canonical(rec.get('url')) or rec.get('id')
            if not key or key in seen or blocked(rec):
                continue
            seen.add(key)
            out.append(rec)
    out.sort(key=lambda r: (r.get('published_at') or r.get('harvested_at') or ''), reverse=True)
    return out


def normalize(before: list[dict] | None = None) -> None:
    before = before or []
    published = merge(before, read_records(PUBLISHED))
    rejected = merge(read_records(REJECTED))
    write_records(PUBLISHED, published)
    write_records(NEWS, published)
    write_records(REJECTED, rejected)
    print(json.dumps({'published': len(published), 'rejected_or_low_confidence': len(rejected)}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--normalize-only', action='store_true')
    args = parser.parse_args()
    before = read_records(PUBLISHED)
    if not args.normalize_only:
        code = subprocess.call([sys.executable, 'scripts/harvest_media_mentions.py'])
        if code != 0:
            print(f'base media harvester exited with {code}; preserving and normalizing existing records', file=sys.stderr)
    normalize(before)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
