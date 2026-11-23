"""Daily watch of iptv-org (`logos watch-iptvorg`, roadmap step 3): what changed there is applied to our registry,
before `channels-init` registers the new channels.

- renamed (`replaced_by`): the new iptv-org ID is mapped to the SAME channel (`ch_` ID and logo kept); the old one
  stays as `iptv-org-former`, so that it is never registered again. Its editions follow (`X@Alsace` -> `Y@Alsace`).
  When the new ID was already registered as another channel with nothing of its own (no logo, no alias, never
  edited here), that channel is absorbed; otherwise that channel is the current one and ours is merged into it
  (status `merged`, both logos kept).
- closed: the channel is marked closed (its logo kept); reopened when iptv-org reopens it.
- name, other names, website changed at iptv-org: taken, unless the channel was edited here (`updated` set).
- removed from iptv-org without a successor: listed only, never removed here.
- open iptv-org issues (channels to add, edit, remove) of the followed countries: listed as coming, never applied.
"""
from __future__ import annotations

import datetime
import re

from worldwide_tv_logos import registry
from worldwide_tv_logos.db import Channel, Database, ExternalId

FORMER = {'iptv-org': 'iptv-org-former', 'iptv-org-feed': 'iptv-org-feed-former'}
ISSUE_LABELS = ('channels:add', 'channels:edit', 'channels:remove')


def _successor(iptv, ident: str) -> str:
    """The current iptv-org ID of a channel, following `replaced_by` (a chain of renames); '' when removed."""
    seen = set()
    while ident in iptv.channels and ident not in seen:
        seen.add(ident)
        nxt = (iptv.channels[ident].get('replaced_by') or '').split('@')[0]
        if not nxt or nxt not in iptv.channels:
            return ident
        ident = nxt
    return ident if ident in iptv.channels else ''


def _has_own(db: Database, cid: str) -> bool:
    """A channel with something of its own: a logo, a guide alias, an edit made here, a Wikidata ID."""
    c = db.channels[cid]
    return ((cid, '') in db.logos or any(a.channel == cid for a in db.aliases.values()) or bool(c.updated)
            or any(x.channel_id == cid and x.source == 'wikidata' for x in db.external_ids.values()))


def _drop(db: Database, cid: str) -> None:
    del db.channels[cid]
    for key in [k for k, x in db.external_ids.items() if x.channel_id == cid]:
        del db.external_ids[key]
    db.__dict__.pop('_ids_cache', None)


def _move_id(db: Database, c: Channel, source: str, old: str, new: str) -> None:
    """`old` becomes a former ID of `c`, `new` its current one."""
    x = db.external_ids.pop((source, old))
    db.external_ids[(FORMER[source], old)] = ExternalId(c.id, FORMER[source], old, x.method, x.added)
    db.external_ids[(source, new)] = ExternalId(c.id, source, new, 'match', registry.today())
    db.__dict__.pop('_ids_cache', None)


def _take(db: Database, keep: Channel, source: str, new: str, lines: list[str]) -> bool:
    """Make `new` free for `keep`: absorbed when another channel holds it with nothing of its own. When that channel
    has a logo or edits of its own, it is the current one: `keep` is merged into it (both keep their logo)."""
    other = registry.by_external(db, source, new)
    if other is None or other.id == keep.id:
        return True
    if _has_own(db, other.id):
        if (keep.status, keep.parent) != ('merged', other.id):
            keep.status, keep.parent = 'merged', other.id
            lines.append(f'- `{keep.id}` {keep.name}: replaced by `{new}` at iptv-org, already our channel '
                         f'`{other.id}` ({other.name}): merged into it, each keeps its logo')
        return False
    for e in [e for e in db.channels.values() if e.parent == other.id]:
        e.parent = keep.id                                   # its editions now belong to the channel kept
    _drop(db, other.id)
    return True


def _refresh(c: Channel, rec: dict, db: Database) -> bool:
    """Name, other names and website of iptv-org, unless the channel was edited here."""
    if c.updated:
        return False
    name = rec.get('name') or c.name
    aliases = ';'.join(a for a in rec.get('alt_names') or () if a and a != name)
    website = rec.get('website') or ''
    if (name, aliases, website) == (c.name, c.aliases, c.website):
        return False
    if name != c.name:
        c.slug = registry.make_slug(name, c.country, {x.slug for x in db.channels.values() if x.id != c.id},
                                    fallback=c.slug.rsplit('.', 1)[0])
    c.name, c.aliases, c.website = name, aliases, website
    return True


