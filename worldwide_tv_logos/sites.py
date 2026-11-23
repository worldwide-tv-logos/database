"""The website of a channel, found and checked: the place where its current logo can be seen.

iptv-org's `website` is often out of date (a page that moved, a dead domain). The addresses tried, in order:

1. iptv-org's `website`, then the official websites of the channel's Wikidata items (P856);
2. the home page of each of their domains (a page that moved: `ceutatv.com/pag/...` -> `ceutatv.com/`);
3. addresses made from the channel's name: `<name>.<country>`, `<name>.com`, `<name>tv.<country>`...

A page is read by web.fetch (a plain request, else a headless browser). A site is **confirmed** when the channel's
name is in its title, its `og:site_name` or its domain name; the first confirmed one is kept, else the first page
that could be read (unconfirmed). The result is cached thirty days in .cache/sites/.
"""
from __future__ import annotations

import html as htmllib
import re
import urllib.parse
from dataclasses import dataclass

from worldwide_tv_logos import web
from worldwide_tv_logos.sources import names

MAX_AGE = 30 * 86400
TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)
SITE_NAME_RE = re.compile(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)', re.IGNORECASE)
TLD = {'uk': 'co.uk', 'us': 'com'}            # the usual domain ending of a country, when it differs from its code


@dataclass
class Site:
    url: str                  # the page to look at
    how: str                  # iptv-org | wikidata | home page | name
    confirmed: bool           # the channel's name is in its title, site name or domain
    title: str = ''
    page: web.Page | None = None


def page_titles(page: web.Page) -> str:
    """What a page says it is: its title and its og:site_name."""
    found = [m.group(1) for r in (TITLE_RE, SITE_NAME_RE) for m in [r.search(page.html)] if m]
    return ' '.join(htmllib.unescape(x).strip() for x in found)


def page_names(page: web.Page) -> str:
    """Its title, its og:site_name and its domain."""
    return f'{page_titles(page)} {urllib.parse.urlsplit(page.final or page.url).hostname or ""}'.strip()


def host_label(page: web.Page) -> str:
    """The name part of the domain: `www.canalcostatv.es` -> `canalcostatv`."""
    host = (urllib.parse.urlsplit(page.final or page.url).hostname or '').removeprefix('www.')
    parts = host.split('.')
    return names.key(parts[-3] if len(parts) > 2 and parts[-2] in ('co', 'com', 'org', 'net') else parts[0])


def confirms(page: web.Page, unit: dict, strict: bool = False) -> bool:
    """The channel's name is in what the page says it is: its words in the title or site name ("Ceuta TV - Inicio";
    not "Golf shop" for Gol), or the domain is the name (canalcostatv.es for CanalCosta). `strict` (an address made
    from the name): both, since any domain of that name would otherwise do."""
    titles = page_titles(page)
    title = any(names.has_name(titles, n) for n in [unit.get('name') or '', *(unit.get('alt_names') or [])] if n)
    label = host_label(page)
    host = any(len(k) >= 3 and label in (k, k + 'tv', k + 'television', 'tv' + k) for k in names.channel_keys(unit))
    return (title and host) if strict else (title or host)


def home(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f'https://{parts.hostname}/' if parts.hostname else ''


def guesses(unit: dict, cc: str) -> list[str]:
    """Addresses made from the channel's name: ceutatv.es, ceutatv.com..."""
    base = names.key((unit.get('name') or '').replace('+', 'plus')).replace('+', '')
    if len(base) < 3:
        return []
    stems = [base] + ([base + 'tv'] if not base.endswith('tv') else [])
    endings = list(dict.fromkeys([TLD.get(cc, cc), 'com', 'tv']))
    return [f'https://www.{s}.{e}/' for s in stems for e in endings][:5]


def addresses(unit: dict, ctx) -> list[tuple[str, str]]:
    """(address, how) to try, best first, each once."""
    out: list[tuple[str, str]] = []
    given = [(unit.get('website') or '', 'iptv-org')] + [(i.get('website') or '', 'wikidata') for i in ctx.items(unit)]
    for url, how in given:
        if url.startswith('http'):
            url = url.replace('http://', 'https://', 1)
            out += [(url, how), (home(url), 'home page')]
    out += [(u, 'name') for u in guesses(unit, ctx.cc)]
    seen: set[str] = set()
    return [(u, h) for u, h in out if u and not (u.rstrip('/') in seen or seen.add(u.rstrip('/')))]


def find(unit: dict, ctx, fetch=web.fetch) -> Site | None:
    """The website of a channel or edition (None when no address could be read)."""
    def compute():
        first = None
        for url, how in addresses(unit, ctx):
            page = fetch(url, browser=how != 'name')        # guessed addresses: a plain request only (cheap)
            if not page.ok:
                continue
            if confirms(page, unit, strict=how == 'name'):
                return {'url': page.final or url, 'how': how, 'confirmed': True, 'title': page_names(page)[:120]}
            if first is None and how != 'name':
                first = {'url': page.final or url, 'how': how, 'confirmed': False, 'title': page_names(page)[:120]}
        return first
    found = ctx.cached('sites', unit['id'], compute, MAX_AGE)
    return Site(**found) if found else None
