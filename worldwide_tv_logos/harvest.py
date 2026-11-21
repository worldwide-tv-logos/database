"""Bulk harvest of the logos of a country, for a pull request (`logos harvest --country <cc>`).

For each open iptv-org channel of the country that has no logo here yet:

1. candidates from tv-logos (https://github.com/tv-logo/tv-logos, folder of the country, matched on the channel
   name, its alternative names and its ID) and from iptv-org's logos.json (logos of the channel itself);
2. each candidate is downloaded (one at a time, with a pause) and goes through the same preparation as a request
   (image.prepare: trimmed, white frame removed, at least 500 px); refused candidates are reported;
3. the best one is kept: SVG first, then the largest, tv-logos before iptv-org at equal size (more recent).

Nothing is written to data/: the result goes to temp/harvest/<cc>/ (originals, manifest.csv for `logos import`,
report.csv, contact sheets to review by eye). Only the reviewed manifest is imported.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont

from worldwide_tv_logos import image, net
from worldwide_tv_logos.db import Database
from worldwide_tv_logos.iptvorg import IptvOrg

TV_LOGOS_REPO = 'tv-logo/tv-logos'
TV_LOGOS_TREE = f'https://api.github.com/repos/{TV_LOGOS_REPO}/git/trees/main?recursive=1'
TV_LOGOS_RAW = f'https://raw.githubusercontent.com/{TV_LOGOS_REPO}/main/'
TREE_MAX_AGE = 7 * 86400
SOURCE_RANK = {'tv-logos': 1, 'iptv-org': 0}
FOLDER_OVERRIDES = {'uk': 'united-kingdom', 'us': 'united-states', 'ae': 'united-arab-emirates'}


def key(text: str) -> str:
    """Comparison key: no accents, lowercase, letters, digits and '+' ("Canal+" differs from "Canal")."""
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9+]', '', text.lower())


def channel_keys(c: dict) -> set[str]:
    names = [c.get('name') or '', *(c.get('alt_names') or []), c['id'].split('.')[0]]
    keys = set()
    for n in names:
        keys |= {key(n), key(n.replace('+', 'plus'))}
    return {k for k in keys if k}


def stem_keys(stem: str) -> set[str]:
    """`la-1-es` -> {'la1'}; `canal-plus-series-fr` -> {'canal+series', 'canalplusseries'}; `-hz` = same channel."""
    tokens = stem.lower().split('-')[:-1]               # last token: country code
    if tokens and tokens[-1] == 'hz':
        tokens = tokens[:-1]
    if not tokens:
        return set()
    return {key(''.join('+' if t == 'plus' else t for t in tokens)), key(''.join(tokens))}


def tv_logos_index(paths: list[str], folder: str) -> dict[str, list[str]]:
    """key -> paths of `countries/<folder>/<stem>.png` (no old versions, no sub-folders, no white versions)."""
    out: dict[str, list[str]] = {}
    for path in paths:
        parts = path.split('/')
        if len(parts) != 3 or parts[:2] != ['countries', folder] or not path.endswith('.png'):
            continue
        stem = parts[2][:-4]
        if 'white' in stem.split('-'):
            continue
        for k in stem_keys(stem):
            out.setdefault(k, []).append(path)
    return out


def load_tree(root: Path, opener=None) -> list[str]:
    path = Path(root) / '.cache' / 'tv-logos-tree.json'
    if path.is_file() and time.time() - path.stat().st_mtime < TREE_MAX_AGE:
        return json.loads(path.read_text(encoding='utf-8'))
    req = urllib.request.Request(TV_LOGOS_TREE, headers={'User-Agent': net.USER_AGENT,
                                                         'Accept': 'application/vnd.github+json'})
    with (opener or urllib.request.urlopen)(req, timeout=120) as resp:
        tree = json.loads(resp.read())
    paths = [e['path'] for e in tree.get('tree', []) if e.get('type') == 'blob']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(paths), encoding='utf-8')
    return paths


def folder_of(cc: str, countries: list[dict]) -> str:
    if cc in FOLDER_OVERRIDES:
        return FOLDER_OVERRIDES[cc]
    name = next((x['name'] for x in countries if x['code'].lower() == cc), cc)
    return '-'.join(key(w) for w in name.split())          # "Spain" -> spain, "Saudi Arabia" -> saudi-arabia


@dataclass
class Candidate:
    source: str
    url: str
    data: bytes = b''
    svg: bool = False
    size: tuple[int, int] = (0, 0)
    error: str = ''
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> tuple:
        return (not self.error, self.svg, min(max(self.size), 1200), SOURCE_RANK.get(self.source, 0))


def candidates(c: dict, tv_index: dict[str, list[str]], iptv_logos: dict[str, list[dict]]) -> list[Candidate]:
    out: list[Candidate] = []
    seen = set()
    for k in sorted(channel_keys(c)):
        for path in tv_index.get(k, ()):
            if path not in seen:
                seen.add(path)
                out.append(Candidate('tv-logos', TV_LOGOS_RAW + quote(path)))
    logos = sorted((x for x in iptv_logos.get(c['id'], ()) if not x.get('feed') and x.get('in_use', True)
                    and 'white' not in (x.get('tags') or []) and str(x.get('url', '')).startswith('https://')),
                   key=lambda x: (x.get('format') != 'SVG', -(x.get('width') or 0)))
    out += [Candidate('iptv-org', x['url']) for x in logos[:2]]
    return out


def evaluate(cand: Candidate, downloader) -> Candidate:
    try:
        cand.data = downloader(cand.url)
        img, cand.notes = image.prepare(cand.data)
        cand.svg = image.is_svg(cand.data)
        cand.size = img.size
        if len(image.png_bytes(img)) > image.MAX_FILE:
            cand.error = 'heavier than 1 MB once converted'
    except (image.ImageError, net.DownloadError) as exc:
        cand.error = str(exc)
    return cand


def _font(size: int):
    for name in ('arial.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheets(rows: list[tuple[dict, Candidate]], out: Path, per_page: int = 30) -> list[Path]:
    """Pages of 3 columns: each logo on a dark and on a light tile, with its channel, ID, source and size."""
    tw, th, cols, cap = 260, 146, 3, 42
    font, small = _font(16), _font(13)
    pages = []
    for p in range(0, len(rows), per_page):
        chunk = rows[p:p + per_page]
        lines = (len(chunk) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * (2 * tw + 30), lines * (th + cap + 16) + 10), '#ffffff')
        draw = ImageDraw.Draw(sheet)
        for i, (c, cand) in enumerate(chunk):
            x, y = (i % cols) * (2 * tw + 30) + 10, (i // cols) * (th + cap + 16) + 10
            img, _ = image.prepare(cand.data)
            img, white = image.variants(img)
            for j, (bg, pic) in enumerate((('#14181f', white or img), ('#eceef1', img))):
                tile = Image.new('RGB', (tw, th), bg)
                pic = pic.copy()
                pic.thumbnail((int(tw * .8), int(th * .8)))
                tile.paste(pic, ((tw - pic.width) // 2, (th - pic.height) // 2), pic)
                sheet.paste(tile, (x + j * (tw + 4), y))
            draw.text((x, y + th + 3), f'{p + i + 1}. {c["name"]}', fill='#111111', font=font)
            draw.text((x, y + th + 23), f'{c["id"]}  {cand.source}  {cand.size[0]}x{cand.size[1]}'
                      + ('  SVG' if cand.svg else ''), fill='#555555', font=small)
        path = out / f'sheet-{p // per_page + 1:02d}.png'
        sheet.save(path)
        pages.append(path)
    return pages


def split_duplicates(kept: list[tuple[dict, Candidate]], existing: dict[str, str] | None = None
                     ) -> tuple[list, list]:
    """The same image chosen for several channels (a regional channel given the national logo), or already used by
    another channel here (`existing`: origin URL -> channel), is a doubt: within a group only the channel with the
    shortest name keeps it (24 Horas, not 24 Horas Canarias)."""
    existing = existing or {}
    groups: dict[str, list[tuple[dict, Candidate]]] = {}
    doubts = []
    for c, cand in kept:
        if existing.get(cand.url, c['id']) != c['id']:
            doubts.append((c, existing[cand.url]))
            continue
        groups.setdefault(hashlib.sha1(cand.data).hexdigest(), []).append((c, cand))
    out = []
    for group in groups.values():
        group.sort(key=lambda x: (len(x[0]['name']), x[0]['name']))
        out.append(group[0])
        doubts += [(c, group[0][0]['id']) for c, _ in group[1:]]
    out.sort(key=lambda x: x[0]['name'].lower())
    return out, doubts


def load_rejected(root: Path) -> set[tuple[str, str]]:
    """(channel, url) pairs refused in review (data/rejected.csv): never proposed again."""
    path = Path(root) / 'data' / 'rejected.csv'
    if not path.is_file():
        return set()
    with open(path, encoding='utf-8', newline='') as fh:
        return {(r['channel'], r['url']) for r in csv.DictReader(fh)}


def update_reason(logo, source: Path, best: Candidate, iptv_urls: set[str]) -> str | None:
    """Why the best candidate should replace the current logo, or None (no clear improvement)."""
    current = source.read_bytes()
    if best.data == current:
        return None
    if best.url == logo.origin:
        return 'the original changed at its source'
    if best.svg and not image.is_svg(current):
        return 'vector (SVG) version found'
    if max(best.size) >= 1.5 * max(logo.width, logo.height):
        return f'larger ({best.size[0]}x{best.size[1]} instead of {logo.width}x{logo.height})'
    if best.source == 'iptv-org' and logo.origin.startswith('https://') and logo.origin not in iptv_urls \
            and iptv_urls:
        return 'iptv-org replaced the logo of this channel'
    return None


def harvest(db: Database, iptv: IptvOrg, cc: str, folder: str, iptv_logos: list[dict], tree: list[str],
            out: Path, pause: float = 2.0, limit: int = 0, updates: bool = False, downloader=None,
            log=print) -> dict[str, int]:
    """Missing logos of the country (and, with `updates`, better or newer versions of its current logos) into
    out/: originals, manifest.csv for `logos import`, report.csv, doubts.csv, summary.md, contact sheets."""
    downloader = downloader or net.download
    current = {k[0]: x for k, x in db.logos.items() if not k[1] and not k[2]}
    channels = sorted((c for c in iptv.country_channels(cc) if updates or c['id'] not in current),
                      key=lambda c: c['name'].lower())
    if limit:
        channels = channels[:limit]
    rejected = load_rejected(db.root)
    tv_index = tv_logos_index(tree, folder)
    by_channel: dict[str, list[dict]] = {}
    for x in iptv_logos:
        by_channel.setdefault(x['channel'], []).append(x)
    (out / 'originals').mkdir(parents=True, exist_ok=True)
    report, kept, changes = [], [], {}
    last = 0.0
    for c in channels:
        cands = [x for x in candidates(c, tv_index, by_channel) if (c['id'], x.url) not in rejected]
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
        if c['id'] in current:
            logo = current[c['id']]
            sources = db.source_files(logo)
            urls = {x['url'] for x in by_channel.get(c['id'], ()) if not x.get('feed')}
            reason = update_reason(logo, sources[0], best, urls) if len(sources) == 1 else None
            if not reason:
                continue
            changes[c['id']] = reason
            log(f'{c["id"]}: UPDATE, {reason}')
        else:
            log(f'{c["id"]}: {best.source} {best.size[0]}x{best.size[1]}{" SVG" if best.svg else ""}')
        kept.append((c, best))
    kept, doubts = split_duplicates(kept, {x.origin: k for k, x in current.items()})
    for c, other in doubts:
        log(f'{c["id"]}: DOUBT, same image as {other} (kept out)')
        changes.pop(c['id'], None)
    rows = []
    for c, best in kept:
        local = out / 'originals' / f'{c["id"]}.{image.extension(best.data)}'
        local.write_bytes(best.data)
        rows.append({'channel': c['id'], 'feed': '', 'origin': local.as_posix(), 'label': best.url})
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
    (out / 'summary.md').write_text(summary(cc, kept, changes, doubts, len(channels)), encoding='utf-8',
                                    newline='\n')
    sheets = contact_sheets(kept, out)
    return {'channels': len(channels), 'kept': len(kept), 'updates': len(changes), 'doubts': len(doubts),
            'candidates': len(report), 'sheets': len(sheets)}


def summary(cc: str, kept: list[tuple[dict, Candidate]], changes: dict[str, str], doubts: list, checked: int) -> str:
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
    return '\n'.join(lines)
