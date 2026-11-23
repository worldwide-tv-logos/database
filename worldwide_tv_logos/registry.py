"""Our channel registry: data/channels.csv (one row per channel, our own ID) and data/external_ids.csv (the iptv-org
and Wikidata IDs of each channel). See roadmap/01-channel-registry.md.

- ID: `ch_` + 10 random Crockford base32 characters (no I, L, O, U), from `secrets`: like a UUID v4, shorter and
  readable. Random, never derived from the name, so a rename never changes it; never reused.
- slug: readable and unique (`france-3-alsace.fr`), derived from the name; it may change on a rename, so it is never
  used as a key by other files.
- iptv-org is a source: `init` gives an ID to each iptv-org channel and edition we need, and can be run again (it only
  adds what is missing).
"""
from __future__ import annotations

import datetime
import re
import secrets
import unicodedata

from worldwide_tv_logos.db import CHANNEL_RE, Channel, Database, ExternalId

ALPHABET = '0123456789abcdefghjkmnpqrstvwxyz'                  # Crockford base32, lowercase
ID_RE = re.compile(r'^ch_[0-9abcdefghjkmnpqrstvwxyz]{10}$')
SLUG_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*\.[a-z]{2}$')
STATUSES = ('active', 'closed', 'merged')
FEED_ID_RE = re.compile(r'^[A-Za-z0-9]+\.[a-z]{2}@[A-Za-z0-9]+$')
SOURCES = {'iptv-org': CHANNEL_RE,
           'iptv-org-feed': FEED_ID_RE,
           'iptv-org-former': CHANNEL_RE,           # an ID iptv-org replaced by the current one (a rename)
           'iptv-org-feed-former': FEED_ID_RE,
           'wikidata': re.compile(r'^Q[1-9]\d*$')}
METHODS = ('import', 'match', 'review')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def today() -> str:
    return datetime.date.today().isoformat()


def new_id(taken) -> str:
    while True:
        cid = 'ch_' + ''.join(secrets.choice(ALPHABET) for _ in range(10))
        if cid not in taken:
            return cid


def slug_base(name: str) -> str:
    """`France 3 Alsace` -> `france-3-alsace`; `Canal+ Sport` -> `canal-plus-sport`; '' for a name without any
    Latin letter or digit."""
    text = unicodedata.normalize('NFKD', name.replace('+', ' plus ').replace('&', ' and '))
    text = text.encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def make_slug(name: str, country: str, taken, fallback: str = '') -> str:
    base = slug_base(name) or slug_base(fallback) or 'channel'
    slug, n = f'{base}.{country}', 2
    while slug in taken:
        slug, n = f'{base}-{n}.{country}', n + 1
    return slug


def by_external(db: Database, source: str, external_id: str) -> Channel | None:
    x = db.external_ids.get((source, external_id))
    return db.channels.get(x.channel_id) if x else None


def by_logo_id(db: Database, logo_id: str) -> Channel | None:
    """The registry channel of an iptv-org channel (`France3.fr`) or edition (`France3.fr@Alsace`)."""
    source = 'iptv-org-feed' if '@' in logo_id else 'iptv-org'
    return by_external(db, source, logo_id) or by_external(db, f'{source}-former', logo_id)


def resolve(db: Database, value: str) -> Channel | None:
    """A channel from our ID, its slug, or its iptv-org or Wikidata ID."""
    value = value.strip()
    if value in db.channels:
        return db.channels[value]
    for c in db.channels.values():
        if c.slug == value:
            return c
    for source in ('iptv-org', 'iptv-org-feed', 'wikidata', 'iptv-org-former', 'iptv-org-feed-former'):
        if (c := by_external(db, source, value)) is not None:
            return c
    return None


def iptv_id(db: Database, cid: str) -> str:
    """The iptv-org ID of a channel (`France3.fr`) or edition (`France3.fr@Alsace`), '' when it has none."""
    return next((x.external_id for x in _ids(db).get(cid, ()) if x.source in ('iptv-org', 'iptv-org-feed')), '')


