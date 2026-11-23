"""One-off migration of roadmap step 2 (`logos migrate-ids`): logos, originals, guide aliases and refused URLs move
from iptv-org IDs (`logos/fr/France3.fr@Alsace.png`) to our channel IDs (`logos/ch_xxxxxxxxxx.png`), through
data/external_ids.csv. Reads the old files directly; to be removed once run.
"""
from __future__ import annotations

import csv
from pathlib import Path

from worldwide_tv_logos import registry
from worldwide_tv_logos.db import Alias, Database, Logo


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


def migrate(db: Database, log=print) -> dict[str, int]:
    data = db.data_dir
    stats = {'logos': 0, 'files': 0, 'aliases': 0, 'rejected': 0, 'unknown': 0}

    def target(channel: str, feed: str = '') -> str | None:
        logo_id = channel + (f'@{feed}' if feed else '')
        c = registry.by_logo_id(db, logo_id)
        if c is None:
            log(f'{logo_id}: not in the registry')
            stats['unknown'] += 1
        return c.id if c else None

    old_logos = _rows(data / 'logos.csv')
    if old_logos and 'feed' not in old_logos[0]:
        log('data/logos.csv already uses our IDs: nothing to do')
        return stats
    db.logos = {}
    for r in old_logos:
        cid = target(r['channel'], r['feed'])
        if cid is None:
            continue
        cc = r['channel'].rsplit('.', 1)[-1]
        stem = r['channel'] + (f'@{r["feed"]}' if r['feed'] else '')
        logo = Logo(cid, r['variant'], int(r['width'] or 0), int(r['height'] or 0), r['origin'], r['added'],
                    r['updated'])
        moves = [(db.root / 'logos' / cc / f'{stem}{"." + r["variant"] if r["variant"] else ""}.png',
                  db.path(logo.file))]
        if not r['variant']:
            moves += [(p, db.root / 'sources' / f'{cid}{p.suffix}')
                      for p in sorted((db.root / 'sources' / cc).glob(f'{stem}.*'))]
        for src, dst in moves:
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.replace(dst)
                stats['files'] += 1
        db.logos[logo.key] = logo
        stats['logos'] += 1
    for folder in ('logos', 'sources'):                       # the emptied country folders
        for d in sorted((db.root / folder).glob('*/'), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
    db.aliases = {}
    for r in _rows(data / 'aliases.csv'):
        cid = target(r['channel'], r.get('feed', ''))
        if cid:
            a = Alias(r['epg_id'], r['source'], cid)
            db.aliases[a.key] = a
            stats['aliases'] += 1
    rejected = _rows(data / 'rejected.csv')
    with (data / 'rejected.csv').open('w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['channel', 'url', 'reason', 'date'])
        for r in rejected:
            channel, _, feed = r['channel'].partition('@')
            cid = r['channel'] if registry.ID_RE.match(r['channel']) else target(channel, feed)
            if cid:
                w.writerow([cid, r['url'], r['reason'], r['date']])
                stats['rejected'] += 1
    db.save()
    return stats
