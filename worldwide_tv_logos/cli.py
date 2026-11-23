"""Command line: `uv run logos <command>` (see .github/docs/scripts.md)."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

from PIL import Image

from worldwide_tv_logos import image, iptvorg, issues, net, ops, registry, sources
from worldwide_tv_logos.db import VARIANTS, Database

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _iptv(db: Database, offline: bool):
    return None if offline else iptvorg.load(db.root)


def validate(db: Database, iptv, warnings: list[str] | None = None) -> list[str]:
    """Errors (blocking). Changes on the iptv-org side (channel removed, closed, replaced) go to `warnings`: they
    must never block the nightly update. Logos are named after our channel IDs (data/channels.csv)."""
    errors = []
    warnings = [] if warnings is None else warnings
    for logo in db.logos.values():
        where = f'data/logos.csv {logo.stem}'
        if not registry.ID_RE.match(logo.channel):
            errors.append(f'{where}: malformed channel ID (ch_ + 10 characters)')
            continue
        if logo.variant not in VARIANTS:
            errors.append(f'{where}: unknown variant `{logo.variant}` ({", ".join(v for v in VARIANTS if v)})')
        if logo.variant and (logo.channel, '') not in db.logos:
            errors.append(f'{where}: variant without the logo itself')
        if not logo.origin:
            errors.append(f'{where}: origin missing')
        if not DATE_RE.match(logo.added) or (logo.updated and not DATE_RE.match(logo.updated)):
            errors.append(f'{where}: dates must be YYYY-MM-DD')
        ident = registry.iptv_id(db, logo.channel) if iptv is not None and not logo.variant else ''
        if ident and (warn := iptv.status_warning(*ident.partition('@')[::2])):
            warnings.append(f'{where} ({ident}): {warn}')
        path = db.path(logo.file)
        if not path.is_file():
            errors.append(f'{where}: {logo.file} missing')
            continue
        errors += [f'{logo.file}: {e}' for e in image.check_file(path, white=logo.variant == 'white')]
        from PIL import Image
        with Image.open(path) as img:
            if img.size != (logo.width, logo.height):
                errors.append(f'{where}: size {logo.width}x{logo.height} in the index, {img.size[0]}x{img.size[1]} on disk')
        if not logo.variant and len(db.source_files(logo)) != 1:
            errors.append(f'{where}: exactly one original expected in sources/ ({len(db.source_files(logo))} found)')
    known = {logo.file for logo in db.logos.values()}
    for path in sorted((db.root / 'logos').rglob('*')) if (db.root / 'logos').is_dir() else []:
        rel = path.relative_to(db.root).as_posix()
        if path.is_file() and rel not in known:
            errors.append(f'{rel}: not listed in data/logos.csv (or wrongly named)')
    originals = {p for logo in db.logos.values() if not logo.variant for p in db.source_files(logo)}
    for path in sorted((db.root / 'sources').rglob('*')) if (db.root / 'sources').is_dir() else []:
        if path.is_file() and path not in originals:
            errors.append(f'{path.relative_to(db.root).as_posix()}: original of no logo')
    for alias in db.aliases.values():
        if (alias.channel, '') not in db.logos:
            errors.append(f'data/aliases.csv {alias.source}:{alias.epg_id}: no logo for {alias.channel}')
    for code in db.countries:
        if not re.match(r'^[a-z]{2}$', code):
            errors.append(f'data/countries.csv: `{code}` must be a lowercase two-letter code')
    return errors + registry.check(db, warnings)


def cmd_validate(args, db: Database) -> int:
    warnings: list[str] = []
    errors = validate(db, _iptv(db, args.offline), warnings)
    for w in warnings:
        print(f'warning: {w}')
    for e in errors:
        print(e)
    print(f'{len(db.logos)} logos, {len(db.aliases)} aliases, {len(db.channels)} channels, {len(errors)} error(s), '
          f'{len(warnings)} warning(s)')
    return 1 if errors else 0


def cmd_import(args, db: Database) -> int:
    """Bulk import from a CSV (channel,origin[,label]) where channel is our ID (or a slug, an iptv-org ID) and origin
    an https URL or a local file."""
    with open(args.manifest, encoding='utf-8', newline='') as fh:
        rows = list(csv.DictReader(fh))
    failed = 0
    last_remote = 0.0
    for row in rows:
        label, origin = row['channel'].strip(), row['origin'].strip()
        try:
            channel = ops.channel_of(db, label).id
            if origin.startswith('https://'):
                wait = last_remote + args.pause - time.time()
                if wait > 0:
                    time.sleep(wait)
                data = net.download(origin)
                last_remote = time.time()
            else:
                data = Path(origin).read_bytes()
            for change in ops.set_logo(db, channel, data, row.get('label') or origin):
                print(f'{label}: {change}')
            db.save()
        except (ops.RequestError, net.DownloadError, OSError) as exc:
            failed += 1
            print(f'{label}: REFUSED — {exc}')
    print(f'{len(rows) - failed} imported, {failed} refused')
    return 0


def _preview(db: Database, req) -> None:
    """temp/preview/sheet-01.png: the proposed logo (and the current one, for an edit) on dark and light tiles, for
    the review of the request (by a maintainer or by Claude)."""
    from worldwide_tv_logos import harvest
    url = req.get('url')
    c = db.channels.get(req.get('channel').strip().lower())
    label = c.id if c else req.get('channel')
    rows = []
    try:
        data = net.download(url)
        img = image.prepare(data)[0]
        rows.append(({'id': label, 'name': f'proposed: {label}'},
                     harvest.Candidate('request', url, data, image.is_svg(data), img.size)))
        old = db.logos.get((c.id, '')) if c else None
        if old is not None and len(db.source_files(old)) == 1:
            data = db.source_files(old)[0].read_bytes()
            rows.append(({'id': label, 'name': f'current: {label}'},
                         harvest.Candidate('current', old.origin, data, image.is_svg(data), image.prepare(data)[0].size)))
        out = db.root / 'temp' / 'preview'
        out.mkdir(parents=True, exist_ok=True)
        harvest.contact_sheets(rows, out)
    except (image.ImageError, net.DownloadError, OSError) as exc:
        print(f'no preview ({exc})')


def cmd_issue_validate(args, db: Database) -> int:
    body = os.environ.get('RAW_BODY', '') if args.body is None else args.body
    labels = [x.strip() for x in (args.labels or '').split(',') if x.strip()]
    try:
        req = issues.parse(args.number or 0, labels, body)
        errors = issues.validate(req, db)
    except ops.RequestError as exc:
        errors = [str(exc)]
    out = db.root / 'temp' / 'errors.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(f'- {e}' for e in errors), encoding='utf-8')
    if not errors and req.kind in ('logos:add', 'logos:edit'):
        _preview(db, req)
    for e in errors:
        print(e)
    return 1 if errors else 0


def cmd_update(args, db: Database) -> int:
    """Apply approved issues, one by one: a faulty request is reported on its issue and skipped, never blocking
    the others."""
    gh = net.GitHub()
    done, notes = [], {}
    for raw in gh.approved_issues():
        labels = [label['name'] for label in raw['labels']]
        snapshot = (dict(db.logos), dict(db.aliases), copy.deepcopy(db.channels), dict(db.external_ids))
        try:
            req = issues.parse(raw['number'], labels, raw.get('body') or '')
            changes = issues.apply(req, db)
        except ops.RequestError as exc:
            db.logos, db.aliases, db.channels, db.external_ids = snapshot
            print(f'#{raw["number"]}: skipped — {exc}')
            gh.comment(raw['number'], f'This request could not be applied:\n\n- {exc}\n\n'
                                      'Please edit the issue to fix it; it will be checked again.')
            gh.remove_label(raw['number'], 'approved')
            gh.add_labels(raw['number'], ['check:failed'])
            continue
        print(f'#{raw["number"]}: ' + '; '.join(changes))
        done.append(raw['number'])
        notes[raw['number']] = changes
    db.save()
    temp = db.root / 'temp'
    temp.mkdir(exist_ok=True)
    (temp / 'processed.txt').write_text(' '.join(f'Closes #{n}' for n in done), encoding='utf-8')
    (temp / 'changes.json').write_text(json.dumps(notes, indent=1), encoding='utf-8')
    print(f'{len(done)} issue(s) applied')
    return 0


def cmd_notify(args, db: Database) -> int:
    """After the update commit is pushed: tell each processed issue what changed."""
    path = db.root / 'temp' / 'changes.json'
    if not path.is_file():
        return 0
    gh = net.GitHub()
    for number, changes in json.loads(path.read_text(encoding='utf-8')).items():
        gh.comment(int(number), 'Applied in ' + (args.commit or 'the latest update') + ':\n\n'
                   + '\n'.join(f'- {c}' for c in changes))
    return 0


def cmd_reprocess(args, db: Database) -> int:
    """Rebuild every logo from its original in sources/ after a change of the image rules; only the logos whose
    result differs are rewritten."""
    changed = 0
    for logo in sorted((x for x in db.logos.values() if not x.variant), key=lambda x: x.key):
        sources = db.source_files(logo)
        if len(sources) != 1:
            print(f'{logo.stem}: original missing, skipped')
            continue
        original = sources[0].read_bytes()
        img, white = image.variants(image.prepare(original)[0])

        def pixels(im):         # compared by their pixels: PNG files of the same image differ between zlib builds
            return None if im is None else (im.size, im.convert('RGBA').tobytes())
        expected = {'': pixels(img), 'white': pixels(white)}
        current = {v: (pixels(Image.open(db.path(db.logos[(logo.channel, v)].file)))
                       if (logo.channel, v) in db.logos else None) for v in ('', 'white')}
        if expected == current:
            continue
        changed += 1
        for change in ops.set_logo(db, logo.channel, original, logo.origin):
            print(f'{logo.stem}: {change}')
    db.save()
    print(f'{changed} logo(s) rebuilt')
    return 0


def _stems_changed(db: Database, base: str) -> list[str]:
    import subprocess
    out = subprocess.run(['git', 'diff', '--name-only', base, '--', 'logos'], cwd=db.root, capture_output=True,
                         text=True, check=True).stdout.split()
    out += subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '--', 'logos'], cwd=db.root,
                          capture_output=True, text=True, check=True).stdout.split()      # new, not committed yet
    return sorted({Path(p).name.removesuffix('.png').removesuffix('.white') for p in out})


def cmd_sheet(args, db: Database) -> int:
    """Contact sheets of logos of the repository: changed since a branch, listed, or of a country."""
    from worldwide_tv_logos import harvest
    if args.changed:
        stems = _stems_changed(db, args.base)
    elif args.channels:
        stems = [x.strip() for x in args.channels.split(',') if x.strip()]
    elif args.country:
        cc = args.country.lower()
        stems = sorted(x.channel for x in db.logos.values()
                       if not x.variant and x.channel in db.channels and db.channels[x.channel].country == cc)
    else:
        print('give --changed, --channels or --country')
        return 1
    out = Path(args.out) if args.out else db.root / 'temp' / 'sheets'
    for old in out.glob('sheet-*.png') if out.is_dir() else []:
        old.unlink()
    pages = harvest.repo_sheets(db, stems, out, args.per_page)
    print(f'{len(stems)} logo(s) on {len(pages)} sheet(s): ' + ', '.join(p.as_posix() for p in pages))
    return 0


def cmd_find(args, db: Database) -> int:
    """Every candidate logo of one channel or feed, from every source, checked and ranked, on a contact sheet."""
    from worldwide_tv_logos import harvest
    c = _channel(db, args.id)
    if c is None:
        return 1
    channel, cc = c.id, c.country
    iptv = iptvorg.load(db.root)
    unit = registry.unit(db, c)
    key = harvest.iptv_key(unit)
    logos = [x for x in iptvorg.load_logos(db.root) if (x['channel'], x.get('feed') or '') == key]
    ctx = sources.Context.for_country(db.root, cc, iptv_logos={key: logos}, deep=True,
                                      ambiguous=sources.names.ambiguous_keys(iptv),
                                      wikidata=not args.no_wikidata, epg=harvest.load_epg(db, cc, net.download, print))
    cands = [harvest.Candidate(src, url) for src, url in sources.collect(unit, ctx)]
    rejected = harvest.load_rejected(db.root)
    for i, cand in enumerate(cands):
        if i:
            time.sleep(args.pause)
        harvest.evaluate(cand, net.download)
        if (channel, cand.url) in rejected:
            cand.error = 'rejected before (data/rejected.csv)'
    cands.sort(key=lambda x: x.score, reverse=True)
    out = Path(args.out) if args.out else db.root / 'temp' / 'find' / channel
    out.mkdir(parents=True, exist_ok=True)
    good = [x for x in cands if not x.error]
    tiles = []
    current = db.logos.get((channel, ''))
    if current is not None:
        white = db.logos.get((channel, 'white'))
        from PIL import Image
        light = Image.open(db.path(current.file)).convert('RGBA')
        tiles.append(('current logo', f'{current.width}x{current.height}  {current.origin[:60]}',
                      Image.open(db.path(white.file)).convert('RGBA') if white else light, light))
    for i, cand in enumerate(good, 1):
        img, white = image.variants(image.prepare(cand.data)[0])
        tiles.append((f'candidate {i}: {cand.source}', f'{cand.size[0]}x{cand.size[1]}' + (' SVG' if cand.svg else ''),
                      white or img, img))
    pages = harvest.render_sheets(tiles, out) if tiles else []
    records = [{'n': i, 'source': x.source, 'url': x.url, 'size': f'{x.size[0]}x{x.size[1]}', 'svg': x.svg}
               for i, x in enumerate(good, 1)]
    (out / 'candidates.json').write_text(json.dumps(records, indent=1), encoding='utf-8')
    for r in records:
        print(f"{r['n']}. {r['source']:9} {r['size']:>9}{' SVG' if r['svg'] else '    '}  {r['url']}")
    for x in cands:
        if x.error:
            print(f'   refused  {x.source:9} {x.url}  ({x.error})')
    print(f'{len(good)} usable candidate(s); sheet: ' + (', '.join(p.as_posix() for p in pages) or 'none')
          + f'; apply one with `logos set {channel} <url>`')
    return 0


def cmd_seen_on(args, db: Database) -> int:
    """Is this logo shown on this page (the channel's website)? Proof that it is the current one."""
    from worldwide_tv_logos import seen
    try:
        logo = args.logo
        c = registry.resolve(db, logo) if not logo.startswith(('https://', 'data:image/')) else None
        if c is not None and (c.id, '') in db.logos:
            data = db.source_files(db.logos[(c.id, '')])[0].read_bytes()
        elif logo.startswith(('https://', 'data:image/')):
            data = net.download(logo)
        else:
            data = Path(logo).read_bytes()
        how = seen.seen_on(args.page, data)
    except (net.DownloadError, image.ImageError, OSError, IndexError) as exc:
        print(f'could not check: {exc}')
        return 2
    print(f'FOUND on {args.page}: {how}' if how else f'NOT FOUND on {args.page}')
    return 0 if how else 1


def cmd_set(args, db: Database) -> int:
    """Add or replace a logo from a URL or a local file (same preparation and checks as a request)."""
    try:
        channel = ops.channel_of(db, args.id).id
        data = net.download(args.source) if args.source.startswith('https://') else Path(args.source).read_bytes()
        for change in ops.set_logo(db, channel, data, args.origin or args.source):
            print(change)
    except (ops.RequestError, net.DownloadError, OSError) as exc:
        print(f'refused: {exc}')
        return 1
    db.save()
    return 0


def cmd_move(args, db: Database) -> int:
    """Move the logos and aliases of a channel to another channel of the registry (a channel registered twice)."""
    try:
        changes = ops.move_logos(db, ops.channel_of(db, args.old).id, ops.channel_of(db, args.new).id)
    except ops.RequestError as exc:
        print(f'refused: {exc}')
        return 1
    db.save()
    print('\n'.join(changes))
    return 0


def cmd_remove(args, db: Database) -> int:
    """Remove a logo (with its variant, original and aliases)."""
    try:
        changes = ops.remove_logo(db, ops.channel_of(db, args.id).id)
    except ops.RequestError as exc:
        print(f'refused: {exc}')
        return 1
    db.save()
    print('\n'.join(changes))
    return 0


def cmd_verdict(args, db: Database) -> int:
    """The reviewer's decision for the workflow (temp/verdict.json): `ready` (may be merged) or `hold` (a maintainer
    must look), with a short report in Markdown."""
    text = args.text if args.text is not None else sys.stdin.read()
    out = db.root / 'temp' / 'verdict.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({'state': args.state, 'text': text.strip()}, ensure_ascii=False), encoding='utf-8')
    print(f'verdict: {args.state}')
    return 0


SHARP_SIDE = 1000      # current logos smaller than this (longest side, raster original) are hunted for a sharper version


def _slice(items: list[str], week: int, size: int) -> list[str]:
    if not items or size <= 0:
        return []
    start = (week * size) % len(items)
    return (items[start:] + items[:start])[:size]


def cmd_hunt(args, db: Database) -> int:
    """Logos of channels still without one, and sharper versions of small logos: a different slice of each every
    week, every source including the channel website, for review like a harvest."""
    import datetime
    import shutil

    from worldwide_tv_logos import harvest
    cc = args.country.lower()
    iptv = iptvorg.load(db.root)
    have = {x.logo_id for x in db.logos.values()}
    ids = [u['id'] for u in registry.units(db, cc)]
    missing = [i for i in ids if i not in have]
    followed = set(ids)
    small = [x.logo_id for x in sorted(db.logos.values(), key=lambda x: x.key)
             if not x.variant and x.logo_id in followed and max(x.width, x.height) < SHARP_SIDE
             and not any(p.suffix == '.svg' for p in db.source_files(x))]
    week = datetime.date.today().isocalendar()[1] if args.offset is None else args.offset
    only = _slice(missing, week, args.limit) + _slice(small, week, args.sharpen)
    if not only:
        print('no channel without a logo, no small logo')
        return 0
    out = db.root / 'temp' / 'harvest' / cc
    shutil.rmtree(out, ignore_errors=True)
    stats = harvest.harvest(db, iptv, cc, iptvorg.load_logos(db.root), out, pause=args.pause, deep=True, only=only,
                            updates=True)
    print(f"hunt: {stats['kept'] - stats['updates']} logo(s) found for {min(len(missing), args.limit)} of the "
          f"{len(missing)} channels without one, {stats['updates']} sharper or newer version(s) among "
          f"{min(len(small), args.sharpen)} of the {len(small)} small logos; {out.as_posix()}/summary.md")
    return 0


def cmd_bulk(args, db: Database) -> int:
    """iptv-org logos of whole countries added directly, without review (see harvest.bulk)."""
    from worldwide_tv_logos import harvest
    iptv, logos = iptvorg.load(db.root), iptvorg.load_logos(db.root)
    for cc in args.country:
        harvest.bulk(db, iptv, cc.lower(), logos, pause=args.pause)
    return 0


def cmd_epg_check(args, db: Database) -> int:
    """Current logos whose iptv-epg guide shows another drawing: replaced when the channel website shows the
    guide's, else listed for review (see harvest.epg_check)."""
    import shutil

    from worldwide_tv_logos import harvest
    iptv = iptvorg.load(db.root)
    for cc in args.country:
        out = db.root / 'temp' / 'epg-check' / cc.lower()
        shutil.rmtree(out, ignore_errors=True)
        harvest.epg_check(db, iptv, cc.lower(), out, review=args.review)
    return 0


def cmd_site_check(args, db: Database) -> int:
    """Current logos looked for on their channel's website, a weekly slice; those absent from it, while the website
    shows another logo, are listed for review (see harvest.sitecheck)."""
    import datetime
    import shutil

    from worldwide_tv_logos.harvest import sitecheck
    iptv = iptvorg.load(db.root)
    week = datetime.date.today().isocalendar()[1] if args.offset is None else args.offset
    for cc in args.country:
        out = db.root / 'temp' / 'site-check' / cc.lower()
        shutil.rmtree(out, ignore_errors=True)
        sitecheck.site_check(db, iptv, cc.lower(), out, size=args.size, week=week, review=args.review)
    return 0


def cmd_dismiss(args, db: Database) -> int:
    """Never propose this logo URL again for this channel (data/rejected.csv): a guide logo kept out after review."""
    from datetime import date
    c = _channel(db, args.id)
    if c is None:
        return 1
    path = db.root / 'data' / 'rejected.csv'
    new = not path.is_file()
    with open(path, 'a', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        if new:
            w.writerow(['channel', 'url', 'reason', 'date'])
        w.writerow([c.id, args.url, args.reason or '', date.today().isoformat()])
    print(f'{args.url} will not be proposed again for `{c.id}` ({c.name})')
    return 0


def cmd_country_add(args, db: Database) -> int:
    """Follow a country (data/countries.csv): harvested and hunted every week, with its missing/<cc>.md list. The code
    is iptv-org's (`uk` for the United Kingdom)."""
    iptv = iptvorg.load(db.root)
    for code in args.code:
        cc = code.lower()
        if cc in db.countries:
            print(f'`{cc}` is already followed')
            continue
        names = {c['code'].lower(): c['name'] for c in iptvorg.load_countries(db.root)}
        if cc not in names or not iptv.country_channels(cc):
            print(f'`{cc}`: no channel of this country in iptv-org')
            return 1
        db.countries[cc] = names[cc]
        print(f'`{cc}` ({names[cc]}) followed: {len(iptv.country_channels(cc))} channels')
    path = db.data_dir / 'countries.csv'
    with path.open('w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['code', 'name'])
        w.writerows(sorted(db.countries.items()))
    return 0


def cmd_harvest(args, db: Database) -> int:
    """A country with more channels than --max (the United States: about 15,000 channels and editions) is harvested
    by weekly slices: three quarters of the slice for channels without a logo, a quarter for the others (--updates),
    a different slice every week."""
    import datetime
    import shutil

    from worldwide_tv_logos import harvest
    cc = args.country.lower()
    out = db.root / 'temp' / 'harvest' / cc
    shutil.rmtree(out, ignore_errors=True)
    iptv = iptvorg.load(db.root)
    have = {x.logo_id for x in db.logos.values()}
    ids = [u['id'] for u in registry.units(db, cc)]
    missing = [i for i in ids if i not in have]
    present = [i for i in ids if i in have] if args.updates else []
    only = None
    if args.max and len(missing) + len(present) > args.max:
        week = datetime.date.today().isocalendar()[1] if args.offset is None else args.offset
        share = args.max - args.max // 4 if present else args.max
        only = _slice(missing, week, share) + _slice(present, week, args.max - share)
        print(f'{len(missing)} channels without a logo and {len(present)} with one: slice {week} of {len(only)}')
    stats = harvest.harvest(db, iptv, cc, iptvorg.load_logos(db.root), out, only=only,
                            pause=args.pause, limit=args.limit, updates=args.updates)
    print(f"{stats['kept']} logo(s) to review ({stats['updates']} update(s), {stats['doubts']} doubt(s)) among "
          f"{stats['channels']} channels, {stats['candidates']} candidates; {out.as_posix()}/sheet-*.png, "
          f"then `logos import {out.as_posix()}/manifest.csv`")
    return 0


def cmd_reject(args, db: Database) -> int:
    """Refuse a logo proposed in a harvest pull request: the channel gets back its logo of `--base` (the main
    branch), and its URL goes to data/rejected.csv so that it is never proposed again; with `--unconfirmed` (right
    perhaps, but no proof found), it is only removed from this pull request and proposed again at the next harvest."""
    from datetime import date
    c = _channel(db, args.channel)
    if c is None:
        return 1
    channel = c.id
    logo = db.logos.get((channel, ''))
    if logo is None:
        print(f'no logo for `{channel}` in this branch')
        return 1
    base = Database(Path(args.base)).load()
    if base.logos.get((channel, '')) and base.logos[(channel, '')].origin == logo.origin:
        print(f'`{args.channel}` is not changed by this pull request')
        return 1
    for key in [k for k in db.logos if k[0] == channel]:
        ops.remove_files(db, db.logos.pop(key))
    for key, old in base.logos.items():
        if key[0] == channel:
            db.logos[key] = old
            for rel in [old.file] + [p.relative_to(base.root).as_posix() for p in base.source_files(old)]:
                target = db.path(rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base.path(rel).read_bytes())
    for key, alias in list(db.aliases.items()):         # a new logo refused: its guide aliases go with it
        if (alias.channel, '') not in db.logos:
            del db.aliases[key]
    db.save()
    if args.unconfirmed:
        print(f'removed {logo.origin} for `{args.channel}` from this pull request (proposed again next time)')
        return 0
    path = db.root / 'data' / 'rejected.csv'
    new = not path.is_file()
    with open(path, 'a', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        if new:
            w.writerow(['channel', 'url', 'reason', 'date'])
        w.writerow([channel, logo.origin, args.reason or '', date.today().isoformat()])
    print(f'rejected {logo.origin} for `{args.channel}`')
    return 0


def cmd_unreject(args, db: Database) -> int:
    """Remove rows of data/rejected.csv (every filter given must match): those logos are proposed again."""
    if not (args.channel or args.date or args.reason_contains):
        print('give at least one filter (--channel, --date, --reason-contains)')
        return 1
    path = db.root / 'data' / 'rejected.csv'
    with open(path, encoding='utf-8', newline='') as fh:
        rows = list(csv.DictReader(fh))
    wanted = (registry.resolve(db, args.channel).id if registry.resolve(db, args.channel) else args.channel) \
        if args.channel else ''
    keep = [r for r in rows if not ((not wanted or r['channel'] == wanted)
                                    and (not args.date or r['date'] == args.date)
                                    and args.reason_contains.lower() in r['reason'].lower())]
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, ['channel', 'url', 'reason', 'date'], lineterminator='\n')
        w.writeheader()
        w.writerows(keep)
    print(f'{len(rows) - len(keep)} refused logo(s) proposed again')
    return 0


def logo_record(db: Database, x) -> dict:
    """One entry of logos.json: our channel ID, its slug and iptv-org ID, then the image."""
    c = db.channels.get(x.channel)
    return {'channel': x.channel, 'slug': c.slug if c else None, 'iptv': registry.iptv_id(db, x.channel) or None,
            'country': c.country if c else None, 'parent': (c.parent or None) if c and c.status != 'merged' else None, 'variant': x.variant or None, 'width': x.width,
            'height': x.height, 'format': 'PNG', 'url': x.url, 'updated': x.updated or x.added}


CHANGES_LABEL = 'iptv-org:changes'
CHANGES_TITLE = 'Changes on the iptv-org side'


def changes_body(warnings: list[str], coming: list[str] = ()) -> str:
    return '\n'.join([
        ('Logos whose channel changed in iptv-org since they were added (found by `logos validate`, '
        'refreshed every week by the `changes` workflow).'), '',
        ('To fix one: a replaced or renamed channel keeps its ID and its logo; map its new iptv-org ID '
        '(`logos channel-map <ch_ id> iptv-org <new id>`, and `channel-edit --name` for a new name). A channel '
        'removed for good gets its logo removed; a closed channel keeps its logo.'), '',
        *[f'- [ ] {w}' for w in warnings], '',
        *(['### Coming at iptv-org', '',
           ('Open requests at iptv-org about channels of the followed countries: applied here once iptv-org accepts '
           'them, nothing to do.'), '', *coming, ''] if coming else []),
        'This issue closes by itself when the list is empty.'])


def cmd_guide_aliases(args, db: Database) -> int:
    """Aliases from the iptv-epg guide of a country: a guide channel found by name for exactly one channel or edition
    (and that channel finding only it) gets the alias `iptv-epg-<cc>:<guide id>`. Listed in the harvest summary
    (temp/harvest/<cc>/summary.md) when there is one, for the review."""
    from worldwide_tv_logos import harvest
    cc = args.country.lower()
    epg = harvest.load_epg(db, cc, net.download, print)
    if epg is None:
        return 0
    source = f'iptv-epg-{cc}'
    known = {a.channel for a in db.aliases.values() if a.source == source}
    taken = {a.epg_id for a in db.aliases.values() if a.source == source}
    found: dict[str, list[dict]] = {}
    for u in registry.units(db, cc):
        if u['id'] in known:
            continue
        epg_id = epg.match(u, harvest.channel_keys(u))
        if epg_id and epg_id not in taken:
            found.setdefault(epg_id, []).append(u)
    added = []
    for epg_id, us in sorted(found.items()):
        u = us[0]
        if len(us) == 1 and (u['id'], '') in db.logos:   # unambiguous, and an alias needs a logo
            ops.set_alias(db, epg_id, source, u['id'])
            added.append((epg_id, u))
    db.save()
    print(f'{len(added)} alias(es) added from the iptv-epg guide of `{cc}`')
    summary = db.root / 'temp' / 'harvest' / cc / 'summary.md'
    if added and summary.is_file():
        lines = ['### New guide aliases', '',
                 f'Guide IDs of the iptv-epg guide matched by name (source `{source}`): check each one.', '']
        lines += [f'- `{epg_id}` -> `{u["id"]}` ({u["name"]})' for epg_id, u in added]
        with open(summary, 'a', encoding='utf-8', newline='\n') as fh:
            fh.write('\n' + '\n'.join(lines) + '\n')
    return 0


def cmd_alias_remove(args, db: Database) -> int:
    for change in ops.remove_alias(db, args.epg_id, args.source):
        print(change)
    db.save()
    return 0


def cmd_changes(args, db: Database) -> int:
    """Open, update or close the single "iptv-org changes" issue from the warnings of `validate`."""
    from worldwide_tv_logos import watch
    iptv = iptvorg.load(db.root)
    warnings: list[str] = []
    validate(db, iptv, warnings)
    # a closed channel keeps its logo, a rename is applied every night by the watch: nothing to do, so they are not
    # listed (the issue can close); what the watch cannot decide is
    warnings = sorted(w for w in warnings if ' closed on ' not in w and ' is replaced by ' not in w)
    warnings += watch.watch(db, iptv)['decisions']            # not saved: the nightly update applies the rest
    warnings += watch.renamed_logos(db)                         # a rename often comes with a new logo
    coming: list[str] = []
    try:
        issues_ = []
        for label in watch.ISSUE_LABELS:
            issues_ += net.GitHub('iptv-org/database').call('GET', f'/issues?state=open&labels={label}&per_page=100')
        coming = watch.coming(issues_, set(db.countries))
    except Exception as exc:  # noqa: BLE001 - the coming list is information only
        print(f'iptv-org issues unavailable ({exc})')
    body = changes_body(warnings, coming)
    if args.dry_run:
        print(body if warnings else 'no change on the iptv-org side')
        return 0
    gh = net.GitHub()
    current = gh.open_issues(CHANGES_LABEL)
    if not warnings:
        for issue in current:
            gh.comment(issue['number'], 'Nothing left to fix: closing.')
            gh.edit_issue(issue['number'], state='closed', state_reason='completed')
        print('no change on the iptv-org side')
        return 0
    if current:
        number = current[0]['number']
        if (current[0].get('body') or '').strip() != body.strip():
            gh.edit_issue(number, body=body)
    else:
        number = gh.create_issue(CHANGES_TITLE, body, [CHANGES_LABEL])
    print(f'issue #{number}: {len(warnings)} change(s)')
    return 0


def _git(root: Path, *args: str) -> bytes:
    import subprocess
    return subprocess.run(['git', *args], cwd=root, capture_output=True, check=True).stdout


def _data_root(root: Path, ref: str, dest: Path) -> Path:
    """A folder holding the data/ index files of a git ref (missing files are left out)."""
    import subprocess
    (dest / 'data').mkdir(parents=True)
    for f in ('logos.csv', 'aliases.csv', 'channels.csv', 'external_ids.csv'):
        out = subprocess.run(['git', 'show', f'{ref}:data/{f}'], cwd=root, capture_output=True, check=False)
        if out.returncode == 0:
            (dest / 'data' / f).write_bytes(out.stdout)
    return dest


FILE_DIRS = ('logos', 'sources', 'missing')


def apply_files(root: Path, base: str, ours: str) -> None:
    """The working tree holds main: the files our commit added, replaced or deleted since `base` (logos/, sources/,
    missing/) are applied on top of it, so that a logo's files follow its row (ours wins for a row both changed). A
    source of main for the same logo under another extension is removed: a logo has one source. data/rejected.csv
    keeps main's rows and adds ours."""
    out = _git(root, 'diff', '--no-renames', '--name-status', '-z', base, ours, '--', *FILE_DIRS).split(b'\0')
    for status, path in zip(out[0::2], out[1::2]):
        if not path:
            continue
        rel = path.decode('utf-8')
        target = root / rel
        if status.startswith(b'D'):
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git(root, 'show', f'{ours}:{rel}'))
        if rel.startswith('sources/'):
            stem = target.name.rsplit('.', 1)[0]
            for other in target.parent.iterdir():
                if other != target and other.name.rsplit('.', 1)[0] == stem:
                    other.unlink()
    rejected = root / 'data' / 'rejected.csv'
    import subprocess
    try:
        theirs = _git(root, 'show', f'{ours}:data/rejected.csv').decode('utf-8').splitlines()
    except subprocess.CalledProcessError:                  # no rejected.csv in our commit
        return
    lines = rejected.read_text(encoding='utf-8').splitlines() if rejected.exists() else theirs[:1]
    known = set(lines)
    lines += [line for line in theirs[1:] if line not in known]
    rejected.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')


def cmd_merge_data(args, db: Database) -> int:
    """data/logos.csv and data/aliases.csv rebuilt from main (`upstream`) and our commit (`ours`), merged row by row
    against their common ancestor (`base`). With --files, the working tree must hold main (`git reset --hard
    origin/main`): our commit's logo files are applied on top of it too, so that no rebase (and no conflict between
    two versions of an image) is needed."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db.merge(*(_data_root(db.root, ref, Path(tmp) / name)
                   for name, ref in (('base', args.base), ('upstream', args.upstream), ('ours', args.ours))))
    db.save()
    if args.files:
        apply_files(db.root, args.base, args.ours)
    return 0


def regressions(db: Database, ref: Database) -> list[str]:
    """Logos whose last replacement is older here than in `ref`: an older version of the logo would come back, as a
    line-by-line merge of two versions of a row can do."""
    out = []
    for key, old in ref.logos.items():
        new = db.logos.get(key)
        if new and (new.updated or new.added) < (old.updated or old.added):
            out.append(f'{new.stem}: version of {new.updated or new.added}, older than the one of '
                       f'{old.updated or old.added}')
    return sorted(out)


def cmd_regress_check(args, db: Database) -> int:
    """Fails when this change brings back an older version of a logo than `ref` has (the commit it starts from)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ref = Database(_data_root(db.root, args.ref, Path(tmp) / 'ref')).load()
    found = regressions(db, ref)
    for line in found:
        print(f'error: {line}')
    print(f'{len(found)} logo(s) older than in {args.ref}')
    return 1 if found else 0


def cmd_export(args, db: Database) -> int:
    """`.api/` for the gh-pages branch (logos.json, aliases.json and, unless offline, the website and its data),
    and `missing/<cc>.md` for the countries of data/countries.csv."""
    api = db.root / '.api'
    api.mkdir(exist_ok=True)
    logos = [logo_record(db, x) for x in sorted(db.logos.values(), key=lambda r: r.key)]
    (api / 'logos.json').write_text(json.dumps(logos, ensure_ascii=False), encoding='utf-8')
    aliases = [{'epg_id': a.epg_id, 'source': a.source, 'channel': a.channel}
               for a in sorted(db.aliases.values(), key=lambda r: r.key)]
    (api / 'aliases.json').write_text(json.dumps(aliases, ensure_ascii=False), encoding='utf-8')
    if (db.root / 'logos').is_dir():                       # the images themselves, served by GitHub Pages
        import shutil
        shutil.rmtree(api / 'logos', ignore_errors=True)
        shutil.copytree(db.root / 'logos', api / 'logos')
    print(f'.api/: {len(logos)} logos, {len(aliases)} aliases')
    if args.offline:
        return 0
    iptv = iptvorg.load(db.root)
    from worldwide_tv_logos import site
    stats = site.build(db, iptv, iptvorg.load_countries(db.root), api)
    print(f".api/ website data: {stats['countries']} countries, {stats['channels']} channels, "
          f"{stats['with_logo']} with a logo")
    have = {k[0] for k in db.logos}
    missing_dir = db.root / 'missing'
    missing_dir.mkdir(exist_ok=True)
    for cc, name in sorted(db.countries.items()):
        channels = [u for u in registry.units(db, cc) if not u['parent']]
        todo = [u for u in channels if u['id'] not in have]
        lines = [f'# {name}: channels without a logo', '',
                 (f'{len(channels) - len(todo)} of {len(channels)} channels have a logo here (editions not counted: '
                  'they use their channel\'s logo). To add one, use the '
                  '[logo form](../../../issues/new?template=01_logos_add.yml).'), '',
                 '| Channel ID | Name | iptv-org ID |', '|---|---|---|']
        lines += [f'| `{u["id"]}` | {u["name"]} | {u["iptv"]} |' for u in todo]
        (missing_dir / f'{cc}.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
        print(f'missing/{cc}.md: {len(todo)} of {len(channels)}')
    return 0


def cmd_watch_iptvorg(args, db: Database) -> int:
    """What changed at iptv-org applied to the registry (renames keep their channel, closures, names), before
    `channels-init` (see watch.py). The summary goes to temp/watch.md (the nightly commit message)."""
    from worldwide_tv_logos import watch
    out = watch.watch(db, iptvorg.load(db.root))
    db.save()
    head = (f'iptv-org watch: {out["renamed"]} renamed (same channel here), {out["closed"]} closed, '
            f'{out["reopened"]} reopened, {out["refreshed"]} name or website updated, {out["removed"]} no longer in '
            f'iptv-org, {len(out["decisions"])} to decide')
    lines = [head, *out['lines'], *[f'- to decide: {d}' for d in out['decisions']]]
    path = db.root / 'temp' / 'watch.md'
    path.parent.mkdir(exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    return 0


def cmd_migrate_ids(args, db: Database) -> int:
    from worldwide_tv_logos import migrate
    stats = migrate.migrate(db)
    print(', '.join(f'{k} {v}' for k, v in stats.items()))
    return 1 if stats['unknown'] else 0


def cmd_channels_init(args, db: Database) -> int:
    """Register (data/channels.csv, data/external_ids.csv) every iptv-org channel and edition we need: those of the
    followed countries, every one with a logo. Only adds what is missing: run every night by the update workflow."""
    stats = registry.init(db, iptvorg.load(db.root), sorted(db.countries))
    db.save()
    print(f'{stats["channels"]} channel(s) and {stats["editions"]} edition(s) registered, {stats["already"]} already '
          f'there, {stats["country changed"]} edition(s) moved to their broadcast country; {len(db.channels)} in the '
          'registry')
    return 0


def _channel(db: Database, ref: str):
    c = registry.resolve(db, ref)
    if c is None:
        print(f'`{ref}`: no such channel (our ID, slug, iptv-org or Wikidata ID)')
    return c


def cmd_channel(args, db: Database) -> int:
    c = registry.resolve(db, args.ref)
    if c is None:                                       # not an ID: channels whose name contains these words
        key = registry.slug_base(args.ref)
        found = sorted((x for x in db.channels.values()
                        if key and any(key in registry.slug_base(n) for n in [x.name, *x.alias_list])),
                       key=lambda x: (x.country, x.name.lower()))
        for x in found[:50]:
            print(f'{x.id}  {x.slug}  {x.name}  ({x.status}{", edition of " + x.parent if x.parent else ""})')
        print(f'{len(found)} channel(s) named like `{args.ref}`' if found else f'`{args.ref}`: no such channel')
        return 0 if found else 1
    for k, v in vars(c).items():
        if v:
            print(f'{k}: {v}')
    for x in sorted((x for x in db.external_ids.values() if x.channel_id == c.id), key=lambda x: x.key):
        print(f'{x.source}: {x.external_id} ({x.method}, {x.added})')
    for e in (e for e in db.channels.values() if e.parent == c.id):
        print(f'{"edition" if e.status != "merged" else "merged into it"}: {e.id} {e.slug} ({e.name})')
    return 0


def cmd_channel_add(args, db: Database) -> int:
    if args.country.lower() not in db.countries and not args.any_country:
        print(f'`{args.country}` is not a followed country (data/countries.csv); --any-country to add it anyway')
        return 1
    parent = _channel(db, args.parent) if args.parent else None
    if args.parent and parent is None:
        return 1
    same = [c for c in db.channels.values() if c.country == args.country.lower()
            and registry.slug_base(args.name) in {registry.slug_base(n) for n in [c.name, *c.alias_list]}]
    if same and not args.force:
        print(f'already in the registry: {", ".join(f"{c.id} ({c.name})" for c in same)}; --force to add anyway')
        return 1
    c = registry.add_channel(db, args.name, args.country, aliases=args.alias or (), website=args.website or '',
                             parent=parent.id if parent else '')
    db.save()
    print(f'{c.id} {c.slug}')
    return 0


def cmd_channel_edit(args, db: Database) -> int:
    c = _channel(db, args.ref)
    if c is None:
        return 1
    if args.name:
        c.name = args.name
        if not args.slug:
            c.slug = registry.make_slug(c.name, c.country, {x.slug for x in db.channels.values() if x.id != c.id})
    if args.slug:
        c.slug = args.slug
    if args.alias is not None:
        c.aliases = ';'.join(a for a in args.alias if a)
    if args.website is not None:
        c.website = args.website
    if args.status:
        c.status = args.status
    if args.parent is not None:
        parent = _channel(db, args.parent) if args.parent else None
        if args.parent and parent is None:
            return 1
        c.parent = parent.id if parent else ''
    c.updated = registry.today()
    errors = registry.check(db)
    if errors:
        print('\n'.join(errors))
        return 1
    db.save()
    print(f'{c.id} {c.slug}')
    return 0


def cmd_channel_map(args, db: Database) -> int:
    c = _channel(db, args.ref)
    if c is None:
        return 1
    key = (args.source, args.external_id)
    if args.remove:
        if db.external_ids.get(key) is None or db.external_ids[key].channel_id != c.id:
            print(f'{args.source}:{args.external_id} is not mapped to {c.id}')
            return 1
        del db.external_ids[key]
    else:
        if args.source not in registry.SOURCES or not registry.SOURCES[args.source].match(args.external_id):
            print(f'{args.source}:{args.external_id}: unknown source or malformed ID ({", ".join(registry.SOURCES)})')
            return 1
        other = db.external_ids.get(key)
        if other is not None and other.channel_id != c.id:
            print(f'{args.source}:{args.external_id} is already mapped to {other.channel_id}')
            return 1
        registry.map_id(db, c, args.source, args.external_id, args.method)
    db.save()
    print(f'{c.id}: {args.source}:{args.external_id} {"removed" if args.remove else "mapped"}')
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog='logos')
    ap.add_argument('--root', default=None, help='repository root (default: this repository)')
    sub = ap.add_subparsers(dest='command', required=True)
    p = sub.add_parser('validate', help='check data/ and every file')
    p.add_argument('--offline', action='store_true', help='do not check ids against iptv-org')
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser('import', help='bulk import from a CSV: channel,feed,origin[,label]')
    p.add_argument('manifest')
    p.add_argument('--pause', type=float, default=5.0, help='seconds between two remote downloads')
    p.add_argument('--offline', action='store_true')
    p.set_defaults(func=cmd_import)
    p = sub.add_parser('issue-validate', help='check one issue request (body in RAW_BODY or --body)')
    p.add_argument('--number', type=int)
    p.add_argument('--labels')
    p.add_argument('--body')
    p.add_argument('--offline', action='store_true')
    p.set_defaults(func=cmd_issue_validate)
    p = sub.add_parser('update', help='apply approved issues (GITHUB_REPOSITORY, GITHUB_TOKEN)')
    p.add_argument('--offline', action='store_true')
    p.set_defaults(func=cmd_update)
    p = sub.add_parser('notify', help='comment the processed issues after the update commit')
    p.add_argument('--commit')
    p.set_defaults(func=cmd_notify)
    p = sub.add_parser('reprocess', help='rebuild the logos from their originals after a change of the image rules')
    p.set_defaults(func=cmd_reprocess)
    p = sub.add_parser('country-add', help='follow countries (data/countries.csv): weekly harvests and hunts')
    p.add_argument('code', nargs='+', help="iptv-org country codes, e.g. de uk us ('uk' for the United Kingdom)")
    p.set_defaults(func=cmd_country_add)
    p = sub.add_parser('harvest', help='collect the best logo of each channel of a country for review (temp/)')
    p.add_argument('--country', required=True, help='two-letter code, e.g. es')
    p.add_argument('--pause', type=float, default=2.0, help='seconds between two downloads')
    p.add_argument('--limit', type=int, default=0, help='only the first N channels (test)')
    p.add_argument('--updates', action='store_true', help='also propose newer or better versions of current logos')
    p.add_argument('--max', type=int, default=700, help='channels per run at most: a weekly slice beyond (0: all)')
    p.add_argument('--offset', type=int, help='slice number (default: the week of the year)')
    p.set_defaults(func=cmd_harvest)
    p = sub.add_parser('epg-check', help='current logos whose iptv-epg guide shows another drawing (newer branding?)')
    p.add_argument('--country', nargs='+', required=True)
    p.add_argument('--review', type=int, default=15, help='cases listed for review at most, per country')
    p.set_defaults(func=cmd_epg_check)
    p = sub.add_parser('site-check', help="current logos looked for on their channel's website (newer branding?)")
    p.add_argument('--country', nargs='+', required=True)
    p.add_argument('--size', type=int, default=150, help='logos checked per country (a different slice every week)')
    p.add_argument('--review', type=int, default=20, help='cases listed for review at most, per country')
    p.add_argument('--offset', type=int, help='slice number (default: the week of the year)')
    p.set_defaults(func=cmd_site_check)
    p = sub.add_parser('dismiss', help='never propose this logo URL again for this channel (data/rejected.csv)')
    p.add_argument('id')
    p.add_argument('url')
    p.add_argument('--reason')
    p.set_defaults(func=cmd_dismiss)
    p = sub.add_parser('bulk', help='add the iptv-org logos of whole countries directly, without review')
    p.add_argument('--country', nargs='+', required=True)
    p.add_argument('--pause', type=float, default=0.3)
    p.set_defaults(func=cmd_bulk)
    p = sub.add_parser('sheet', help='contact sheets of logos of the repository (temp/sheets/)')
    p.add_argument('--changed', action='store_true', help='logos changed since --base')
    p.add_argument('--base', default='origin/main')
    p.add_argument('--channels', help='comma-separated logo IDs, e.g. France3.fr,France3.fr@Alsace')
    p.add_argument('--country')
    p.add_argument('--out')
    p.add_argument('--per-page', type=int, default=30)
    p.set_defaults(func=cmd_sheet)
    p = sub.add_parser('find', help='every candidate logo of a channel, from every source (temp/find/<id>/)')
    p.add_argument('id', help='logo ID, e.g. CanalSur.es or France3.fr@Alsace')
    p.add_argument('--no-wikidata', action='store_true')
    p.add_argument('--pause', type=float, default=1.0)
    p.add_argument('--out')
    p.set_defaults(func=cmd_find)
    p = sub.add_parser('seen-on', help='is a logo shown on a web page (read like a browser)? proof that it is current')
    p.add_argument('page', help='https:// page, e.g. the channel website')
    p.add_argument('logo', help='https:// or data:image URL, local file, or logo ID of this repository')
    p.set_defaults(func=cmd_seen_on)
    p = sub.add_parser('set', help='add or replace a logo from a URL or a file')
    p.add_argument('id')
    p.add_argument('source', help='https:// URL or local file')
    p.add_argument('--origin', help='origin to record (default: the source)')
    p.set_defaults(func=cmd_set)
    p = sub.add_parser('move', help='move the logos and aliases of a channel to another one (a channel registered twice)')
    p.add_argument('old')
    p.add_argument('new')
    p.set_defaults(func=cmd_move)
    p = sub.add_parser('remove', help='remove a logo (with its variant, original and aliases)')
    p.add_argument('id')
    p.set_defaults(func=cmd_remove)
    p = sub.add_parser('verdict', help='record a review decision for the workflow (temp/verdict.json)')
    p.add_argument('state', choices=('ready', 'hold'))
    p.add_argument('text', nargs='?', help='short report in Markdown (default: read from stdin)')
    p.set_defaults(func=cmd_verdict)
    p = sub.add_parser('hunt', help='look for the logos of channels without one, a slice every week (temp/harvest/)')
    p.add_argument('--country', required=True)
    p.add_argument('--limit', type=int, default=40)
    p.add_argument('--sharpen', type=int, default=30,
                   help=f'small logos (under {SHARP_SIDE} px) checked for a sharper version')
    p.add_argument('--offset', type=int, help='slice number (default: the week of the year)')
    p.add_argument('--pause', type=float, default=2.0)
    p.set_defaults(func=cmd_hunt)
    p = sub.add_parser('reject', help='refuse a logo proposed in a harvest pull request')
    p.add_argument('channel')
    p.add_argument('--reason', default='')
    p.add_argument('--base', required=True, help='checkout of the main branch')
    p.add_argument('--unconfirmed', action='store_true',
                   help='no proof found (not wrong): removed from this pull request, proposed again next time')
    p.set_defaults(func=cmd_reject)
    p = sub.add_parser('unreject', help='propose again logos refused before (rows of data/rejected.csv)')
    p.add_argument('--channel', default='', help='this channel or feed only')
    p.add_argument('--date', default='', help='refused on this day only (YYYY-MM-DD)')
    p.add_argument('--reason-contains', default='', help='whose reason contains this text')
    p.set_defaults(func=cmd_unreject)
    p = sub.add_parser('guide-aliases', help='add the aliases of the iptv-epg guide of a country found by name')
    p.add_argument('--country', required=True)
    p.set_defaults(func=cmd_guide_aliases)
    p = sub.add_parser('alias-remove', help='remove a guide alias')
    p.add_argument('source')
    p.add_argument('epg_id')
    p.set_defaults(func=cmd_alias_remove)
    p = sub.add_parser('changes', help='open/update/close the "iptv-org changes" issue (GITHUB_TOKEN)')
    p.add_argument('--dry-run', action='store_true', help='print the issue body instead')
    p.set_defaults(func=cmd_changes)
    p = sub.add_parser('merge-data', help='after a rebase: merge the data files row by row with the commit before it')
    p.add_argument('base', help='common ancestor (git merge-base before the rebase)')
    p.add_argument('ours', help='the commit before the rebase')
    p.add_argument('upstream', nargs='?', default='origin/main', help='the branch rebased onto (default: origin/main)')
    p.add_argument('--files', action='store_true',
                   help='the working tree holds upstream: apply our logo files on top too (no rebase needed)')
    p.set_defaults(func=cmd_merge_data)
    p = sub.add_parser('regress-check', help='fail when a logo is older than in a git ref (an older version back)')
    p.add_argument('ref', help='the commit this change starts from (e.g. origin/main, or the merge base of a PR)')
    p.set_defaults(func=cmd_regress_check)
    p = sub.add_parser('export', help='write .api/ and missing/')
    p.add_argument('--offline', action='store_true', help='skip missing/ (needs iptv-org)')
    p.set_defaults(func=cmd_export)
    p = sub.add_parser('watch-iptvorg', help='apply iptv-org changes to the registry (renames, closures, names)')
    p.set_defaults(func=cmd_watch_iptvorg)
    p = sub.add_parser('migrate-ids', help='one-off (roadmap step 2): logos and their files moved to our channel IDs')
    p.set_defaults(func=cmd_migrate_ids)
    p = sub.add_parser('channels-init', help='register the iptv-org channels we need in our registry (adds only)')
    p.set_defaults(func=cmd_channels_init)
    p = sub.add_parser('channel', help='show a channel of the registry (our ID, slug, iptv-org or Wikidata ID), or find channels by name')
    p.add_argument('ref')
    p.set_defaults(func=cmd_channel)
    p = sub.add_parser('channel-add', help='add a channel to the registry (a new ch_ ID)')
    p.add_argument('name')
    p.add_argument('--country', required=True, help='two-letter code')
    p.add_argument('--alias', action='append', help='another name (repeat for several)')
    p.add_argument('--website')
    p.add_argument('--parent', help='main channel of this edition')
    p.add_argument('--any-country', action='store_true', help='allow a country that is not followed')
    p.add_argument('--force', action='store_true', help='add even if a channel of the country has the same name')
    p.set_defaults(func=cmd_channel_add)
    p = sub.add_parser('channel-edit', help='change a channel of the registry (its ID never changes)')
    p.add_argument('ref')
    p.add_argument('--name', help='new name (the slug follows unless --slug)')
    p.add_argument('--slug')
    p.add_argument('--alias', action='append', help='other names, replacing the current ones (repeat; "" for none)')
    p.add_argument('--website')
    p.add_argument('--status', choices=registry.STATUSES)
    p.add_argument('--parent', help='main channel, or the channel it merged into ("" for none)')
    p.set_defaults(func=cmd_channel_edit)
    p = sub.add_parser('channel-map', help='map an iptv-org or Wikidata ID to a channel of the registry')
    p.add_argument('ref')
    p.add_argument('source', choices=sorted(registry.SOURCES))
    p.add_argument('external_id')
    p.add_argument('--method', default='review', choices=registry.METHODS)
    p.add_argument('--remove', action='store_true')
    p.set_defaults(func=cmd_channel_map)
    args = ap.parse_args(argv)
    db = Database(Path(args.root)) if args.root else Database()
    db.load()
    return args.func(args, db)


if __name__ == '__main__':
    sys.exit(main())
