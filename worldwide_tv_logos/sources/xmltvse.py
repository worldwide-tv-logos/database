"""xmltv.se channel logos (gitlab.com/xmltv-se/open-source/channel-logos): about 900 vector logos, mostly of Nordic
and German channels, named by their XMLTV ID (`1.bluemovie.de_color.svg`). The list of files is read once (GitLab
API, nine pages, cached thirty days); a channel matches when the labels of the ID, without the country at the end,
give one of its names (`bluemovie` + `1`), and the ID's country is the channel's or a generic one (.com, .eu)."""
from __future__ import annotations

import urllib.parse

from worldwide_tv_logos.sources import names

API = 'https://gitlab.com/api/v4/projects/1802116/repository/tree?path=vector&per_page=100&page={page}'
RAW = 'https://gitlab.com/xmltv-se/open-source/channel-logos/-/raw/master/vector/'
MAX_AGE = 30 * 86400
GENERIC = {'com', 'eu', 'tv', 'net', 'org', 'int'}


def keys_of(xmltv_id: str) -> tuple[str, set[str]]:
    """(country label, comparison keys) of an XMLTV ID: `1.bluemovie.de` -> ('de', {'1bluemovie', 'bluemovie1'})."""
    labels = xmltv_id.split('.')
    country, rest = labels[-1], [x for x in labels[:-1] if x]
    return country, {names.key(''.join(rest)), names.key(''.join(reversed(rest)))} - {''}


def index(ctx) -> list[str]:
    """File names of the collection, colour versions first."""
    def compute():
        files: list[str] = []
        for page in range(1, 30):
            rows = ctx.json(API.format(page=page))
            files += [r['name'] for r in rows if r.get('type') == 'blob' and r['name'].endswith('.svg')]
            if len(rows) < 100:
                break
        return sorted(files, key=lambda f: ('_color' not in f, f))
    return ctx.cached('xmltv-se', 'index', compute, MAX_AGE)


def find(unit: dict, ctx) -> list[str]:
    cc = unit.get('channel', unit['id']).rsplit('.', 1)[-1]
    wanted = {k for k in names.channel_keys(unit) if len(k) >= 3}
    for file in index(ctx):
        country, keys = keys_of(file.rsplit('_', 1)[0] if '_' in file else file[:-4])
        if (country == cc or country in GENERIC) and keys & wanted:
            return [RAW + urllib.parse.quote(file)]
    return []
