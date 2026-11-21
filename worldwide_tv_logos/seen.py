"""Is a logo shown on a web page? (`logos seen-on <page> <logo>`): the proof that a logo is the current one of a
channel, read like a browser does (many channel websites refuse automated readers).

The page is read once, then:
1. a SVG logo whose drawing (its paths) is written in the page: found (the logo drawn inline in the page header);
2. otherwise the drawings of the page (inline SVG, images, icons, og:image) are compared, by their perceptual
   fingerprint, with the logo and its white or dark version (small images included: a header logo is often
   small). Images are downloaded one at a time, with a pause.
"""
from __future__ import annotations

import re
import time
import urllib.parse

from PIL import Image

from worldwide_tv_logos import image, net

BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/130.0 Safari/537.36')
TOLERANCE = 20                  # bits of the 256-bit fingerprint
MAX_IMAGES = 40
PATH_RE = re.compile(rb'\sd="([^"]{40,})"')
SVG_RE = re.compile(r'<svg\b.*?</svg>', re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r'<(?:img|source|link|meta)\b[^>]*>', re.IGNORECASE)
ATTR_RE = re.compile(r'([a-zA-Z:-]+)\s*=\s*("[^"]*"|\'[^\']*\')')


def drawing(data: bytes) -> Image.Image:
    """The drawing of an image, whatever its size: rendered, white background removed, trimmed."""
    img, _ = image.open_image(data)
    if image.white_frame(img):
        img = image.remove_white_frame(img)
    return image.trim(img)


def fingerprints(img: Image.Image) -> list[int]:
    """The logo and its white or dark version: a page may show either."""
    logo, other = image.variants(img)
    return [image.fingerprint(x) for x in (img, logo, other) if x is not None]


def page_images(page_url: str, html: str) -> list[str]:
    out = []
    for tag in TAG_RE.findall(html):
        a = {k.lower(): v.strip('"\'') for k, v in ATTR_RE.findall(tag)}
        name = tag[1:].split(None, 1)[0].lower()
        if name == 'link' and 'icon' not in a.get('rel', '').lower():
            continue
        if name == 'meta' and a.get('property', a.get('name', '')).lower() not in ('og:image', 'twitter:image'):
            continue
        for src in (a.get('src'), a.get('data-src'), a.get('href'), a.get('content'),
                    (a.get('srcset') or '').split(',')[-1].strip().split(' ')[0]):
            if src and not src.startswith('data:'):
                out.append(urllib.parse.urljoin(page_url, src))
    return [u for u in dict.fromkeys(out) if u.startswith('https://')]


def seen_on(page_url: str, logo: bytes, downloader=None, pause: float = 0.5, log=print) -> str | None:
    """How the logo was found on the page, or None."""
    downloader = downloader or net.download
    html = downloader(page_url, accept='text/html,*/*', user_agent=BROWSER_UA).decode('utf-8', errors='replace')
    if image.is_svg(logo):
        paths = PATH_RE.findall(logo)
        if paths and all(p.decode('utf-8', errors='replace') in html for p in paths):
            return f'the SVG drawing of the logo is written in the page ({len(paths)} path(s), identical)'
    wanted = fingerprints(drawing(logo))

    def same(img: Image.Image) -> bool:
        return any(image.same_drawing(fp, w, TOLERANCE) for fp in fingerprints(img) for w in wanted)
    for i, svg in enumerate(SVG_RE.findall(html)[:60]):
        if 'xmlns=' not in svg[:200]:
            svg = svg.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"', 1)
        try:
            if same(drawing(svg.encode('utf-8'))):
                return f'same drawing as the SVG number {i + 1} drawn in the page'
        except Exception:  # noqa: BLE001, S112 - an icon that cannot be rendered is skipped
            continue
    for url in page_images(page_url, html)[:MAX_IMAGES]:
        time.sleep(pause)
        try:
            if same(drawing(downloader(url, user_agent=BROWSER_UA))):
                return f'same drawing as the image {url} of the page'
        except Exception:  # noqa: BLE001, S112 - an image that cannot be read is skipped
            continue
    return None
