"""picons (github.com/picons/picons): logos of satellite, cable and IPTV channels, mostly European, as SVG or PNG,
for set-top boxes. Its index (build-source/utf8snp.index, about 33,000 channel names) gives the logo of a channel by
its simplified name; the list of its logo files is read once (one request to the GitHub API). Both are cached seven
days; a logo is downloaded only when it matches a channel. Some logos are older brandings: checked like iptv-epg's."""
from __future__ import annotations

from worldwide_tv_logos.sources import names

RAW = 'https://raw.githubusercontent.com/picons/picons/master/build-source/'
TREE = 'https://api.github.com/repos/picons/picons/git/trees/master:build-source/logos'
MAX_AGE = 7 * 86400
VARIANTS = ('default', 'light', 'white', 'dark')     # the logo on a transparent background first


def index(ctx) -> dict[str, list[str]]:
    """Comparison key of a channel name -> logo files (best variant first)."""
    def compute():
        files = [x['path'] for x in ctx.json(TREE).get('tree', []) if x.get('type') == 'blob']
        by_stem: dict[str, list[str]] = {}
        for f in files:
            stem = f.partition('.')[0]
            by_stem.setdefault(stem, []).append(f)
        for stem, fs in by_stem.items():
            fs.sort(key=lambda f: (VARIANTS.index(f.split('.')[1]) if f.split('.')[1] in VARIANTS else 9,
                                   not f.endswith('.svg')))
        text = ctx.get(RAW + 'utf8snp.index', accept='text/plain').decode('utf-8', errors='replace')
        out: dict[str, list[str]] = {}
        for line in text.splitlines():
            name, _, stem = line.rpartition('=')
            k = names.key(name)
            if len(k) >= 3 and stem in by_stem:
                out.setdefault(k, by_stem[stem])
        for stem, fs in by_stem.items():
            out.setdefault(stem, fs)
        return out
    return ctx.cached('picons', 'index', compute, MAX_AGE)


def find(unit: dict, ctx) -> list[str]:
    idx = index(ctx)
    for k in sorted(names.channel_keys(unit), key=len, reverse=True):
        if len(k) >= 3 and k in idx:
            return [RAW + 'logos/' + idx[k][0]]
    return []
