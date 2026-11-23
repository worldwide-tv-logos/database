"""iptv-org: the logos of the channel or edition itself in its logos.json (SVG first, then the largest; never the
white versions, which are made here)."""
from __future__ import annotations


def find(unit: dict, ctx) -> list[str]:
    logos = sorted((x for x in ctx.iptv_logos.get((unit.get('channel', unit['id']), unit.get('feed', '')), ())
                    if x.get('in_use', True)
                    and 'white' not in (x.get('tags') or []) and str(x.get('url', '')).startswith('https://')),
                   key=lambda x: (x.get('format') != 'SVG', -(x.get('width') or 0)))
    return [x['url'] for x in logos[:2]]
