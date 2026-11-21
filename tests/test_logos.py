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
    block = Image.new('RGBA', (800, 300), (0, 0, 0, 255))                       # white text on a black block
    block.paste(Image.new('RGBA', (500, 100), (255, 255, 255, 255)), (150, 100))
    assert image.white_variant(block) is None


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
    with pytest.raises(ops.NotInIptvOrg, match='does not exist in iptv-org'):
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
    assert issues.validate(bad, db, IPTV, downloader=fake.__getitem__) == []     # unknown feed: waits for iptv-org
    assert 'Mars' in bad.waiting and 'known: Alsace, National' in bad.waiting
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
    bad = {'number': 2, 'labels': [{'name': 'logos:add'}, {'name': 'approved'}], 'body': BODY.replace('France3.fr', 'France 3')}
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


def test_every_form_action(db):
    fake = {'https://example.org/f3-alsace.png': png(1000, 400)}
    get = fake.__getitem__
    add = issues.parse(1, ['logos:add'], BODY)
    issues.apply(add, db, IPTV, downloader=get)
    assert 'use the logos/edit form' in issues.validate(add, db, IPTV, downloader=get)[0]
    edit = issues.parse(2, ['logos:edit'], BODY)
    assert issues.validate(edit, db, IPTV, downloader=get) == []
    assert issues.apply(edit, db, IPTV, downloader=get)[0].startswith('replaced logos/fr/France3.fr@Alsace.png')
    new_edit = issues.parse(3, ['logos:edit'], BODY.replace('France3.fr', 'TF1.fr').replace('Alsace', ''))
    assert 'use the logos/add form' in issues.validate(new_edit, db, IPTV, downloader=get)[0]
    request = issues.parse(4, ['logos:request'], '### Channel ID\n\nTF1.fr\n')
    assert issues.validate(request, db, IPTV) == []
    with pytest.raises(ops.RequestError, match='fulfilled by a logos/add'):
        issues.apply(request, db, IPTV)
    alias = '### EPG ID\n\nF3A.fr\n\n### EPG source\n\nx\n\n### Channel ID\n\nFrance3.fr\n\n### Feed ID\n\nAlsace\n'
    issues.apply(issues.parse(5, ['aliases:add'], alias), db, IPTV)
    remove = issues.parse(6, ['aliases:remove'], alias)
    assert issues.validate(remove, db, IPTV) == []
    assert issues.apply(remove, db, IPTV) == ['removed alias x:F3A.fr']
    assert 'no alias' in issues.validate(remove, db, IPTV)[0]
    gone = issues.parse(7, ['logos:remove'], BODY)
    assert issues.apply(gone, db, IPTV)[0] == 'removed logos/fr/France3.fr@Alsace.png'


def test_a_logo_can_wait_for_its_channel_in_iptv_org(db, monkeypatch):
    body = BODY.replace('France3.fr', 'NewChannel.fr').replace('Alsace', '')
    fake = {'https://example.org/f3-alsace.png': png(1000, 400)}
    req = issues.parse(9, ['logos:add'], body)
    assert issues.validate(req, db, IPTV, downloader=fake.__getitem__) == []
    assert 'NewChannel.fr' in req.waiting                                  # image checked, channel awaited
    edit = issues.parse(10, ['logos:edit'], body)
    assert 'does not exist' in issues.validate(edit, db, IPTV, downloader=fake.__getitem__)[0]
    item = {'number': 9, 'labels': [{'name': 'logos:add'}, {'name': 'approved'}], 'body': body}
    gh = FakeGitHub([item])
    monkeypatch.setattr(cli.net, 'GitHub', lambda: gh)
    monkeypatch.setattr(issues.net, 'download', lambda url: png(1000, 400))
    monkeypatch.setattr(cli.iptvorg, 'load', lambda root: IPTV)
    cli.main(['--root', str(db.root), 'update'])
    assert (db.root / 'temp/processed.txt').read_text() == ''
    assert gh.labels == [(9, ['waiting:iptv-org'])] and gh.comments == []  # kept approved, no failure
    later = IptvOrg({**IPTV.channels, 'NewChannel.fr': {'id': 'NewChannel.fr', 'country': 'FR'}}, IPTV.feeds)
    monkeypatch.setattr(cli.iptvorg, 'load', lambda root: later)
    item['labels'].append({'name': 'waiting:iptv-org'})
    cli.main(['--root', str(db.root), 'update'])
    assert (db.root / 'temp/processed.txt').read_text() == 'Closes #9'
    assert (9, '-waiting:iptv-org') in gh.labels


