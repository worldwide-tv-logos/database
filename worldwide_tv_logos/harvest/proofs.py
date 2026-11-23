"""The proof that a logo found is the one on air now: the channel's website, checked by the harvest itself before the
review (the reviewer does not have to reach the websites itself).

For each logo kept that does not come from Wikidata or the channel's Wikipedia article: its website is found
(sites.find), the logo is looked for on it (seen.seen_on: the same drawing in the page, read plainly or rendered by a
browser), and the top of the home page is captured (web.screenshot) for the review sheet `sites-NN.png`: the logo
found next to the website as people see it.
"""
from __future__ import annotations

import io
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from worldwide_tv_logos import net, seen, sites, web
from worldwide_tv_logos.harvest.candidates import Candidate
from worldwide_tv_logos.harvest.sheets import website_sheets

TRUSTED = {'wikidata', 'wikipedia'}                # the channel's own record: no other proof needed


@dataclass
class Proof:
    result: str                 # found | not found | unreadable | no website
    site: str = ''              # the page looked at
    confirmed: bool = False     # the website is the channel's (its name in the title or the domain)
    detail: str = ''
    screenshot: bytes | None = None

    def text(self) -> str:
        host = urllib.parse.urlsplit(self.site).hostname or self.site
        where = f'{host}{"" if self.confirmed else " (site not confirmed)"}'
        return {'found': f'FOUND on {where}', 'not found': f'not found on {where}',
                'unreadable': f'{where} unreadable', 'no website': 'no website found'}[self.result]


def check(unit: dict, cand: Candidate, ctx, shots: bool = True) -> Proof:
    site = sites.find(unit, ctx)
    if site is None:
        return Proof('no website')
    proof = Proof('not found', site.url, site.confirmed)
    try:
        how = seen.seen_on(site.url, cand.data, log=ctx.log)
        if how:
            proof.result, proof.detail = 'found', how
    except (net.DownloadError, ValueError, OSError) as exc:
        proof.result, proof.detail = 'unreadable', str(exc)
    if shots and proof.result != 'unreadable':
        proof.screenshot = web.screenshot(site.url)
    return proof


def check_all(kept: list[tuple[dict, Candidate]], ctx, out: Path, log=print) -> dict[str, Proof]:
    """Proofs of the logos kept that need one, and their review sheet (out/sites-NN.png)."""
    proofs: dict[str, Proof] = {}
    rows = []
    for c, cand in kept:
        if cand.source in TRUSTED:
            continue
        try:
            proofs[c['id']] = proof = check(c, cand, ctx)
        except Exception as exc:  # noqa: BLE001 - a website that breaks a tool never stops a harvest
            proofs[c['id']] = proof = Proof('unreadable', detail=f'{type(exc).__name__}: {exc}')
        log(f'{c["id"]}: website {proof.text()}')
        if proof.screenshot:
            rows.append((f'{c["name"]} ({c["id"]}): {proof.text()}', cand.data,
                         Image.open(io.BytesIO(proof.screenshot)).convert('RGB')))
    if rows:
        website_sheets(rows, out)
    return proofs
