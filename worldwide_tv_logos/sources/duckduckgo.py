"""DuckDuckGo image search: images found for "<channel name> logo" whose longest side is at least MIN_SIDE pixels,
from sites other than social networks, stock-image banks and design portfolios (which gave mockups, photos and
concepts in reviews). Asked first: on the 2026-11 hunts of eleven European countries it found a usable logo for about a
quarter of the channels that every other source had missed. Free and without key, through the `ddgs` package (which
reads DuckDuckGo like a browser, and Bing when DuckDuckGo does not answer); one search per channel, cached thirty days, and at least PAUSE seconds between two
searches (DuckDuckGo answers nothing to searches sent in a row). A name that channels of several countries share is
searched with the country's name. Results are often wrong: every candidate is checked on the contact sheet.
"""
from __future__ import annotations

import os
import time

from worldwide_tv_logos import image, net
from worldwide_tv_logos.sources import names

MAX_AGE = 30 * 86400
MIN_SIDE = image.MIN_SIDE            # the size the repository asks for: smaller ones are refused
MAX_RESULTS = 30                     # results read per search
KEEP = 6                             # candidates returned
PAUSE = float(os.environ.get('WTL_DDG_PAUSE', '8'))     # seconds between two searches
RETRY_AFTER = 30.0                   # one more try after a failed search
SKIP = ('facebook.', 'fbcdn.', 'instagram.', 'lookaside.', 'x.com', 'twimg.', 'twitter.', 'tiktok.', 'youtube.',
        'ytimg.', 'pinimg.', 'pinterest.', 'redbubble.', 'etsy', 'shutterstock.', 'alamy.', 'istockphoto.',
        'gettyimages.', 'dreamstime.', 'freepik.', 'vecteezy.', 'behance.', 'dribbble.', 'creativemarket.',
        'creativefabrica.', 'photo-tmdb.', 'stalker')
_last = [0.0]


def _ddgs_images(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS
    return DDGS(timeout=30).images(query, max_results=max_results)    # backend 'auto': DuckDuckGo, else Bing


search_images = _ddgs_images          # replaced in tests


def _search(query: str) -> list[dict]:
    """The results of one search, with the pause between two searches and one retry."""
    for attempt in (0, 1):
        wait = _last[0] + (PAUSE if not attempt else RETRY_AFTER) - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            hits = search_images(query, MAX_RESULTS) or []
            if hits:
                return [{k: h.get(k) for k in ('image', 'width', 'height')} for h in hits]
            error: Exception = ValueError('no result')      # what a throttled search answers: never cached
        except Exception as exc:  # noqa: BLE001 - any failure of the search library: a missing source, never a crash
            error = exc
        finally:
            _last[0] = time.time()
    raise net.DownloadError(f'DuckDuckGo: {type(error).__name__}: {error}')


def usable(hit: dict) -> bool:
    url = (hit.get('image') or '').lower()
    try:
        side = max(int(hit.get('width') or 0), int(hit.get('height') or 0))
    except (TypeError, ValueError):
        side = 0
    return url.startswith('https://') and side >= MIN_SIDE and not any(s in url for s in SKIP)


def country_name(root, cc: str) -> str:
    from worldwide_tv_logos import iptvorg
    try:
        return next((c['name'] for c in iptvorg.load_countries(root) if c['code'].lower() == cc), '')
    except Exception:  # noqa: BLE001 - without countries.json, the name alone
        return ''


def find(unit: dict, ctx) -> list[str]:
    name = unit.get('name') or ''
    if len(names.key(name)) < 3:
        return []
    query = f'{name} logo'
    if names.channel_keys(unit) & ctx.ambiguous:
        query = f'{name} {country_name(ctx.root, ctx.cc)} TV logo'.replace('  ', ' ')
    hits = ctx.cached('duckduckgo', query, lambda: _search(query), MAX_AGE)
    out: list[str] = []
    for hit in hits:
        url = hit.get('image') or ''
        if usable(hit) and url not in out:
            out.append(url)
    return out[:KEEP]
