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

from owntv_logos import image, iptvorg, issues, net, ops
from owntv_logos.db import CHANNEL_RE, FEED_RE, VARIANTS, Database

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _iptv(db: Database, offline: bool):
    return None if offline else iptvorg.load(db.root)


def validate(db: Database, iptv) -> list[str]:
    errors = []
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
        if iptv is not None and (err := iptv.channel_error(logo.channel, logo.feed)):
            errors.append(f'{where}: {err}')
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
    errors = validate(db, _iptv(db, args.offline))
    for e in errors:
        print(e)
    print(f'{len(db.logos)} logos, {len(db.aliases)} aliases, {len(errors)} error(s)')
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


def cmd_issue_validate(args, db: Database) -> int:
    body = os.environ.get('RAW_BODY', '') if args.body is None else args.body
    labels = [x.strip() for x in (args.labels or '').split(',') if x.strip()]
    try:
        req = issues.parse(args.number or 0, labels, body)
        errors = issues.validate(req, db, _iptv(db, args.offline))
    except ops.RequestError as exc:
        errors = [str(exc)]
    out = db.root / 'temp' / 'errors.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(f'- {e}' for e in errors), encoding='utf-8')
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
        except ops.RequestError as exc:
            db.logos, db.aliases = snapshot
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


def cmd_export(args, db: Database) -> int:
    """`.api/` (logos.json, aliases.json) for the gh-pages branch, and `missing/<cc>.md` for contributors."""
    api = db.root / '.api'
    api.mkdir(exist_ok=True)
    logos = [{'channel': x.channel, 'feed': x.feed or None, 'variant': x.variant or None, 'width': x.width,
              'height': x.height, 'url': x.url, 'updated': x.updated or x.added} for x in
             sorted(db.logos.values(), key=lambda r: r.key)]
    (api / 'logos.json').write_text(json.dumps(logos, ensure_ascii=False), encoding='utf-8')
    aliases = [{'epg_id': a.epg_id, 'source': a.source, 'channel': a.channel, 'feed': a.feed or None}
               for a in sorted(db.aliases.values(), key=lambda r: r.key)]
    (api / 'aliases.json').write_text(json.dumps(aliases, ensure_ascii=False), encoding='utf-8')
    print(f'.api/: {len(logos)} logos, {len(aliases)} aliases')
    if args.offline or not db.countries:
        return 0
    iptv = iptvorg.load(db.root)
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
        (missing_dir / f'{cc}.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
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
    p = sub.add_parser('export', help='write .api/ and missing/')
    p.add_argument('--offline', action='store_true', help='skip missing/ (needs iptv-org)')
    p.set_defaults(func=cmd_export)
    args = ap.parse_args(argv)
    db = Database(Path(args.root)) if args.root else Database()
    db.load()
    return args.func(args, db)


if __name__ == '__main__':
    sys.exit(main())
