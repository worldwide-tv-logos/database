"""Changes to the database: add or replace a logo, remove one, add an alias. Used by `import` and `update`."""
from __future__ import annotations

from datetime import date

from owntv_logos import image
from owntv_logos.db import CHANNEL_RE, EPG_ID_RE, FEED_RE, Alias, Database, Logo
from owntv_logos.iptvorg import IptvOrg


class RequestError(ValueError):
    pass


def check_ids(channel: str, feed: str, iptv: IptvOrg | None) -> None:
    if not CHANNEL_RE.match(channel):
        raise RequestError(f'`{channel}` is not an iptv-org channel id (e.g. `France3.fr`)')
    if feed and not FEED_RE.match(feed):
        raise RequestError(f'`{feed}` is not an iptv-org feed id (letters and digits, e.g. `Alsace`)')
    if iptv is not None and (err := iptv.channel_error(channel, feed)):
        raise RequestError(err)


def set_logo(db: Database, channel: str, feed: str, original: bytes, origin: str, iptv: IptvOrg | None,
             today: str | None = None) -> list[str]:
    """Add or replace the logo of a channel (or feed) from an original image. Returns a change summary."""
    check_ids(channel, feed, iptv)
    try:
        img, notes = image.prepare(original)
    except image.ImageError as exc:
        raise RequestError(str(exc)) from None
    today = today or date.today().isoformat()
    changes = []
    white = image.white_variant(img)
    pngs = {v: image.png_bytes(p) for v, p in (('', img), ('white', white)) if p is not None}
    if any(len(b) > image.MAX_FILE for b in pngs.values()):
        raise RequestError(f'logo heavier than {image.MAX_FILE // 1000} KB once converted (too detailed)')
    for variant, picture in (('', img), ('white', white)):
        key = (channel, feed, variant)
        old = db.logos.get(key)
        if picture is None:
            if old is not None:                      # the new logo needs no white variant any more
                remove_files(db, old)
                del db.logos[key]
                changes.append(f'removed {old.file}')
            continue
        logo = Logo(channel, feed, variant, picture.size[0], picture.size[1], origin,
                    old.added if old else today, today if old else '')
        for path in db.source_files(logo):
            path.unlink()
        src = db.root / 'sources' / logo.country / f'{logo.stem}.{image.extension(original)}'
        src.parent.mkdir(parents=True, exist_ok=True)
        if variant == '':
            src.write_bytes(original)
        out = db.path(logo.file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pngs[variant])
        db.logos[key] = logo
        changes.append(f'{"replaced" if old else "added"} {logo.file} ({logo.width}x{logo.height})'
                       + (f', {", ".join(notes)}' if notes and not variant else ''))
    return changes


def remove_files(db: Database, logo: Logo) -> None:
    db.path(logo.file).unlink(missing_ok=True)
    for path in db.source_files(logo):
        path.unlink()


def remove_logo(db: Database, channel: str, feed: str) -> list[str]:
    keys = [k for k in db.logos if k[:2] == (channel, feed)]
    if not keys:
        raise RequestError(f'no logo for `{channel}{"@" + feed if feed else ""}` in this repository')
    out = []
    for k in keys:
        remove_files(db, db.logos.pop(k))
        out.append(f'removed {Logo(*k).file}')
    return out


def set_alias(db: Database, epg_id: str, source: str, channel: str, feed: str, iptv: IptvOrg | None) -> list[str]:
    check_ids(channel, feed, iptv)
    if not EPG_ID_RE.match(epg_id) or not EPG_ID_RE.match(source):
        raise RequestError('EPG id and EPG source must not contain spaces, commas or quotes')
    alias = Alias(epg_id, source, channel, feed)
    old = db.aliases.get(alias.key)
    db.aliases[alias.key] = alias
    return [f'{"changed" if old else "added"} alias {source}:{epg_id} -> {channel}{"@" + feed if feed else ""}']
