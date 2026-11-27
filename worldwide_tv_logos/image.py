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

MIN_SIDE = 300                  # longest side of the drawing, in pixels (smaller than SHARP_SIDE: looked for again)
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


def open_image(data: bytes, svg_width: int = TARGET_WIDTH * 3) -> tuple[Image.Image, bool]:
    """(RGBA image, vector?)"""
    if is_svg(data):
        import resvg_py
        try:
            png = bytes(resvg_py.svg_to_bytes(svg_string=data.decode('utf-8'), width=svg_width))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ImageError(f'unreadable SVG ({exc})') from None
        return Image.open(io.BytesIO(png)).convert('RGBA'), True
    if data[:512].lstrip().startswith(b'<'):
        raise ImageError('an HTML page, not an image: give the address of the image itself (right-click on the logo, '
                         '"Copy image address"), or of its Wikimedia Commons file page')
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
            raise ImageError(f'too small ({w}x{h} once trimmed): longest side must be at least {MIN_SIDE} px. '
                             "Look for an SVG or a larger version (Wikimedia Commons, the channel's press page)")
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    if size != img.size:
        img = img.resize(size, Image.Resampling.LANCZOS)
        img = trim(img)                 # a faint edge row may fade below the trim threshold once resized
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
    """PNG file of a logo, compressed without loss by oxipng (about 15 % smaller), always RGBA (no palette or
    colour type reduction: the files keep the same format for every user)."""
    import oxipng
    out = io.BytesIO()
    img.save(out, 'PNG', optimize=True)
    return oxipng.optimize_from_memory(out.getvalue(), level=4, strip=oxipng.StripChunks.safe(),
                                       bit_depth_reduction=False, color_type_reduction=False,
                                       palette_reduction=False, grayscale_reduction=False)


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
    variant, and the logo is its dark version; a mostly black or grey logo gets a white variant (white_variant).
    Then what still vanishes is made visible (legible): on a light screen in the logo, on a dark one in the white
    variant, made from the logo when there was none."""
    if white_edge_share(img) > WHITE_EDGE and (dark := dark_version(img)) is not None:
        logo, white = dark, img
    else:
        logo, white = img, white_variant(img)
    light = legible(logo)                                 # what still vanishes on a light screen is darkened…
    if white is None and light is not logo and vanishing(logo, dark=True) < VANISH_ALERT:
        white = logo                                      # (the original, made for dark screens, is their version)
    logo = light
    on_dark = white if white is not None else logo
    if vanishing(on_dark, dark=True) >= VANISH_ALERT:   # …and on a dark one lightened, as a white variant
        white = legible(on_dark, dark=True)
    return logo, white


def _ink(img: Image.Image) -> np.ndarray:
    """Where the drawing is (0..1): its opacity, or for an opaque image its distance to the colour of its border."""
    a = np.asarray(img.convert('RGBA'), dtype=np.float32)
    alpha = a[:, :, 3] / 255
    if alpha.min() < 0.95:
        return alpha
    border = np.concatenate([a[0, :, :3], a[-1, :, :3], a[:, 0, :3], a[:, -1, :3]])
    ground = np.median(border, axis=0)
    return np.clip(np.abs(a[:, :, :3] - ground).max(axis=2) / 128, 0, 1)


def silhouette(a: Image.Image, b: Image.Image, width: int = 160) -> float:
    """How much two drawings have the same shape (-1..1, 1: identical): both shapes at the same size, slightly
    blurred, correlated. Unlike the fingerprint, a small shift or another spacing barely changes it (the logo of
    Ceuta TV on its website and in picons: 0.89; two logos of different channels: 0.10 at most). Drawings whose
    proportions differ by more than a quarter are not compared (0)."""
    from PIL import ImageFilter
    ra, rb = a.width / max(a.height, 1), b.width / max(b.height, 1)
    if min(ra, rb) <= 0 or max(ra, rb) / min(ra, rb) > 1.25:
        return 0.0
    height = max(8, round(width / ((ra + rb) / 2)))
    shapes = []
    for img in (a, b):
        ink = Image.fromarray((_ink(img) * 255).astype(np.uint8)).resize((width, height), Image.LANCZOS)
        v = np.asarray(ink.filter(ImageFilter.GaussianBlur(2)), dtype=np.float32)
        shapes.append(v - v.mean())
    x, y = shapes
    norm = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / norm) if norm else 0.0


# Legibility: how much of a drawing vanishes on the screen it is made for (the logo on a light screen, its white
# variant on a dark one). Calibrated on 200 logos annotated by eye (2026-11-26): 10 of the 13 unreadable ones found,
# 3 readable ones flagged.
LIGHT_SCREEN = (236, 238, 241)  # the light and dark tiles of the contact sheets (harvest/sheets.py)
DARK_SCREEN = (20, 24, 31)
VISIBLE_ON_LIGHT = 16           # colour difference (CIEDE2000) to the screen under which a pixel is hard to see…
VISIBLE_ON_DARK = 20            # …larger on a dark screen, where dark colours blend more (navy, dark grey)
FRAME_CONTENT = 0.03            # a vanishing part enclosing visible drawing (this share of its area) is a frame
OUTLINE_SHARE = 0.5             # a vanishing part mostly bordered by a visible outline keeps its shape
PLATE_LIGHTNESS = 65            # CIELAB L of drawing a part lightened for a dark screen would no longer stand out from
PLATE_SHARE = 0.25              # share of a part's border along such drawing above which the part is its plate
COUNTER_CHROMA = 10             # CIELAB chroma above which a filled area is drawing, not a hole painted like the page
COUNTER_SPREAD = 4            # the hole of a letter covers at most this many discs of its inscribed circle
VANISH_ALERT = 0.02             # share of the drawing above which a logo is reported as unreadable
LEGIBILITY_SIDE = 300           # measured on a copy this size


def _vanishing_parts(img: Image.Image, dark: bool, soft_edge: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(parts that vanish, opaque pixels, colour difference to the screen) of an RGBA image, at its own size.
    `soft_edge`: the outside reaches the drawing through its anti-aliased edge (full size images, where that edge is
    a band of half-transparent pixels); the measure itself is calibrated without it, on small copies."""
    from scipy import ndimage
    from skimage.color import deltaE_ciede2000, rgb2lab
    a = np.asarray(img.convert('RGBA')).astype(np.float32) / 255
    opaque = a[:, :, 3] > 0.5
    screen = np.array(DARK_SCREEN if dark else LIGHT_SCREEN, dtype=np.float32).reshape(1, 1, 3) / 255
    lab = rgb2lab(a[:, :, :3])
    diff = deltaE_ciede2000(lab, np.broadcast_to(rgb2lab(screen), lab.shape))
    gone = np.zeros_like(opaque)
    counters = np.zeros_like(opaque)
    inside = np.zeros_like(opaque)
    if not opaque.any():
        return gone, opaque, diff, counters
    low = opaque & (diff < (VISIBLE_ON_DARK if dark else VISIBLE_ON_LIGHT))
    clear, _ = ndimage.label(np.pad(~opaque if soft_edge else a[:, :, 3] < 0.12, 1, constant_values=True))
    outside = (clear == clear[0, 0])[1:-1, 1:-1]                      # the outside, not the holes…
    if soft_edge:               # …but at full size a hole shows the screen too (the digit in a ring)
        outside = ~opaque
    ring = ndimage.binary_dilation(outside) & ~outside                 # first ring of the drawing
    parts, _ = ndimage.label(low)
    if soft_edge:               # full size: the outside is a few px away, past a dark matte or a drop shadow
        reach = ndimage.binary_dilation(outside, iterations=3) & ~outside
        candidates = np.unique(parts[low & reach])
    else:
        candidates = np.unique(parts[low & ring])
    for i in candidates:
        if i == 0:
            continue
        part = parts == i
        enclosed = ndimage.binary_fill_holes(part) & ~part & opaque & ~low
        if soft_edge:           # a shadow in the hole of a letter is no drawing framed by it
            enclosed = ndimage.binary_opening(enclosed, iterations=2)
        painted = enclosed.sum() > FRAME_CONTENT * part.sum()
        if painted and not (soft_edge and _filled_counter(part, enclosed, lab, dark)):
            continue
        if soft_edge:           # an outline goes round the part; a shadow or a matte leaves it open to the outside
            near = ndimage.binary_dilation(part, iterations=3) & ~ndimage.binary_dilation(part)
            edge = (near & outside).sum()
        else:
            near = ndimage.binary_dilation(part) & ~part
            edge = (part & ring).sum()
        outline = (near & ~outside & opaque & ~low).sum()
        if edge < OUTLINE_SHARE * (edge + outline):
            continue
        if soft_edge and dark:  # a plate under white drawing keeps its colour, or the drawing would vanish into it
            alike = lab[:, :, 0] > PLATE_LIGHTNESS  # (painted holes of letters are not drawing on it; on a light
            if painted:                             # screen, white letters crossing black drawing would pass for one)
                alike &= ~ndimage.binary_fill_holes(part)
            if (near & ~outside & opaque & ~low & alike).sum() > PLATE_SHARE * (edge + outline):
                continue
        gone |= part
        if painted:             # repainted only with the letter around it
            filled = ndimage.binary_fill_holes(part) & ~part
            inside |= filled
            paint = filled & (np.abs(lab - np.median(lab[enclosed], axis=0)).max(axis=2) < 12)
            counters |= filled & ndimage.binary_dilation(paint, iterations=2)  # its paint and rim, not what is drawn
            # in it (the red HD in the white hole of a black play sign)
    gone |= inside & low        # drawing in the painted hole (the R of ®) goes with the letter around it
    return gone, opaque, diff, counters & ~low


