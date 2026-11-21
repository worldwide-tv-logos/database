"""Command line: `uv run logos <command>` (see .github/docs/scripts.md)."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

from worldwide_tv_logos import image, iptvorg, issues, net, ops
from worldwide_tv_logos.db import CHANNEL_RE, FEED_RE, VARIANTS, Database, parse_logo_id

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _iptv(db: Database, offline: bool):
    return None if offline else iptvorg.load(db.root)


def validate(db: Database, iptv, warnings: list[str] | None = None) -> list[str]:
    """Errors (blocking). Changes on the iptv-org side (channel removed, closed, replaced) go to `warnings`: they
    must never block the nightly update."""
    errors = []
    warnings = [] if warnings is None else warnings
    for logo in db.logos.values():
        where = f'data/logos.csv {logo.stem}'
        if not CHANNEL_RE.match(logo.channel) or (logo.feed and not FEED_RE.match(logo.feed)):
            errors.append(f'{where}: malformed iptv-org id')
            continue
        if logo.variant not in VARIANTS:
            errors.append(f'{where}: unknown variant `{logo.variant}` ({", ".join(v for v in VARIANTS if v)})')
        if logo.variant and (logo.channel, logo.feed, '') not in db.logos:
            errors.append(f'{where}: variant without the logo itself')
        if not logo.origin:
            errors.append(f'{where}: origin missing')
        if not DATE_RE.match(logo.added) or (logo.updated and not DATE_RE.match(logo.updated)):
            errors.append(f'{where}: dates must be YYYY-MM-DD')
        if iptv is not None and not logo.variant and (warn := iptv.status_warning(logo.channel, logo.feed)):
            warnings.append(f'{where}: {warn}')
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
            errors.append(f'{where}: exactly one original expected in sources/{logo.country}/ '
                          f'({len(db.source_files(logo))} found)')
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
        if (alias.channel, alias.feed, '') not in db.logos:
            errors.append(f'data/aliases.csv {alias.source}:{alias.epg_id}: no logo for '
                          f'{alias.channel}{"@" + alias.feed if alias.feed else ""}')
    for code in db.countries:
        if not re.match(r'^[a-z]{2}$', code):
            errors.append(f'data/countries.csv: `{code}` must be a lowercase two-letter code')
    return errors


def cmd_validate(args, db: Database) -> int:
    warnings: list[str] = []
    errors = validate(db, _iptv(db, args.offline), warnings)
    for w in warnings:
        print(f'warning: {w}')
    for e in errors:
        print(e)
    print(f'{len(db.logos)} logos, {len(db.aliases)} aliases, {len(errors)} error(s), {len(warnings)} warning(s)')
    return 1 if errors else 0


def cmd_import(args, db: Database) -> int:
    """Bulk import from a CSV (channel,feed,origin) where origin is an https URL or a local file."""
    iptv = _iptv(db, args.offline)
    with open(args.manifest, encoding='utf-8', newline='') as fh:
        rows = list(csv.DictReader(fh))
    failed = 0
    last_remote = 0.0
    for row in rows:
        channel, feed, origin = row['channel'].strip(), (row.get('feed') or '').strip(), row['origin'].strip()
        label = channel + (f'@{feed}' if feed else '')
        try:
            if origin.startswith('https://'):
                wait = last_remote + args.pause - time.time()
                if wait > 0:
                    time.sleep(wait)
                data = net.download(origin)
                last_remote = time.time()
            else:
                data = Path(origin).read_bytes()
            for change in ops.set_logo(db, channel, feed, data, row.get('label') or origin, iptv):
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
    channel, feed, url = req.get('channel'), req.get('feed'), req.get('url')
    label = channel + (f'@{feed}' if feed else '')
    rows = []
    try:
        data = net.download(url)
        img = image.prepare(data)[0]
        rows.append(({'id': label, 'name': f'proposed: {label}'},
                     harvest.Candidate('request', url, data, image.is_svg(data), img.size)))
        old = db.logos.get((channel, feed, ''))
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
    waiting = ''
    try:
        req = issues.parse(args.number or 0, labels, body)
        errors = issues.validate(req, db, _iptv(db, args.offline))
        waiting = req.waiting
    except ops.RequestError as exc:
        errors = [str(exc)]
    out = db.root / 'temp' / 'errors.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(f'- {e}' for e in errors), encoding='utf-8')
    (db.root / 'temp' / 'waiting.md').write_text(
        (f'{waiting}.\n\nThe image is fine. This request waits for the channel to be added to iptv-org '
         '([form](https://github.com/iptv-org/database/issues/new?template=01_channels_add.yml); use exactly the '
         'same ID). Once approved here, it is checked again every night and applied as soon as iptv-org has the '
         'channel: nothing else to do.') if waiting and not errors else '', encoding='utf-8')
    if waiting and not errors:
        print(f'waiting: {waiting}')
    if not errors and req.kind in ('logos:add', 'logos:edit'):
        _preview(db, req)
    for e in errors:
        print(e)
    return 1 if errors else 0


def cmd_update(args, db: Database) -> int:
    """Apply approved issues, one by one: a faulty request is reported on its issue and skipped, never blocking
    the others."""
    gh = net.GitHub()
    iptv = _iptv(db, args.offline)
    done, notes = [], {}
    for raw in gh.approved_issues():
        labels = [label['name'] for label in raw['labels']]
        snapshot = (dict(db.logos), dict(db.aliases))
        try:
            req = issues.parse(raw['number'], labels, raw.get('body') or '')
            changes = issues.apply(req, db, iptv)
        except ops.NotInIptvOrg as exc:
            db.logos, db.aliases = snapshot
            print(f'#{raw["number"]}: waiting — {exc}')
            if 'waiting:iptv-org' not in labels:
                gh.add_labels(raw['number'], ['waiting:iptv-org'])
            continue
        except ops.RequestError as exc:
            db.logos, db.aliases = snapshot
            print(f'#{raw["number"]}: skipped — {exc}')
            gh.comment(raw['number'], f'This request could not be applied:\n\n- {exc}\n\n'
                                      'Please edit the issue to fix it; it will be checked again.')
            gh.remove_label(raw['number'], 'approved')
            gh.add_labels(raw['number'], ['check:failed'])
            continue
        print(f'#{raw["number"]}: ' + '; '.join(changes))
        if 'waiting:iptv-org' in labels:
            gh.remove_label(raw['number'], 'waiting:iptv-org')
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
        expected = {'': image.png_bytes(img), 'white': image.png_bytes(white) if white is not None else None}
        current = {v: (db.path(db.logos[(logo.channel, logo.feed, v)].file).read_bytes()
                       if (logo.channel, logo.feed, v) in db.logos else None) for v in ('', 'white')}
        if expected == current:
            continue
        changed += 1
        for change in ops.set_logo(db, logo.channel, logo.feed, original, logo.origin, None):
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
        stems = sorted(x.logo_id for x in db.logos.values() if not x.variant and x.country == args.country.lower())
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
    channel, feed = parse_logo_id(args.id)
    iptv = iptvorg.load(db.root)
    c = iptv.channels.get(channel)
    if c is None:
        print(f'`{channel}` is not in iptv-org')
        return 1
    cc = (c.get('country') or channel.rsplit('.', 1)[-1]).lower()
    logos = [x for x in iptvorg.load_logos(db.root) if x['channel'] == channel and (x.get('feed') or '') == feed]
    unit = next((u for u in harvest.units(iptv, cc) if u['id'] == args.id), dict(c, channel=channel, feed=feed))
    extra = harvest.more_candidates(db.root, unit, cc, not args.no_wikidata, True, net.download, print,
                                    harvest.load_epg(db, cc, net.download, print))
    cands = harvest.candidates(unit, {(channel, feed): logos}, extra)
    rejected = harvest.load_rejected(db.root)
    for i, cand in enumerate(cands):
        if i:
            time.sleep(args.pause)
        harvest.evaluate(cand, net.download)
        if (channel, cand.url) in rejected:
            cand.error = 'rejected before (data/rejected.csv)'
    cands.sort(key=lambda x: x.score, reverse=True)
    out = Path(args.out) if args.out else db.root / 'temp' / 'find' / args.id
    out.mkdir(parents=True, exist_ok=True)
    good = [x for x in cands if not x.error]
    tiles = []
    current = db.logos.get((channel, feed, ''))
    if current is not None:
        white = db.logos.get((channel, feed, 'white'))
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
          + f'; apply one with `logos set {args.id} <url>`')
    return 0


def cmd_set(args, db: Database) -> int:
    """Add or replace a logo from a URL or a local file (same preparation and checks as a request)."""
    channel, feed = parse_logo_id(args.id)
    try:
        data = net.download(args.source) if args.source.startswith('https://') else Path(args.source).read_bytes()
        for change in ops.set_logo(db, channel, feed, data, args.origin or args.source, iptvorg.load(db.root)):
            print(change)
    except (ops.RequestError, net.DownloadError, OSError) as exc:
        print(f'refused: {exc}')
        return 1
    db.save()
    return 0


def cmd_move(args, db: Database) -> int:
    """Move the logos and aliases of a channel to its new iptv-org ID."""
    try:
        changes = ops.move_channel(db, args.old, args.new, iptvorg.load(db.root))
    except ops.RequestError as exc:
        print(f'refused: {exc}')
        return 1
    db.save()
    print('\n'.join(changes))
    return 0


def cmd_remove(args, db: Database) -> int:
    """Remove a logo (channel or feed, with its variant, original and aliases)."""
    channel, feed = parse_logo_id(args.id)
    try:
        changes = ops.remove_logo(db, channel, feed)
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


def cmd_hunt(args, db: Database) -> int:
    """Logos of channels still without one: a different slice of them every week, every source including their
    website, for review like a harvest."""
    import datetime
    import shutil

    from worldwide_tv_logos import harvest
    cc = args.country.lower()
    iptv = iptvorg.load(db.root)
    have = {x.logo_id for x in db.logos.values()}
    missing = [u['id'] for u in harvest.units(iptv, cc) if u['id'] not in have]
    if not missing:
        print('no channel without a logo')
        return 0
    week = datetime.date.today().isocalendar()[1] if args.offset is None else args.offset
    start = (week * args.limit) % len(missing)
    only = (missing[start:] + missing[:start])[:args.limit]
    out = db.root / 'temp' / 'harvest' / cc
    shutil.rmtree(out, ignore_errors=True)
    stats = harvest.harvest(db, iptv, cc, iptvorg.load_logos(db.root), out, pause=args.pause, deep=True, only=only)
    print(f"hunt: {stats['kept']} logo(s) found for {len(only)} of the {len(missing)} channels without one; "
          f"{out.as_posix()}/summary.md")
    return 0


def cmd_harvest(args, db: Database) -> int:
    from worldwide_tv_logos import harvest
    cc = args.country.lower()
    out = db.root / 'temp' / 'harvest' / cc
    import shutil
    shutil.rmtree(out, ignore_errors=True)
    stats = harvest.harvest(db, iptvorg.load(db.root), cc, iptvorg.load_logos(db.root), out,
                            pause=args.pause, limit=args.limit, updates=args.updates)
    print(f"{stats['kept']} logo(s) to review ({stats['updates']} update(s), {stats['doubts']} doubt(s)) among "
          f"{stats['channels']} channels, {stats['candidates']} candidates; {out.as_posix()}/sheet-*.png, "
          f"then `logos import {out.as_posix()}/manifest.csv`")
    return 0


def cmd_reject(args, db: Database) -> int:
    """Refuse a logo proposed in a harvest pull request: the channel gets back its logo of `--base` (the main
    branch), and its URL goes to data/rejected.csv so that it is never proposed again."""
    from datetime import date
    channel, feed = parse_logo_id(args.channel)
    if not CHANNEL_RE.match(channel) or (feed and not FEED_RE.match(feed)):
        print(f'`{args.channel}` is not an iptv-org channel or feed ID')
        return 1
    logo = db.logos.get((channel, feed, ''))
    if logo is None:
        print(f'no logo for `{channel}` in this branch')
        return 1
    base = Database(Path(args.base)).load()
    if base.logos.get((channel, feed, '')) and base.logos[(channel, feed, '')].origin == logo.origin:
        print(f'`{args.channel}` is not changed by this pull request')
        return 1
    for key in [k for k in db.logos if k[:2] == (channel, feed)]:
        ops.remove_files(db, db.logos.pop(key))
    for key, old in base.logos.items():
        if key[:2] == (channel, feed):
            db.logos[key] = old
            for rel in [old.file] + [p.relative_to(base.root).as_posix() for p in base.source_files(old)]:
                target = db.path(rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base.path(rel).read_bytes())
    db.save()
    path = db.root / 'data' / 'rejected.csv'
    new = not path.is_file()
    with open(path, 'a', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        if new:
            w.writerow(['channel', 'url', 'reason', 'date'])
        w.writerow([args.channel, logo.origin, args.reason or '', date.today().isoformat()])
    print(f'rejected {logo.origin} for `{args.channel}`')
    return 0


def logo_record(x) -> dict:
    """One entry of logos.json: the fields of iptv-org's logos.json (drop-in), then ours."""
    return {'channel': x.channel, 'feed': x.feed or None, 'in_use': True, 'tags': [x.variant] if x.variant else [],
            'width': x.width, 'height': x.height, 'format': 'PNG', 'url': x.url,
            'country': x.country, 'variant': x.variant or None, 'updated': x.updated or x.added}


