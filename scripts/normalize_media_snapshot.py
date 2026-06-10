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

from media_postprocess import is_blocked_record, postprocess_media_files

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
    r'Основные сведения Структура|Новости Минобрнауки РФ|slick|bootstrap|font-awesome|'
    r'ДЕМ\.ИНФОРМ - первое демографическое информационное агентство России Главная',
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

EN_OVERRIDES = {
    'https://kaluga-zaprava.ru/biblioteka/rf/hossijan-molozhe-35-let-ostanetsja-lish-chetvert-naselenija': {
        'title_en': 'Russians under 35 will make up only a quarter of the population',
        'description_en': 'A secondary republication of a story about Arseniy Sitkovskiy’s demographic estimates.',
        'source_name_en': 'Kaluga Za Pravdu',
    },
    'https://deminform.ru/analytics/vliyaniye-gosudarstvennoy-politiki-aglomerirovaniya-na-dolgosrochnye-tendentsii-izmeneniya-chislennosti-naseleniya-rossii': {
        'title_en': 'The effect of agglomeration policy on long-term population trends in Russia',
        'description_en': 'A DEM.INFORM analytical article on the long-term demographic consequences of agglomeration policy and spatial population concentration.',
        'source_name_en': 'DEM.INFORM',
    },
    'https://www.sobaka.ru/city/society/210740': {
        'title_en': 'Very soon Russians under 35 will make up only a quarter of the population; in 1990 they accounted for half. What happens next?',
        'description_en': 'A Sobaka.ru article on a new demographic forecast and the social landscape it implies.',
        'source_name_en': 'Sobaka.ru',
    },
    'https://www.rosbalt.ru/news/2026-01-31/obschestvo-superzrelosti-my-stremitelno-stareem-5543743': {
        'title_en': 'A super-mature society: we are ageing rapidly',
        'description_en': 'A Rosbalt article on population ageing, shifts in the age structure and the social consequences of these processes.',
        'source_name_en': 'Rosbalt',
    },
    'https://t.me/tolk_tolk/27280': {
        'title_en': 'Tolk: Russian agglomerations and settlement trends',
        'description_en': 'A Telegram post discussing research by Sitkovskiy, Raysikh, Gladky and Bezverbnaya on Russian agglomerations, settlement systems and regional growth trends.',
        'source_name_en': 'Telegram',
    },
    'https://t.me/tolk_tolk/27274': {
        'title_en': 'Tolk: Russia’s shrinking younger population',
        'description_en': 'A Telegram post citing Arseniy Sitkovskiy’s work on the declining share of Russians aged 0-35 and its social implications.',
        'source_name_en': 'Telegram',
    },
    'https://new.ras.ru/press-center/vi-vserossiyskiy-demograficheskiy-forum-s-mezhdunarodnym-uchastiem': {
        'title_en': '6th All-Russian Demographic Forum with International Participation',
        'description_en': 'The Russian Academy of Sciences page lists Arseniy M. Sitkovskiy, junior researcher at the Institute for Social Demography, FCTAS RAS.',
        'source_name_en': 'Russian Academy of Sciences',
    },
    'https://chelyabinsk.bezformata.com/listnews/konferentciya-molodyozh/152835280': {
        'title_en': 'All-Russian Conference “Youth as a Resource for the Development of Russian Regions”',
        'description_en': 'A BezFormata Chelyabinsk news item mentioning A. M. Sitkovskiy as a researcher at the Digital Demography Laboratory, FCTAS RAS.',
        'source_name_en': 'BezFormata Chelyabinsk',
    },
    'https://deminform.ru/analytics/demograficheskiye-resursy-rossii-variativnost-podkhodov-i-otsenok': {
        'title_en': 'Russia’s demographic resources: variation in approaches and estimates',
        'description_en': 'A DEM.INFORM article listing A. M. Sitkovskiy among the authors.',
        'source_name_en': 'DEM.INFORM',
    },
    'https://www.demoscope.ru/weekly/2025/01081/gazeta03.php': {
        'title_en': 'Newspapers write about educational migration',
        'description_en': 'A Demoscope Weekly press review item on educational migration.',
        'source_name_en': 'Demoscope Weekly',
    },
    'https://phil.rudn.ru/ru/media/news/123574': {
        'title_en': 'RUDN delegation took part in an All-Russian research and practice conference',
        'description_en': 'A RUDN University news item mentioning A. M. Sitkovskiy’s conference presentation.',
        'source_name_en': 'RUDN University',
    },
    'https://phil.rudn.ru/ru/media/news/123453': {
        'title_en': 'The National Demographic Report 2024 was presented at the Institute for Demographic Research of the Russian Academy of Sciences',
        'description_en': 'A RUDN University news item noting that A. M. Sitkovskiy co-authored three sections of the report.',
        'source_name_en': 'RUDN University',
    },
    'https://deminform.ru/analytics/urbanizatsiya-protiv-rozhdayemosti-strategiya-prostranstvennogo-razvitiya-rossii-do-2030-goda': {
        'title_en': 'Urbanisation versus fertility: Russia’s spatial development strategy to 2030',
        'description_en': 'A DEM.INFORM analytical article on the links between urbanisation, spatial development and demographic dynamics.',
        'source_name_en': 'DEM.INFORM',
    },
    'https://mgimo.ru/about/news/departments/geodata-and-geoinformation-systems': {
        'title_en': 'Geodata and GIS: a methodological seminar for the Digital Department programme',
        'description_en': 'An MGIMO page mentioning Arseniy Sitkovskiy in the context of a geodata and GIS seminar.',
        'source_name_en': 'MGIMO',
    },
    'https://deminform.ru/analytics/semeynaya-ipoteka-2024-infrastrukturnoye-obespecheniye-mnogodetnoy-semyi': {
        'title_en': 'Family mortgage 2024: infrastructure support for large families',
        'description_en': 'A DEM.INFORM analytical article on family mortgages, infrastructure provision and spatial living conditions for large families.',
        'source_name_en': 'DEM.INFORM',
    },
    'https://deminform.ru/analytics/demograficheskoye-chudo-izrailya-mozhem-povtorit': {
        'title_en': 'Israel’s demographic miracle: can it be replicated?',
        'description_en': 'A DEM.INFORM analytical article on the drivers of high fertility in Israel and the applicability of selected demographic practices in Russia.',
        'source_name_en': 'DEM.INFORM',
    },
    'https://deminform.ru/analytics/voprosy-sistemy-rasseleniya-rossii-kotorym-ochen-nuzhny-otvety': {
        'title_en': 'Questions about Russia’s settlement system that urgently need answers',
        'description_en': 'An author article by A. M. Sitkovskiy on DEM.INFORM.',
        'source_name_en': 'DEM.INFORM',
    },
    'https://ion.ranepa.ru/news/studenty-ion-posetili-shirakskiy-gosudarstvennyy-universitet-v-armenii': {
        'title_en': 'ION students visited Shirak State University in Armenia',
        'description_en': 'A RANEPA Institute of Public Administration article listing Arseniy Sitkovskiy among master’s students of the Chelyabinsk branch of RANEPA.',
        'source_name_en': 'RANEPA',
    },
    'https://demografplatforma.ru/?p=1033': {
        'title_en': 'International Scientific Conference of Young Demographers',
        'description_en': 'A Demographic Platform news item identifying A. M. Sitkovskiy as an analyst at the Spatial Development Models laboratory.',
        'source_name_en': 'Demographic Platform',
    },
    'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3106523': {
        'title_en': 'Demographic policy of the Russian Federation',
        'description_en': 'An SSRN record for an early work authored by Arseniy Sitkovskiy, RANEPA Chelyabinsk branch.',
        'source_name_en': 'SSRN',
    },
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def records_from_text(text: str) -> list[dict]:
    try:
        payload = json.loads(text)
        return payload.get('records') or []
    except Exception:
        return []


def read_records(path: Path) -> list[dict]:
    try:
        return records_from_text(path.read_text(encoding='utf-8'))
    except Exception:
        return []


def read_head_records(path: Path) -> list[dict]:
    """Recover the committed snapshot even after a harvester has overwritten files."""
    try:
        raw = subprocess.check_output(
            ['git', 'show', f'HEAD:{path.as_posix()}'],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return records_from_text(raw)
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
    if is_blocked_record(record):
        return True
    if record.get('source') == 'institutional_site_scan' and (title.strip() in {'ФНИСЦ РАН', 'РУДН'} or JUNK.search(desc)):
        return True
    return False


def override(record: dict) -> dict:
    info = OVERRIDES.get(canonical(record.get('url')))
    if info:
        record.update(info)
        record['title'] = info.get('title_ru') or record.get('title')
        record['description'] = info.get('description_ru') or record.get('description')
        record['language'] = 'ru'
    en_info = EN_OVERRIDES.get(canonical(record.get('url')))
    if en_info:
        record.update(en_info)
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
    published = merge(
        before,
        read_head_records(PUBLISHED),
        read_head_records(NEWS),
        read_records(PUBLISHED),
        read_records(NEWS),
    )
    rejected = merge(read_head_records(REJECTED), read_records(REJECTED))
    write_records(PUBLISHED, published)
    write_records(NEWS, published)
    write_records(REJECTED, rejected)
    post = postprocess_media_files()
    print(json.dumps({'published': post['published'], 'rejected_or_low_confidence': post['rejected_or_low_confidence']}, ensure_ascii=False))


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
