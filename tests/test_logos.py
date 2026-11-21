import io
import json

import pytest
from PIL import Image

from worldwide_tv_logos import cli, image, issues, ops
from worldwide_tv_logos.db import Database, Logo, parse_logo_id
from worldwide_tv_logos.iptvorg import IptvOrg

IPTV = IptvOrg({'France3.fr': {'id': 'France3.fr', 'name': 'France 3', 'country': 'FR'},
                'TF1.fr': {'id': 'TF1.fr', 'name': 'TF1', 'country': 'FR'}},
               {('France3.fr', 'Alsace'): {}, ('France3.fr', 'National'): {}})


def png(w, h, color=(200, 0, 0, 255), bg=(0, 0, 0, 0), margin=0):
    img = Image.new('RGBA', (w + 2 * margin, h + 2 * margin), bg)
    img.paste(Image.new('RGBA', (w, h), color), (margin, margin))
    out = io.BytesIO()
    img.save(out, 'PNG')
    return out.getvalue()


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect x="5" y="5" width="30" height="10" fill="#111"/></svg>'


@pytest.fixture
def db(tmp_path):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data' / 'countries.csv').write_text('code,name\nfr,France\n', encoding='utf-8')
    return Database(tmp_path).load()


def test_names_are_derived_from_the_iptv_org_id():
    logo = Logo('France3.fr', 'Alsace', 'white')
    assert (logo.file, logo.logo_id) == ('logos/fr/France3.fr@Alsace.white.png', 'France3.fr@Alsace')
    assert Logo('TF1.fr').file == 'logos/fr/TF1.fr.png'
    assert parse_logo_id('France3.fr@Alsace') == ('France3.fr', 'Alsace')


def test_prepare_trims_removes_white_frame_and_refuses_bad_images():
    img, notes = image.prepare(png(800, 300, margin=50))
    assert img.size == (800, 300) and notes == []                         # margin trimmed, never upscaled
    img, notes = image.prepare(png(800, 300, bg=(255, 255, 255, 255), margin=40))
    assert notes == ['white frame removed'] and img.size == (800, 300)
    img, notes = image.prepare(png(800, 300, bg=(0, 0, 255, 255), margin=40))   # brand block kept
    assert notes == [] and img.size == (880, 380)
    with pytest.raises(image.ImageError, match='too small'):
        image.prepare(png(300, 100))
    with pytest.raises(image.ImageError, match='HTML'):
        image.prepare(b'<html>blocked</html>')


