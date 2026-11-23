"""The channel's own website: its home page is read once; images whose address, class, id or alternative text says
"logo" (and SVG icons) are candidates. Nothing else on the site is followed. The address comes from iptv-org (field
`website`), else from Wikidata."""
from __future__ import annotations

import re
import urllib.parse

from worldwide_tv_logos import net

IMG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
LINK_RE = re.compile(r'<link\b[^>]*>', re.IGNORECASE)
ATTR_RE = re.compile(r'([a-zA-Z:-]+)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)')


def _attrs(tag: str) -> dict[str, str]:
    return {k.lower(): v.strip('"\'') for k, v in ATTR_RE.findall(tag)}


def website_logos(page_url: str, html: str, limit: int = 3) -> list[str]:
    """Logo images of a home page: <img> whose src, class, id or alt contains "logo", then SVG icons."""
    out: list[str] = []
    for tag in IMG_RE.findall(html):
        a = _attrs(tag)
        src = a.get('src') or a.get('data-src') or ''
        if not src or src.startswith('data:'):
            continue
        if 'logo' in ' '.join((src, a.get('class', ''), a.get('id', ''), a.get('alt', ''))).lower():
            out.append(urllib.parse.urljoin(page_url, src))
    for tag in LINK_RE.findall(html):
        a = _attrs(tag)
        href = a.get('href', '')
        if 'icon' in a.get('rel', '').lower() and href.lower().split('?')[0].endswith('.svg'):
            out.append(urllib.parse.urljoin(page_url, href))
    return [u for u in dict.fromkeys(out) if u.startswith('https://')][:limit]


def load_website_logos(url: str, downloader=None) -> list[str]:
    if not url or not url.startswith('http'):
        return []
    url = url.replace('http://', 'https://', 1)
    try:
        html = (downloader or net.download)(url, accept='text/html')
    except net.DownloadError:
        return []
    return website_logos(url, html.decode('utf-8', errors='replace'))


def find(unit: dict, ctx) -> list[str]:
    url = unit.get('website') or next((i['website'] for i in ctx.items(unit) if i.get('website')), '')
    return load_website_logos(url, ctx.get)
