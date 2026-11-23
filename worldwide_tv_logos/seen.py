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

from worldwide_tv_logos import image, net, web

BROWSER_UA = web.BROWSER_UA
TOLERANCE = 20                  # bits of the 256-bit fingerprint
MAX_IMAGES = 25                 # images downloaded per page at most, those named "logo" first
PATH_RE = re.compile(rb'\sd="([^"]{40,})"')
SVG_RE = re.compile(r'<svg\b.*?</svg>', re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r'<(?:img|source|link|meta)\b[^>]*>', re.IGNORECASE)
ATTR_RE = re.compile(r'([a-zA-Z:-]+)\s*=\s*("[^"]*"|\'[^\']*\')')


# image.silhouette above which two drawings are the same logo, at 160 and at 320 px wide (the finer one tells letters
# apart: the logo of Ceuta TV on its website 0.89 / 0.84; Terrassa Digital against Canal Terrassa, same layout,
# 0.87 / 0.74; measured on 2026-11-23)
SILHOUETTE = 0.85
SILHOUETTE_FINE = 0.80
COMPARE_SIDE = 400              # images are compared at this size at most: a fingerprint is 17x16 pixels


def drawing(data: bytes) -> Image.Image:
    """The drawing of an image, whatever its size: rendered, white background removed, trimmed (at most
    COMPARE_SIDE wide or high: comparing large images is slow and gives the same fingerprint)."""
    img, _ = image.open_image(data, svg_width=2 * COMPARE_SIDE)
    img.thumbnail((2 * COMPARE_SIDE, 2 * COMPARE_SIDE))
    if image.white_frame(img):
        img = image.remove_white_frame(img)
    return image.trim(img)


def fingerprints(img: Image.Image) -> list[int]:
    """The logo and its white or dark version: a page may show either."""
    img = img.copy()
    img.thumbnail((COMPARE_SIDE, COMPARE_SIDE))
    logo, other = image.variants(img)
    return [image.fingerprint(x) for x in (img, logo, other) if x is not None]


def page_images(page_url: str, html: str) -> list[str]:
    """Image addresses of a page, those whose tag says "logo" (address, class, alt...) and the icons first."""
    out = []
    first = set()
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
                url = urllib.parse.urljoin(page_url, src)
                out.append(url)
                if 'logo' in tag.lower() or name in ('link', 'meta'):
                    first.add(url)
    urls = [u for u in dict.fromkeys(out) if u.startswith('https://')]
    return sorted(urls, key=lambda u: u not in first)


def _found(page_url: str, html: str, logo: bytes, wanted: list[int], downloader, pause: float) -> str | None:
    shape = drawing(logo)
    if image.is_svg(logo):
        paths = PATH_RE.findall(logo)
        if paths and all(p.decode('utf-8', errors='replace') in html for p in paths):
            return f'the SVG drawing of the logo is written in the page ({len(paths)} path(s), identical)'

    def same(img: Image.Image) -> bool:
        if any(image.same_drawing(fp, w, TOLERANCE) for fp in fingerprints(img) for w in wanted):
            return True
        return (min(img.size) >= 12 and image.silhouette(shape, img) >= SILHOUETTE
                and image.silhouette(shape, img, 320) >= SILHOUETTE_FINE)
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


def seen_on(page_url: str, logo: bytes, downloader=None, pause: float = 0.3, log=print,
            page: web.Page | None = None) -> str | None:
    """How the logo was found on the page, or None. The page is read by a plain request, then, when the logo is not
    found there (or the site refuses it), as rendered by a headless browser (logos added by JavaScript). A
    `downloader` given (tests) reads the page itself, without browser. Raises net.DownloadError when the page
    cannot be read at all."""
    wanted = fingerprints(drawing(logo))
    if downloader is not None:
        html = downloader(page_url, accept='text/html,*/*', user_agent=BROWSER_UA).decode('utf-8', errors='replace')
        return _found(page_url, html, logo, wanted, downloader, pause)
    first = page or web.fetch(page_url)
    if first.ok:
        how = _found(first.final or page_url, first.html, logo, wanted, net.download, pause)
        if how or first.how == 'browser':
            return how
    browser = web.Browser.get()
    if browser is None:
        if not first.ok:
            raise net.DownloadError(first.error or 'page not readable')
        return None
    rendered = browser.open(page_url)
    if not rendered.ok:
        if not first.ok:
            raise net.DownloadError(rendered.error or first.error or 'page not readable')
        return None
    how = _found(rendered.final or page_url, rendered.html, logo, wanted, net.download, pause)
    return f'{how} (page rendered by a browser)' if how else None
