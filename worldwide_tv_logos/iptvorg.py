"""iptv-org channels and feeds (https://iptv-org.github.io/api/), cached one day in .cache/iptvorg/."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from worldwide_tv_logos.net import USER_AGENT

API = 'https://iptv-org.github.io/api/'
MAX_AGE = 86400


@dataclass
class IptvOrg:
    channels: dict[str, dict]                 # id -> channel record
    feeds: dict[tuple[str, str], dict]        # (channel, feed) -> feed record

    def channel_error(self, channel: str, feed: str = '') -> str | None:
        if channel not in self.channels:
            return f'channel `{channel}` does not exist in iptv-org yet'
        if feed and (channel, feed) not in self.feeds:
            known = sorted(f for c, f in self.feeds if c == channel)
            return f'feed `{feed}` of `{channel}` does not exist in iptv-org yet (known: {", ".join(known) or "none"})'
        return None

    def status_warning(self, channel: str, feed: str = '') -> str | None:
        """A logo whose channel changed in iptv-org since it was added: removed, closed or replaced."""
        if channel not in self.channels:
            return f'`{channel}` is no longer in iptv-org: rename the logo if the channel got a new ID, else remove it'
        if feed and (channel, feed) not in self.feeds:
            return f'feed `{channel}@{feed}` is no longer in iptv-org'
        c = self.channels[channel]
        if c.get('replaced_by'):
            return f'`{channel}` is replaced by `{c["replaced_by"]}` in iptv-org: move the logo to the new ID'
        if c.get('closed'):
            return f'`{channel}` closed on {c["closed"]} according to iptv-org'
        return None

    def country_channels(self, cc: str) -> list[dict]:
        return [c for c in self.channels.values() if c.get('country', '').lower() == cc and not c.get('closed')
                and not c.get('is_nsfw')]


def _get(name: str, cache: Path, opener) -> list[dict]:
    path = cache / name
    if path.is_file() and time.time() - path.stat().st_mtime < MAX_AGE:
        return json.loads(path.read_text(encoding='utf-8'))
    import urllib.request
    req = urllib.request.Request(API + name, headers={'User-Agent': USER_AGENT})
    with (opener or urllib.request.urlopen)(req, timeout=120) as resp:
        data = resp.read()
    cache.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return json.loads(data)


def load(root: Path, opener=None) -> IptvOrg:
    cache = Path(root) / '.cache' / 'iptvorg'
    channels = {c['id']: c for c in _get('channels.json', cache, opener)}
    feeds = {(f['channel'], f['id']): f for f in _get('feeds.json', cache, opener)}
    return IptvOrg(channels, feeds)


def load_countries(root: Path, opener=None) -> list[dict]:
    """[{name, code, flag, languages}] from the iptv-org API (cached one day)."""
    return _get('countries.json', Path(root) / '.cache' / 'iptvorg', opener)


def load_logos(root: Path, opener=None) -> list[dict]:
    """iptv-org's logos.json: [{channel, feed, in_use, tags, width, height, format, url}] (cached one day)."""
    return _get('logos.json', Path(root) / '.cache' / 'iptvorg', opener)
