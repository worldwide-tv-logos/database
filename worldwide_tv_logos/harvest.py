"""Bulk harvest of the logos of a country, for a pull request (`logos harvest --country <cc>`).

For each open iptv-org channel of the country that has no logo here yet:

1. candidates from iptv-org's logos.json (logos of the channel or edition itself), from the iptv-epg guide of the
   country, from Wikidata (its current logo, see sources.py) and, for a hunt, from the channel website;
2. each candidate is downloaded (one at a time, with a pause) and goes through the same preparation as a request
   (image.prepare: trimmed, white frame removed, at least 500 px); refused candidates are reported;
3. the best one is kept: SVG first, then the largest, Wikidata before iptv-org and iptv-epg at equal size.

Nothing is written to data/: the result goes to temp/harvest/<cc>/ (originals, manifest.csv for `logos import`,
report.csv, contact sheets to review by eye). Only the reviewed manifest is imported.
"""
from __future__ import annotations

import csv
import functools
import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from worldwide_tv_logos import image, iptvorg, net, sources
from worldwide_tv_logos.db import SITE_BASE, Database
from worldwide_tv_logos.iptvorg import IptvOrg

QUALITY_FEED = re.compile(r'^(SD|HD|FHD|UHD|QHD|4K|8K|HDR|H265|HEVC|1080p?|720p?|Plus\d+)$', re.IGNORECASE)  # quality and timeshift (+1)
SOURCE_RANK = {'wikidata': 2, 'iptv-epg': 1, 'iptv-org': 1, 'website': 0}


def key(text: str) -> str:
    """Comparison key: no accents, lowercase, letters, digits and '+' ("Canal+" differs from "Canal")."""
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9+]', '', text.lower())


def channel_keys(c: dict) -> set[str]:
    names = [c.get('name') or '', *(c.get('alt_names') or [])]
    if '@' not in c['id']:
        names.append(c['id'].split('.')[0])
    keys = set()
    for n in names:
        keys |= {key(n), key(n.replace('+', 'plus'))}
    return {k for k in keys if k}


@dataclass
class Candidate:
    source: str
    url: str
    data: bytes = b''
    svg: bool = False
    size: tuple[int, int] = (0, 0)
    error: str = ''
    fp: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> tuple:
        return (not self.error, self.svg, min(max(self.size), 1200), SOURCE_RANK.get(self.source, 0))


def candidates(c: dict, iptv_logos: dict[tuple[str, str], list[dict]],
               extra: list[tuple[str, str]] = ()) -> list[Candidate]:
    """`c`: a channel or an edition (see units); `iptv_logos`: iptv-org logos by (channel, feed)."""
    out: list[Candidate] = [Candidate(src, url) for src, url in dict.fromkeys(extra)]
    logos = sorted((x for x in iptv_logos.get((c.get('channel', c['id']), c.get('feed', '')), ())
                    if x.get('in_use', True)
                    and 'white' not in (x.get('tags') or []) and str(x.get('url', '')).startswith('https://')),
                   key=lambda x: (x.get('format') != 'SVG', -(x.get('width') or 0)))
    out += [Candidate('iptv-org', x['url']) for x in logos[:2]]
    return out


def evaluate(cand: Candidate, downloader) -> Candidate:
    from urllib.parse import unquote
    name = unquote(cand.url.rsplit('/', 1)[-1])
    if sources.is_old({'end': '', 'file': name}):
        cand.error = 'old branding (its file name gives a period already over)'
        return cand
    try:
        cand.data = downloader(cand.url)
        img, cand.notes = image.prepare(cand.data)
        cand.svg = image.is_svg(cand.data)
        cand.size = img.size
        cand.fp = image.fingerprint(img)
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


