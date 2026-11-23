"""Requests submitted through the issue forms (.github/ISSUE_TEMPLATE/): parsing, validation, application."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from worldwide_tv_logos import image, net, ops, registry
from worldwide_tv_logos.db import Database

KINDS = ('logos:add', 'logos:edit', 'logos:remove', 'logos:request', 'aliases:add', 'aliases:remove',
         'channels:add', 'channels:edit')
# form label -> field name (labels of the issue forms, without « (optional) »)
FIELDS = {'channel id': 'channel', 'feed id': 'feed', 'logo url': 'url', 'epg id': 'epg_id',
          'epg source': 'source', 'reason': 'reason', 'notes': 'notes', 'channel name': 'name', 'country': 'country',
          'website': 'website', 'other names': 'aliases', 'main channel': 'parent', 'status': 'status',
          'iptv-org id': 'iptv', 'wikidata id': 'wikidata'}
EMPTY = {'', '_no response_', '~', 'none', '-'}


@dataclass
class Request:
    number: int
    kind: str
    values: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        return self.values.get(name, '')


def parse_body(body: str) -> dict[str, str]:
    """GitHub issue form body (`### Label` followed by the answer) -> {field: value}."""
    out: dict[str, str] = {}
    for block in re.split(r'^###\s+', body or '', flags=re.MULTILINE)[1:]:
        label, _, value = block.partition('\n')
        name = FIELDS.get(re.sub(r'\s*\(optional\)\s*$', '', label.strip(), flags=re.IGNORECASE).lower())
        value = value.strip()
        if name:
            out[name] = '' if value.lower() in EMPTY else value
    return out


def parse(number: int, labels: list[str], body: str) -> Request:
    kinds = [k for k in labels if k in KINDS]
    if len(kinds) != 1:
        raise ops.RequestError(f'one of the labels {", ".join(KINDS)} is required')
    return Request(number, kinds[0], parse_body(body))


def channel_of(req: Request, db: Database):
    """The channel of a request: our channel ID only (`ch_` and 10 characters, filled in by the buttons of the
    website), never a slug (it changes on a rename) nor another project's ID. A channel merged into another one is
    refused with a pointer to the current one."""
    value = req.get('channel').strip().lower()
    if not registry.ID_RE.match(value):
        raise ops.RequestError(f'`{req.get("channel")}` is not a channel ID: give our ID (`ch_` and 10 characters), '
                               'shown on the channel\'s page of the website (its buttons fill it in)')
    c = db.channels.get(value)
    if c is None:
        raise ops.RequestError(f'no channel `{value}` here: check the ID on the website; a channel not listed yet is '
                               'added with the channels/add form')
    if c.status == 'merged' and c.parent in db.channels:
        current = db.channels[c.parent]
        raise ops.RequestError(f'`{value}` ({c.name}) is now `{current.id}` ({current.name}): use that channel')
    return c


def _has_logo(db: Database, cid: str) -> bool:
    return (cid, '') in db.logos


def _channel_problems(req: Request, db: Database, current=None) -> list[str]:
    """Problems of a channels:add or channels:edit request (`current`: the channel edited)."""
    out = []
    name, country = req.get('name'), req.get('country').lower()
    cc = current.country if current else country
    if current is None and not re.match(r'^[a-z]{2}$', country):
        out.append('Country must be a two-letter code (e.g. `fr`, `uk` for the United Kingdom)')
    if name or current is None:
        key = registry.slug_base(name)
        if registry.ID_RE.match(name.strip().lower()):
            out.append('Channel name is the name of the channel: its ID is made here, automatically')
        if not key:
            out.append('Channel name is required, with at least one Latin letter or digit')
        same = [c for c in db.channels.values() if c.country == cc and (current is None or c.id != current.id)
                and key in {registry.slug_base(n) for n in [c.name, *c.alias_list]}]
        if key and same:
            out.append(f'`{same[0].id}` ({same[0].name}) is already this channel here: use the channels/edit form')
    website = req.get('website')
    if website and not re.match(r'^https?://[^\s/]+\.[^\s]+$', website):
        out.append('Website must be a web address (`https://...`)')
    if req.get('parent'):
        parent = db.channels.get(req.get('parent').strip().lower())
        if parent is None:
            out.append(f'Main channel `{req.get("parent")}` is not a channel ID here (`ch_` and 10 characters, shown '
                       "on the channel's page of the website)")
        elif current is not None and parent.id == current.id:
            out.append('A channel cannot be its own main channel')
        elif parent.status == 'merged':
            out.append(f'Main channel `{parent.id}` ({parent.name}) was merged into `{parent.parent}`: use that one')
    if req.get('status') and req.get('status') not in ('active', 'closed'):
        out.append('Status must be `active` or `closed`')
    for kind, sources in (('iptv', ('iptv-org', 'iptv-org-feed')), ('wikidata', ('wikidata',))):
        value = req.get(kind)
        if not value:
            continue
        source = next((x for x in sources if registry.SOURCES[x].match(value)), None)
        if source is None:
            out.append(f'`{value}` is not a valid {"iptv-org" if kind == "iptv" else "Wikidata"} ID')
            continue
        other = registry.by_external(db, source, value)
        if other is not None and (current is None or other.id != current.id):
            out.append(f'`{value}` is already the channel `{other.id}` ({other.name}) here')
    if current is not None and not any(req.get(f) for f in ('name', 'website', 'aliases', 'parent', 'status', 'iptv',
                                                            'wikidata')):
        out.append('Nothing to change: fill in at least one field')
    return out


def _apply_channel(req: Request, db: Database) -> list[str]:
    current = channel_of(req, db) if req.kind == 'channels:edit' else None
    problems = _channel_problems(req, db, current)
    if problems:
        raise ops.RequestError(problems[0])
    parent = req.get('parent').strip().lower() if req.get('parent') else None
    aliases = [a.strip() for a in req.get('aliases').split(';') if a.strip()]
    if current is None:
        c = registry.add_channel(db, req.get('name'), req.get('country'), aliases=aliases,
                                 website=req.get('website'), parent=parent or '')
        out = [f'added channel {c.id} ({c.slug})']
    else:
        c, out = current, []
        if req.get('name'):
            c.name = req.get('name')
            c.slug = registry.make_slug(c.name, c.country, {x.slug for x in db.channels.values() if x.id != c.id})
            out.append(f'renamed {c.name} ({c.slug})')
        if req.get('aliases'):
            c.aliases = ';'.join(aliases)
            out.append('other names changed')
        if req.get('website'):
            c.website = req.get('website')
            out.append('website changed')
        if parent is not None:
            c.parent = parent
            out.append(f'main channel {parent}')
        if req.get('status'):
            c.status = req.get('status')
            out.append(f'status {c.status}')
        c.updated = registry.today()                      # edited here: iptv-org changes no longer overwrite it
    for kind in ('iptv', 'wikidata'):
        value = req.get(kind)
        if value:
            source = 'wikidata' if kind == 'wikidata' else ('iptv-org-feed' if '@' in value else 'iptv-org')
            registry.map_id(db, c, source, value, 'review')
            out.append(f'{source} ID {value}')
    return [f'{c.id}: ' + ', '.join(out)]


def validate(req: Request, db: Database, downloader=None) -> list[str]:
    """Problems that prevent the request from being applied (empty list: valid). Downloads the image to check it."""
    if req.kind == 'channels:add':
        return _channel_problems(req, db)
    if req.kind == 'channels:edit':
        try:
            return _channel_problems(req, db, channel_of(req, db))
        except ops.RequestError as exc:
            return [str(exc)]
    if not req.get('channel'):
        return ['Channel ID is required']
    try:
        c = channel_of(req, db)
        cid, label = c.id, f'`{c.id}` ({c.name})'
        if req.kind in ('logos:add', 'logos:edit'):
            if req.kind == 'logos:add' and _has_logo(db, cid):
                return [f'{label} already has a logo: use the logos/edit form to replace it']
            if req.kind == 'logos:edit' and not _has_logo(db, cid):
                return [f'no logo for {label} yet: use the logos/add form']
            url = req.get('url')
            if not url:
                return ['Logo URL is required']
            try:
                image.prepare((downloader or net.download)(url))
            except net.DownloadError as exc:
                return [f'the logo could not be downloaded: {exc}']
            except image.ImageError as exc:
                return [f'the logo does not meet the rules: {exc}']
        elif req.kind == 'logos:remove':
            if not _has_logo(db, cid):
                return [f'no logo for {label} in this repository']
        elif req.kind == 'logos:request':
            if _has_logo(db, cid):
                return [f'{label} already has a logo']
        elif req.kind in ('aliases:add', 'aliases:remove'):
            epg_id, source = req.get('epg_id'), req.get('source')
            if not (epg_id and source):
                return ['EPG ID and EPG source are required']
            known = db.aliases.get((source, epg_id))
            if req.kind == 'aliases:remove' and (known is None or known.channel != cid):
                return [f'no alias `{source}:{epg_id}` for {label} in this repository']
            if req.kind == 'aliases:add' and known is not None and known.channel != cid:
                return [f'`{source}:{epg_id}` is already the alias of `{known.channel}`: remove it there first']
            if req.kind == 'aliases:add' and not _has_logo(db, cid):
                return [f'no logo for {label} yet: an alias needs a logo to point to']
    except ops.RequestError as exc:
        return [str(exc)]
    return []


def apply(req: Request, db: Database, downloader=None) -> list[str]:
    if req.kind in ('channels:add', 'channels:edit'):
        return _apply_channel(req, db)
    c = channel_of(req, db)
    cid, label = c.id, f'`{c.id}` ({c.name})'
    if req.kind in ('logos:add', 'logos:edit'):
        if req.kind == 'logos:add' and _has_logo(db, cid):
            raise ops.RequestError(f'{label} already has a logo (added meanwhile): '
                                   'use the logos/edit form to replace it')
        if req.kind == 'logos:edit' and not _has_logo(db, cid):
            raise ops.RequestError(f'no logo for {label} any more: use the logos/add form')
        try:
            data = (downloader or net.download)(req.get('url'))
        except net.DownloadError as exc:
            raise ops.RequestError(f'the logo could not be downloaded: {exc}') from None
        return ops.set_logo(db, cid, data, f'issue #{req.number}')
    if req.kind == 'logos:remove':
        return ops.remove_logo(db, cid)
    if req.kind == 'aliases:add':
        return ops.set_alias(db, req.get('epg_id'), req.get('source'), cid)
    if req.kind == 'aliases:remove':
        known = db.aliases.get((req.get('source'), req.get('epg_id')))
        if known is None or known.channel != cid:
            raise ops.RequestError(f'no alias `{req.get("source")}:{req.get("epg_id")}` for {label} any more')
        return ops.remove_alias(db, req.get('epg_id'), req.get('source'))
    raise ops.RequestError('a logo request is fulfilled by a logos/add request with an image, not by approval')
