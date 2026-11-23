"""Weekly check of current logos on their channel's website (`logos site-check`): a channel can change its logo
on air and on its website while iptv-org, iptv-epg and Wikidata still show the old one.

For a weekly slice of the logos of a country: the channel's website is found (sites.find, confirmed sites only:
the channel's name in its title or domain); when our logo is not on it (seen.seen_on, read plainly then rendered
by a browser), the logos of the website (images named "logo") that differ from ours become a case to review:
`summary.md` and `sites-NN.png` (ours, then each website logo, next to the top of the website). Nothing is
changed here: the reviewer applies a newer logo (`logos set`) or dismisses it (`logos dismiss`).
"""
from __future__ import annotations

import io
import time
from pathlib import Path

from PIL import Image

from worldwide_tv_logos import image, net, registry, seen, sites, sources, web
from worldwide_tv_logos.db import Database
from worldwide_tv_logos.harvest.candidates import Candidate, evaluate, load_rejected
from worldwide_tv_logos.harvest.sheets import website_sheets
from worldwide_tv_logos.iptvorg import IptvOrg


def weekly_slice(items: list, week: int, size: int) -> list:
    if not items or size <= 0:
        return []
    start = (week * size) % len(items)
    return (items[start:] + items[:start])[:size]


def same_logo(a: bytes, b: bytes) -> bool:
    x, y = seen.drawing(a), seen.drawing(b)
    if any(image.same_drawing(p, q, seen.TOLERANCE) for p in seen.fingerprints(x) for q in seen.fingerprints(y)):
        return True
    return image.silhouette(x, y) >= seen.SILHOUETTE and image.silhouette(x, y, 320) >= seen.SILHOUETTE_FINE


def site_check(db: Database, iptv: IptvOrg, cc: str, out: Path, size: int = 150, week: int = 0, review: int = 20,
               log=print, ctx=None) -> dict[str, int]:
    ctx = ctx or sources.Context.for_country(db.root, cc, log=log, ambiguous=sources.names.ambiguous_keys(iptv))
    rejected = load_rejected(db.root)
    current = {x.logo_id: x for x in db.logos.values() if not x.variant}
    todo = weekly_slice([u for u in registry.units(db, cc) if u['id'] in current], week, size)
    stats = {'checked': 0, 'on site': 0, 'no site': 0, 'unreadable': 0, 'review': 0}
    cases = []
    started = time.time()
    for u in todo:
        if len(cases) >= review:
            break
        logo = current[u['id']]
        files = db.source_files(logo)
        ours = (files[0] if files else db.path(logo.file)).read_bytes()
        site = sites.find(u, ctx)
        if site is None or not site.confirmed:
            stats['no site'] += 1
            continue
        stats['checked'] += 1
        try:
            if seen.seen_on(site.url, ours, log=log):
                stats['on site'] += 1
                continue
        except (net.DownloadError, ValueError, OSError):
            stats['unreadable'] += 1
            continue
        found = []
        for url in sources.load_website_logos(site.url, ctx.get):
            if (u['id'], url) in rejected:
                continue
            cand = evaluate(Candidate('website', url), ctx.get)
            if not cand.error and not same_logo(ours, cand.data):
                found.append(cand)
        if found:
            cases.append((u, ours, site, found[:2], web.screenshot(site.url)))
            log(f'{u["id"]}: our logo is not on {site.url}, {len(found)} other logo(s) there')
    stats['review'] = len(cases)
    out.mkdir(parents=True, exist_ok=True)
    lines = [(f'Website check of `{cc}`: {stats["checked"]} current logos looked for on their channel\'s website '
              f'(confirmed sites), **{stats["on site"]} seen there**, {stats["unreadable"]} unreadable, '
              f'{stats["no site"]} without a confirmed website; **{len(cases)} to review**: our logo is not on the '
              f'website, which shows another one ({time.time() - started:.0f} s).'), '']
    if cases:
        lines += ['### To review', '',
                  'Sheet `sites-NN.png`: our logo, then each logo of the website, next to the top of the website.', '',
                  '| # | Channel | ID | Website | Logos of the website |', '|---|---|---|---|---|']
        rows = []
        for i, (u, ours, site, found, shot) in enumerate(cases, 1):
            lines.append(f'| {i} | {u["name"]} | `{u["id"]}` | {site.url} | '
                         + ', '.join(f'[{j}]({c.url}) {c.size[0]}x{c.size[1]}' for j, c in enumerate(found, 1)) + ' |')
            picture = Image.open(io.BytesIO(shot)).convert('RGB') if shot else Image.new('RGB', (1280, 420), 'white')
            rows.append((f'case {i}, {u["name"]}: OUR logo', ours, picture))
            rows += [(f'case {i}, {u["name"]}: website logo {j} ({c.url.rsplit("/", 1)[-1][:40]})', c.data, picture)
                     for j, c in enumerate(found, 1)]
        website_sheets(rows, out)
    (out / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    log(f'{cc}: ' + ', '.join(f'{k} {v}' for k, v in stats.items()))
    return stats