def render_sheets(tiles: list[tuple[str, str, Image.Image, Image.Image]], out: Path, per_page: int = 30,
                  prefix: str = 'sheet') -> list[Path]:
    """Pages of 3 columns: (title, caption, picture for a dark tile, picture for a light tile), numbered."""
    tw, th, cols, cap = 260, 146, 3, 42
    font, small = _font(16), _font(13)
    out.mkdir(parents=True, exist_ok=True)
    pages = []
    for p in range(0, len(tiles), per_page):
        chunk = tiles[p:p + per_page]
        lines = (len(chunk) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * (2 * tw + 30), lines * (th + cap + 16) + 10), '#ffffff')
        draw = ImageDraw.Draw(sheet)
        for i, (title, caption, dark, light) in enumerate(chunk):
            x, y = (i % cols) * (2 * tw + 30) + 10, (i // cols) * (th + cap + 16) + 10
            for j, (bg, pic) in enumerate((('#14181f', dark), ('#eceef1', light))):
                tile = Image.new('RGB', (tw, th), bg)
                pic = pic.copy()
                pic.thumbnail((int(tw * .8), int(th * .8)))
                tile.paste(pic, ((tw - pic.width) // 2, (th - pic.height) // 2), pic)
                sheet.paste(tile, (x + j * (tw + 4), y))
            draw.text((x, y + th + 3), f'{p + i + 1}. {title}', fill='#111111', font=font)
            draw.text((x, y + th + 23), caption, fill='#555555', font=small)
        path = out / f'{prefix}-{p // per_page + 1:02d}.png'
        sheet.save(path)
        pages.append(path)
    return pages


def contact_sheets(rows: list[tuple[dict, Candidate]], out: Path, per_page: int = 30) -> list[Path]:
    """Candidates as they would be published: each logo on a dark and on a light tile."""
    tiles = []
    for c, cand in rows:
        img, white = image.variants(image.prepare(cand.data)[0])
        tiles.append((c['name'], f'{c["id"]}  {cand.source}  {cand.size[0]}x{cand.size[1]}'
                      + ('  SVG' if cand.svg else ''), white or img, img))
    return render_sheets(tiles, out, per_page)


def repo_sheets(db: Database, stems: list[str], out: Path, per_page: int = 30) -> list[Path]:
    """Logos of the repository (`stems` such as France3.fr or France3.fr@Alsace): their files as served."""
    tiles = []
    for stem in stems:
        channel, _, feed = stem.partition('@')
        main = db.logos.get((channel, feed, ''))
        if main is None:
            continue
        white = db.logos.get((channel, feed, 'white'))
        light = Image.open(db.path(main.file)).convert('RGBA')
        dark = Image.open(db.path(white.file)).convert('RGBA') if white else light
        origin = re.sub(r'^https://([^/]+)/.*', r'\1', main.origin)
        tiles.append((stem, f'{main.width}x{main.height}  {origin}', dark, light))
    return render_sheets(tiles, out, per_page)


CROSS_TOLERANCE = 6   # bits of the fingerprint: the same drawing, give or take resizing and compression


def family(channel_id: str) -> str:
    """Channels of one family may share a drawing: the same brand in several countries (ComedyCentral.es and .fr)
    or numbered sister channels whose logos differ by a digit only (Eurosport6.fr, Eurosport8.fr)."""
    return re.sub(r'\d+', '', channel_id.split('@')[0].rsplit('.', 1)[0]).lower()


REGION_WORDS = {'international', 'intl', 'europe', 'europa', 'european', 'africa', 'afrique', 'asia', 'latino', 'latina',
                'latinamerica', 'latam', 'arabia', 'arabic', 'middleeast', 'mena', 'nordic', 'scandinavia', 'balkans',
                'adria', 'benelux', 'global', 'world', 'america', 'americas', 'pacific', 'emea', 'cee'}
COUNTRY_WORDS: set[str] = set()


def set_countries(countries: list[dict]) -> None:
    """Country names of iptv-org (countries.json), used by `brand`."""
    COUNTRY_WORDS.update(w for w in (re.sub(r'[^a-z]', '', c.get('name', '').lower()) for c in countries) if len(w) > 3)
    _region_suffix.cache_clear()
    brand.cache_clear()


@functools.cache
def _region_suffix() -> re.Pattern:
    words = sorted(REGION_WORDS | COUNTRY_WORDS, key=len, reverse=True)
    return re.compile(r'^(.{2,}?)(?:' + '|'.join(map(re.escape, words)) + r')$')


@functools.cache
def brand(channel_id: str) -> str:
    """The family without a country or region at the end: HGTVSouthAfrica.za and HGTV.be are one brand, whose logo
    is the same in every country."""
    f = family(channel_id)
    m = _region_suffix().match(f)
    return m.group(1) if m else f


def repo_drawings(db: Database) -> list[tuple[str, str, int]]:
    """(channel, logo id, fingerprint) of every logo of the repository (main version, every country)."""
    out = []
    for x in db.logos.values():
        path = db.path(x.file)
        if not x.variant and path.is_file():
            try:
                out.append((x.channel, x.logo_id, image.fingerprint(Image.open(path).convert('RGBA'))))
            except OSError:
                pass
    return out


def drawing_of_other(channel: str, fp: int, drawings: list[tuple[str, str, int]]) -> str | None:
    """Logo ID of another channel, outside the family and brand of `channel`, that has this drawing (a logo given to
    the wrong channel: Action.fr's logo found for BlueAction.ch; not HGTV.be's for HGTVSouthAfrica.za)."""
    return next((lid for ch, lid, f in drawings if ch != channel and brand(ch) != brand(channel)
                 and (f ^ fp).bit_count() <= CROSS_TOLERANCE), None)


def shared_drawings(cc: str, drawings: list[tuple[str, str, int]]) -> list[tuple[str, str]]:
    """Current logos of the country that have the drawing of a channel of another family: (logo id, other)."""
    out = []
    for ch, lid, fp in drawings:
        if ch.rsplit('.', 1)[-1] == cc:
            other = drawing_of_other(ch, fp, drawings)
            if other:
                out.append((lid, other))
    return out


def split_duplicates(kept: list[tuple[dict, Candidate]], existing: dict[str, str] | None = None,
                     drawings: list[tuple[str, str, int]] | None = None) -> tuple[list, list]:
    """The same image chosen for several channels (a regional channel given the national logo), already used by
    another channel here (`existing`: origin URL -> channel), or the drawing of a channel of another family anywhere
    in the repository (`drawings`), is a doubt: within a group only the channel with the shortest name keeps it
    (24 Horas, not 24 Horas Canarias)."""
    existing = existing or {}
    groups: list[list[tuple[dict, Candidate]]] = []
    doubts = []
    for c, cand in kept:
        owner = existing.get(cand.url, c['id'])
        owner_channel = owner.split('@')[0]
        if owner != c['id'] and (owner_channel == c['channel'] or brand(owner_channel) != brand(c['channel'])):
            doubts.append((c, owner))                    # an edition given its channel's file, or another brand's
            continue
        other = drawing_of_other(c['channel'], cand.fp, drawings or []) if cand.fp else None
        if other:
            doubts.append((c, other))
            continue
        group = next((g for g in groups if all(same_image(c, cand, gc, gcand) for gc, gcand in g)), None)
        if group is None:
            groups.append(group := [])
        group.append((c, cand))
    out = []
    for group in groups:
        group.sort(key=lambda x: (len(x[0]['name']), x[0]['name']))
        numbered = {number(c) for c, _ in group if number(c)}
        if len(numbered) > 1:
            # one image for Sport 1, Sport 2...: the brand logo without the number, never the logo of one of them
            names = ', '.join(c['id'] for c, _ in group)
            plain = [x for x in group if not number(x[0])]
            out += plain[:1]
            doubts += [(c, f'{names} (a brand logo without the channel number)') for c, _ in group
                       if not plain or c is not plain[0][0]]
            continue
        out.append(group[0])
        doubts += [(c, group[0][0]['id']) for c, _ in group[1:]]
    out.sort(key=lambda x: x[0]['name'].lower())
    return out, doubts


def number(c: dict) -> str:
    """The number in a channel's name (`Sky Sport 2` -> '2', `TSN3` -> '3'), '' when it has none."""
    return ' '.join(re.findall(r'\d+', c.get('name') or c['id'].split('.')[0]))


def same_image(c: dict, cand: Candidate, other: dict, other_cand: Candidate) -> bool:
    """The same image for two channels. Numbered channels of one family (Sport 1, Sport 2) have logos that differ by
    the digit only, which the fingerprint does not see: for them only the same file counts."""
    exact = cand.url == other_cand.url or (bool(cand.data) and cand.data == other_cand.data)
    if exact:
        return True
    if family(c['channel']) == family(other['channel']) and number(c) != number(other):
        return False
    a = cand.fp or int(hashlib.sha1(cand.data).hexdigest(), 16)
    b = other_cand.fp or int(hashlib.sha1(other_cand.data).hexdigest(), 16)
    return image.same_drawing(a, b)


def logo_url(logo_id: str) -> str:
    return f'{SITE_BASE}logos/{logo_id.split("@")[0].rsplit(".", 1)[-1]}/{logo_id}.png'


def brand_differences(kept: list[tuple[dict, Candidate]], drawings: list[tuple[str, str, int]]) -> list[tuple[str, list[str]]]:
    """Logos found that differ from every logo of the same brand already in the repository (other countries): often
    an older branding (the repository has the current one), sometimes a regional one. (channel id, brand logo IDs)."""
    out = []
    for c, cand in kept:
        if not cand.fp:
            continue
        others = [(lid, fp) for ch, lid, fp in drawings if ch != c['channel'] and brand(ch) == brand(c['channel'])]
        if others and not any(image.same_drawing(fp, cand.fp) for _, fp in others):
            out.append((c['id'], [lid for lid, _ in others][:4]))
    return out


def load_rejected(root: Path) -> set[tuple[str, str]]:
    """(channel, url) pairs refused in review (data/rejected.csv): never proposed again."""
    path = Path(root) / 'data' / 'rejected.csv'
    if not path.is_file():
        return set()
    with open(path, encoding='utf-8', newline='') as fh:
        return {(r['channel'], r['url']) for r in csv.DictReader(fh)}


def update_reason(logo, source: Path, best: Candidate, iptv_urls: set[str], current_fps: list[int] = ()) -> str | None:
    """Why the best candidate should replace the current logo, or None (no clear improvement). A sharper version
    says whether it is the same drawing as the current logo (`current_fps`: fingerprints of the logo and its white
    variant) or another one, to be checked as the current branding."""
    current = source.read_bytes()
    if best.data == current:
        return None
    if best.url == logo.origin:
        return 'the original changed at its source'
    same = any(image.same_drawing(fp, best.fp) for fp in current_fps) if best.fp else False
    drawing = 'same drawing' if same else 'DIFFERENT drawing: check that it is the current branding'
    if best.svg and not image.is_svg(current):
        return f'vector (SVG) version found, {drawing}'
    if max(best.size) >= 1.5 * max(logo.width, logo.height):
        return f'larger ({best.size[0]}x{best.size[1]} instead of {logo.width}x{logo.height}), {drawing}'
    if best.source == 'iptv-org' and logo.origin.startswith('https://') and logo.origin not in iptv_urls \
            and iptv_urls:
        return 'iptv-org replaced the logo of this channel'
    return None


def more_candidates(root: Path, c: dict, cc: str, wikidata: bool, deep: bool, downloader, log,
                    epg: sources.EpgIndex | None = None) -> list[tuple[str, str]]:
    """(source, url) of the iptv-epg logos, of the current Wikidata logo and, when `deep`, of the logos found on the
    channel website."""
    out: list[tuple[str, str]] = [('iptv-epg', u) for u in epg.logos(c, channel_keys(c))] if epg else []
    website = c.get('website') or ''
    if wikidata:
        try:
            names = [c['name'], *(c.get('alt_names') or [])]
            for item in sources.find_items(root, names, cc, channel_keys(c), key, downloader)[:2]:
                out += [('wikidata', u) for u in sources.current_logos(item)[:1]]
                website = website or item['website']
        except (net.DownloadError, ValueError, KeyError) as exc:
            log(f'{c["id"]}: Wikidata unavailable ({exc})')
    if deep and website:
        out += [('website', u) for u in sources.load_website_logos(website, downloader)]
    return out


def units(iptv: IptvOrg, cc: str) -> list[dict]:
    """The open channels of a country and their editions (iptv-org feeds other than the main one), each as
    {id, channel, feed, name, alt_names, website}; an edition is named after its channel ("France 3 Alsace")."""
    out = []
    feeds: dict[str, list[dict]] = {}
    for (channel, fid), f in iptv.feeds.items():
        if not f.get('is_main') and not QUALITY_FEED.match(fid):     # TF1@HD uses the logo of TF1
            feeds.setdefault(channel, []).append(dict(f, id=fid))
    for c in sorted(iptv.country_channels(cc), key=lambda c: c['name'].lower()):
        out.append(dict(c, channel=c['id'], feed=''))
        for f in sorted(feeds.get(c['id'], []), key=lambda f: f['id']):
            name = f.get('name') or f['id']
            out.append({'id': f'{c["id"]}@{f["id"]}', 'channel': c['id'], 'feed': f['id'],
                        'name': name if name.lower().startswith(c['name'].lower()) else f'{c["name"]} {name}',
                        'alt_names': [], 'website': c.get('website') or ''})
    return out


def same_as_channel(db: Database, u: dict, best: Candidate, kept: list[tuple[dict, Candidate]]) -> bool:
    """The logo found for an edition is the drawing of its channel (current, or found in this run)."""
    fps = [cand.fp for c, cand in kept if c['id'] == u['channel']]
    logo = db.logos.get((u['channel'], '', ''))
    if logo is not None and db.path(logo.file).is_file():
        fps.append(image.fingerprint(Image.open(db.path(logo.file)).convert('RGBA')))
    return any(image.same_drawing(fp, best.fp) for fp in fps)


def load_epg(db: Database, cc: str, downloader, log) -> sources.EpgIndex | None:
    """Index of the iptv-epg guide of the country; None (logged) when it cannot be read."""
    try:
        return sources.EpgIndex(sources.load_iptv_epg(db.root, cc, downloader), list(db.aliases.values()), key)
    except Exception as exc:  # noqa: BLE001 - a guide that cannot be read never stops a harvest
        log(f'iptv-epg guide of `{cc}` unavailable ({exc})')
        return None


def harvest(db: Database, iptv: IptvOrg, cc: str, iptv_logos: list[dict], out: Path, pause: float = 2.0, limit: int = 0, updates: bool = False, downloader=None,
            log=print, wikidata: bool = True, deep: bool = False, only: list[str] | None = None) -> dict[str, int]:
    """Missing logos of the country (and, with `updates`, better or newer versions of its current logos) into
    out/: originals, manifest.csv for `logos import`, report.csv, doubts.csv, summary.md, contact sheets.
    `wikidata`: also the current logos of the channel on Wikidata; `deep`: also the logos of its website;
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
    epg = load_epg(db, cc, downloader, log)
    by_channel: dict[tuple[str, str], list[dict]] = {}
    for x in iptv_logos:
        by_channel.setdefault((x['channel'], x.get('feed') or ''), []).append(x)
    (out / 'originals').mkdir(parents=True, exist_ok=True)
    report, kept, changes = [], [], {}
    last = 0.0
    for c in channels:
        extra = more_candidates(db.root, c, cc, wikidata, deep, downloader, log, epg)
        cands = [x for x in candidates(c, by_channel, extra) if (c['id'], x.url) not in rejected]
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
            sources = db.source_files(logo)
            urls = {x['url'] for x in by_channel.get((c['channel'], c['feed']), ())}
            fps = [image.fingerprint(Image.open(db.path(x.file)).convert('RGBA'))
                   for x in (logo, db.logos.get((logo.channel, logo.feed, 'white'))) if x and db.path(x.file).is_file()]
            reason = update_reason(logo, sources[0], best, urls, fps) if len(sources) == 1 else None
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
