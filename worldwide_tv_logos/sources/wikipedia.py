"""Wikipedia: the image of the channel's article (the logo of its infobox). Many logos are hosted by one Wikipedia
edition only, not by Wikimedia Commons: Wikidata does not have them (almost every American station, many British,
Italian and Spanish channels).

The articles are the Wikidata item's (its sitelinks), in the country's languages then English; without an item, the
article named like the channel, if it is not a disambiguation page and its title is the channel's name. The image is
read with the MediaWiki API (`prop=pageimages`, its original file, one request per article, cached thirty days).
Kept only when its file name says "logo" or is an SVG, and does not give a period already over ("2011-2017").
"""
from __future__ import annotations

import re
import urllib.parse

from worldwide_tv_logos.sources import names
from worldwide_tv_logos.sources.wikidata import is_old

MAX_AGE = 30 * 86400
LOGO_WORDS = ('logo', 'logotipo', 'logotype', 'logotyp')


def page_image(lang: str, title: str, ctx) -> dict:
    """{'title': resolved title, 'image': original image URL or '', 'disambiguation': bool, 'missing': bool}."""
    def compute():
        url = f'https://{lang}.wikipedia.org/w/api.php?' + urllib.parse.urlencode(
            {'action': 'query', 'format': 'json', 'redirects': 1, 'prop': 'pageimages|pageprops',
             'piprop': 'original', 'ppprop': 'disambiguation|wikibase_item', 'titles': title})
        pages = list(ctx.json(url).get('query', {}).get('pages', {}).values())
        page = pages[0] if pages else {}
        return {'title': page.get('title', title), 'image': page.get('original', {}).get('source', ''),
                'disambiguation': 'disambiguation' in page.get('pageprops', {}), 'missing': 'missing' in page,
                'item': page.get('pageprops', {}).get('wikibase_item', '')}
    return ctx.cached('wikipedia', f'{lang}-{title}', compute, MAX_AGE)


def plausible(url: str) -> bool:
    """A logo by its file name: says "logo" or is an SVG, and is not an old branding."""
    file = urllib.parse.unquote(url.rsplit('/', 1)[-1])
    low = file.lower()
    return (any(w in low for w in LOGO_WORDS) or low.endswith('.svg')) and not is_old({'end': '', 'file': file})


def articles(unit: dict, ctx) -> list[tuple[str, str]]:
    """(language, title) of the channel's articles, the country's languages first."""
    links: dict[str, str] = {}
    for item in ctx.items(unit):
        for lang, title in item.get('sitelinks', {}).items():
            links.setdefault(lang, title)
    found = [(lang, links[lang]) for lang in ctx.languages if lang in links]
    if not found and unit.get('name'):
        found = [(lang, unit['name']) for lang in ctx.languages[:2]]          # by name: checked below
    return found


def find(unit: dict, ctx) -> list[str]:
    out: list[str] = []
    items = {i['qid'] for i in ctx.items(unit)}
    keys = names.channel_keys(unit)
    for lang, title in articles(unit, ctx):
        page = page_image(lang, title, ctx)
        if page['missing'] or page['disambiguation'] or not page['image']:
            continue
        by_name = not items
        if by_name and names.key(re.sub(r'\s*\(.*\)$', '', page['title'])) not in keys:
            continue                                     # an article found by name must be about this channel
        if items and page.get('item') and page['item'] not in items:
            continue
        if plausible(page['image']) and page['image'] not in out:
            out.append(page['image'])
        if len(out) >= 2:
            break
    return out
