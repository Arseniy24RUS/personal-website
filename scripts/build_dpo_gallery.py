#!/usr/bin/env python3
"""Build a static continuing-professional-education gallery.

The workflow mirrors the diplomas gallery builder, but keeps every rendered PDF
page for the modal view while using the first page as the thumbnail.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile

import fitz  # PyMuPDF
from PIL import Image, ImageOps

ROOT = Path('.')
INPUT_DIR = ROOT / 'content' / 'dpo'
WORK = ROOT / '.tmp_dpo'
THUMBS = ROOT / 'assets' / 'dpo' / 'thumbs'
PAGES = ROOT / 'assets' / 'dpo' / 'pages'
OUT = ROOT / 'data' / 'dpo' / 'gallery.json'
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp'}
PDF_EXTS = {'.pdf'}
SUPPORTED_EXTS = IMAGE_EXTS | PDF_EXTS

TRANSLIT = str.maketrans({
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y',
    'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
    'х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
})


def slugify(value: str) -> str:
    value = value.lower().translate(TRANSLIT)
    value = re.sub(r'[^a-z0-9]+', '-', value).strip('-')
    return value[:90] or 'dpo'


def year_from_name(name: str):
    if 'master of public policy' in name.lower():
        return 2022
    years = re.findall(r'(20\d{2}|19\d{2})', name)
    return int(years[-1]) if years else None


def title_from_name(path: Path) -> str:
    name = re.sub(r'[_-]+', ' ', path.stem)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:1].upper() + name[1:] if name else 'Document'


def file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()[:10]


def reset_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def prepare_workdir():
    reset_dir(WORK)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    direct_dir = WORK / 'direct-files'
    direct_dir.mkdir(parents=True, exist_ok=True)

    archives = sorted(INPUT_DIR.glob('*.zip'))
    for src in INPUT_DIR.rglob('*'):
        if src.is_file() and src.suffix.lower() in SUPPORTED_EXTS:
            dst = direct_dir / src.name
            if dst.exists():
                dst = direct_dir / f"{src.stem}-{file_hash(src)}{src.suffix}"
            shutil.copy2(src, dst)

    for idx, zip_path in enumerate(archives, start=1):
        extract_to = WORK / f'archive-{idx:02d}-{slugify(zip_path.stem)}'
        extract_to.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_to)

    return archives


def collect_source_files():
    files = []
    for p in WORK.rglob('*'):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            if '__MACOSX' in p.parts or p.name.startswith('._'):
                continue
            files.append(p)
    files.sort(key=lambda p: (-(year_from_name(p.as_posix()) or -1), p.as_posix().lower()))
    return files


def resize_max(img: Image.Image, max_side: int) -> Image.Image:
    img = img.copy()
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return img


def render_pdf_pages(path: Path):
    doc = fitz.open(path)
    try:
        for page_number in range(doc.page_count):
            page = doc.load_page(page_number)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            yield Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
    finally:
        doc.close()


def load_source_pages(path: Path):
    if path.suffix.lower() in PDF_EXTS:
        return list(render_pdf_pages(path))
    img = Image.open(path)
    return [ImageOps.exif_transpose(img).convert('RGB')]


def main():
    archives = prepare_workdir()
    files = collect_source_files()
    if not archives and not files:
        raise FileNotFoundError('No ZIP, PDF or image files found in content/dpo/')

    reset_dir(THUMBS)
    reset_dir(PAGES)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    items = []
    used = set()
    for path in files:
        year = year_from_name(path.as_posix())
        base = f"{year or 'nd'}-{slugify(path.stem)}"
        if base in used:
            base = f"{base}-{file_hash(path)}"
        used.add(base)
        try:
            images = load_source_pages(path)
        except Exception as exc:
            print(f'SKIP {path}: {exc}')
            continue
        if not images:
            continue

        page_records = []
        for page_index, img in enumerate(images, start=1):
            width, height = img.size
            page_path = PAGES / f"{base}-p{page_index:02d}.webp"
            resize_max(img, 1800).save(page_path, 'WEBP', quality=84, method=6)
            page_records.append({
                'page': page_index,
                'src': str(page_path).replace('\\', '/'),
                'width': width,
                'height': height,
                'orientation': 'landscape' if width > height else 'portrait',
            })

        thumb_path = THUMBS / f"{base}.webp"
        resize_max(images[0], 520).save(thumb_path, 'WEBP', quality=76, method=6)
        first = page_records[0]
        orientation = first['orientation']
        items.append({
            'id': base,
            'title': title_from_name(path),
            'year': year,
            'kind': 'pdf' if path.suffix.lower() in PDF_EXTS else 'image',
            'source_filename': path.name,
            'page_count': len(page_records),
            'width': first['width'],
            'height': first['height'],
            'orientation': orientation,
            'span': 2 if orientation == 'landscape' else 1,
            'thumb': str(thumb_path).replace('\\', '/'),
            'full': first['src'],
            'download': first['src'],
            'pages': page_records,
        })

    OUT.write_text(json.dumps({
        'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'count': len(items),
        'sort': 'year_desc_name_asc',
        'input_archives': [str(p).replace('\\', '/') for p in archives],
        'items': items,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Built DPO gallery: {len(items)} items')


if __name__ == '__main__':
    main()
