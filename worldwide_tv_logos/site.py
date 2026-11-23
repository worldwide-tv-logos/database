"""Data of the website (GitHub Pages): the channels of our registry (data/channels.csv), with their editions and
the logos of this repository.

    countries.json            [{code, name, flag, channels, logos}]   countries with at least one channel
    countries/<cc>.json       {code, name, flag, channels: [...]}     channels of a country, their editions and logos
    search.json               [[id, name, cc, logos]]                 every channel, for the global search

A channel is listed in its country with its editions (`feeds`: our IDs of its regional or market versions, wherever
they are broadcast). NSFW channels of iptv-org are left out. The website itself (site/, Nuxt) reads these files; it
is built by `npm run generate`.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from worldwide_tv_logos import registry
from worldwide_tv_logos.db import Database
from worldwide_tv_logos.iptvorg import IptvOrg

IPTV_KEYS = ('network', 'categories', 'launched')


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8', newline='\n')


def build(db: Database, iptv: IptvOrg, countries: list[dict], out: Path) -> dict[str, int]:
    def logos_of(cid: str, feed: str | None) -> list[dict]:
        return [{'feed': feed, 'variant': x.variant or None, 'url': x.url, 'width': x.width, 'height': x.height,
                 'updated': x.updated or x.added}
                for x in (db.logos.get((cid, v)) for v in ('', 'white')) if x is not None]

    aliases = defaultdict(list)
    for a in db.aliases.values():
        aliases[a.channel].append({'epg_id': a.epg_id, 'source': a.source})
    editions = defaultdict(list)
    for c in db.channels.values():
        if c.parent and c.status != 'merged':
            editions[c.parent].append(c)
    by_country = defaultdict(list)
    for c in db.channels.values():
        if c.parent and c.status != 'merged':
            continue                                               # listed with its channel
        ident = registry.iptv_id(db, c.id)
        rec = iptv.channels.get(ident.split('@')[0]) or {} if ident else {}
        if rec.get('is_nsfw'):
            continue
        merged = db.channels.get(c.parent) if c.status == 'merged' else None
        record = {'id': c.id, 'slug': c.slug, 'iptv': ident or None, 'country': c.country, 'name': c.name,
                  'alt_names': c.alias_list,
                  **{k: rec.get(k) for k in IPTV_KEYS}, 'website': c.website or None,
                  'closed': (rec.get('closed') or 'yes') if c.status in ('closed', 'merged') else None,
                  'replaced_by': merged.id if merged else None,
                  'replaced_by_country': merged.country if merged else None,
                  'feeds': [], 'logos': logos_of(c.id, None),
                  'aliases': [dict(a, feed=None) for a in aliases.get(c.id, [])]}
        for e in sorted(editions.get(c.id, []), key=lambda e: e.name.lower()):
            record['feeds'].append({'id': e.id, 'slug': e.slug, 'name': e.name, 'is_main': False, 'format': None,
                                    'country': e.country, 'closed': e.status == 'closed'})
            record['logos'] += logos_of(e.id, e.id)
            record['aliases'] += [dict(a, feed=e.id) for a in aliases.get(e.id, [])]
        by_country[c.country].append(record)
    names = {x['code'].lower(): x for x in countries}
    index, search = [], []
    for cc, channels in sorted(by_country.items()):
        if not cc:
            continue
        info = names.get(cc, {'name': cc.upper(), 'flag': ''})
        channels.sort(key=lambda c: c['name'].lower())
        _dump(out / 'countries' / f'{cc}.json',
              {'code': cc, 'name': info['name'], 'flag': info.get('flag', ''), 'channels': channels})
        on_air = [c for c in channels if not c['closed']]          # counts: open channels, as in missing/
        index.append({'code': cc, 'name': info['name'], 'flag': info.get('flag', ''), 'channels': len(on_air),
                      'logos': sum(1 for c in on_air if c['logos'])})
        search += [[c['id'], c['name'], cc, len(c['logos'])] for c in channels]
    index.sort(key=lambda x: x['name'].lower())
    _dump(out / 'countries.json', index)
    _dump(out / 'search.json', search)
    return {'countries': len(index), 'channels': sum(x['channels'] for x in index),
            'with_logo': sum(x['logos'] for x in index)}