def test_svg_is_rendered_at_target_width_and_dark_logo_gets_white_variant():
    img, _ = image.prepare(SVG)
    assert img.size == (image.TARGET_WIDTH, image.TARGET_WIDTH // 3)
    white = image.white_variant(img)
    assert white is not None and white.getpixel((10, 10))[:3] == (255, 255, 255)
    assert image.white_variant(image.prepare(png(800, 300))[0]) is None     # red logo: readable on dark


def test_set_logo_writes_logo_original_variant_and_validates(db):
    changes = ops.set_logo(db, 'France3.fr', 'Alsace', SVG, 'https://example.org/f3.svg', IPTV, today='2026-11-21')
    assert len(changes) == 2
    db.save()
    assert (db.root / 'logos/fr/France3.fr@Alsace.png').is_file()
    assert (db.root / 'logos/fr/France3.fr@Alsace.white.png').is_file()
    assert (db.root / 'sources/fr/France3.fr@Alsace.svg').read_bytes() == SVG
    assert cli.validate(Database(db.root).load(), IPTV) == []
    # replacement by a coloured logo: same file names, no white variant any more, dates kept / updated
    ops.set_logo(db, 'France3.fr', 'Alsace', png(900, 300), 'issue #3', IPTV, today='2026-12-01')
    db.save()
    again = Database(db.root).load()
    logo = again.logos[('France3.fr', 'Alsace', '')]
    assert (logo.added, logo.updated, logo.origin) == ('2026-11-21', '2026-12-01', 'issue #3')
    assert ('France3.fr', 'Alsace', 'white') not in again.logos
    assert not (db.root / 'logos/fr/France3.fr@Alsace.white.png').exists()
    assert [p.name for p in (db.root / 'sources/fr').iterdir()] == ['France3.fr@Alsace.png']
    assert cli.validate(again, IPTV) == []


def test_unknown_ids_are_refused(db):
    with pytest.raises(ops.RequestError, match='does not exist in iptv-org'):
        ops.set_logo(db, 'Nope.fr', '', png(800, 300), 'x', IPTV)
    with pytest.raises(ops.RequestError, match='known: Alsace, National'):
        ops.set_logo(db, 'France3.fr', 'Mars', png(800, 300), 'x', IPTV)
    with pytest.raises(ops.RequestError, match='not an iptv-org channel id'):
        ops.set_logo(db, 'France 3', '', png(800, 300), 'x', IPTV)


def test_validate_finds_stray_and_misnamed_files(db):
    ops.set_logo(db, 'TF1.fr', '', png(800, 300), 'x', IPTV)
    db.save()
    (db.root / 'logos/fr/tf1-fr.png').write_bytes(png(800, 300))
    (db.root / 'sources/fr/Old.fr.png').write_bytes(b'x')
    errors = cli.validate(Database(db.root).load(), IPTV)
    assert any('tf1-fr.png: not listed' in e for e in errors)
    assert any('Old.fr.png: original of no logo' in e for e in errors)


BODY = """### Channel ID

France3.fr

### Feed ID (optional)

Alsace

### Logo URL

https://example.org/f3-alsace.png

### Notes (optional)

_No response_
"""


def test_issue_form_is_parsed_validated_and_applied(db):
    req = issues.parse(12, ['logos:add', 'approved'], BODY)
    assert (req.kind, req.get('channel'), req.get('feed'), req.get('notes')) == ('logos:add', 'France3.fr', 'Alsace', '')
    fake = {'https://example.org/f3-alsace.png': png(1000, 400)}
    assert issues.validate(req, db, IPTV, downloader=fake.__getitem__) == []
    changes = issues.apply(req, db, IPTV, downloader=fake.__getitem__)
    assert changes[0].startswith('added logos/fr/France3.fr@Alsace.png')
    assert db.logos[('France3.fr', 'Alsace', '')].origin == 'issue #12'
    bad = issues.parse(13, ['logos:add'], BODY.replace('Alsace', 'Mars'))
    assert 'does not exist' in issues.validate(bad, db, IPTV, downloader=fake.__getitem__)[0]
    alias = issues.parse(14, ['aliases:add'], '### EPG ID\n\nFrance3-Alsace.fr\n\n### EPG source\n\niptv-epg-fr\n\n'
                                               '### Channel ID\n\nFrance3.fr\n\n### Feed ID (optional)\n\nAlsace\n')
    assert issues.apply(alias, db, IPTV) == ['added alias iptv-epg-fr:France3-Alsace.fr -> France3.fr@Alsace']


class FakeGitHub:
    def __init__(self, items):
        self.items, self.comments, self.labels = items, [], []

    def approved_issues(self):
        return self.items

    def comment(self, n, text):
        self.comments.append((n, text))

    def add_labels(self, n, labels):
        self.labels.append((n, labels))

    def remove_label(self, n, label):
        self.labels.append((n, '-' + label))


def test_update_applies_each_issue_alone_and_skips_faulty_ones(db, monkeypatch):
    good = {'number': 1, 'labels': [{'name': 'logos:add'}, {'name': 'approved'}], 'body': BODY}
    bad = {'number': 2, 'labels': [{'name': 'logos:add'}, {'name': 'approved'}], 'body': BODY.replace('Alsace', 'Mars')}
    gh = FakeGitHub([good, bad])
    monkeypatch.setattr(cli.net, 'GitHub', lambda: gh)
    monkeypatch.setattr(cli.iptvorg, 'load', lambda root: IPTV)
    monkeypatch.setattr(issues.net, 'download', lambda url: png(1000, 400))
    monkeypatch.setattr(issues, 'apply', lambda req, db_, iptv, downloader=None, _a=issues.apply:
                        _a(req, db_, iptv, downloader=lambda u: png(1000, 400)))
    assert cli.main(['--root', str(db.root), 'update']) == 0
    assert (db.root / 'temp/processed.txt').read_text() == 'Closes #1'
    assert gh.comments[0][0] == 2 and (2, ['check:failed']) in gh.labels
    assert list(json.loads((db.root / 'temp/changes.json').read_text())) == ['1']
    assert cli.validate(Database(db.root).load(), IPTV) == []