CHANGES_LABEL = 'iptv-org:changes'
CHANGES_TITLE = 'Changes on the iptv-org side'


def changes_body(warnings: list[str]) -> str:
    return '\n'.join([
        ('Logos whose channel changed in iptv-org since they were added (found by `logos validate`, '
        'refreshed every week by the `changes` workflow).'), '',
        ('To fix one: a replaced channel gets its logo moved to the new ID (open a logos/add request for the new '
        'ID with the same image, then a logos/remove request for the old one); a channel removed for good gets '
        'its logo removed; a closed channel can keep its logo.'), '',
        *[f'- [ ] {w}' for w in warnings], '',
        'This issue closes by itself when the list is empty.'])


def cmd_changes(args, db: Database) -> int:
    """Open, update or close the single "iptv-org changes" issue from the warnings of `validate`."""
    warnings: list[str] = []
    validate(db, iptvorg.load(db.root), warnings)
    warnings.sort()
    body = changes_body(warnings)
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


def cmd_export(args, db: Database) -> int:
    """`.api/` for the gh-pages branch (logos.json, aliases.json and, unless offline, the website and its data),
    and `missing/<cc>.md` for the countries of data/countries.csv."""
    api = db.root / '.api'
    api.mkdir(exist_ok=True)
    logos = [logo_record(x) for x in sorted(db.logos.values(), key=lambda r: r.key)]
    (api / 'logos.json').write_text(json.dumps(logos, ensure_ascii=False), encoding='utf-8')
    aliases = [{'epg_id': a.epg_id, 'source': a.source, 'channel': a.channel, 'feed': a.feed or None}
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
        channels = sorted(iptv.country_channels(cc), key=lambda c: c['name'].lower())
        todo = [c for c in channels if c['id'] not in have]
        lines = [f'# {name}: channels without a logo', '',
                 (f'{len(channels) - len(todo)} of {len(channels)} iptv-org channels have a logo here. '
                  'To add one, use the [logo form](../../../issues/new?template=01_logos_add.yml).'), '',
                 '| Channel ID | Name |', '|---|---|']
        lines += [f'| `{c["id"]}` | {c["name"]} |' for c in todo]
        (missing_dir / f'{cc}.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
        print(f'missing/{cc}.md: {len(todo)} of {len(channels)}')
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
    p = sub.add_parser('harvest', help='collect the best logo of each channel of a country for review (temp/)')
    p.add_argument('--country', required=True, help='two-letter code, e.g. es')
    p.add_argument('--pause', type=float, default=2.0, help='seconds between two downloads')
    p.add_argument('--limit', type=int, default=0, help='only the first N channels (test)')
    p.add_argument('--updates', action='store_true', help='also propose newer or better versions of current logos')
    p.set_defaults(func=cmd_harvest)
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
    p = sub.add_parser('set', help='add or replace a logo from a URL or a file')
    p.add_argument('id')
    p.add_argument('source', help='https:// URL or local file')
    p.add_argument('--origin', help='origin to record (default: the source)')
    p.set_defaults(func=cmd_set)
    p = sub.add_parser('move', help='move the logos and aliases of a channel to its new iptv-org ID')
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
    p.add_argument('--offset', type=int, help='slice number (default: the week of the year)')
    p.add_argument('--pause', type=float, default=2.0)
    p.set_defaults(func=cmd_hunt)
    p = sub.add_parser('reject', help='refuse a logo proposed in a harvest pull request')
    p.add_argument('channel')
    p.add_argument('--reason', default='')
    p.add_argument('--base', required=True, help='checkout of the main branch')
    p.set_defaults(func=cmd_reject)
    p = sub.add_parser('changes', help='open/update/close the "iptv-org changes" issue (GITHUB_TOKEN)')
    p.add_argument('--dry-run', action='store_true', help='print the issue body instead')
    p.set_defaults(func=cmd_changes)
    p = sub.add_parser('export', help='write .api/ and missing/')
    p.add_argument('--offline', action='store_true', help='skip missing/ (needs iptv-org)')
    p.set_defaults(func=cmd_export)
    args = ap.parse_args(argv)
    db = Database(Path(args.root)) if args.root else Database()
    db.load()
    return args.func(args, db)


if __name__ == '__main__':
    sys.exit(main())
