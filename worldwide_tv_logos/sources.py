"""Logo sources beyond iptv-org: Wikidata (logos with their dates) and the channel's own website.

Wikidata (action API, fast; the SPARQL service is too slow for whole countries): the channel is searched by name
among the items of its country, then its item is read (names, type, website, logo statements P154 with their start
and end dates). Only items whose name matches exactly and that are not a radio station or a programme are kept. A
logo with an end date, or whose file name gives a period already over ("2011-2017"), is an old branding: never
proposed. Cached thirty days in .cache/wikidata/.

Website: the home page of the channel is read once; images whose address, class, id or alternative text says
"logo" (and SVG icons) are candidates. Nothing else on the site is followed.
"""
from __future__ import annotations

import datetime
import json
import re
import time
import urllib.parse
from pathlib import Path

from worldwide_tv_logos import net

API = 'https://www.wikidata.org/w/api.php?'
COMMONS_FILE = 'https://commons.wikimedia.org/wiki/Special:FilePath/'
MAX_AGE = 30 * 86400
LANGS = ('en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'ca', 'eu', 'gl', 'ar')
NOT_CHANNELS = {'Q14350', 'Q15416', 'Q5398426', 'Q1555508', 'Q4830453'}  # radio station, programme, series, radio, business
PERIOD_RE = re.compile(r'(?:19|20)\d\d\s*[-–—_]\s*((?:19|20)\d\d)')


def _api(params: dict, downloader) -> dict:
    url = API + urllib.parse.urlencode({**params, 'format': 'json'})
    return json.loads(downloader(url, accept='application/json'))


def _cached(root: Path, name: str, compute):
    path = Path(root) / '.cache' / 'wikidata' / f'{name}.json'
    if path.is_file() and time.time() - path.stat().st_mtime < MAX_AGE:
        return json.loads(path.read_text(encoding='utf-8'))
    value = compute()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return value


def _time(claim_qualifiers: dict, prop: str) -> str:
    for q in claim_qualifiers.get(prop, []):
        value = q.get('datavalue', {}).get('value', {})
        if isinstance(value, dict) and value.get('time'):
            return value['time'][1:11].replace('-00', '-01')
    return ''


def parse_entity(ent: dict) -> dict:
    claims = ent.get('claims', {})

    def values(prop):
        return [c['mainsnak'].get('datavalue', {}).get('value') for c in claims.get(prop, [])
                if c.get('rank') != 'deprecated' and c['mainsnak'].get('datavalue')]
    names = [x['value'] for x in ent.get('labels', {}).values()]
    names += [a['value'] for aliases in ent.get('aliases', {}).values() for a in aliases]
    logos = []
    for c in claims.get('P154', []):
        file = c['mainsnak'].get('datavalue', {}).get('value')
        if not file or c.get('rank') == 'deprecated':
            continue
        logos.append({'url': COMMONS_FILE + urllib.parse.quote(file.replace(' ', '_')), 'file': file,
                      'start': _time(c.get('qualifiers', {}), 'P580'), 'end': _time(c.get('qualifiers', {}), 'P582'),
                      'preferred': c.get('rank') == 'preferred'})
    websites = [v for v in values('P856') if isinstance(v, str)]
    return {'qid': ent.get('id', ''), 'names': list(dict.fromkeys(names)),
            'types': [v.get('id') for v in values('P31') if isinstance(v, dict)],
            'countries': [v.get('id') for v in values('P17') if isinstance(v, dict)],
            'website': websites[0] if websites else '', 'logos': logos}


def is_old(logo: dict, year: int | None = None) -> bool:
    """An end date, or a file name giving a period already over ("Canal Sur 2011-2017 logo.svg")."""
    if logo['end']:
        return True
    year = year or datetime.date.today().year
    return any(int(m) < year for m in PERIOD_RE.findall(logo['file']))


def current_logos(item: dict) -> list[str]:
    """Logos still in use: preferred rank first, then the most recent, SVG before raster at equal rank."""
    alive = [x for x in item['logos'] if not is_old(x)]
    alive.sort(key=lambda x: not x['file'].lower().endswith('.svg'))
    alive.sort(key=lambda x: x['start'] or '0000', reverse=True)
    alive.sort(key=lambda x: not x['preferred'])
    return [x['url'] for x in alive]


def country_qid(root: Path, cc: str, downloader=None) -> str:
    downloader = downloader or net.download

    def compute():
        res = _api({'action': 'query', 'list': 'search', 'srsearch': f'haswbstatement:P297={cc.upper()}',
                    'srlimit': 1}, downloader)
        hits = res.get('query', {}).get('search', [])
        return hits[0]['title'] if hits else ''
    return _cached(root, f'country-{cc}', compute)


def find_items(root: Path, names: list[str], cc: str, keys: set[str], key, downloader=None,
               pause: float = 1.0) -> list[dict]:
    """Wikidata items of the country whose name (label or alias) has one of the comparison `keys`."""
    downloader = downloader or net.download
    country = country_qid(root, cc, downloader)
    if not country:
        return []

    def compute():
        ids: list[str] = []
        for name in names[:2]:
            res = _api({'action': 'query', 'list': 'search', 'srlimit': 8,
                        'srsearch': f'{name} haswbstatement:P17={country}'}, downloader)
            ids += [h['title'] for h in res.get('query', {}).get('search', []) if h['title'] not in ids]
            time.sleep(pause)
        if not ids:
            return []
        res = _api({'action': 'wbgetentities', 'ids': '|'.join(ids[:50]), 'props': 'claims|labels|aliases',
                    'languages': '|'.join(LANGS)}, downloader)
        time.sleep(pause)
        return [parse_entity(e) for e in res.get('entities', {}).values()]
    items = _cached(root, 'search-' + re.sub(r'[^A-Za-z0-9.@_-]', '_', '|'.join(names[:2]))[:150] + f'-{cc}',
                    compute)
    return [i for i in items if country in i['countries'] and not NOT_CHANNELS & set(i['types'])
            and keys & {key(n) for n in i['names']}]


IMG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
LINK_RE = re.compile(r'<link\b[^>]*>', re.IGNORECASE)
ATTR_RE = re.compile(r'([a-zA-Z:-]+)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)')


def _attrs(tag: str) -> dict[str, str]:
    return {k.lower(): v.strip('"\'') for k, v in ATTR_RE.findall(tag)}


def website_logos(page_url: str, html: str, limit: int = 3) -> list[str]:
    """Logo images of a home page: <img> whose src, class, id or alt contains "logo", then SVG icons."""
    out: list[str] = []
    for tag in IMG_RE.findall(html):
        a = _attrs(tag)
        src = a.get('src') or a.get('data-src') or ''
        if not src or src.startswith('data:'):
            continue
        if 'logo' in ' '.join((src, a.get('class', ''), a.get('id', ''), a.get('alt', ''))).lower():
            out.append(urllib.parse.urljoin(page_url, src))
    for tag in LINK_RE.findall(html):
        a = _attrs(tag)
        href = a.get('href', '')
        if 'icon' in a.get('rel', '').lower() and href.lower().split('?')[0].endswith('.svg'):
            out.append(urllib.parse.urljoin(page_url, href))
    return [u for u in dict.fromkeys(out) if u.startswith('https://')][:limit]


def load_website_logos(url: str, downloader=None) -> list[str]:
    if not url or not url.startswith('http'):
        return []
    url = url.replace('http://', 'https://', 1)
    try:
        html = (downloader or net.download)(url, accept='text/html')
    except net.DownloadError:
        return []
    return website_logos(url, html.decode('utf-8', errors='replace'))
