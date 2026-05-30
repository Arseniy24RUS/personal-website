#!/usr/bin/env python3
"""Build diplomas gallery assets from a ZIP archive uploaded to content/diplomas/.

Expected input:
  content/diplomas/*.zip

Outputs:
  assets/diplomas/thumbs/*.webp
  assets/diplomas/full/*.webp
  data/diplomas/gallery.json

PDF files are rendered by PyMuPDF using the first page. Images are processed by
Pillow. The script is deterministic and safe for GitHub Pages static hosting.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import re
import shutil
import zipfile

from PIL import Image, ImageOps
import fitz  # PyMuPDF

ROOT = Path('.')
INPUT_DIR = ROOT / 'content' / 'diplomas'
WORK = ROOT / '.tmp_diplomas'
THUMBS = ROOT / 'assets' / 'diplomas' / 'thumbs'
FULL = ROOT / 'assets' / 'diplomas' / 'full'
OUT = ROOT / 'data' / 'diplomas' / 'gallery.json'
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp'}
PDF_EXTS = {'.pdf'}


def slugify(value: str) -> str:
    value = value.lower().replace('ё', 'e')
    table = str.maketrans({
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
    })
    value = value.translate(table)
    value = re.sub(r'[^a-z0-9]+', '-', value).strip('-')
    return value[:90] or 'diploma'


def year_from_name(name: str):
    m = re.search(r'(20\d{2}|19\d{2})', name)
    return int(m.group(1)) if m else None


def title_from_name(path: Path) -> str:
    name = re.sub(r'[_-]+', ' ', path.stem)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:1].upper() + name[1:]


def find_archive() -> Path:
    zips = sorted(INPUT_DIR.glob('*.zip'))
    if not zips:
        raise FileNotFoundError('No ZIP archive found in content/diplomas/')
    return zips[-1]


def extract_archive(zip_path: Path):
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(WORK)


def load_image(path: Path) -> Image.Image:
    if path.suffix.lower() in PDF_EXTS:
        doc = fitz.open(path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
        doc.close()
        return img
    img = Image.open(path)
    return ImageOps.exif_transpose(img).convert('RGB')


def resize_max(img: Image.Image, max_side: int) -> Image.Image:
    img = img.copy()
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return img


def main():
    zip_path = find_archive()
    extract_archive(zip_path)
    THUMBS.mkdir(parents=True, exist_ok=True)
    FULL.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    files = []
    for p in WORK.rglob('*'):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS | PDF_EXTS:
            files.append(p)
    files.sort(key=lambda p: (year_from_name(p.name) or 9999, p.name.lower()))

    items = []
    used = set()
    for idx, path in enumerate(files, start=1):
        year = year_from_name(path.name)
        base = f"{year or 'nd'}-{slugify(path.stem)}"
        if base in used:
            base = f"{base}-{idx}"
        used.add(base)
        full_path = FULL / f"{base}.webp"
        thumb_path = THUMBS / f"{base}.webp"
        try:
            img = load_image(path)
        except Exception as exc:
            print(f'SKIP {path}: {exc}')
            continue
        resize_max(img, 1800).save(full_path, 'WEBP', quality=84, method=6)
        resize_max(img, 520).save(thumb_path, 'WEBP', quality=76, method=6)
        items.append({
            'id': base,
            'title': title_from_name(path),
            'year': year,
            'thumb': str(thumb_path).replace('\\', '/'),
            'full': str(full_path).replace('\\', '/'),
            'download': str(full_path).replace('\\', '/'),
            'download_filename': full_path.name,
            'source_filename': path.name,
        })

    OUT.write_text(json.dumps({'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(), 'count': len(items), 'items': items}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Built diplomas gallery: {len(items)} items from {zip_path}')


if __name__ == '__main__':
    main()