def test_iptv_org_changes_are_warnings_and_aliases_follow_their_logo(db):
    ops.set_logo(db, 'TF1.fr', '', png(800, 300), 'x', IPTV)
    ops.set_alias(db, 'TF1-HD.fr', 'iptv-epg-fr', 'TF1.fr', '', IPTV)
    db.save()
    later = IptvOrg({'TF1.fr': {'id': 'TF1.fr', 'country': 'FR', 'replaced_by': 'TF1New.fr'}}, {})
    warnings = []
    assert cli.validate(Database(db.root).load(), later, warnings) == []          # never blocking
    assert 'replaced by `TF1New.fr`' in warnings[0]
    gone = IptvOrg({}, {})
    warnings = []
    assert cli.validate(Database(db.root).load(), gone, warnings) == []
    assert 'no longer in iptv-org' in warnings[0]
    assert ops.remove_logo(db, 'TF1.fr', '') == ['removed logos/fr/TF1.fr.png', 'removed alias iptv-epg-fr:TF1-HD.fr']
    db.save()
    assert cli.validate(Database(db.root).load(), IPTV) == []


def test_second_addition_the_same_night_is_refused(db):
    fake = {'https://example.org/f3-alsace.png': png(1000, 400)}
    first, second = issues.parse(1, ['logos:add'], BODY), issues.parse(2, ['logos:add'], BODY)
    assert issues.validate(second, db, IPTV, downloader=fake.__getitem__) == []    # valid when submitted
    issues.apply(first, db, IPTV, downloader=fake.__getitem__)
    with pytest.raises(ops.RequestError, match='already has a logo'):
        issues.apply(second, db, IPTV, downloader=fake.__getitem__)


def test_changes_issue_body_lists_each_warning():
    body = cli.changes_body(['data/logos.csv Syfy.fr: `Syfy.fr` is replaced by `SciFi.fr` in iptv-org'])
    assert '- [ ] data/logos.csv Syfy.fr: `Syfy.fr` is replaced by `SciFi.fr`' in body


def test_site_data(db, tmp_path):
    from worldwide_tv_logos import site
    ops.set_logo(db, 'TF1.fr', '', png(800, 300), 'x', IPTV)
    db.save()
    out = tmp_path / 'api'
    stats = site.build(db, IPTV, [{'code': 'FR', 'name': 'France', 'flag': ''}], out)
    assert stats['with_logo'] == 1
    import json
    fr = json.loads((out / 'countries' / 'fr.json').read_text(encoding='utf-8'))
    tf1 = next(c for c in fr['channels'] if c['id'] == 'TF1.fr')
    assert tf1['logos'][0]['url'].endswith('logos/fr/TF1.fr.png')
    assert json.loads((out / 'countries.json').read_text(encoding='utf-8'))[0]['name'] == 'France'


def test_logos_json_is_a_drop_in_for_iptv_org(db):
    ops.set_logo(db, 'TF1.fr', '', png(800, 300), 'x', IPTV)
    rec = cli.logo_record(db.logos[('TF1.fr', '', '')])
    iptv_org_fields = ['channel', 'feed', 'in_use', 'tags', 'width', 'height', 'format', 'url']
    assert list(rec)[:8] == iptv_org_fields
    assert rec['url'] == 'https://worldwide-tv-logos.github.io/database/logos/fr/TF1.fr.png'
    assert rec['country'] == 'fr' and rec['format'] == 'PNG' and rec['tags'] == []


def test_white_logo_gets_a_dark_version_and_white_box_with_black_text_is_kept():
    from PIL import Image as PILImage
    from PIL import ImageDraw as PILDraw
    letters = PILImage.new('RGBA', (800, 300), (0, 0, 0, 0))
    PILDraw.Draw(letters).rectangle((0, 0, 799, 299), outline=(255, 255, 255, 255), width=40)   # white on clear
    main, white = image.variants(letters)
    assert white is letters and main.getpixel((10, 10))[:3] == (image.INK,) * 3
    box = PILImage.new('RGBA', (800, 300), (255, 255, 255, 255))
    PILDraw.Draw(box).rectangle((200, 100, 600, 200), fill=(0, 0, 0, 255))                       # black text in a white box
    main, white = image.variants(box)
    assert main is box and white is None
