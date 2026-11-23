"""Where candidate logos come from. One module per source, each with `find(unit, ctx) -> list[str]` (logo URLs, best
first; `unit`: a channel or an edition, see harvest.units; `ctx`: context.Context). `collect` asks them in the order
of SOURCES: `logos find`, harvests and hunts all go through it, so a source added here is used everywhere.

| Source | Rank | Asked | What |
|---|---|---|---|
| wikidata | 3 | always | current logo of the channel's item (P154, with dates) |
| wikipedia | 2 | missing | image of the channel's article, in the country's languages then English (local files too) |
| commons | 2 | missing | Commons files named after the channel with "logo" |
| iptv-org | 1 | always | logos.json of the channel or edition |
| iptv-epg | 1 | always | logo of the channel in the country's guide |
| picons | 1 | always | picons collection, by simplified name |
| xmltv-se | 1 | always | xmltv.se vector logos, by XMLTV ID |
| website | 0 | deep | images named "logo" on the channel's home page |

Rank: at equal quality (SVG, size), the candidate of the higher rank wins. Asked: `always` (local data, or read
once per country), `missing` (one request or more per channel: only for channels without a logo, unless deep),
`deep` (hunts and `logos find` only).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from worldwide_tv_logos import net
from worldwide_tv_logos.sources import commons, iptvepg, iptvorg_logos, picons, website, wikidata, wikipedia, xmltvse
from worldwide_tv_logos.sources.context import Context
from worldwide_tv_logos.sources.iptvepg import EpgIndex, load_iptv_epg, parse_iptv_epg
from worldwide_tv_logos.sources.names import channel_keys, key
from worldwide_tv_logos.sources.website import load_website_logos, website_logos
from worldwide_tv_logos.sources.wikidata import COMMONS_FILE, current_logos, find_items, is_old, parse_entity


@dataclass(frozen=True)
class Source:
    name: str
    rank: int
    asked: str            # always | missing | deep
    find: Callable


SOURCES = (
    Source('wikidata', 3, 'always', wikidata.find),
    Source('wikipedia', 2, 'missing', wikipedia.find),
    Source('commons', 2, 'missing', commons.find),
    Source('iptv-org', 1, 'always', iptvorg_logos.find),
    Source('iptv-epg', 1, 'always', iptvepg.find),
    Source('picons', 1, 'always', picons.find),
    Source('xmltv-se', 1, 'always', xmltvse.find),
    Source('website', 0, 'deep', website.find),
)
RANK = {s.name: s.rank for s in SOURCES}


def collect(unit: dict, ctx: Context, only: set[str] | None = None) -> list[tuple[str, str]]:
    """(source, url) of every candidate of a channel or edition, each URL once. A source that fails is logged and
    skipped: it never stops a harvest."""
    out: list[tuple[str, str]] = []
    for s in SOURCES:
        if only is not None and s.name not in only:
            continue
        if (s.asked == 'deep' and not ctx.deep) or (s.asked == 'missing' and not (ctx.deep or ctx.missing(unit))):
            continue
        try:
            urls = s.find(unit, ctx)
        except (net.DownloadError, ValueError, KeyError, TypeError, OSError) as exc:
            ctx.log(f'{unit["id"]}: {s.name} unavailable ({exc})')
            continue
        out += [(s.name, u) for u in urls if u not in {x for _, x in out}]
    return out


__all__ = ['COMMONS_FILE', 'RANK', 'SOURCES', 'Context', 'EpgIndex', 'Source', 'channel_keys', 'collect',
           'current_logos', 'find_items', 'is_old', 'key', 'load_iptv_epg', 'load_website_logos', 'net',
           'parse_entity', 'parse_iptv_epg', 'website_logos']
