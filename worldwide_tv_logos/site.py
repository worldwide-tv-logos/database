"""Data of the website (GitHub Pages): every iptv-org country and channel, with the logos of this repository.

    countries.json            [{code, name, flag, channels, logos}]   countries with at least one channel
    countries/<cc>.json       {code, name, flag, channels: [...]}     channels of a country, their feeds and logos
    search.json               [[id, name, cc, logos]]                 every channel, for the global search

NSFW channels are left out. The website itself (site/, Nuxt) reads these files; it is built by `npm run generate`.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from worldwide_tv_logos.db import Database
from worldwide_tv_logos.iptvorg import IptvOrg

CHANNEL_KEYS = ('name', 'alt_names', 'network', 'categories', 'website', 'launched', 'closed', 'replaced_by')


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8', newline='\n')


def build(db: Database, iptv: IptvOrg, countries: list[dict], out: Path) -> dict[str, int]:
    logos = defaultdict(list)
    for x in db.logos.values():
        logos[x.channel].append({'feed': x.feed or None, 'variant': x.variant or None, 'url': x.url,
                                 'width': x.width, 'height': x.height, 'updated': x.updated or x.added})
    aliases = defaultdict(list)
    for a in db.aliases.values():
        aliases[a.channel].append({'epg_id': a.epg_id, 'source': a.source, 'feed': a.feed or None})
    feeds = defaultdict(list)
    for (channel, fid), f in iptv.feeds.items():
        feeds[channel].append({'id': fid, 'name': f.get('name') or fid, 'is_main': bool(f.get('is_main')),
                               'format': f.get('format')})
    by_country = defaultdict(list)
    for c in iptv.channels.values():
        if c.get('is_nsfw'):
            continue
        record = {'id': c['id'], **{k: c.get(k) for k in CHANNEL_KEYS},
                  'feeds': sorted(feeds.get(c['id'], []), key=lambda f: (not f['is_main'], f['name'].lower())),
                  'logos': sorted(logos.get(c['id'], []), key=lambda x: (x['feed'] or '', x['variant'] or '')),
                  'aliases': aliases.get(c['id'], [])}
        by_country[(c.get('country') or '').lower()].append(record)
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
