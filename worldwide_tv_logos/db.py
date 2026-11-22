"""The database: data/logos.csv, data/aliases.csv, data/countries.csv, and the files they describe.

Naming is derived from the iptv-org id and never chosen by hand:

    logos/<cc>/<channel>[@<feed>][.<variant>].png     the logo served
    sources/<cc>/<channel>[@<feed>][.<variant>].<ext>  the original it was built from

`<cc>` is the country code at the end of the channel id (`France3.fr` -> `fr`).
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(os.getenv('LOGOS_ROOT') or Path(__file__).resolve().parent.parent)
CHANNEL_RE = re.compile(r'^[A-Za-z0-9]+\.[a-z]{2}$')        # iptv-org channel id: Latin letters, digits, `.cc`
FEED_RE = re.compile(r'^[A-Za-z0-9]+$')
EPG_ID_RE = re.compile(r'^[^,"\s]+$')
VARIANTS = ('', 'white')                                     # '' : the logo itself; white : for dark backgrounds
RAW_BASE = 'https://raw.githubusercontent.com/worldwide-tv-logos/database/main/'
SITE_BASE = 'https://worldwide-tv-logos.github.io/database/'   # GitHub Pages (CDN): the address to use


@dataclass
class Logo:
    channel: str
    feed: str = ''
    variant: str = ''
    width: int = 0
    height: int = 0
    origin: str = ''          # where the original comes from (URL, or `issue #N`)
    added: str = ''           # YYYY-MM-DD
    updated: str = ''         # YYYY-MM-DD, last replacement of the file

    @property
    def key(self) -> tuple[str, str, str]:
        return self.channel, self.feed, self.variant

    @property
    def logo_id(self) -> str:
        return self.channel + (f'@{self.feed}' if self.feed else '')

    @property
    def country(self) -> str:
        return self.channel.rsplit('.', 1)[-1]

    @property
    def stem(self) -> str:
        return self.logo_id + (f'.{self.variant}' if self.variant else '')

    @property
    def file(self) -> str:
        return f'logos/{self.country}/{self.stem}.png'

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
    channel: str
    feed: str = ''

    @property
    def key(self) -> tuple[str, str]:
        return self.source, self.epg_id


def parse_logo_id(value: str) -> tuple[str, str]:
    """`France3.fr@Alsace` -> ('France3.fr', 'Alsace')."""
    channel, _, feed = value.strip().partition('@')
    return channel, feed


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
        self.logos: dict[tuple[str, str, str], Logo] = {}
        self.aliases: dict[tuple[str, str], Alias] = {}
        self.countries: dict[str, str] = {}

    @property
    def data_dir(self) -> Path:
        return self.root / 'data'

    def load(self) -> Database:
        self.logos = {r.key: r for r in _read(self.data_dir / 'logos.csv', Logo)}
        self.aliases = {r.key: r for r in _read(self.data_dir / 'aliases.csv', Alias)}
        path = self.data_dir / 'countries.csv'
        if path.exists():
            with path.open(encoding='utf-8', newline='') as fh:
                self.countries = {r['code']: r['name'] for r in csv.DictReader(fh)}
        return self

    def merge(self, base: Path, ours: Path) -> None:
        """Rows of this database (upstream, e.g. after a rebase) merged with those of our commit (`ours`) against
        their common ancestor (`base`); `base` and `ours` are repository roots holding a data/ folder."""
        b, o = Database(base).load(), Database(ours).load()
        self.logos = merge_rows(b.logos, self.logos, o.logos)
        self.aliases = merge_rows(b.aliases, self.aliases, o.aliases)

    def save(self) -> None:
        _write(self.data_dir / 'logos.csv', Logo, sorted(self.logos.values(), key=lambda r: tuple(s.lower() for s in r.key)))
        _write(self.data_dir / 'aliases.csv', Alias, sorted(self.aliases.values(), key=lambda r: r.key))

    def path(self, rel: str) -> Path:
        return self.root / rel

    def source_files(self, logo: Logo) -> list[Path]:
        folder = self.root / 'sources' / logo.country
        return sorted(folder.glob(f'{logo.stem}.*')) if folder.is_dir() else []
