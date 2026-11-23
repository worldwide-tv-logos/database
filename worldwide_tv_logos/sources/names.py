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
    if '@' not in c['id']:
        names.append(c['id'].split('.')[0])
    keys = set()
    for n in names:
        keys |= {key(n), key(n.replace('+', 'plus'))}
    return {k for k in keys if k}
