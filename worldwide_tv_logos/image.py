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
WHITE_BORDER = 0.5              # share of white border pixels above which that background is white (the drawing may
                                # touch the edges elsewhere: the black block of EDA TV, the skyline of Distrito TV)
FRINGE = 2                      # pixels of the drawing's edge unblended from the removed white
WHITE = 232
FLOOD_TOLERANCE = 40
DARK_NEUTRAL = 110              # neutral dark pixel: max(R, G, B) below this…
NEUTRAL_SPREAD = 40             # …and max - min below this (black, greys)
DARK_SHARE = 0.5                # share of neutral dark pixels above which a white variant is made…
ON_DARK_SHARE = 0.2             # …unless white parts lie on the dark ones (white text on a black block: CANAL+):
ON_DARK_AREA = 0.05             # share of the light parts, or of the dark area, that they cover
DEEP_LUMINANCE = 0.06           # very dark colour (navy, dark grey, teal): contrast below 2:1 on a dark background
GRADIENT_LUMINANCE = 0.15       # pixels between the dark colour and this luminance are its shades…
GRADIENT_SHARE = 0.15           # …above this share of it, it is a gradient
DEEP_SHARE = 0.2                # share of very dark parts (any colour) above which a white variant is made too


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
    """White background -> transparent (flood fill from the white of the edges). Next to it, the anti-aliased edge
    of the drawing, blended with the white, is unblended (colour to alpha), so that no light fringe remains around
    the drawing on a dark screen."""
    out = img.convert('RGBA')
    before = np.asarray(out).copy()
    w, h = out.size
    px = out.load()
    for x, y in [(x, 0) for x in range(0, w, 7)] + [(x, h - 1) for x in range(0, w, 7)] + \
                [(0, y) for y in range(0, h, 7)] + [(w - 1, y) for y in range(0, h, 7)]:
        p = px[x, y]
        if p[3] > 240 and min(p[:3]) >= WHITE:
            ImageDraw.floodfill(out, (x, y), (255, 255, 255, 0), thresh=FLOOD_TOLERANCE)
    b = np.asarray(out).copy()
    clear = (b[:, :, 3] == 0) & (before[:, :, 3] > 0)
    band = _dilate(clear, FRINGE) & ~clear & (b[:, :, 3] > 0)
    rgb = b[:, :, :3].astype(np.float32)
    alpha = (255.0 - rgb.min(axis=2)) / 255.0                 # share of the drawing in a pixel blended with white
    soft = band & (alpha < 1)
    keep = np.maximum(alpha, 1e-3)[:, :, None]
    unblended = np.clip(255.0 - (255.0 - rgb) / keep, 0, 255)
    b[:, :, :3] = np.where(soft[:, :, None], unblended, rgb).astype(np.uint8)
    b[:, :, 3] = np.where(soft, (b[:, :, 3] * alpha).astype(np.uint8), b[:, :, 3])
    return Image.fromarray(b, 'RGBA')


def white_frame(img: Image.Image) -> bool:
    """Opaque border mostly white: a white background around the logo, to be made transparent (only the white
    reached from the edges is removed)."""
    border = _border(np.asarray(img))
    opaque = border[:, 3] > 240
    white = opaque & (border[:, :3].min(axis=1) >= WHITE)
    return opaque.mean() >= OPAQUE_BORDER and white.mean() >= WHITE_BORDER


def without_white_background(img: Image.Image) -> Image.Image | None:
    """The logo with its white background removed, or None: no white background, or a dark drawing that would be
    unreadable on a dark screen without it (white left inside dark letters, the counters of EDA TV, prevent its
    white variant): the white background is then part of the logo and kept."""
    if not white_frame(img):
        return None
    clear = remove_white_frame(img)
    if is_dark(clear) and white_variant(clear) is None:
        return None
    return clear


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
    if (clear := without_white_background(img)) is not None:
        img = clear
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


def _luminance(rgb: np.ndarray) -> np.ndarray:
    """Relative luminance (0 black, 1 white) of sRGB pixels."""
    c = rgb.astype(np.float32) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def on_dark(light: np.ndarray, dark: np.ndarray, side: int = 300) -> int:
    """Pixels of the light parts that lie on a dark part: whole parts touching it, not only their edge (the thick
    white letters of CANAL+ on its black block). Computed at a small scale."""
    h, w = light.shape
    k = max(1, round(max(h, w) / side))
    small, dark = light[::k, ::k], dark[::k, ::k]
    mark = small & _dilate(dark, 1)
    while True:
        grown = small & _dilate(mark, 1)
        if grown.sum() == mark.sum():
            return int(mark.sum()) * k * k
        mark = grown


def _dark_parts(a: np.ndarray) -> tuple:
    """(neutral dark pixels, very dark pixels, opaque pixels, share of neutral dark, share of dark of any colour)."""
    rgb = a[:, :, :3].astype(np.int16)
    neutral = (a[:, :, 3] > 0) & (rgb.max(axis=2) < DARK_NEUTRAL) & ((rgb.max(axis=2) - rgb.min(axis=2)) < NEUTRAL_SPREAD)
    deep = (a[:, :, 3] > 0) & (_luminance(a[:, :, :3]) < DEEP_LUMINANCE)
    opaque = a[:, :, 3] > 128
    n = max(1, int(opaque.sum()))
    return neutral, deep, opaque, (neutral & opaque).sum() / n, ((neutral | deep) & opaque).sum() / n


