from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from seo_config import (
    ALTERNATE_NAMES,
    BASE_URL,
    PAGES,
    ROBOTS_META,
    SAME_AS,
    SITE_IMAGE,
    description_for,
    page_url,
    title_for,
)

ROOT = Path(__file__).resolve().parents[1]
EN_DIR = ROOT / "en"


def esc_attr(value: str) -> str:
    return html.escape(value, quote=True)


def json_script(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return f'<script type="application/ld+json">\n{payload}\n</script>'


def person_graph(page: dict[str, str], lang: str) -> dict:
    canonical = page_url(page, lang)
    person_name = "Ситковский Арсений Михайлович" if lang == "ru" else "Arseniy M. Sitkovskiy"
    site_name = "Ситковский А. М." if lang == "ru" else "Arseniy M. Sitkovskiy"
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{BASE_URL}/#website",
                "url": f"{BASE_URL}/",
                "name": site_name,
                "inLanguage": lang,
                "about": {"@id": f"{BASE_URL}/#person"},
            },
            {
                "@type": "ProfilePage",
                "@id": f"{canonical}#webpage",
                "url": canonical,
                "name": title_for(page, lang),
                "isPartOf": {"@id": f"{BASE_URL}/#website"},
                "about": {"@id": f"{BASE_URL}/#person"},
                "mainEntity": {"@id": f"{BASE_URL}/#person"},
                "inLanguage": lang,
            },
            {
                "@type": "Person",
                "@id": f"{BASE_URL}/#person",
                "name": person_name,
                "alternateName": ALTERNATE_NAMES,
                "sameAs": SAME_AS,
                "url": f"{BASE_URL}/",
                "image": SITE_IMAGE,
                "email": "mailto:omnistat@yandex.ru",
                "jobTitle": ["демограф", "экономгеограф", "научный сотрудник", "преподаватель"],
                "knowsAbout": [
                    "демография",
                    "economic geography",
                    "spatial development",
                    "regional economics",
                    "GIS",
                    "geoanalytics",
                ],
                "worksFor": [
                    {"@type": "Organization", "name": "ФНИСЦ РАН"},
                    {"@type": "Organization", "name": "РУДН"},
                ],
            },
        ],
    }


def webpage_graph(page: dict[str, str], lang: str) -> dict:
    canonical = page_url(page, lang)
    return {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "@id": f"{canonical}#webpage",
        "url": canonical,
        "name": title_for(page, lang),
        "isPartOf": {"@id": f"{BASE_URL}/#website"},
        "about": {"@id": f"{BASE_URL}/#person"},
        "inLanguage": lang,
    }


def seo_head(page: dict[str, str], lang: str, include_base: bool) -> str:
    canonical = page_url(page, lang)
    ru_url = page_url(page, "ru")
    en_url = page_url(page, "en")
    title = title_for(page, lang)
    description = description_for(page, lang)
    og_title = page.get(f"{lang}_og_title", title)
    og_description = page.get(f"{lang}_og_description", description)
    site_name = "Ситковский А. М." if lang == "ru" else "Arseniy M. Sitkovskiy"
    locale = "ru_RU" if lang == "ru" else "en_US"
    alternate_locale = "en_US" if lang == "ru" else "ru_RU"
    graph = person_graph(page, lang) if page["file"] == "index.html" else webpage_graph(page, lang)
    lines = [
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
    ]
    if include_base:
        lines.append('  <base href="../">')
    lines.extend(
        [
            f"  <title>{html.escape(title)}</title>",
            f'  <meta name="description" content="{esc_attr(description)}">',
            f'  <meta name="robots" content="{ROBOTS_META}">',
            f'  <link rel="canonical" href="{canonical}">',
            f'  <link rel="alternate" hreflang="ru" href="{ru_url}">',
            f'  <link rel="alternate" hreflang="en" href="{en_url}">',
            f'  <link rel="alternate" hreflang="x-default" href="{ru_url}">',
            f'  <meta property="og:type" content="{page.get("og_type", "website")}">',
            f'  <meta property="og:site_name" content="{esc_attr(site_name)}">',
            f'  <meta property="og:title" content="{esc_attr(og_title)}">',
            f'  <meta property="og:description" content="{esc_attr(og_description)}">',
            f'  <meta property="og:url" content="{canonical}">',
            f'  <meta property="og:image" content="{SITE_IMAGE}">',
            f'  <meta property="og:locale" content="{locale}">',
            f'  <meta property="og:locale:alternate" content="{alternate_locale}">',
            '  <meta name="twitter:card" content="summary_large_image">',
            f'  <meta name="twitter:title" content="{esc_attr(og_title)}">',
            f'  <meta name="twitter:description" content="{esc_attr(og_description)}">',
            f'  <meta name="twitter:image" content="{SITE_IMAGE}">',
        ]
    )
    if page["file"] == "index.html":
        lines.extend(
            [
                '  <link rel="stylesheet" href="assets/site.css">',
                '  <link rel="stylesheet" href="assets/additions.css?v=20260607-nav-nowrap">',
                '  <link rel="stylesheet" href="assets/diplomas.css?v=20260607-dpo">',
                '  <script defer src="assets/site.js?v=20260607-it-resources"></script>',
                '  <script defer src="assets/dpo.js?v=20260607-dpo"></script>',
            ]
        )
    else:
        lines.extend(extract_assets(page["file"]))
    lines.append("  " + json_script(graph).replace("\n", "\n  "))
    lines.append("</head>")
    return "\n".join(lines)


