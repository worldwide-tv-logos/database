"""A candidate logo: downloaded, prepared like a request (image.prepare), measured, ranked; the channels and
editions of a country (registry.units); what decides an update of a current logo."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from worldwide_tv_logos import image, net, sources
from worldwide_tv_logos.db import Database
from worldwide_tv_logos.sources.names import key


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
        return (not self.error, self.svg, min(max(self.size), 1200), sources.RANK.get(self.source, 0))


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


def iptv_key(u: dict) -> tuple[str, str]:
    """(iptv-org channel, feed) of a unit, ('', '') when it has no iptv-org ID: the key of iptv-org's logos."""
    channel, _, feed = (u.get('iptv') or '').partition('@')
    return channel, feed


def same_as_channel(db: Database, u: dict, best: Candidate, kept: list[tuple[dict, Candidate]]) -> bool:
    """The logo found for an edition is the drawing of its channel (current, or found in this run)."""
    fps = [cand.fp for c, cand in kept if c['id'] == u['parent']]
    logo = db.logos.get((u['parent'], ''))
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
