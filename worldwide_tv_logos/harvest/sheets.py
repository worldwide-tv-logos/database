"""Contact sheets: logos on a dark and a light tile, to be looked at by eye (harvests, `logos find`, `logos sheet`)."""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from worldwide_tv_logos import image
from worldwide_tv_logos.db import Database
from worldwide_tv_logos.harvest.candidates import Candidate


def _font(size: int):
    for name in ('arial.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_sheets(tiles: list[tuple[str, str, Image.Image, Image.Image]], out: Path, per_page: int = 30,
                  prefix: str = 'sheet') -> list[Path]:
    """Pages of 3 columns: (title, caption, picture for a dark tile, picture for a light tile), numbered."""
    tw, th, cols, cap = 260, 146, 3, 42
    font, small = _font(16), _font(13)
    out.mkdir(parents=True, exist_ok=True)
    pages = []
    for p in range(0, len(tiles), per_page):
        chunk = tiles[p:p + per_page]
        lines = (len(chunk) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * (2 * tw + 30), lines * (th + cap + 16) + 10), '#ffffff')
        draw = ImageDraw.Draw(sheet)
        for i, (title, caption, dark, light) in enumerate(chunk):
            x, y = (i % cols) * (2 * tw + 30) + 10, (i // cols) * (th + cap + 16) + 10
            for j, (bg, pic) in enumerate((('#14181f', dark), ('#eceef1', light))):
                tile = Image.new('RGB', (tw, th), bg)
                pic = pic.copy()
                pic.thumbnail((int(tw * .8), int(th * .8)))
                tile.paste(pic, ((tw - pic.width) // 2, (th - pic.height) // 2), pic)
                sheet.paste(tile, (x + j * (tw + 4), y))
            draw.text((x, y + th + 3), f'{p + i + 1}. {title}', fill='#111111', font=font)
            draw.text((x, y + th + 23), caption, fill='#555555', font=small)
        path = out / f'{prefix}-{p // per_page + 1:02d}.png'
        sheet.save(path)
        pages.append(path)
    return pages


def contact_sheets(rows: list[tuple[dict, Candidate]], out: Path, per_page: int = 30) -> list[Path]:
    """Candidates as they would be published: each logo on a dark and on a light tile."""
    tiles = []
    for c, cand in rows:
        img, white = image.variants(image.prepare(cand.data)[0])
        tiles.append((c['name'], f'{c["id"]}  {cand.source}  {cand.size[0]}x{cand.size[1]}'
                      + ('  SVG' if cand.svg else ''), white or img, img))
    return render_sheets(tiles, out, per_page)


def repo_sheets(db: Database, stems: list[str], out: Path, per_page: int = 30) -> list[Path]:
    """Logos of the repository (`stems` such as France3.fr or France3.fr@Alsace): their files as served."""
    tiles = []
    for stem in stems:
        channel, _, feed = stem.partition('@')
        main = db.logos.get((channel, feed, ''))
        if main is None:
            continue
        white = db.logos.get((channel, feed, 'white'))
        light = Image.open(db.path(main.file)).convert('RGBA')
        dark = Image.open(db.path(white.file)).convert('RGBA') if white else light
        origin = re.sub(r'^https://([^/]+)/.*', r'\1', main.origin)
        tiles.append((stem, f'{main.width}x{main.height}  {origin}', dark, light))
    return render_sheets(tiles, out, per_page)
