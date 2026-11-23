"""Matching the channels of public TV guides (EPG) with ours (roadmap step 6): `guides.json`, rebuilt every night.

Guide IDs are never stored as data: each guide's channel list is read again and matched every night, so a guide that
renames its IDs is followed without anything to maintain. The only stored guide IDs are the aliases confirmed by
review (data/aliases.csv), which win over the automatic matching.

Score of a match:
    1.0   confirmed: an alias of data/aliases.csv
    0.95  same ID: the guide uses the channel's iptv-org ID (case aside)
    0.9   by name: one channel of the country only has this main name (its name, or its iptv-org ID)
    0.7   by another name only (iptv-org's other names are sometimes loose), or one channel of another country only
    0.5   ambiguous: several channels have it (each listed, at most three)
Quality and timeshift versions (`TF1 HD`, `TF1 +1`) are matched with their channel, whose logo they show. The search
of the website uses the matches of 0.9 and more.
"""
from __future__ import annotations

import re

from worldwide_tv_logos import registry
from worldwide_tv_logos.db import Database
from worldwide_tv_logos.sources.names import key

SURE = 0.9                                  # from this score a match is used by the search of the website


VERSION_RE = re.compile(r'(?:\s*(?:\+\s*1|\bHD\b|\bFHD\b|\bUHD\b|\b4K\b|\bSD\b|\bTV\b))+\s*$', re.IGNORECASE)


def _keys(name: str) -> set[str]:
    return {k for k in (key(name), key(name.replace('+', 'plus'))) if k}


def name_keys(name: str) -> set[str]:
    """Keys of a guide channel name, and of the name without a quality or timeshift mark or a final "TV"."""
    bare = VERSION_RE.sub('', name)
    return _keys(name) | (_keys(bare) if bare.strip() else set())


def _names_index(db: Database) -> dict:
    """{'main': {(country, key): ids}, 'other': {(country, key): ids}, 'any': {key: ids}, 'any other': {key: ids}}
    for every channel not merged: main = its name and iptv-org ID, other = its other names."""
    main: dict = {}
    other: dict = {}
    anywhere: dict = {}
    other_anywhere: dict = {}
    for c in db.channels.values():
        if c.status == 'merged':
            continue
        ident = registry.iptv_id(db, c.id)
        mk = _keys(c.name) | ({key(ident.split('.')[0])} if ident and '@' not in ident else set())
        for k in mk - {''}:
            main.setdefault((c.country, k), set()).add(c.id)
            anywhere.setdefault(k, set()).add(c.id)
        for a in c.alias_list:
            for k in _keys(a):
                other.setdefault((c.country, k), set()).add(c.id)
                other_anywhere.setdefault(k, set()).add(c.id)
    return {'main': main, 'other': other, 'any': anywhere, 'any other': other_anywhere}


def _found(index: dict, part: str, cc: str, keys: set[str]) -> set[str]:
    table = index[part]
    hits = [table.get((cc, k) if cc else k, set()) for k in keys]
    return set().union(*hits) if hits else set()


def match(db: Database, guide: str, cc: str, channels: list[dict], index=None, iptv_ids=None) -> dict[str, list]:
    """{guide channel ID: [{channel, score, how}]} for the channels of one guide of country `cc`
    ([{id, names}], or [{id, keys}]); channels found nowhere are left out."""
    index = _names_index(db) if index is None else index
    if iptv_ids is None:
        iptv_ids = {x.external_id.lower(): x.channel_id for x in db.external_ids.values()
                    if x.source in ('iptv-org', 'iptv-org-feed')}
    confirmed = {a.epg_id: a.channel for a in db.aliases.values() if a.source == guide and a.channel in db.channels}
    out: dict[str, list] = {}
    for g in channels:
        gid = g['id']
        if gid in confirmed:
            out[gid] = [{'channel': confirmed[gid], 'score': 1.0, 'how': 'confirmed'}]
            continue
        same = iptv_ids.get(gid.lower())
        if same in db.channels:
            out[gid] = [{'channel': same, 'score': 0.95, 'how': 'same ID'}]
            continue
        keys = set(g.get('keys') or ())
        for n in g.get('names') or ():
            keys |= name_keys(n)
        if not g.get('names') and '.' in gid:              # an ID made of the name: France3.fr
            keys |= name_keys(gid.rsplit('.', 1)[0])
        keys.discard('')
        for part, where, score, how in (('main', cc, SURE, 'name'), ('other', cc, 0.7, 'other name'),
                                        ('any', '', 0.7, 'name, another country')):
            found = _found(index, part, where, keys)
            if len(found) == 1:
                out[gid] = [{'channel': found.pop(), 'score': score, 'how': how}]
                break
            if 1 < len(found) <= 3:
                out[gid] = [{'channel': c, 'score': 0.5, 'how': f'{how}, ambiguous'} for c in sorted(found)]
                break
            if found:                                        # more than three: too common a name
                break
    return out