def _ids(db: Database) -> dict[str, list]:
    """channel ID -> its external IDs, built once per state of the registry."""
    sig = (id(db.external_ids), len(db.external_ids))
    cache = db.__dict__.get('_ids_cache')
    if cache is None or cache[0] != sig:
        by: dict[str, list] = {}
        for x in db.external_ids.values():
            by.setdefault(x.channel_id, []).append(x)
        cache = (sig, by)
        db.__dict__['_ids_cache'] = cache
    return cache[1]


def family_name(db: Database, cid: str) -> str:
    """A name in the iptv-org form (`France3.fr`) used to tell brands and numbered sister channels apart
    (harvest.duplicates): the iptv-org channel ID, else one made from the slug; an edition takes its channel's."""
    ident = iptv_id(db, cid)
    if ident:
        return ident.split('@')[0]
    c = db.channels.get(cid)
    if c is None:
        return cid
    if c.parent and c.parent in db.channels and c.status != 'merged':
        return family_name(db, c.parent)
    base, _, cc = c.slug.rpartition('.')
    return f'{base.replace("-", "")}.{cc}'


def unit(db: Database, c: Channel) -> dict:
    """A channel or edition as the harvest and the sources see it: {id, name, alt_names, website, country, parent,
    iptv (its iptv-org ID or ''), channel (family name), feed (its iptv-org feed or '')}."""
    ident = iptv_id(db, c.id)
    return {'id': c.id, 'name': c.name, 'alt_names': c.alias_list, 'website': c.website, 'country': c.country,
            'parent': c.parent if c.status != 'merged' else '', 'iptv': ident, 'channel': family_name(db, c.id),
            'feed': ident.partition('@')[2]}


def units(db: Database, cc: str) -> list[dict]:
    """The active channels of a country, each followed by its editions (editions of a channel of another country
    broadcast here come last)."""
    here = [c for c in db.channels.values() if c.country == cc and c.status == 'active']
    mains = sorted((c for c in here if not c.parent), key=lambda c: c.name.lower())
    editions: dict[str, list[Channel]] = {}
    for c in here:
        if c.parent:
            editions.setdefault(c.parent, []).append(c)
    out = []
    for m in mains:
        out.append(unit(db, m))
        out += [unit(db, e) for e in sorted(editions.pop(m.id, []), key=lambda e: e.name.lower())]
    out += [unit(db, e) for es in editions.values() for e in sorted(es, key=lambda e: e.name.lower())]
    return out


def add_channel(db: Database, name: str, country: str, *, aliases=(), status: str = 'active', parent: str = '',
                website: str = '', fallback: str = '') -> Channel:
    country = country.lower()
    c = Channel(new_id(db.channels), make_slug(name, country, {x.slug for x in db.channels.values()}, fallback),
                name, ';'.join(a for a in aliases if a and a != name), country, status, parent, website, today(), '')
    db.channels[c.id] = c
    return c


def map_id(db: Database, channel: Channel, source: str, external_id: str, method: str) -> None:
    db.external_ids[(source, external_id)] = ExternalId(channel.id, source, external_id, method, today())
    db.__dict__.pop('_ids_cache', None)


QUALITY_FEED = re.compile(r'^(SD|HD|FHD|UHD|QHD|4K|8K|HDR|H265|HEVC|1080p?|720p?|Plus\d+)$', re.IGNORECASE)  # quality, +1


