from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.dont_write_bytecode = True

from seo_config import ALTERNATE_NAMES, BASE_URL, PAGES, ROBOTS_META, SAME_AS, page_url

ROOT = Path(__file__).resolve().parents[1]
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def attr_value(tag: str, attr: str) -> str | None:
    match = re.search(rf'\b{re.escape(attr)}="([^"]*)"', tag, flags=re.I)
    return match.group(1) if match else None


def find_tag(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.I | re.S)
    return match.group(0) if match else None


def json_ld_blocks(text: str) -> list[dict]:
    blocks = []
    for match in re.finditer(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', text, flags=re.I | re.S):
        try:
            blocks.append(json.loads(match.group(1)))
        except json.JSONDecodeError as exc:
            fail(f"Invalid JSON-LD: {exc}")
    return blocks


def graph_types(blocks: list[dict]) -> set[str]:
    types = set()
    for block in blocks:
        nodes = block.get("@graph", [block])
        if isinstance(nodes, dict):
            nodes = [nodes]
        for node in nodes:
            node_type = node.get("@type") if isinstance(node, dict) else None
            if isinstance(node_type, list):
                types.update(str(item) for item in node_type)
            elif node_type:
                types.add(str(node_type))
    return types


def person_nodes(blocks: list[dict]) -> list[dict]:
    people = []
    for block in blocks:
        nodes = block.get("@graph", [block])
        if isinstance(nodes, dict):
            nodes = [nodes]
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "Person":
                people.append(node)
    return people


def path_for_url(url: str) -> Path:
    rel = url.removeprefix(BASE_URL).lstrip("/")
    if rel == "":
        return ROOT / "index.html"
    if rel == "en/":
        return ROOT / "en" / "index.html"
    return ROOT / rel


def check_base_files() -> None:
    cname = ROOT / "CNAME"
    if not cname.exists():
        fail("CNAME is missing")
    elif read(cname).strip() != "sitkovskiy.ru":
        fail("CNAME must contain exactly sitkovskiy.ru")
    if not (ROOT / ".nojekyll").exists():
        fail(".nojekyll is missing")
    robots = ROOT / "robots.txt"
    if not robots.exists():
        fail("robots.txt is missing")
    else:
        text = read(robots)
        if "Disallow: /" in text:
            fail("robots.txt must not contain Disallow: /")
        if "Sitemap: https://sitkovskiy.ru/sitemap.xml" not in text:
            fail("robots.txt must point to canonical sitemap")


def check_sitemap() -> list[str]:
    sitemap = ROOT / "sitemap.xml"
    if not sitemap.exists():
        fail("sitemap.xml is missing")
        return []
    try:
        tree = ET.parse(sitemap)
    except ET.ParseError as exc:
        fail(f"sitemap.xml is invalid XML: {exc}")
        return []
    urls = [el.text or "" for el in tree.findall(".//sm:loc", NS)]
    expected = [page_url(page, lang) for lang in ("ru", "en") for page in PAGES]
    if urls != expected:
        fail("sitemap.xml URL list/order does not match the 18 canonical ru/en pages")
    if len(urls) != 18:
        fail(f"sitemap.xml must contain exactly 18 URLs, found {len(urls)}")
    for url in urls:
        if not url.startswith(f"{BASE_URL}/"):
            fail(f"Non-canonical sitemap URL: {url}")
        if "github.io" in url:
            fail(f"github.io URL found in sitemap: {url}")
        if "admin.html" in url:
            fail("admin.html must not appear in sitemap")
        if not path_for_url(url).exists():
            fail(f"Sitemap page does not exist: {url}")
    return urls


def check_page(url: str) -> None:
    path = path_for_url(url)
    text = read(path)
    canonical_tag = find_tag(text, r'<link\b[^>]*rel="canonical"[^>]*>')
    if not canonical_tag:
        fail(f"Missing canonical in {path.relative_to(ROOT)}")
    elif attr_value(canonical_tag, "href") != url:
        fail(f"Canonical mismatch in {path.relative_to(ROOT)}")

    robots_tag = find_tag(text, r'<meta\b[^>]*name="robots"[^>]*>')
    if not robots_tag:
        fail(f"Missing robots meta in {path.relative_to(ROOT)}")
    elif attr_value(robots_tag, "content") != ROBOTS_META:
        fail(f"Wrong robots meta in {path.relative_to(ROOT)}")

    is_en = "/en/" in url
    html_tag = find_tag(text, r"<html\b[^>]*>")
    if not html_tag:
        fail(f"Missing html tag in {path.relative_to(ROOT)}")
    elif is_en:
        if 'lang="en"' not in html_tag or "lang-en" not in html_tag:
            fail(f"English html tag is not localized in {path.relative_to(ROOT)}")
    elif 'lang="ru"' not in html_tag:
        fail(f"Russian html tag must have lang=ru in {path.relative_to(ROOT)}")

    if is_en:
        body_tag = find_tag(text, r"<body\b[^>]*>")
        if not body_tag or "lang-en" not in body_tag:
            fail(f"English body is missing lang-en in {path.relative_to(ROOT)}")
        for resource in ('href="assets/', 'src="assets/', "fetch('data/", 'fetch(\"data/'):
            if resource in text and '<base href="../">' not in text:
                fail(f"English page lacks base href for root resources: {path.relative_to(ROOT)}")

    page = next((p for p in PAGES if page_url(p, "en" if is_en else "ru") == url), None)
    if page:
        alternates = {
            attr_value(tag, "hreflang"): attr_value(tag, "href")
            for tag in re.findall(r'<link\b[^>]*rel="alternate"[^>]*>', text, flags=re.I | re.S)
        }
        expected = {
            "ru": page_url(page, "ru"),
            "en": page_url(page, "en"),
            "x-default": page_url(page, "ru"),
        }
        if alternates != expected:
            fail(f"Broken hreflang set in {path.relative_to(ROOT)}")

    blocks = json_ld_blocks(text)
    types = graph_types(blocks)
    if path.name == "index.html" and (not is_en or path.parent.name == "en"):
        missing = {"Person", "ProfilePage", "WebSite"} - types
        if missing:
            fail(f"Home JSON-LD missing {sorted(missing)} in {path.relative_to(ROOT)}")
        for person in person_nodes(blocks):
            names = set(person.get("alternateName", []))
            same_as = set(person.get("sameAs", []))
            for name in ["Ситковский Арсений", "Ситковский А. М.", "Sitkovskiy Arseniy", "Arseniy M. Sitkovskiy"]:
                if name not in names:
                    fail(f"Person alternateName missing {name} in {path.relative_to(ROOT)}")
            for marker in SAME_AS:
                if marker not in same_as:
                    fail(f"Person sameAs missing {marker} in {path.relative_to(ROOT)}")
    elif "WebPage" not in types:
        fail(f"Internal page missing WebPage JSON-LD in {path.relative_to(ROOT)}")


def check_admin() -> None:
    admin = ROOT / "admin.html"
    if not admin.exists():
        return
    text = read(admin)
    robots_tag = find_tag(text, r'<meta\b[^>]*name="robots"[^>]*>')
    if not robots_tag or attr_value(robots_tag, "content") != "noindex,follow":
        fail("admin.html must contain robots noindex,follow")
    if (ROOT / "en" / "admin.html").exists():
        fail("en/admin.html must not exist")


def check_site_js() -> None:
    text = read(ROOT / "assets" / "site.js")
    update_match = re.search(r"function\s+updatePageMeta\s*\([^)]*\)\s*\{(?P<body>.*?)\n\}", text, flags=re.S)
    if not update_match:
        fail("assets/site.js missing updatePageMeta guard")
    else:
        body = update_match.group("body")
        if "document.title" in body or "meta[name=\"description\"]" in body or "meta[name='description']" in body:
            fail("updatePageMeta must not mutate title or description")


def check_public_json_data() -> None:
    conflict_markers = ("<<<<<<<", "=======", ">>>>>>>")
    for path in sorted((ROOT / "data").rglob("*.json")):
        rel = path.relative_to(ROOT).as_posix()
        text = read(path)
        if any(marker in text for marker in conflict_markers):
            fail(f"Conflict marker found in public JSON data: {rel}")
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            fail(f"Invalid public JSON data in {rel}: {exc}")


def check_forbidden_files_and_meta() -> None:
    forbidden_names = ["BingSiteAuth.xml", "docs/search-indexing.md"]
    for name in forbidden_names:
        if (ROOT / name).exists():
            fail(f"Forbidden file exists: {name}")
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        lower = path.name.lower()
        if re.fullmatch(r"google.*\.html", lower) or re.fullmatch(r"yandex.*\.html", lower):
            fail(f"Forbidden verification file exists: {rel}")
        if path.suffix.lower() in {".html", ".js", ".py"}:
            text = read(path)
            if re.search(r'<meta\b[^>]*name="keywords"', text, flags=re.I):
                fail(f"meta keywords found in {rel}")
            if re.search(r'<meta\b[^>]*name="(?:google-site-verification|yandex-verification)"', text, flags=re.I):
                fail(f"Verification meta tag found in {rel}")


def main() -> int:
    check_base_files()
    urls = check_sitemap()
    for url in urls:
        check_page(url)
    check_admin()
    check_site_js()
    check_public_json_data()
    check_forbidden_files_and_meta()
    if ERRORS:
        print("SEO check failed:")
        for error in ERRORS:
            print(f"- {error}")
        return 1
    print("SEO check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
