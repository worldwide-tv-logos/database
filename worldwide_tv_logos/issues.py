"""Requests submitted through the issue forms (.github/ISSUE_TEMPLATE/): parsing, validation, application."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from worldwide_tv_logos import image, net, ops
from worldwide_tv_logos.db import Database
from worldwide_tv_logos.iptvorg import IptvOrg

KINDS = ('logos:add', 'logos:remove', 'aliases:add')
# form label -> field name (labels of the issue forms, without « (optional) »)
FIELDS = {'channel id': 'channel', 'feed id': 'feed', 'logo url': 'url', 'epg id': 'epg_id',
          'epg source': 'source', 'reason': 'reason', 'notes': 'notes'}
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


def validate(req: Request, db: Database, iptv: IptvOrg | None, downloader=net.download) -> list[str]:
    """Problems that prevent the request from being applied (empty list: valid). Downloads the image to check it."""
    channel, feed = req.get('channel'), req.get('feed')
    if not channel:
        return ['Channel ID is required']
    try:
        ops.check_ids(channel, feed, iptv)
        if req.kind == 'logos:add':
            url = req.get('url')
            if not url:
                return ['Logo URL is required']
            try:
                image.prepare(downloader(url))
            except net.DownloadError as exc:
                return [f'the logo could not be downloaded: {exc}']
            except image.ImageError as exc:
                return [f'the logo does not meet the rules: {exc}']
        elif req.kind == 'logos:remove':
            if not any(k[:2] == (channel, feed) for k in db.logos):
                return [f'no logo for `{channel}{"@" + feed if feed else ""}` in this repository']
        elif req.kind == 'aliases:add' and not (req.get('epg_id') and req.get('source')):
            return ['EPG ID and EPG source are required']
    except ops.RequestError as exc:
        return [str(exc)]
    return []


def apply(req: Request, db: Database, iptv: IptvOrg | None, downloader=net.download) -> list[str]:
    channel, feed = req.get('channel'), req.get('feed')
    if req.kind == 'logos:add':
        try:
            data = downloader(req.get('url'))
        except net.DownloadError as exc:
            raise ops.RequestError(f'the logo could not be downloaded: {exc}') from None
        return ops.set_logo(db, channel, feed, data, f'issue #{req.number}', iptv)
    if req.kind == 'logos:remove':
        return ops.remove_logo(db, channel, feed)
    return ops.set_alias(db, req.get('epg_id'), req.get('source'), channel, feed, iptv)