def watch(db: Database, iptv) -> dict:
    """Apply iptv-org's changes to the registry. Returns {renamed, absorbed, closed, reopened, refreshed, removed,
    decisions: [...], lines: [...]}."""
    out = {'renamed': 0, 'closed': 0, 'reopened': 0, 'refreshed': 0, 'removed': 0, 'decisions': [], 'lines': []}
    for x in [x for x in db.external_ids.values() if x.source == 'iptv-org']:
        c = db.channels.get(x.channel_id)
        if c is None:
            continue
        current = _successor(iptv, x.external_id)
        if not current:
            if c.status != 'closed':
                out['removed'] += 1
                out['lines'].append(f'- `{c.id}` {c.name}: `{x.external_id}` is no longer in iptv-org')
            continue
        if current != x.external_id:
            if not _take(db, c, 'iptv-org', current, out['lines']):
                continue
            _move_id(db, c, 'iptv-org', x.external_id, current)
            for e in [e for e in db.channels.values() if e.parent == c.id]:    # its editions follow
                old = registry.iptv_id(db, e.id)
                feed = old.partition('@')[2]
                new = f'{current}@{feed}'
                if old and feed and (current, feed) in iptv.feeds and _take(db, e, 'iptv-org-feed', new, out['lines']):
                    _move_id(db, e, 'iptv-org-feed', old, new)
            out['renamed'] += 1
            out['lines'].append(f'- `{c.id}` {c.name}: renamed `{x.external_id}` -> `{current}` at iptv-org, '
                                'same channel here')
            if c.status == 'merged':                         # merged by the first load: the rename decides now
                c.status, c.parent = 'active', ''
        rec = iptv.channels[current]
        closed = bool(rec.get('closed'))
        if not c.updated and closed and c.status == 'active':
            c.status = 'closed'
            out['closed'] += 1
            out['lines'].append(f'- `{c.id}` {c.name}: closed on {rec["closed"]} at iptv-org (logo kept)')
        elif not c.updated and not closed and c.status == 'closed':
            c.status = 'active'
            out['reopened'] += 1
            out['lines'].append(f'- `{c.id}` {c.name}: open again at iptv-org')
        if _refresh(c, rec, db):
            out['refreshed'] += 1
    return out


def renamed_logos(db: Database, days: int = 7) -> list[str]:
    """Channels with a logo renamed at iptv-org in the last `days` days (listed once by the weekly `changes` issue):
    a rename often comes with a new logo, to be checked."""
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    formers = {x.channel_id: x.external_id for x in db.external_ids.values() if x.source == 'iptv-org-former'}
    out = []
    for x in sorted(db.external_ids.values(), key=lambda x: x.external_id):
        if x.source == 'iptv-org' and x.method == 'match' and x.added >= since and x.channel_id in formers                 and (x.channel_id, '') in db.logos:
            out.append(f'`{x.channel_id}` ({db.channels[x.channel_id].name}): renamed `{formers[x.channel_id]}` -> '
                       f'`{x.external_id}` at iptv-org on {x.added}: check that its logo is still the current one')
    return out


def _section(body: str, label: str) -> str:
    m = re.search(rf'^###\s+{re.escape(label)}[^\n]*\n+(.*?)(?=^###|\Z)', body or '', re.MULTILINE | re.DOTALL)
    value = m.group(1).strip() if m else ''
    return '' if value.lower() in ('', '_no response_') else value


def coming(issues: list[dict], countries) -> list[str]:
    """Open iptv-org requests about channels of the followed countries: [label] title (link)."""
    out = []
    for i in issues:
        labels = {x['name'] if isinstance(x, dict) else x for x in i.get('labels', [])}
        kind = next((k for k in ISSUE_LABELS if k in labels), None)
        if kind is None:
            continue
        cc = _section(i.get('body', ''), 'Country').lower()
        if not cc:
            ident = _section(i.get('body', ''), 'Channel ID')
            cc = ident.rsplit('.', 1)[-1].lower() if '.' in ident else ''
        if cc in countries:
            out.append(f'- {kind.split(":")[1]} ({cc}): [{i["title"]}]({i.get("html_url") or i.get("url", "")})')
    return out
