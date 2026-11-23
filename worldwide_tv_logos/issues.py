"""Requests submitted through the issue forms (.github/ISSUE_TEMPLATE/): parsing, validation, application."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from worldwide_tv_logos import image, net, ops
from worldwide_tv_logos.db import Database

KINDS = ('logos:add', 'logos:edit', 'logos:remove', 'logos:request', 'aliases:add', 'aliases:remove')
# form label -> field name (labels of the issue forms, without « (optional) »)
FIELDS = {'channel id': 'channel', 'feed id': 'feed', 'logo url': 'url', 'epg id': 'epg_id',
          'epg source': 'source', 'reason': 'reason', 'notes': 'notes'}
EMPTY = {'', '_no response_', '~', 'none', '-'}


@dataclass
class Request:
    number: int
    kind: str
    values: dict[str, str] = field(default_factory=dict)
    waiting: str = ''           # set by validate(): the channel is not in our registry yet

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


def ref(req: Request) -> str:
    """The channel asked: our ID, a slug or an iptv-org ID; an older form gave the iptv-org feed apart."""
    channel, feed = req.get('channel'), req.get('feed')
    return channel + (f'@{feed}' if feed and '@' not in channel else '')


def _has_logo(db: Database, cid: str) -> bool:
    return (cid, '') in db.logos


def validate(req: Request, db: Database, downloader=None) -> list[str]:
    """Problems that prevent the request from being applied (empty list: valid). Downloads the image to check it."""
    if not req.get('channel'):
        return ['Channel ID is required']
    label = ref(req)
    try:
        try:
            cid = ops.channel_of(db, label).id
        except ops.NotRegistered as exc:
            if req.kind not in ('logos:add', 'logos:request'):
                raise
            req.waiting = str(exc)                    # checked again every night until the registry has it
            cid = ''
        if req.kind in ('logos:add', 'logos:edit'):
            if req.kind == 'logos:add' and cid and _has_logo(db, cid):
                return [f'`{label}` already has a logo: use the logos/edit form to replace it']
            if req.kind == 'logos:edit' and not _has_logo(db, cid):
                return [f'no logo for `{label}` yet: use the logos/add form']
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
                return [f'no logo for `{label}` in this repository']
        elif req.kind == 'logos:request':
            if cid and _has_logo(db, cid):
                return [f'`{label}` already has a logo']
        elif req.kind in ('aliases:add', 'aliases:remove'):
            epg_id, source = req.get('epg_id'), req.get('source')
            if not (epg_id and source):
                return ['EPG ID and EPG source are required']
            known = db.aliases.get((source, epg_id))
            if req.kind == 'aliases:remove' and known is None:
                return [f'no alias `{source}:{epg_id}` in this repository']
            if req.kind == 'aliases:add' and not _has_logo(db, cid):
                return [f'no logo for `{label}` yet: an alias needs a logo to point to']
    except ops.RequestError as exc:
        return [str(exc)]
    return []


def apply(req: Request, db: Database, downloader=None) -> list[str]:
    label = ref(req)
    if req.kind in ('logos:add', 'logos:edit'):
        cid = ops.channel_of(db, label).id               # before downloading: a missing channel waits
        if req.kind == 'logos:add' and _has_logo(db, cid):
            raise ops.RequestError(f'`{label}` already has a logo (added meanwhile): '
                                   'use the logos/edit form to replace it')
        if req.kind == 'logos:edit' and not _has_logo(db, cid):
            raise ops.RequestError(f'no logo for `{label}` any more: use the logos/add form')
        try:
            data = (downloader or net.download)(req.get('url'))
        except net.DownloadError as exc:
            raise ops.RequestError(f'the logo could not be downloaded: {exc}') from None
        return ops.set_logo(db, cid, data, f'issue #{req.number}')
    if req.kind == 'logos:remove':
        return ops.remove_logo(db, ops.channel_of(db, label).id)
    if req.kind == 'aliases:add':
        return ops.set_alias(db, req.get('epg_id'), req.get('source'), ops.channel_of(db, label).id)
    if req.kind == 'aliases:remove':
        return ops.remove_alias(db, req.get('epg_id'), req.get('source'))
    raise ops.RequestError('a logo request is fulfilled by a logos/add request with an image, not by approval')
