#!/usr/bin/env python3
"""Build a static diplomas/certificates gallery from user-uploaded files.

Universal workflow for future scientist portfolios:

1. Put one or more ZIP archives with any file names into content/diplomas/.
2. Optionally put standalone PDF/JPG/PNG/WebP files into content/diplomas/.
3. Run GitHub Action "Build diplomas gallery" manually.

The script recursively extracts all ZIP archives, processes images and the first
page of PDFs, creates lightweight thumbnails and full-screen WebP versions, and
writes data/diplomas/gallery.json for diplomas.html.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import hashlib
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
SUPPORTED_EXTS = IMAGE_EXTS | PDF_EXTS


def slugify(value: str) -> str:
    value = value.lower().replace('ё', 'e')
    table = str.maketrans({
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
    })
    value = value.translate(table)
    value = re.sub(r'[^a-z0-9]+', '-', value).strip('-')
    return value[:90] or 'diploma'


def year_from_name(name: str):
    years = re.findall(r'(20\d{2}|19\d{2})', name)
    return int(years[-1]) if years else None


def title_from_name(path: Path) -> str:
    name = re.sub(r'[_-]+', ' ', path.stem)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:1].upper() + name[1:] if name else 'Диплом / сертификат'


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
    archives = sorted(INPUT_DIR.glob('*.zip'))
    direct_dir = WORK / 'direct-files'
    direct_dir.mkdir(parents=True, exist_ok=True)

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
            # Ignore macOS service files and temporary artefacts inside archives.
            if '__MACOSX' in p.parts or p.name.startswith('._'):
                continue
            files.append(p)
    # Newest first by inferred year. Unknown years go last. Stable title order inside a year.
    files.sort(key=lambda p: (year_from_name(p.name) or -1, p.name.lower()), reverse=True)
    return files


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
    archives = prepare_workdir()
    files = collect_source_files()
    if not archives and not files:
        raise FileNotFoundError('No ZIP, PDF or image files found in content/diplomas/')

    reset_dir(THUMBS)
    reset_dir(FULL)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    items = []
    used = set()
    for idx, path in enumerate(files, start=1):
        year = year_from_name(path.name)
        base = f"{year or 'nd'}-{slugify(path.stem)}"
        if base in used:
            base = f"{base}-{file_hash(path)}"
        used.add(base)
        full_path = FULL / f"{base}.webp"
        thumb_path = THUMBS / f"{base}.webp"
        try:
            img = load_image(path)
        except Exception as exc:
            print(f'SKIP {path}: {exc}')
            continue
        resize_max(img, 1800).save(full_path, 'WEBP', quality=84, method=6)
        # Smaller thumbnails: the page now displays roughly twice as many items per screen.
        resize_max(img, 340).save(thumb_path, 'WEBP', quality=74, method=6)
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

    OUT.write_text(json.dumps({
        'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'count': len(items),
        'sort': 'year_desc_name_desc',
        'input_archives': [str(p).replace('\\', '/') for p in archives],
        'items': items,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Built diplomas gallery: {len(items)} items from {len(archives)} archive(s) and/or direct files')


if __name__ == '__main__':
    main()
