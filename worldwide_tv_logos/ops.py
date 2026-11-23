"""Changes to the database: add or replace a logo, remove one, add an alias. Used by `import` and `update`."""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from worldwide_tv_logos import image, registry
from worldwide_tv_logos.db import EPG_ID_RE, Alias, Channel, Database, Logo


class RequestError(ValueError):
    pass


class NotRegistered(RequestError):
    """A channel not (yet) in our registry: a request can wait for it instead of being refused."""


def channel_of(db: Database, ref: str) -> Channel:
    """The registry channel of `ref`: our ID, a slug, or an iptv-org or Wikidata ID."""
    c = registry.resolve(db, ref)
    if c is None and any(registry.SOURCES[s].match(ref) for s in ('iptv-org', 'iptv-org-feed')):
        raise NotRegistered(f'`{ref}` is not a channel of our registry yet (iptv-org channels of the followed '
                            'countries are registered every night)')
    if c is None:
        raise RequestError(f'`{ref}`: unknown channel (give our ID `ch_...`, its slug, or its iptv-org ID)')
    return c


def set_logo(db: Database, channel: str, original: bytes, origin: str, today: str | None = None) -> list[str]:
    """Add or replace the logo of a registry channel (its ID) from an original image. Returns a change summary."""
    if channel not in db.channels:
        raise RequestError(f'`{channel}` is not a channel ID of our registry')
    try:
        img, notes = image.prepare(original)
    except image.ImageError as exc:
        raise RequestError(str(exc)) from None
    today = today or date.today().isoformat()
    changes = []
    img, white = image.variants(img)
    pngs = {v: image.png_bytes(p) for v, p in (('', img), ('white', white)) if p is not None}
    if any(len(b) > image.MAX_FILE for b in pngs.values()):
        raise RequestError(f'logo heavier than {image.MAX_FILE // 1000} KB once converted (too detailed)')
    with tempfile.TemporaryDirectory() as tmp:       # the files must pass the repository rules before anything is written
        for variant, data in pngs.items():
            probe = Path(tmp) / f'{variant or "main"}.png'
            probe.write_bytes(data)
            errors = image.check_file(probe, white=variant == 'white')
            if errors:
                raise RequestError(f'prepared logo refused by the repository rules: {"; ".join(errors)}')
    for variant, picture in (('', img), ('white', white)):
        key = (channel, variant)
        old = db.logos.get(key)
        if picture is None:
            if old is not None:                      # the new logo needs no white variant any more
                remove_files(db, old)
                del db.logos[key]
                changes.append(f'removed {old.file}')
            continue
        logo = Logo(channel, variant, picture.size[0], picture.size[1], origin,
                    old.added if old else today, today if old and old.added != today else '')
        for path in db.source_files(logo):
            path.unlink()
        src = db.root / 'sources' / f'{logo.channel}.{image.extension(original)}'
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


def remove_logo(db: Database, channel: str) -> list[str]:
    keys = [k for k in db.logos if k[0] == channel]
    if not keys:
        raise RequestError(f'no logo for `{channel}` in this repository')
    out = []
    for k in keys:
        logo = db.logos.pop(k)
        remove_files(db, logo)
        out.append(f'removed {logo.file}')
    for key, alias in list(db.aliases.items()):
        if alias.channel == channel:
            del db.aliases[key]
            out.append(f'removed alias {alias.source}:{alias.epg_id}')
    return out


def set_alias(db: Database, epg_id: str, source: str, channel: str) -> list[str]:
    if channel not in db.channels:
        raise RequestError(f'`{channel}` is not a channel ID of our registry')
    if not EPG_ID_RE.match(epg_id) or not EPG_ID_RE.match(source):
        raise RequestError('EPG id and EPG source must not contain spaces, commas or quotes')
    alias = Alias(epg_id, source, channel)
    old = db.aliases.get(alias.key)
    db.aliases[alias.key] = alias
    return [f'{"changed" if old else "added"} alias {source}:{epg_id} -> {channel}']


def remove_alias(db: Database, epg_id: str, source: str) -> list[str]:
    if db.aliases.pop((source, epg_id), None) is None:
        raise RequestError(f'no alias `{source}:{epg_id}` in this repository')
    return [f'removed alias {source}:{epg_id}']


def move_logos(db: Database, old: str, new: str, today: str | None = None) -> list[str]:
    """Move every logo (with its variant and original) and alias of channel `old` to channel `new`: a channel
    registered twice. A rename never needs it: the channel keeps its ID."""
    keys = sorted(k for k in db.logos if k[0] == old)
    if not keys:
        raise RequestError(f'no logo for `{old}`')
    if new not in db.channels:
        raise RequestError(f'`{new}` is not a channel ID of our registry')
    if any(k[0] == new for k in db.logos):
        raise RequestError(f'`{new}` already has a logo: remove it first')
    today = today or date.today().isoformat()
    out = []
    for k in keys:
        logo = db.logos.pop(k)
        moved = Logo(new, logo.variant, logo.width, logo.height, logo.origin, logo.added, today)
        files = [(db.path(logo.file), db.path(moved.file))]
        files += [(p, db.root / 'sources' / f'{new}{p.suffix}') for p in db.source_files(logo)]
        for src, dst in files:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dst)
        db.logos[moved.key] = moved
        out.append(f'moved {logo.file} to {moved.file}')
    for key, alias in list(db.aliases.items()):
        if alias.channel == old:
            db.aliases[key] = Alias(alias.epg_id, alias.source, new)
            out.append(f'alias {alias.source}:{alias.epg_id} now points to {new}')
    return out
