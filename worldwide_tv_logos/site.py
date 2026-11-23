"""Data of the website (GitHub Pages): the channels of our registry (data/channels.csv), with their editions and
the logos of this repository.

    countries.json            [{code, name, flag, channels, logos}]   countries with at least one channel
    countries/<cc>.json       {code, name, flag, channels: [...]}     channels of a country, their editions and logos
    search.json               [[id, name, cc, logos, other IDs]]      every channel, for the global search
    channels.json             {version, channels: [...]}              every channel of the registry (public API)
    guides.json               {version, guides: {...}}                guide channel IDs -> our channels (guides.py)

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


def channels_json(db: Database) -> dict:
    """Every channel with its IDs and logo; an edition without a logo of its own gives its channel's (`logo_from`)."""
    def logo(cid: str, variant: str = '') -> str | None:
        x = db.logos.get((cid, variant))
        return x.url if x else None

    ids: dict[str, dict[str, str]] = {}
    for x in db.external_ids.values():
        if x.source in ('iptv-org', 'iptv-org-feed', 'wikidata'):
            ids.setdefault(x.channel_id, {})['wikidata' if x.source == 'wikidata' else 'iptv'] = x.external_id
    out = []
    for c in sorted(db.channels.values(), key=lambda c: (c.country, c.slug)):
        source = c.id
        if logo(c.id) is None and c.parent and c.status != 'merged' and logo(c.parent):
            source = c.parent
        out.append({'id': c.id, 'slug': c.slug, 'name': c.name, 'aliases': c.alias_list, 'country': c.country,
                    'status': c.status, 'parent': c.parent or None, 'website': c.website or None,
                    'iptv': ids.get(c.id, {}).get('iptv'), 'wikidata': ids.get(c.id, {}).get('wikidata'),
                    'logo': logo(source), 'logo_white': logo(source, 'white'),
                    'logo_from': source if source != c.id else None})
    return {'version': 1, 'channels': out}


def build(db: Database, iptv: IptvOrg, countries: list[dict], out: Path, guides_data: dict | None = None) -> dict[str, int]:
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
    other_ids: dict[str, set[str]] = defaultdict(set)      # what the global search also finds a channel by
    for x in db.external_ids.values():
        if x.source in ('iptv-org', 'iptv-org-feed', 'wikidata'):
            other_ids[x.channel_id].add(x.external_id)
    for matches in (guides_data or {}).get('guides', {}).values():
        for gid, found in matches.items():
            for m in found:
                if m['score'] >= 0.9:
                    other_ids[m['channel']].add(gid)
    for c in db.channels.values():                           # an edition is found under its channel's card
        if c.parent and c.status != 'merged' and c.id in other_ids:
            other_ids[c.parent] |= other_ids[c.id] | {c.id}
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
        search += [[c['id'], c['name'], cc, len(c['logos']), ' '.join(sorted(other_ids.get(c['id'], ())))]
                   for c in channels]
    index.sort(key=lambda x: x['name'].lower())
    _dump(out / 'countries.json', index)
    _dump(out / 'search.json', search)
    _dump(out / 'channels.json', channels_json(db))
    if guides_data is not None:
        _dump(out / 'guides.json', guides_data)
    return {'countries': len(index), 'channels': sum(x['channels'] for x in index),
            'with_logo': sum(x['logos'] for x in index)}
