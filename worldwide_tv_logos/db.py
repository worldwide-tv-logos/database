"""The database: data/logos.csv, data/aliases.csv, data/countries.csv, and the files they describe; our channel
registry, data/channels.csv and data/external_ids.csv (see registry.py).

Naming is derived from our channel ID (`ch_` + 10 characters, never changed) and never chosen by hand:

    logos/<id>[.<variant>].png       the logo served
    sources/<id>.<ext>               the original it was built from

A path never changes: a channel renamed, or moved to another country, keeps its ID.
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(os.getenv('LOGOS_ROOT') or Path(__file__).resolve().parent.parent)
CHANNEL_RE = re.compile(r'^[A-Za-z0-9]+\.[a-z]{2}$')        # iptv-org channel id: Latin letters, digits, `.cc`
EPG_ID_RE = re.compile(r'^[^,"\s]+$')
VARIANTS = ('', 'white')                                     # '' : the logo itself; white : for dark backgrounds
RAW_BASE = 'https://raw.githubusercontent.com/worldwide-tv-logos/database/main/'
SITE_BASE = 'https://worldwide-tv-logos.github.io/database/'   # GitHub Pages (CDN): the address to use


@dataclass
class Logo:
    channel: str              # our channel ID (data/channels.csv)
    variant: str = ''
    width: int = 0
    height: int = 0
    origin: str = ''          # where the original comes from (URL, or `issue #N`)
    added: str = ''           # YYYY-MM-DD
    updated: str = ''         # YYYY-MM-DD, last replacement of the file

    @property
    def key(self) -> tuple[str, str]:
        return self.channel, self.variant

    @property
    def logo_id(self) -> str:
        return self.channel

    @property
    def stem(self) -> str:
        return self.channel + (f'.{self.variant}' if self.variant else '')

    @property
    def file(self) -> str:
        return f'logos/{self.stem}.png'

    @property
    def url(self) -> str:
        return SITE_BASE + self.file

    @property
    def raw_url(self) -> str:
        return RAW_BASE + self.file


@dataclass
class Alias:
    epg_id: str               # id of the channel in an EPG source (e.g. France3-Alsace.fr)
    source: str               # EPG source (e.g. iptv-epg-fr)
    channel: str              # our channel ID

    @property
    def key(self) -> tuple[str, str]:
        return self.source, self.epg_id


@dataclass
class Channel:
    """A channel of our registry (data/channels.csv): `id` never changes and is never reused (see registry.py)."""
    id: str                   # ch_ + 10 Crockford base32 characters
    slug: str                 # readable and unique (france-3-alsace.fr); may change on a rename, never a key
    name: str
    aliases: str = ''         # other names, separated by `;`
    country: str = ''         # two-letter code (iptv-org's: `uk` for the United Kingdom)
    status: str = 'active'    # active | closed | merged
    parent: str = ''          # edition (regional, timeshift): its main channel; merged: the channel it became
    website: str = ''
    added: str = ''           # YYYY-MM-DD
    updated: str = ''         # YYYY-MM-DD

    @property
    def key(self) -> str:
        return self.id

    @property
    def alias_list(self) -> list[str]:
        return [a.strip() for a in self.aliases.split(';') if a.strip()]


@dataclass
class ExternalId:
    """An ID another project gives to one of our channels (data/external_ids.csv): iptv-org and Wikidata only;
    guide IDs are never stored (they change on the guides' side)."""
    channel_id: str
    source: str               # iptv-org | iptv-org-feed | wikidata
    external_id: str
    method: str = ''          # import | match | review
    added: str = ''

    @property
    def key(self) -> tuple[str, str]:
        return self.source, self.external_id


def _read(path: Path, cls):
    if not path.exists():
        return []
    names = [f.name for f in fields(cls)]
    out = []
    with path.open(encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            values = {k: row.get(k, '') or '' for k in names}
            for f in fields(cls):
                if f.type == 'int':
                    values[f.name] = int(values[f.name] or 0)
            out.append(cls(**values))
    return out


def _write(path: Path, cls, rows) -> None:
    names = [f.name for f in fields(cls)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(names)
        for r in rows:
            w.writerow([getattr(r, n) for n in names])


def merge_rows(base: dict, upstream: dict, ours: dict) -> dict:
    """Three-way merge of index rows by key: a row our commit did not change (or delete) takes the upstream version,
    a row it changed takes ours. A line-by-line merge (merge=union) keeps both versions of a row changed upstream,
    and the older one could win."""
    out = {}
    for key in base.keys() | upstream.keys() | ours.keys():
        row = upstream.get(key) if ours.get(key) == base.get(key) else ours.get(key)
        if row is not None:
            out[key] = row
    return out


class Database:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root)
        self.logos: dict[tuple[str, str], Logo] = {}
        self.aliases: dict[tuple[str, str], Alias] = {}
        self.countries: dict[str, str] = {}
        self.channels: dict[str, Channel] = {}
        self.external_ids: dict[tuple[str, str], ExternalId] = {}

    @property
    def data_dir(self) -> Path:
        return self.root / 'data'

    def load(self) -> Database:
        self.logos = {r.key: r for r in _read(self.data_dir / 'logos.csv', Logo)}
        self.aliases = {r.key: r for r in _read(self.data_dir / 'aliases.csv', Alias)}
        self.channels = {r.key: r for r in _read(self.data_dir / 'channels.csv', Channel)}
        self.external_ids = {r.key: r for r in _read(self.data_dir / 'external_ids.csv', ExternalId)}
        path = self.data_dir / 'countries.csv'
        if path.exists():
            with path.open(encoding='utf-8', newline='') as fh:
                self.countries = {r['code']: r['name'] for r in csv.DictReader(fh)}
        return self

    def merge(self, base: Path, upstream: Path, ours: Path) -> None:
        """This database's rows replaced by the merge of `upstream` (main) and `ours` (our commit) against their
        common ancestor (`base`): repository roots holding a data/ folder. The working tree is not used as upstream:
        after a line-by-line merge it holds both versions of a row, and the older one may be read last."""
        b, u, o = (Database(p).load() for p in (base, upstream, ours))
        self.logos = merge_rows(b.logos, u.logos, o.logos)
        self.aliases = merge_rows(b.aliases, u.aliases, o.aliases)
        self.channels = merge_rows(b.channels, u.channels, o.channels)
        self.external_ids = merge_rows(b.external_ids, u.external_ids, o.external_ids)

    def save(self) -> None:
        _write(self.data_dir / 'logos.csv', Logo, sorted(self.logos.values(), key=lambda r: tuple(s.lower() for s in r.key)))
        _write(self.data_dir / 'aliases.csv', Alias, sorted(self.aliases.values(), key=lambda r: r.key))
        if self.channels or (self.data_dir / 'channels.csv').exists():
            _write(self.data_dir / 'channels.csv', Channel, sorted(self.channels.values(), key=lambda r: r.slug))
            _write(self.data_dir / 'external_ids.csv', ExternalId,
                   sorted(self.external_ids.values(), key=lambda r: (r.source, r.external_id.lower())))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def source_files(self, logo: Logo) -> list[Path]:
        """The original of a logo (one expected); none for a variant, made from the logo's original."""
        folder = self.root / 'sources'
        if logo.variant:
            return []
        return sorted(folder.glob(f'{logo.channel}.*')) if folder.is_dir() else []