def is_dark(img: Image.Image) -> bool:
    """Mostly black or grey, or with a good part in a very dark colour: unreadable on a dark screen as it is."""
    _, _, opaque, share, deep_share = _dark_parts(np.asarray(img.convert('RGBA')))
    return bool(opaque.any()) and (share >= DARK_SHARE or deep_share >= DEEP_SHARE)


def white_variant(img: Image.Image) -> Image.Image | None:
    """Drawing unreadable on a dark background -> same logo with its dark parts in white: mostly black / grey, or with
    a good part in a very dark colour (navy text: LA 7, Eurosport, Val TV). Not when white parts lie on the dark ones:
    the dark is a block carrying white text (CANAL+, CINE+, TMC, the C of CNEWS), which would vanish. White parts
    elsewhere (the white 6 in the red box of Eurosport 6) do not matter."""
    a = np.asarray(img).copy()
    rgb = a[:, :, :3].astype(np.int16)
    neutral, deep, opaque, share, deep_share = _dark_parts(a)
    if share < DARK_SHARE and deep_share < DEEP_SHARE:
        return None
    light = opaque & (rgb.min(axis=2) > 140)          # white or light grey (metallic text)
    if light.any():
        lying = on_dark(light, neutral | deep)
        if lying > ON_DARK_SHARE * light.sum() or lying > ON_DARK_AREA * ((neutral | deep) & opaque).sum():
            return None                                 # white text on the dark part would vanish
    coloured = deep & ~neutral
    if share < DARK_SHARE and (coloured & opaque).sum() > 0.05 * opaque.sum():
        lum = _luminance(a[:, :, :3])
        shades = opaque & ~deep & (lum < GRADIENT_LUMINANCE)          # just lighter than the dark colour
        if shades.sum() > GRADIENT_SHARE * (coloured & opaque).sum():
            return None                                 # a gradient, not dark letters (TELEGILENA, DEJATE DE HISTORIAS)
    a[neutral | deep, 0:3] = 255
    return Image.fromarray(a, 'RGBA')


def fingerprint(img: Image.Image) -> int:
    """Perceptual fingerprint (difference hash, 256 bits) of a logo on a grey background: the same drawing gives
    (almost) the same fingerprint whatever its size, format or compression."""
    ground = Image.new('RGBA', img.size, (128, 128, 128, 255))
    ground.alpha_composite(img.convert('RGBA'))
    g = np.asarray(ground.convert('L').resize((17, 16), Image.LANCZOS), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int(''.join('1' if b else '0' for b in bits), 2)


def same_drawing(a: int, b: int, tolerance: int = 20) -> bool:
    return (a ^ b).bit_count() <= tolerance


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
        if not white and without_white_background(img.convert('RGBA')) is not None:
            errors.append('white frame around the logo: make it transparent')
        alpha = np.asarray(img.getchannel('A'))
        bbox = Image.fromarray(((alpha > 8) * 255).astype(np.uint8)).getbbox()
        if bbox and (bbox[0] > 1 or bbox[1] > 1 or bbox[2] < w - 1 or bbox[3] < h - 1):
            errors.append(f'empty margin (drawing {bbox} in {w}x{h}): trim to the drawing')
    return errors


WHITE_EDGE = 0.1                # share of the drawing's outline that is white above which it is made for dark screens


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
ENCLOSED_SHARE = 0.05           # share of black parts inside the drawing above which their surroundings count


def _dilate(mask: np.ndarray, r: int = 1) -> np.ndarray:
    h, w = mask.shape
    pad = np.pad(mask, r)
    out = np.zeros_like(mask)
    for dy in range(2 * r + 1):
        for dx in range(2 * r + 1):
            out |= pad[dy:dy + h, dx:dx + w]
    return out


def _exterior(a: np.ndarray) -> np.ndarray:
    """Transparent pixels connected to the edges of the image (the outside of the drawing, not its holes)."""
    clear = np.pad((a[:, :, 3] < 32).astype(np.uint8) * 255, 1, constant_values=255)
    mask = Image.fromarray(clear, 'L')
    ImageDraw.floodfill(mask, (0, 0), 128, thresh=0)
    return (np.asarray(mask) == 128)[1:-1, 1:-1]


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
    inside = dark & ~_dilate(_exterior(a), 2)          # black parts that do not touch the outside
    if inside.sum() > ENCLOSED_SHARE * dark.sum():
        ring = _dilate(inside, 3) & ~dark
        if (ring & white).sum() > 0.5 * ring.sum():     # ...surrounded by the white: they would vanish (CANAL 10)
            return None
    a[white, 0:3] = INK
    return Image.fromarray(a, 'RGBA')


def variants(img: Image.Image) -> tuple[Image.Image, Image.Image | None]:
    """(logo, white variant or None). A logo whose outline is white (made for dark screens) becomes its own white
    variant, and the logo is its dark version; a mostly black or grey logo gets a white variant (white_variant)."""
    if white_edge_share(img) > WHITE_EDGE and (dark := dark_version(img)) is not None:
        return dark, img
    return img, white_variant(img)