def iptv_units(iptv, cc: str) -> list[dict]:
    """The open iptv-org channels of a country and their editions (feeds other than the main one, quality and
    timeshift versions excepted), each as {id, channel, feed, name, alt_names, website}; an edition is named after
    its channel ("France 3 Alsace")."""
    out = []
    feeds: dict[str, list[dict]] = {}
    for (channel, fid), f in iptv.feeds.items():
        if not f.get('is_main') and not QUALITY_FEED.match(fid):     # TF1@HD uses the logo of TF1
            feeds.setdefault(channel, []).append(dict(f, id=fid))
    for c in sorted(iptv.country_channels(cc), key=lambda c: c['name'].lower()):
        out.append(dict(c, channel=c['id'], feed=''))
        for f in sorted(feeds.get(c['id'], []), key=lambda f: f['id']):
            name = f.get('name') or f['id']
            out.append({'id': f'{c["id"]}@{f["id"]}', 'channel': c['id'], 'feed': f['id'],
                        'name': name if name.lower().startswith(c['name'].lower()) else f'{c["name"]} {name}',
                        'alt_names': [], 'website': c.get('website') or ''})
    return out


def _iptv_country(record: dict, logo_id: str) -> str:
    return (record.get('country') or logo_id.split('@')[0].rsplit('.', 1)[-1]).lower()


def edition_country(feed: dict, default: str) -> str:
    """The country an edition is broadcast in: the only country of its iptv-org broadcast area (`c/BG`), else its
    channel's (a region `s/AU-QLD`, several countries or none)."""
    areas = {a[2:].lower() for a in feed.get('broadcast_area') or () if a.startswith('c/')}
    others = [a for a in feed.get('broadcast_area') or () if not a.startswith(('c/', 's/'))]
    if len(areas) == 1 and not others:
        cc = areas.pop()
        if re.match(r'^[a-z]{2}$', cc):
            return cc
    return default


def refresh_editions(db: Database, iptv) -> int:
    """Editions loaded from iptv-org and never edited here (`updated` empty) follow their iptv-org broadcast country;
    their slug follows. Returns the number changed."""
    changed = 0
    slugs = {c.slug for c in db.channels.values()}
    for x in [x for x in db.external_ids.values() if x.source == 'iptv-org-feed' and x.method == 'import']:
        c = db.channels.get(x.channel_id)
        channel, _, fid = x.external_id.partition('@')
        feed = iptv.feeds.get((channel, fid))
        if c is None or c.updated or feed is None:
            continue
        parent = db.channels.get(c.parent)
        cc = edition_country(feed, parent.country if parent else c.country)
        if cc != c.country:
            slugs.discard(c.slug)
            c.country, c.slug = cc, make_slug(c.name, cc, slugs, fallback=x.external_id.replace('@', ' '))
            slugs.add(c.slug)
            changed += 1
    return changed


def init(db: Database, iptv, countries) -> dict[str, int]:
    """Every iptv-org channel and edition we need gets a registry row and its iptv-org ID: the channels and editions
    of the followed countries, the main channel of each edition, and the channels they were replaced by (the first
    load, before step 2, also took every iptv-org channel that had a logo here). Rows already mapped are left as they are: running it again only adds what is missing."""
    wanted: dict[str, dict] = {}
    for cc in countries:
        for u in iptv_units(iptv, cc):
            wanted[u['id']] = u
    for u in list(wanted.values()):                            # the main channel of every edition
        if u['feed'] and u['channel'] not in wanted:
            wanted[u['channel']] = {'id': u['channel'], 'channel': u['channel'], 'feed': ''}
    for u in list(wanted.values()):                            # the channel a closed one was replaced by
        target = (iptv.channels.get(u['channel']) or {}).get('replaced_by') or ''
        target = target.split('@')[0]
        if target in iptv.channels and target not in wanted:
            wanted[target] = {'id': target, 'channel': target, 'feed': ''}
    stats = {'channels': 0, 'editions': 0, 'already': 0}
    for logo_id in sorted(wanted, key=lambda i: ('@' in i, i.lower())):   # channels first: editions need them
        u = wanted[logo_id]
        if by_logo_id(db, logo_id) is not None:
            stats['already'] += 1
            continue
        rec = iptv.channels.get(u['channel']) or {}
        country = _iptv_country(rec, logo_id)
        if u['feed']:
            parent = by_logo_id(db, u['channel'])
            feed = iptv.feeds.get((u['channel'], u['feed'])) or {}
            name = u.get('name') or feed.get('name') or u['feed']
            base = rec.get('name') or u['channel'].split('.')[0]
            if not name.lower().startswith(base.lower()):
                name = f'{base} {name}'
            c = add_channel(db, name, edition_country(feed, parent.country),
                            status=parent.status if parent.status == 'closed' else 'active',
                            parent=parent.id, website=rec.get('website') or '', fallback=logo_id.replace('@', ' '))
            map_id(db, c, 'iptv-org-feed', logo_id, 'import')
            stats['editions'] += 1
        else:
            status = 'closed' if rec.get('closed') or rec.get('replaced_by') else 'active'
            c = add_channel(db, rec.get('name') or logo_id.split('.')[0], country, aliases=rec.get('alt_names') or (),
                            status=status, website=rec.get('website') or '', fallback=logo_id.split('.')[0])
            map_id(db, c, 'iptv-org', logo_id, 'import')
            stats['channels'] += 1
    for logo_id, u in wanted.items():                          # replaced channels: merged into their successor
        target = ((iptv.channels.get(u['channel']) or {}).get('replaced_by') or '').split('@')[0]
        c, new = by_logo_id(db, logo_id), by_logo_id(db, target) if target else None
        if not u['feed'] and c is not None and new is not None and c.status != 'merged' and new.id != c.id:
            c.status, c.parent = 'merged', new.id
    stats['country changed'] = refresh_editions(db, iptv)
    return stats


