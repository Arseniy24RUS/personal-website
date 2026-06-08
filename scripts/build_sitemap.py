from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True

from seo_config import PAGES, page_url

ROOT = Path(__file__).resolve().parents[1]
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def lastmod_for(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path.relative_to(ROOT))],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            return value
    except Exception:
        pass
    return date.today().isoformat()


def build() -> None:
    ET.register_namespace("", NS)
    urlset = ET.Element(f"{{{NS}}}urlset")
    for lang in ("ru", "en"):
        for page in PAGES:
            file_path = ROOT / page["file"] if lang == "ru" else ROOT / "en" / page["file"]
            item = ET.SubElement(urlset, f"{{{NS}}}url")
            loc = ET.SubElement(item, f"{{{NS}}}loc")
            loc.text = page_url(page, lang)
            lastmod = ET.SubElement(item, f"{{{NS}}}lastmod")
            lastmod.text = lastmod_for(file_path)

    tree = ET.ElementTree(urlset)
    ET.indent(tree, space="  ", level=0)
    tree.write(ROOT / "sitemap.xml", encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    build()