def _filled_counter(part: np.ndarray, enclosed: np.ndarray, lab: np.ndarray, dark: bool) -> bool:
    """Whether what a part encloses is the filled hole of a letter (an "a" whose hole is painted white), not drawing
    framed by it: one or two plain round areas, as wide as the stroke of the part around them (the text of a box is
    thinner than the box), painted white or grey for a dark screen (a red disc in a black badge is drawing)."""
    from scipy import ndimage
    holes, n = ndimage.label(enclosed)
    if not 1 <= n <= 2:
        return False
    colours = lab[enclosed]     # plain: most of it one colour, past its anti-aliased rim
    if (np.abs(colours - np.median(colours, axis=0)).max(axis=1) < 6).mean() < 0.5:
        return False
    if dark and np.hypot(*np.median(colours, axis=0)[1:]) > COUNTER_CHROMA:
        return False
    stroke = ndimage.distance_transform_edt(part).max()  # a hole is about as wide as the stroke; a badge is wider
    for k in range(1, n + 1):
        hole = holes == k
        radius = ndimage.distance_transform_edt(hole).max()
        if not 0.5 * stroke <= radius <= 5 * stroke:
            return False
        if hole.sum() > COUNTER_SPREAD * np.pi * radius ** 2:  # a hole is round-ish; a letter in a box is a long stroke
            return False
    return True