def iptv_epg_guides(db: Database, downloader=None, log=print) -> list[tuple[str, str, list[dict]]]:
    """(guide name, country, channels) of the iptv-epg guides of the followed countries (cached one day)."""
    from worldwide_tv_logos.sources.iptvepg import load_iptv_epg
    out = []
    for cc in sorted(db.countries):
        try:
            channels = load_iptv_epg(db.root, cc, downloader)
        except Exception as exc:  # noqa: BLE001 - a guide that cannot be read is skipped, never blocking
            log(f'iptv-epg guide of `{cc}` unavailable ({exc})')
            continue
        if channels:
            out.append((f'iptv-epg-{cc}', cc, channels))
    return out


def xmltv_se_guides(db: Database, log=print) -> list[tuple[str, str, list[dict]]]:
    """(guide name, country, channels) of the xmltv.se IDs (the names of its logo collection), by country."""
    from worldwide_tv_logos import sources
    from worldwide_tv_logos.sources import xmltvse
    try:
        files = xmltvse.index(sources.Context(root=db.root, cc='', log=log))
    except Exception as exc:  # noqa: BLE001
        log(f'xmltv-se index unavailable ({exc})')
        return []
    countries = {c.country for c in db.channels.values()}
    by_cc: dict[str, dict[str, dict]] = {}
    for f in files:
        gid = f[:-4].rsplit('_', 1)[0] if '_' in f else f[:-4]
        cc, keys = xmltvse.keys_of(gid)
        cc = 'uk' if cc == 'gb' else cc
        if cc in countries and gid not in by_cc.get(cc, {}):
            by_cc.setdefault(cc, {})[gid] = {'id': gid, 'names': [], 'keys': sorted(keys)}
    return [('xmltv-se', cc, list(chs.values())) for cc, chs in sorted(by_cc.items())]


def build(db: Database, guides: list[tuple[str, str, list[dict]]]) -> dict:
    """The content of guides.json: {version, guides: {guide: {guide channel ID: [{channel, score, how}]}}}."""
    index = _names_index(db)
    iptv_ids = {x.external_id.lower(): x.channel_id for x in db.external_ids.values()
                if x.source in ('iptv-org', 'iptv-org-feed')}
    out: dict[str, dict] = {}
    for name, cc, channels in guides:
        out.setdefault(name, {}).update(match(db, name, cc, channels, index, iptv_ids))
    for a in db.aliases.values():                            # confirmed aliases of guides not read this night
        if a.channel in db.channels:
            out.setdefault(a.source, {})[a.epg_id] = [{'channel': a.channel, 'score': 1.0, 'how': 'confirmed'}]
    return {'version': 1, 'guides': {g: dict(sorted(m.items())) for g, m in sorted(out.items())}}


def lookup(db: Database, text: str, cc: str = '', guides_data: dict | None = None) -> list[dict]:
    """Channels for what a user holds: our ID, a slug, an iptv-org or Wikidata ID, a guide channel ID (with
    guides.json), or a channel name (in country `cc`, or anywhere): [{channel, score, how}]."""
    c = registry.resolve(db, text.strip()) or registry.resolve(db, text.strip().lower())
    if c is None:                                            # another project's ID, case aside
        low = text.strip().lower()
        c = next((db.channels.get(x.channel_id) for x in db.external_ids.values()
                  if x.external_id.lower() == low and x.channel_id in db.channels), None)
    if c is not None:
        return [{'channel': c.id, 'score': 1.0, 'how': 'ID'}]
    found = []
    for name, matches in (guides_data or {}).get('guides', {}).items():
        found += [dict(m, how=f'{m["how"]} ({name})') for m in matches.get(text, ())]
    if found:
        return sorted(found, key=lambda m: -m['score'])
    index = _names_index(db)
    if cc:
        found = match(db, '', cc, [{'id': text, 'names': [text]}], index).get(text, [])
        if found:
            return found
    for part, score, how in (('any', SURE, 'name'), ('any other', 0.7, 'other name')):   # anywhere: at most ten
        hits = sorted(_found(index, part, '', name_keys(text)))
        if hits:
            return [{'channel': h, 'score': score if len(hits) == 1 else 0.5, 'how': how} for h in hits[:10]]
    return []