def check(db: Database, warnings: list[str] | None = None) -> list[str]:
    """Errors of data/channels.csv and data/external_ids.csv, and logos or aliases of no registry channel."""
    errors = []
    warnings = [] if warnings is None else warnings
    slugs: dict[str, str] = {}
    for c in db.channels.values():
        where = f'data/channels.csv {c.id}'
        if not ID_RE.match(c.id):
            errors.append(f'{where}: malformed ID (ch_ + 10 characters of {ALPHABET})')
        if not SLUG_RE.match(c.slug):
            errors.append(f'{where}: malformed slug `{c.slug}`')
        elif c.slug in slugs:
            errors.append(f'{where}: slug `{c.slug}` already used by {slugs[c.slug]}')
        slugs[c.slug] = c.id
        if not c.name.strip():
            errors.append(f'{where}: name missing')
        if not re.match(r'^[a-z]{2}$', c.country) or not c.slug.endswith(f'.{c.country}'):
            errors.append(f'{where}: country `{c.country}` must be a two-letter code ending the slug')
        if c.status not in STATUSES:
            errors.append(f'{where}: unknown status `{c.status}` ({", ".join(STATUSES)})')
        if c.parent and (c.parent == c.id or c.parent not in db.channels):
            errors.append(f'{where}: parent `{c.parent}` is not another channel of the registry')
        if c.status == 'merged' and not c.parent:
            errors.append(f'{where}: a merged channel needs the channel it became (parent)')
        if not DATE_RE.match(c.added) or (c.updated and not DATE_RE.match(c.updated)):
            errors.append(f'{where}: dates must be YYYY-MM-DD')
    for x in db.external_ids.values():
        where = f'data/external_ids.csv {x.source}:{x.external_id}'
        if x.channel_id not in db.channels:
            errors.append(f'{where}: unknown channel `{x.channel_id}`')
        if x.source not in SOURCES:
            errors.append(f'{where}: unknown source ({", ".join(SOURCES)}; guide IDs are not stored)')
        elif not SOURCES[x.source].match(x.external_id):
            errors.append(f'{where}: malformed ID')
        if x.method not in METHODS:
            errors.append(f'{where}: unknown method `{x.method}` ({", ".join(METHODS)})')
    for lg in db.logos.values():
        if lg.channel not in db.channels:
            errors.append(f'data/logos.csv {lg.stem}: not a channel of the registry (data/channels.csv)')
    for a in db.aliases.values():
        if a.channel not in db.channels:
            errors.append(f'data/aliases.csv {a.source}:{a.epg_id}: not a channel of the registry')
    return errors