def extract_assets(file_name: str) -> list[str]:
    source = (ROOT / file_name).read_text(encoding="utf-8")
    assets = extract_assets_from_source(source)
    has_inline_script = any(is_inline_script(asset) for asset in assets)
    if not has_inline_script:
        tracked = tracked_source(file_name)
        if tracked:
            for asset in extract_assets_from_source(tracked):
                if is_inline_script(asset) and asset not in assets:
                    assets.append(asset)
    return assets


def opening_tag(tag: str) -> str:
    return tag.split(">", 1)[0].lower()


def is_inline_script(tag: str) -> bool:
    return tag.lstrip().lower().startswith("<script") and " src=" not in opening_tag(tag)


def tracked_source(file_name: str) -> str:
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{file_name}"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except Exception:
        return ""
    return result.stdout if result.returncode == 0 else ""


def extract_assets_from_source(source: str) -> list[str]:
    head_match = re.search(r"<head\b[^>]*>(.*?)</head>", source, flags=re.I | re.S)
    if not head_match:
        raise RuntimeError("Missing head")
    head = head_match.group(1)
    tags = re.findall(r"<link\b[^>]*>|<script\b[^>]*>.*?</script>", head, flags=re.I | re.S)
    assets = []
    for tag in tags:
        stripped = tag.strip()
        lower_open = opening_tag(stripped)
        lower = stripped.lower()
        if lower.startswith("<script") and 'type="application/ld+json"' in lower_open:
            continue
        if lower.startswith("<link") and 'rel="stylesheet"' not in lower and "rel='stylesheet'" not in lower:
            continue
        assets.append("  " + stripped)
    return assets


def replace_head(text: str, new_head: str) -> str:
    return re.sub(r"<head\b[^>]*>.*?</head>", lambda _: new_head, text, count=1, flags=re.I | re.S)


def set_html_attrs(text: str, lang: str) -> str:
    if lang == "en":
        return re.sub(
            r"<html\b[^>]*>",
            '<html lang="en" class="lang-en" data-default-lang="en">',
            text,
            count=1,
            flags=re.I,
        )
    return re.sub(r"<html\b[^>]*>", '<html lang="ru">', text, count=1, flags=re.I)


def add_body_lang_en(text: str) -> str:
    body_match = re.search(r"<body\b([^>]*)>", text, flags=re.I)
    if not body_match:
        raise RuntimeError("Missing body")
    attrs = body_match.group(1)
    class_match = re.search(r'class="([^"]*)"', attrs, flags=re.I)
    if class_match:
        classes = class_match.group(1).split()
        if "lang-en" not in classes:
            classes.append("lang-en")
        new_attrs = attrs[: class_match.start()] + f'class="{" ".join(classes)}"' + attrs[class_match.end() :]
    else:
        new_attrs = attrs + ' class="lang-en"'
    return text[: body_match.start()] + f"<body{new_attrs}>" + text[body_match.end() :]


def build() -> None:
    EN_DIR.mkdir(exist_ok=True)
    for page in PAGES:
        source_path = ROOT / page["file"]
        source = source_path.read_text(encoding="utf-8")
        source = set_html_attrs(replace_head(source, seo_head(page, "ru", include_base=False)), "ru")
        source_path.write_text(source, encoding="utf-8", newline="\n")

        english = set_html_attrs(source, "en")
        english = add_body_lang_en(english)
        english = replace_head(english, seo_head(page, "en", include_base=True))
        (EN_DIR / page["file"]).write_text(english, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    build()
