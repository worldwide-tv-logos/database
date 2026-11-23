"""What the sources share while one country is searched: downloads, logs, data loaded once, results per channel."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldwide_tv_logos import net

# iptv-org languages (ISO 639-3) -> Wikipedia editions
WIKI_LANGS = {'eng': 'en', 'spa': 'es', 'cat': 'ca', 'eus': 'eu', 'glg': 'gl', 'fra': 'fr', 'deu': 'de', 'ita': 'it',
              'por': 'pt', 'nld': 'nl', 'pol': 'pl', 'ara': 'ar', 'swe': 'sv', 'nor': 'no', 'nob': 'no', 'dan': 'da',
              'fin': 'fi', 'ces': 'cs', 'slk': 'sk', 'hun': 'hu', 'ron': 'ro', 'bul': 'bg', 'hrv': 'hr', 'srp': 'sr',
              'slv': 'sl', 'ell': 'el', 'tur': 'tr', 'rus': 'ru', 'ukr': 'uk', 'heb': 'he', 'jpn': 'ja', 'kor': 'ko',
              'zho': 'zh', 'hin': 'hi', 'ind': 'id', 'msa': 'ms', 'tha': 'th', 'vie': 'vi', 'fas': 'fa'}


@dataclass
class Context:
    root: Path
    cc: str                                             # iptv-org country code (`uk` for the United Kingdom)
    downloader: Callable = net.download
    log: Callable = print
    iptv_logos: dict = field(default_factory=dict)      # (channel, feed) -> rows of iptv-org's logos.json
    epg: Any = None                                     # iptvepg.EpgIndex of the country, or None
    wikidata: bool = True                               # Wikidata and Wikipedia asked
    deep: bool = False                                  # every source for every channel (hunts, `logos find`)
    have: set[str] = field(default_factory=set)         # logo IDs that already have a logo here
    languages: list[str] = field(default_factory=lambda: ['en'])   # Wikipedia editions, the country's first
    pause: float = 1.0                                  # between two requests to the same site
    _items: dict = field(default_factory=dict)
    _last: dict = field(default_factory=dict)

    @classmethod
    def for_country(cls, root: Path, cc: str, **kw) -> Context:
        """With the Wikipedia editions of the country's languages (iptv-org countries.json), then English."""
        from worldwide_tv_logos import iptvorg
        langs = []
        try:
            country = next((c for c in iptvorg.load_countries(root) if c['code'].lower() == cc), {})
            langs = [WIKI_LANGS[x] for x in country.get('languages', []) if x in WIKI_LANGS]
        except Exception:  # noqa: BLE001, S110 - without countries.json, English only
            pass
        return cls(root=Path(root), cc=cc, languages=list(dict.fromkeys([*langs, 'en'])), **kw)

    def missing(self, unit: dict) -> bool:
        return unit['id'] not in self.have

    def get(self, url: str, **kw) -> bytes:
        """A download with a pause between two requests to the same site (one request at a time)."""
        host = url.split('/', 3)[2] if '://' in url else ''
        wait = self._last.get(host, 0.0) + self.pause - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            return self.downloader(url, **kw)
        finally:
            self._last[host] = time.time()

    def json(self, url: str) -> Any:
        return json.loads(self.get(url, accept='application/json'))

    def items(self, unit: dict) -> list[dict]:
        """The Wikidata items of a channel (at most two), found once per run (see wikidata.find_items)."""
        if not self.wikidata:
            return []
        if unit['id'] not in self._items:
            from worldwide_tv_logos.sources import names, wikidata
            self._items[unit['id']] = wikidata.find_items(
                self.root, [unit['name'], *(unit.get('alt_names') or [])], self.cc, names.channel_keys(unit),
                names.key, self.downloader, pause=self.pause)[:2]
        return self._items[unit['id']]

    def cached(self, folder: str, name: str, compute: Callable, max_age: float):
        """A JSON value kept in .cache/<folder>/<name>.json for `max_age` seconds."""
        import re
        path = self.root / '.cache' / folder / (re.sub(r'[^A-Za-z0-9.@_-]', '_', name)[:150] + '.json')
        if path.is_file() and time.time() - path.stat().st_mtime < max_age:
            return json.loads(path.read_text(encoding='utf-8'))
        value = compute()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return value
