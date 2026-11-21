"""Image rules: what a logo must be, and how an original becomes one.

A logo is a PNG on a transparent background, trimmed to the drawing (no margin), whose longest side is between
MIN_SIDE and MAX_SIDE pixels. An original may be SVG (rendered at TARGET_WIDTH) or a raster image (never upscaled).
A white frame added around a logo (opaque white border) is made transparent. A coloured block that touches the edges
is part of many brands (BFM TV, LCI) and is kept.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, UnidentifiedImageError

MIN_SIDE = 500                  # longest side of the drawing, in pixels
MAX_SIDE = 2000
TARGET_WIDTH = 1200             # vector originals are rendered so the drawing is this wide…
TARGET_HEIGHT = 800             # …or this high, whichever comes first
MAX_FILE = 1_000_000            # bytes, served PNG
MAX_PIXELS = 40_000_000
OPAQUE_BORDER = 0.9             # share of opaque border pixels above which the image has a background
WHITE = 232
FLOOD_TOLERANCE = 40
DARK_NEUTRAL = 110              # neutral dark pixel: max(R, G, B) below this…
NEUTRAL_SPREAD = 40             # …and max - min below this (black, greys)
DARK_SHARE = 0.5                # share of neutral dark pixels above which a white variant is made…
LIGHT_SHARE = 0.03              # …unless the logo already has white parts (white text on a black block: CANAL+)


class ImageError(ValueError):
    pass


def is_svg(data: bytes) -> bool:
    head = data[:1024].lstrip().lower()
    return head.startswith(b'<?xml') and b'<svg' in data[:4096].lower() or head.startswith(b'<svg')


def extension(data: bytes) -> str:
    if is_svg(data):
        return 'svg'
    try:
        with Image.open(io.BytesIO(data)) as img:
            return {'JPEG': 'jpg'}.get(img.format, (img.format or 'bin').lower())
    except (UnidentifiedImageError, OSError):
        return 'bin'


def open_image(data: bytes) -> tuple[Image.Image, bool]:
    """(RGBA image, vector?)"""
    if is_svg(data):
        import resvg_py
        try:
            png = bytes(resvg_py.svg_to_bytes(svg_string=data.decode('utf-8'), width=TARGET_WIDTH * 3))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ImageError(f'unreadable SVG ({exc})') from None
        return Image.open(io.BytesIO(png)).convert('RGBA'), True
    if data[:512].lstrip().startswith(b'<'):
        raise ImageError('an HTML page, not an image')
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageError(f'unreadable image ({type(exc).__name__})') from None
    return img.convert('RGBA'), False


def _border(a: np.ndarray) -> np.ndarray:
    return np.concatenate([a[0], a[-1], a[1:-1, 0], a[1:-1, -1]])


def remove_white_frame(img: Image.Image) -> Image.Image:
    """Opaque white border -> transparent (flood fill from the edges, light fringe softened)."""
    out = img.copy()
    w, h = out.size
    px = out.load()
    for x, y in [(x, 0) for x in range(0, w, 7)] + [(x, h - 1) for x in range(0, w, 7)] + \
                [(0, y) for y in range(0, h, 7)] + [(w - 1, y) for y in range(0, h, 7)]:
        p = px[x, y]
        if p[3] > 240 and min(p[:3]) >= WHITE:
            ImageDraw.floodfill(out, (x, y), (255, 255, 255, 0), thresh=FLOOD_TOLERANCE)
    b = np.asarray(out).copy()
    clear = b[:, :, 3] == 0
    near = np.zeros_like(clear)
    near[1:] |= clear[:-1]
    near[:-1] |= clear[1:]
    near[:, 1:] |= clear[:, :-1]
    near[:, :-1] |= clear[:, 1:]
    light = b[:, :, :3].min(axis=2).astype(np.float32)
    halo = near & ~clear & (light >= WHITE - 30)
    factor = np.clip((255.0 - light) / (255.0 - (WHITE - 30)), 0, 1)
    b[:, :, 3] = np.where(halo, (b[:, :, 3] * factor).astype(np.uint8), b[:, :, 3])
    return Image.fromarray(b, 'RGBA')


def white_frame(img: Image.Image) -> bool:
    """Opaque white border all around: a frame added around the logo, to be made transparent."""
    border = _border(np.asarray(img))
    opaque = border[:, 3] > 240
    white = opaque & (border[:, :3].min(axis=1) >= WHITE)
    return opaque.mean() >= OPAQUE_BORDER and white.mean() >= 0.85


def trim(img: Image.Image) -> Image.Image:
    alpha = np.asarray(img.getchannel('A'))
    bbox = Image.fromarray(((alpha > 8) * 255).astype(np.uint8)).getbbox()
    if bbox is None:
        raise ImageError('empty image')
    return img.crop(bbox)


def prepare(data: bytes) -> tuple[Image.Image, list[str]]:
    """Original -> logo (trimmed, transparent, scaled). Returns (image, notes). ImageError if unusable."""
    img, vector = open_image(data)
    notes = []
    if white_frame(img):
        img = remove_white_frame(img)
        notes.append('white frame removed')
    img = trim(img)
    w, h = img.size
    scale = min(TARGET_WIDTH / w, TARGET_HEIGHT / h, MAX_SIDE / max(w, h))
    if not vector:
        scale = min(scale, 1.0)                            # a raster original is never upscaled
        if max(w, h) < MIN_SIDE:
            raise ImageError(f'too small ({w}x{h} once trimmed): longest side must be at least {MIN_SIDE} px')
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    if size != img.size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    return img, notes


def white_variant(img: Image.Image) -> Image.Image | None:
    """Mostly black / grey drawing (unreadable on a dark background) -> same logo with its neutral dark parts in white.
    Not for a logo with white parts: its black is a block carrying white text (CANAL+, CINE+, TMC), which would vanish."""
    a = np.asarray(img).copy()
    rgb = a[:, :, :3].astype(np.int16)
    dark = (a[:, :, 3] > 0) & (rgb.max(axis=2) < DARK_NEUTRAL) & ((rgb.max(axis=2) - rgb.min(axis=2)) < NEUTRAL_SPREAD)
    opaque = a[:, :, 3] > 128
    if not opaque.any() or (dark & opaque).sum() / opaque.sum() < DARK_SHARE:
        return None
    light = opaque & (rgb.min(axis=2) > 140)          # white or light grey (metallic text)
    if light.sum() / opaque.sum() > LIGHT_SHARE:
        return None
    a[dark, 0:3] = 255
    return Image.fromarray(a, 'RGBA')


def png_bytes(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, 'PNG', optimize=True)
    return out.getvalue()


def check_file(path: Path, white: bool = False) -> list[str]:
    """Rules every file in logos/ must follow (`white`: a white variant, which may be white up to its edges)."""
    errors = []
    if path.stat().st_size > MAX_FILE:
        errors.append(f'file too heavy ({path.stat().st_size // 1024} KB, {MAX_FILE // 1000} KB max)')
    with Image.open(path) as img:
        if img.format != 'PNG':
            return errors + [f'{img.format} file, PNG expected']
        if img.mode != 'RGBA':
            return errors + [f'mode {img.mode}, RGBA expected']
        w, h = img.size
        if max(w, h) < MIN_SIDE or max(w, h) > MAX_SIDE:
            errors.append(f'size {w}x{h}: longest side must be {MIN_SIDE} to {MAX_SIDE} px')
        if not white and white_frame(img):
            errors.append('white frame around the logo: make it transparent')
        alpha = np.asarray(img.getchannel('A'))
        bbox = Image.fromarray(((alpha > 8) * 255).astype(np.uint8)).getbbox()
        if bbox and (bbox[0] > 1 or bbox[1] > 1 or bbox[2] < w - 1 or bbox[3] < h - 1):
            errors.append(f'empty margin (drawing {bbox} in {w}x{h}): trim to the drawing')
    return errors


WHITE_EDGE = 0.25               # share of the drawing's outline that is white above which it is made for dark screens


def white_edge_share(img: Image.Image) -> float:
    """Share of the drawing's outline (opaque pixels next to transparency) that is white or light grey.
    High for white letters on a transparent background (readable on dark screens only); low for white text inside a
    coloured block (CANAL+), whose outline is the block."""
    a = np.asarray(img)
    opaque = a[:, :, 3] > 128
    clear = np.pad(a[:, :, 3] < 32, 2, constant_values=True)
    near = np.zeros_like(opaque)
    h, w = opaque.shape
    for dy in range(5):
        for dx in range(5):
            near |= clear[dy:dy + h, dx:dx + w]
    edge = opaque & near
    if not edge.any():
        return 0.0
    light = a[:, :, :3].min(axis=2) > 200
    return float((edge & light).sum() / edge.sum())


INK = 20                        # grey level of the dark version of a white logo
OUTER_MAJORITY = 0.5            # share of the white on the outline above which all the white is turned dark
MERGE_SHARE = 0.1               # share of black parts touching the white ones above which they would merge


def _dilate(mask: np.ndarray, r: int = 1) -> np.ndarray:
    h, w = mask.shape
    pad = np.pad(mask, r)
    out = np.zeros_like(mask)
    for dy in range(2 * r + 1):
        for dx in range(2 * r + 1):
            out |= pad[dy:dy + h, dx:dx + w]
    return out


def _light(a: np.ndarray) -> np.ndarray:
    rgb = a[:, :, :3].astype(np.int16)
    return (a[:, :, 3] > 0) & (rgb.min(axis=2) > 170) & ((rgb.max(axis=2) - rgb.min(axis=2)) < NEUTRAL_SPREAD)


def outer_white(a: np.ndarray) -> np.ndarray:
    """White / light grey parts connected to the outline of the drawing (white letters on a transparent background),
    not those inside a coloured block (white letters of BFM PARIS inside its blue square)."""
    light = _light(a)
    cur = light & _dilate(a[:, :, 3] < 32, 2)
    while True:
        grown = _dilate(cur) & light
        if (grown == cur).all():
            return cur
        cur = grown


def dark_version(img: Image.Image) -> Image.Image | None:
    """The white parts on the outline turned dark, so that a logo made for dark screens is readable on a light
    background. None when its white is a box carrying black text (LCP, TELE 1): they would merge."""
    a = np.asarray(img).copy()
    white, light = outer_white(a), _light(a)
    if white.sum() >= OUTER_MAJORITY * light.sum():     # mostly white letters: all of them (NICKELODEON)
        white = light
    rgb = a[:, :, :3].astype(np.int16)
    dark = (a[:, :, 3] > 128) & (rgb.max(axis=2) < DARK_NEUTRAL) & ((rgb.max(axis=2) - rgb.min(axis=2)) < NEUTRAL_SPREAD)
    if not white.any() or dark.any() and (dark & _dilate(white, 2)).sum() > MERGE_SHARE * dark.sum():
        return None
    a[white, 0:3] = INK
    return Image.fromarray(a, 'RGBA')


def variants(img: Image.Image) -> tuple[Image.Image, Image.Image | None]:
    """(logo, white variant or None). A logo whose outline is white (made for dark screens) becomes its own white
    variant, and the logo is its dark version; a mostly black or grey logo gets a white variant (white_variant)."""
    if white_edge_share(img) > WHITE_EDGE and (dark := dark_version(img)) is not None:
        return dark, img
    return img, white_variant(img)
