"""Wikimedia Commons: files whose title has the channel's name and the word "logo" (search in the File namespace),
for logos that no Wikidata item links to. One request per channel, cached thirty days. Files giving a period already
over ("2011-2017") are left out; SVG first. Not asked for a name that channels of several countries share.
"""
from __future__ import annotations

import re
import urllib.parse

from worldwide_tv_logos.sources import names
from worldwide_tv_logos.sources.wikidata import COMMONS_FILE, is_old

API = 'https://commons.wikimedia.org/w/api.php?'
MAX_AGE = 30 * 86400


def search(name: str, ctx) -> list[str]:
    """Titles of the files found (without the `File:` prefix)."""
    def compute():
        url = API + urllib.parse.urlencode({'action': 'query', 'format': 'json', 'list': 'search', 'srnamespace': 6,
                                            'srlimit': 20, 'srsearch': f'intitle:"{name}" logo'})
        return [h['title'].split(':', 1)[-1] for h in ctx.json(url).get('query', {}).get('search', [])]
    return ctx.cached('commons', name, compute, MAX_AGE)


NOISE = {'logo', 'logotipo', 'logotype', 'svg', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'file', 'of', 'the', 'new',
         'official'}


words = names.words


GROUP_WORDS = {'network', 'networks', 'group', 'media', 'corporation', 'corp', 'inc', 'company', 'holdings',
               'productions', 'production', 'studios', 'entertainment', 'communications', 'broadcasting', 'radio',
               'hd', 'uhd', 'fhd', '4k', 'sd'}               # a group, or a quality badge (never published)


def named_after(title: str, name: str) -> bool:
    """The file title starts with the channel's name (after "Logo of"), with at most one other word besides "logo"
    and a year, never a group word or a quality badge: "Antena 3 logo 2023.svg" for Antena 3; not "Thoma Bravo logo 2024.svg" for Bravo,
    "AMC Networks logo.svg" for AMC, or "Huaju Film Co production logo, 1927.jpg" for Film&Co."""
    t, n = words(title), words(name)
    while t and t[0] in NOISE:
        t = t[1:]
    if not n or t[:len(n)] != n:
        return False
    extra = [w for w in t[len(n):] if w not in NOISE and not re.fullmatch(r'(19|20)\d\d', w)]
    return len(extra) <= 1 and not GROUP_WORDS & set(extra)


def find(unit: dict, ctx) -> list[str]:
    name = unit.get('name') or ''
    if len(names.key(name)) < 3 or names.channel_keys(unit) & ctx.ambiguous:
        return []                                # a name of channels of several countries: whose logo is it?
    files = []
    for title in search(name, ctx):
        low = title.lower()
        if 'logo' not in low or is_old({'end': '', 'file': title}):
            continue
        if low.rsplit('.', 1)[-1] not in ('svg', 'png', 'jpg', 'jpeg', 'webp', 'gif'):
            continue
        if named_after(title.rsplit('.', 1)[0], name):
            files.append(title)
    files.sort(key=lambda t: not t.lower().endswith('.svg'))
    return [COMMONS_FILE + urllib.parse.quote(t.replace(' ', '_')) for t in files[:2]]