def vanishing(img: Image.Image, dark: bool = False) -> float:
    """Share of the drawing that cannot be seen on the screen it is made for: parts whose colour is too close to
    the screen (white letters on a light screen, navy on a dark one) and that meet the transparent outside. Not
    counted: a frame around visible drawing (the white box of a logo), a part drawn with a visible outline (a white
    shape edged in black), colours that differ by their hue (yellow on a light screen)."""
    small = img.convert('RGBA')
    small.thumbnail((LEGIBILITY_SIDE, LEGIBILITY_SIDE))
    gone, opaque, _, _ = _vanishing_parts(small, dark)
    return float(gone.sum() / opaque.sum()) if opaque.any() else 0.0


LEGIBLE_ON_LIGHT = (12.0, 38.0)  # lightness (CIELAB, 0..100) given to the parts that vanished on a light screen…
LEGIBLE_ON_DARK = (80.0, 100.0)  # …and on a dark one; their hue and their shading (lighter / darker) are kept


def legible(img: Image.Image, dark: bool = False) -> Image.Image:
    """The logo with the parts that vanish on its screen made visible: darkened for a light screen, lightened for a
    dark one, keeping their hue (a pale pink becomes a dark pink, white becomes a dark ink, navy a light blue) and
    their shading. Their anti-aliased edge goes with them. Unchanged when nothing vanishes."""
    from scipy import ndimage
    from skimage.color import lab2rgb, rgb2lab
    if vanishing(img, dark) < VANISH_ALERT:
        return img
    a = np.asarray(img.convert('RGBA')).copy()
    gone, _, diff, counters = _vanishing_parts(img, dark, soft_edge=True)
    limit = VISIBLE_ON_DARK if dark else VISIBLE_ON_LIGHT
    fringe = ndimage.binary_dilation(gone, iterations=2) & (a[:, :, 3] > 0) & (diff < 1.5 * limit)
    mask = gone | fringe
    if not mask.any():
        return img
    if counters.any():          # the painted hole of a letter takes the letter's colour, and reads as a hole again
        a[:, :, :3][counters] = np.median(a[:, :, :3][gone], axis=0).astype(np.uint8)
        mask &= ~counters
    lab = rgb2lab(a[:, :, :3].astype(np.float32) / 255)
    lightness = lab[:, :, 0][mask]
    low, high = lightness.min(), lightness.max()
    lo, hi = LEGIBLE_ON_DARK if dark else LEGIBLE_ON_LIGHT
    span = (lightness - low) / (high - low) if high - low > 1 else np.full_like(lightness, 0.5)
    lab[:, :, 0][mask] = lo + span * (hi - lo)
    a[:, :, :3][mask] = np.clip(lab2rgb(lab)[mask] * 255 + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(a, 'RGBA')

