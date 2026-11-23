"""Bulk harvest of the logos of a country, for a pull request (`logos harvest --country <cc>`), the hunt of a weekly
slice (`logos hunt`), the bulk import of iptv-org logos (`logos bulk`) and the weekly check against the guide
(`logos epg-check`).

For each open iptv-org channel of the country that has no logo here yet (and, with `updates`, those that have one):

1. candidates from every source (sources.collect: Wikidata, Wikipedia, Commons, iptv-org, iptv-epg, picons,
   xmltv-se and, for a hunt, the channel website);
2. each candidate is downloaded (one at a time, with a pause) and goes through the same preparation as a request
   (image.prepare: trimmed, white frame removed, at least 500 px); refused candidates are reported;
3. the best one is kept: SVG first, then the largest, then the source's rank.

Nothing is written to data/: the result goes to temp/harvest/<cc>/ (originals, manifest.csv for `logos import`,
report.csv, contact sheets to review by eye). Only the reviewed manifest is imported.
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

from PIL import Image

from worldwide_tv_logos import image, iptvorg, net, sources
from worldwide_tv_logos.db import Database
from worldwide_tv_logos.harvest.candidates import (
    Candidate,
    evaluate,
    load_epg,
    load_rejected,
    same_as_channel,
    units,
    update_reason,
)
from worldwide_tv_logos.harvest.duplicates import (
    brand_differences,
    logo_url,
    repo_drawings,
    set_countries,
    shared_drawings,
    split_duplicates,
)
from worldwide_tv_logos.harvest.sheets import contact_sheets, render_sheets
from worldwide_tv_logos.iptvorg import IptvOrg
from worldwide_tv_logos.sources.names import channel_keys


def harvest(db: Database, iptv: IptvOrg, cc: str, iptv_logos: list[dict], out: Path, pause: float = 2.0, limit: int = 0, updates: bool = False, downloader=None,
            log=print, wikidata: bool = True, deep: bool = False, only: list[str] | None = None) -> dict[str, int]:
    """Missing logos of the country (and, with `updates`, better or newer versions of its current logos) into
    out/: originals, manifest.csv for `logos import`, report.csv, doubts.csv, summary.md, contact sheets.
    `wikidata`: also Wikidata and Wikipedia; `deep`: every source for every channel, the website included;
    `only`: these channel IDs only (logos hunt)."""
    downloader = downloader or net.download
    current = {x.logo_id: x for x in db.logos.values() if not x.variant}
    try:
        set_countries(iptvorg.load_countries(db.root))
    except Exception as exc:  # noqa: BLE001 - without country names, brands are only matched by family
        log(f'iptv-org countries unavailable ({exc})')
    channels = [u for u in units(iptv, cc) if updates or u['id'] not in current]
    if only is not None:
        channels = [c for c in channels if c['id'] in set(only)]
    if limit:
        channels = channels[:limit]
    rejected = load_rejected(db.root)
    by_channel: dict[tuple[str, str], list[dict]] = {}
    for x in iptv_logos:
        by_channel.setdefault((x['channel'], x.get('feed') or ''), []).append(x)
    ctx = sources.Context.for_country(db.root, cc, downloader=downloader, log=log, iptv_logos=by_channel,
                                      epg=load_epg(db, cc, downloader, log), wikidata=wikidata, deep=deep,
                                      have=set(current))
    (out / 'originals').mkdir(parents=True, exist_ok=True)
    report, kept, changes = [], [], {}
    last = 0.0
    for c in channels:
        cands = [Candidate(src, url) for src, url in sources.collect(c, ctx) if (c['id'], url) not in rejected]
        for cand in cands:
            wait = last + pause - time.time()
            if wait > 0:
                time.sleep(wait)
            evaluate(cand, downloader)
            last = time.time()
            report.append({'channel': c['id'], 'name': c['name'], 'source': cand.source, 'url': cand.url,
                           'size': f'{cand.size[0]}x{cand.size[1]}' if not cand.error else '',
                           'svg': 'yes' if cand.svg else '', 'error': cand.error})
        good = [x for x in cands if not x.error]
        if not good:
            if c['id'] not in current:
                log(f'{c["id"]}: {"no candidate" if not cands else "every candidate refused"}')
            continue
        best = max(good, key=lambda x: x.score)
        if c['feed'] and same_as_channel(db, c, best, kept):
            continue                                     # the edition uses the logo of its channel: nothing to add
        if c['id'] in current:
            logo = current[c['id']]
            files = db.source_files(logo)
            urls = {x['url'] for x in by_channel.get((c['channel'], c['feed']), ())}
            fps = [image.fingerprint(Image.open(db.path(x.file)).convert('RGBA'))
                   for x in (logo, db.logos.get((logo.channel, logo.feed, 'white'))) if x and db.path(x.file).is_file()]
            reason = update_reason(logo, files[0], best, urls, fps) if len(files) == 1 else None
            if not reason:
                continue
            changes[c['id']] = reason
            log(f'{c["id"]}: UPDATE, {reason}')
        else:
            log(f'{c["id"]}: {best.source} {best.size[0]}x{best.size[1]}{" SVG" if best.svg else ""}')
        kept.append((c, best))
    drawings = repo_drawings(db)
    kept, doubts = split_duplicates(kept, {x.origin: k for k, x in current.items()}, drawings)
    shared = shared_drawings(cc, drawings)
    differs = brand_differences(kept, drawings)
    for c, other in doubts:
        log(f'{c["id"]}: DOUBT, same image as {other} (kept out)')
        changes.pop(c['id'], None)
    rows = []
    for c, best in kept:
        local = out / 'originals' / f'{c["id"]}.{image.extension(best.data)}'
        local.write_bytes(best.data)
        rows.append({'channel': c['channel'], 'feed': c['feed'], 'origin': local.as_posix(), 'label': best.url})
    with open(out / 'manifest.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, ['channel', 'feed', 'origin', 'label'])
        w.writeheader()
        w.writerows(rows)
    with open(out / 'report.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, ['channel', 'name', 'source', 'url', 'size', 'svg', 'error'])
        w.writeheader()
        w.writerows(report)
    with open(out / 'doubts.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['channel', 'reason'])
        w.writerows([(c['id'], f'same image as {other}') for c, other in doubts])
    (out / 'summary.md').write_text(summary(cc, kept, changes, doubts, len(channels), shared, differs), encoding='utf-8',
                                    newline='\n')
    sheets = contact_sheets(kept, out)
    return {'channels': len(channels), 'kept': len(kept), 'updates': len(changes), 'doubts': len(doubts),
            'candidates': len(report), 'sheets': len(sheets)}


def summary(cc: str, kept: list[tuple[dict, Candidate]], changes: dict[str, str], doubts: list, checked: int,
            shared: list[tuple[str, str]] = (), differs: list[tuple[str, list[str]]] = ()) -> str:
    """Body of the harvest pull request."""
    new = [(c, b) for c, b in kept if c['id'] not in changes]
    upd = [(c, b) for c, b in kept if c['id'] in changes]
    lines = [(f'Logos found for `{cc}` by `logos harvest` ({checked} channels checked): **{len(new)} new**, '
             f'**{len(upd)} updated**. Every file went through the same checks as a request.'), '',
             ('**Review** in the *Files changed* tab (each image is shown, before and after for an update): the logo '
             'must be the one currently on air for this exact channel. To refuse one, comment '
             '`/reject <channel id> <reason>`: it is removed from this pull request and never proposed again.'), '']
    if new:
        lines += ['### New', '', '| Channel | ID | Source | Size |', '|---|---|---|---|']
        lines += [f'| {c["name"]} | `{c["id"]}` | [{b.source}]({b.url}) | {b.size[0]}x{b.size[1]}'
                  f'{" SVG" if b.svg else ""} |' for c, b in new]
        lines.append('')
    if upd:
        lines += ['### Updated', '', '| Channel | ID | Why | Source |', '|---|---|---|---|']
        lines += [f'| {c["name"]} | `{c["id"]}` | {changes[c["id"]]} | [{b.source}]({b.url}) |' for c, b in upd]
        lines.append('')
    if doubts:
        lines += ['### Kept out (doubts)', '']
        lines += [f'- `{c["id"]}`: same image as `{other}`' for c, other in doubts]
        lines.append('')
    if differs:
        lines += ["### Different from the brand's logo in other countries", '',
                  ('Logos found above that differ from every logo of the same brand in this repository: often an older '
                  'branding (the repository has the current one), sometimes a regional one. Compare them '
                  "(`uv run logos sheet --channels <a>,<b>`); when the brand's logo is the current one, apply it with "
                  '`uv run logos set <channel id> <URL of that logo>`.'), '']
        lines += [f'- `{cid}`: differs from ' + ', '.join(f'[`{x}`]({logo_url(x)})' for x in others)
                  for cid, others in differs]
        lines.append('')
    if shared:
        lines += ['### Current logos to check', '',
                  'Already published, with the drawing of a channel of another family: one of them is probably wrong.',
                  '']
        lines += [f'- `{lid}`: same drawing as `{other}`' for lid, other in shared]
        lines.append('')
    return '\n'.join(lines)


def bulk(db: Database, iptv: IptvOrg, cc: str, iptv_logos: list[dict], pause: float = 0.3, downloader=None,
         log=print, ops_set=None) -> dict[str, int]:
    """iptv-org and iptv-epg logos of a country added directly, without review (maintainer's decision of
    2026-11-22: these logos are already reviewed there): every channel and edition without a logo here whose iptv-org
    logo, or the logo of its iptv-epg guide channel found without doubt (EpgIndex.sure), passes the rules once
    prepared (SVG or at least MIN_SIDE px, under 1 MB); the best one is kept (SVG, larger, the guide's at equal size). Skipped: an edition whose logo is the drawing of
    its channel, a URL refused before (data/rejected.csv), and the same drawing as a channel of another family
    (one of them is wrong). Errors and skips go to temp/bulk/<cc>.csv."""
    from worldwide_tv_logos import ops
    downloader = downloader or net.download
    ops_set = ops_set or ops.set_logo
    current = {x.logo_id for x in db.logos.values()}
    rejected = load_rejected(db.root)
    by_channel: dict[tuple[str, str], list[dict]] = {}
    for x in iptv_logos:
        if x.get('in_use', True) and 'white' not in (x.get('tags') or []) and str(x.get('url', '')).startswith('https://'):
            by_channel.setdefault((x['channel'], x.get('feed') or ''), []).append(x)
    report, kept = [], []
    last = 0.0
    todo = [u for u in units(iptv, cc) if u['id'] not in current]
    epg = load_epg(db, cc, downloader, log) if todo else None
    for u in todo:
        logos = [x for x in by_channel.get((u['channel'], u['feed']), ()) if (u['id'], x['url']) not in rejected
                 and (x.get('format') == 'SVG' or not x.get('width')
                      or max(x.get('width') or 0, x.get('height') or 0) >= image.MIN_SIDE)]
        logos.sort(key=lambda x: (x.get('format') != 'SVG', -(x.get('width') or 0)))
        tries = [('iptv-org', x['url']) for x in logos[:2]]
        guide = epg.sure(u, channel_keys(u)) if epg else None
        if guide and guide['icon'] and (u['id'], guide['icon']) not in rejected:
            tries.append(('iptv-epg', guide['icon']))      # often the most recent branding
        good = []
        for source, url in tries:
            if good and good[0].svg:
                break
            wait = last + pause - time.time()
            if wait > 0:
                time.sleep(wait)
            cand = evaluate(Candidate(source, url), downloader)
            last = time.time()
            if cand.error:
                report.append({'id': u['id'], 'url': url, 'result': cand.error})
            else:
                good.append(cand)
        if not good:
            if not tries:
                report.append({'id': u['id'], 'url': '', 'result': 'no logo of 500 px or SVG (iptv-org, iptv-epg)'})
            continue
        best = max(good, key=lambda x: (x.score, x.source == 'iptv-epg'))    # equal: the guide's, more recent
        if u['feed'] and same_as_channel(db, u, best, kept):
            report.append({'id': u['id'], 'url': best.url, 'result': 'edition with the logo of its channel'})
            continue
        kept.append((u, best))
    kept, doubts = split_duplicates(kept, {x.origin: x.logo_id for x in db.logos.values() if not x.variant},
                                    repo_drawings(db))
    for u, other in doubts:
        report.append({'id': u['id'], 'url': '', 'result': f'same drawing as {other}: skipped'})
    added = 0
    for u, best in kept:
        try:
            ops_set(db, u['channel'], u['feed'], best.data, best.url, iptv)
            added += 1
        except ops.RequestError as exc:
            report.append({'id': u['id'], 'url': best.url, 'result': str(exc)})
    db.save()
    out = db.root / 'temp' / 'bulk' / f'{cc}.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, ['id', 'url', 'result'])
        w.writeheader()
        w.writerows(report)
    log(f'{cc}: {added} logo(s) added from iptv-org and iptv-epg among {len(todo)} channels and editions without one, '
        f'{len(doubts)} duplicate(s) skipped; details in {out.as_posix()}')
    return {'todo': len(todo), 'added': added, 'doubts': len(doubts)}


def epg_check(db: Database, iptv: IptvOrg, cc: str, out: Path, review: int = 15, pause: float = 0.5,
              downloader=None, log=print, seen_on=None) -> dict[str, int]:
    """Current logos of a country whose iptv-epg guide channel (found without doubt) shows another drawing: often a
    newer branding (NRK 1), sometimes a wrong guide channel. The channel's website (iptv-org field `website`) decides
    when it can: the guide's drawing on it and not ours -> replaced automatically; otherwise the case goes to review
    (at most `review` per run, listed in out/summary.md with a contact sheet: ours, then the guide's). A guide logo
    refused before (data/rejected.csv) is never proposed again."""
    from worldwide_tv_logos import ops, seen
    downloader = downloader or net.download
    seen_on = seen_on or seen.seen_on
    epg = load_epg(db, cc, downloader, log)
    if epg is None:
        return {'checked': 0, 'replaced': 0, 'review': 0}
    rejected = load_rejected(db.root)
    current = {x.logo_id: x for x in db.logos.values() if not x.variant}
    out.mkdir(parents=True, exist_ok=True)
    checked, replaced, cases, last = 0, [], [], 0.0
    for u in units(iptv, cc):
        logo = current.get(u['id'])
        guide = epg.sure(u, channel_keys(u)) if logo else None
        if not guide or not guide['icon'] or guide['icon'] == logo.origin or (u['id'], guide['icon']) in rejected:
            continue
        wait = last + pause - time.time()
        if wait > 0:
            time.sleep(wait)
        cand = evaluate(Candidate('iptv-epg', guide['icon']), downloader)
        last = time.time()
        if cand.error:
            continue
        checked += 1
        ours = Image.open(db.path(logo.file)).convert('RGBA')
        theirs = image.prepare(cand.data)[0]
        if any(image.same_drawing(a, b) for a in seen.fingerprints(ours) for b in seen.fingerprints(theirs)):
            continue                                                  # same drawing: nothing to do
        verdict = None
        website = u.get('website') or ''
        if website.startswith('http'):
            website = website.replace('http://', 'https://', 1)
            try:
                theirs_seen = seen_on(website, cand.data, downloader)
                ours_seen = seen_on(website, db.source_files(logo)[0].read_bytes(), downloader) if theirs_seen else None
                verdict = 'replace' if theirs_seen and not ours_seen else None
            except Exception as exc:  # noqa: BLE001 - a website that cannot be read leaves the case to review
                log(f'{u["id"]}: website unreadable ({exc})')
        if verdict == 'replace':
            ops.set_logo(db, u['channel'], u['feed'], cand.data, cand.url, iptv)
            replaced.append((u, cand, website))
            log(f'{u["id"]}: replaced by the guide logo, shown on {website}')
        elif len(cases) < review:
            cases.append((u, cand, ours, theirs))
    db.save()
    lines = [(f'iptv-epg check of `{cc}`: {checked} logos compared with their guide logo, '
              f'**{len(replaced)} replaced** (the guide logo is on the channel website, ours is not), '
              f'**{len(cases)} to review**.'), '']
    if replaced:
        lines += ['### Replaced (proof: the channel website)', '']
        lines += [f'- `{u["id"]}` ({u["name"]}): [guide logo]({c.url}), seen on {w}' for u, c, w in replaced]
        lines.append('')
    if cases:
        lines += ['### To review', '',
                  'The guide shows another drawing; the website could not decide. Sheet: our logo, then the guide\'s.',
                  '', '| # | Channel | ID | Guide logo | Website |', '|---|---|---|---|---|']
        lines += [f'| {i} | {u["name"]} | `{u["id"]}` | {c.url} | {u.get("website") or ""} |'
                  for i, (u, c, _, _) in enumerate(cases, 1)]
        tiles = []
        for i, (u, c, ours, theirs) in enumerate(cases, 1):
            lo, wo = image.variants(ours)
            lt, wt = image.variants(theirs)
            tiles += [(f'{u["name"]} (case {i}): ours', u['id'], wo or lo, lo),
                      (f'{u["name"]} (case {i}): guide', c.url.rsplit('/', 1)[-1][:40], wt or lt, lt)]
        render_sheets(tiles, out)
    (out / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    log(f'{cc}: {checked} compared, {len(replaced)} replaced, {len(cases)} to review; {(out / "summary.md").as_posix()}')
    return {'checked': checked, 'replaced': len(replaced), 'review': len(cases)}
