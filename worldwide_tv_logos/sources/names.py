"""Comparison keys of channel names, shared by every source."""
from __future__ import annotations

import re
import unicodedata


def key(text: str) -> str:
    """Comparison key: no accents, lowercase, letters, digits and '+' ("Canal+" differs from "Canal")."""
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9+]', '', text.lower())


def channel_keys(c: dict) -> set[str]:
    """Keys of a channel or edition: its name, its other names and (a channel) its ID; "+" also written "plus"."""
    names = [c.get('name') or '', *(c.get('alt_names') or [])]
    ident = c.get('iptv', c['id'])                   # an iptv-org channel ID gives a name too: France3.fr
    if ident and '@' not in ident and '.' in ident:
        names.append(ident.split('.')[0])
    keys = set()
    for n in names:
        keys |= {key(n), key(n.replace('+', 'plus'))}
    return {k for k in keys if k}


def words(text: str) -> list[str]:
    """Words of a name or a title, compared like names ("Plus+" and "Canal+" keep their "+")."""
    return [w for w in (key(x.replace('+', 'plus')) for x in re.split(r'[\s_\-.,()|:/]+', text)) if w]


def has_name(text: str, name: str) -> bool:
    """The words of `name`, in a row, among the words of `text` ("Ceuta TV - Inicio" has "Ceuta TV", "Golf shop"
    has not "Gol")."""
    t, n = words(text), words(name)
    return bool(n) and any(t[i:i + len(n)] == n for i in range(len(t) - len(n) + 1))


def ambiguous_keys(iptv) -> set[str]:
    """Keys of names that open iptv-org channels of several countries share (TV4: Spain and Sweden): a collection
    matched by name only (picons) cannot tell which one its logo is."""
    countries: dict[str, set[str]] = {}
    for c in iptv.channels.values():
        if c.get('closed'):
            continue
        for k in channel_keys(dict(c, id=c['id'])):
            countries.setdefault(k, set()).add(c.get('country') or c['id'].rsplit('.', 1)[-1])
    return {k for k, cs in countries.items() if len(cs) > 1}
