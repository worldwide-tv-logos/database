"""iptv-epg (iptv-epg.org): the logos of the channels of its TV guide of the country, found for a channel or an
edition by its guide alias (data/aliases.csv), by the same ID, or by name. One file per country, cached one day."""
from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path

from worldwide_tv_logos import net

EPG_URL = 'https://iptv-epg.org/files/epg-{cc}.xml.gz'
EPG_MAX_AGE = 86400
EPG_MAX_SIZE = 40_000_000
EPG_PREFIX_RE = re.compile(r'^[A-Z]{2,3}\s*-\s*')


def parse_iptv_epg(data: bytes) -> list[dict]:
    """Channels of an iptv-epg guide (XMLTV, gzip): [{id, names, icon}] (icon: '' when the guide has none). Only the
    channel list at the top of the file is read, not the programmes."""
    import gzip
    import xml.etree.ElementTree as ET
    out = []
    stream = gzip.GzipFile(fileobj=io.BytesIO(data)) if data[:2] == b'\x1f\x8b' else io.BytesIO(data)
    for _, el in ET.iterparse(stream, events=('end',)):
        if el.tag == 'programme':
            break
        if el.tag != 'channel':
            continue
        names = [EPG_PREFIX_RE.sub('', (d.text or '').strip()) for d in el.findall('display-name')]
        icon = el.find('icon')
        src = icon.get('src', '') if icon is not None else ''
        if el.get('id'):
            out.append({'id': el.get('id'), 'names': [n for n in names if n],
                        'icon': src if src.startswith('https://') else ''})
        el.clear()
    return out


def load_iptv_epg(root: Path, cc: str, downloader=None) -> list[dict]:
    """Channels of the iptv-epg guide of a country (none when there is no guide for it), cached one day."""
    path = Path(root) / '.cache' / 'iptv-epg' / f'{cc}.json'
    if path.is_file() and time.time() - path.stat().st_mtime < EPG_MAX_AGE:
        return json.loads(path.read_text(encoding='utf-8'))
    try:
        data = (downloader or net.download)(EPG_URL.format(cc=cc), accept='application/gzip,*/*',
                                            max_size=EPG_MAX_SIZE)
        channels = parse_iptv_epg(data)
    except net.DownloadError as exc:
        if 'HTTP 404' not in str(exc):
            raise
        channels = []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(channels, ensure_ascii=False), encoding='utf-8')
    return channels


class EpgIndex:
    """iptv-epg logos of a country, found for a channel or an edition by its guide alias (data/aliases.csv), by the
    same ID, or by name."""

    def __init__(self, channels: list[dict], aliases: list, key):
        self.key = key
        self.by_id = {c['id']: c for c in channels}
        self.by_key: dict[str, list[dict]] = {}
        for c in channels:
            for k in {key(c['id'].rsplit('.', 1)[0]), *(key(n) for n in c['names'])} - {''}:
                self.by_key.setdefault(k, []).append(c)
        self.aliases = {(a.channel, a.feed): a.epg_id for a in aliases if a.source.startswith('iptv-epg')}

    def logos(self, unit: dict, keys: set[str]) -> list[str]:
        found = []
        epg_id = self.aliases.get((unit.get('channel', unit['id']), unit.get('feed', '')))
        for c in ([self.by_id[epg_id]] if epg_id in self.by_id else []) + \
                ([self.by_id[unit['id']]] if unit['id'] in self.by_id else []) + \
                [c for k in sorted(keys) for c in self.by_key.get(k, [])]:
            if c['icon'] and c['icon'] not in found:
                found.append(c['icon'])
        return found[:2]

    def sure(self, unit: dict, keys: set[str]) -> dict | None:
        """The guide channel of a channel or edition when there is no doubt: its guide alias, the same ID, or the
        only guide channel with one of its names; None otherwise (no match, or several)."""
        epg_id = self.aliases.get((unit.get('channel', unit['id']), unit.get('feed', '')))
        for i in (epg_id, unit['id']):
            if i in self.by_id:
                return self.by_id[i]
        found = {c['id'] for k in keys for c in self.by_key.get(k, [])}
        return self.by_id[found.pop()] if len(found) == 1 else None

    def match(self, unit: dict, keys: set[str]) -> str | None:
        """Guide ID of a channel or edition found by name, when exactly one channel of the guide has one of its
        names and that ID differs from the iptv-org ID; None otherwise."""
        found = {c['id'] for k in keys for c in self.by_key.get(k, [])}
        if len(found) != 1:
            return None
        epg_id = found.pop()
        return None if epg_id == unit['id'] else epg_id


def find(unit: dict, ctx) -> list[str]:
    from worldwide_tv_logos.sources.names import channel_keys
    return ctx.epg.logos(unit, channel_keys(unit)) if ctx.epg else []
