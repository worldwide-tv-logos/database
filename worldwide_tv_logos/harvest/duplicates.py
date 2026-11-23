"""The same image for two channels: families and brands, doubts, numbered sister channels, and logos found that
differ from the brand's logo published elsewhere."""
from __future__ import annotations

import functools
import hashlib
import re

from PIL import Image

from worldwide_tv_logos import image
from worldwide_tv_logos.db import SITE_BASE, Database
from worldwide_tv_logos.harvest.candidates import Candidate

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
