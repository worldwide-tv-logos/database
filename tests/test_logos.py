import io
import json

import pytest
from PIL import Image

from worldwide_tv_logos import cli, harvest, image, issues, ops
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


def _png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, 'PNG')
    return out.getvalue()


def test_white_background_touching_the_drawing_is_removed_unless_the_logo_needs_it():
    # white background (60 % of the border) cut by a red band touching the left, right and bottom edges: it goes,
    # with the white reached from the edges; the red parts stay
    img = Image.new('RGBA', (800, 300), (255, 255, 255, 255))
    img.paste(Image.new('RGBA', (800, 100), (200, 0, 0, 255)), (0, 200))
    img.paste(Image.new('RGBA', (100, 50), (200, 0, 0, 255)), (600, 0))
    out, notes = image.prepare(_png(img))
    assert notes == ['white frame removed'] and out.size == (800, 300)
    assert out.getpixel((10, 10))[3] == 0 and out.getpixel((330, 299))[3] == 255 and out.getpixel((650, 10))[3] == 255
    # black letters with white counters on a white background (EDA TV): without it the logo would be unreadable
    # on a dark screen, so the white background is kept
    img = Image.new('RGBA', (800, 300), (255, 255, 255, 255))
    for x in (0, 325, 650):
        img.paste(Image.new('RGBA', (150, 300), (10, 10, 10, 255)), (x, 0))
        img.paste(Image.new('RGBA', (50, 100), (255, 255, 255, 255)), (x + 50, 100))
    out, notes = image.prepare(_png(img))
    assert notes == [] and out.getpixel((250, 150))[3] == 255
    assert image.without_white_background(out) is None                   # so check_file does not report it


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
    for x in range(200, 600, 40):                                                     # thin black letters in a white box
        PILDraw.Draw(box).rectangle((x, 100, x + 8, 200), fill=(0, 0, 0, 255))
    main, white = image.variants(box)
    assert main is box and white is None


def test_reject_restores_the_logo_of_main_and_records_the_url(db, tmp_path_factory):
    import shutil
    ops.set_logo(db, 'TF1.fr', '', png(800, 300), 'https://example.org/old.png', IPTV)
    db.save()
    base = tmp_path_factory.mktemp('base')
    shutil.copytree(db.root, base, dirs_exist_ok=True)
    ops.set_logo(db, 'TF1.fr', '', png(1000, 300), 'https://example.org/new.png', IPTV)   # proposed update
    db.save()
    assert cli.main(['--root', str(db.root), 'reject', 'TF1.fr', '--reason', 'old branding',
                     '--base', str(base)]) == 0
    again = Database(db.root).load()
    assert again.logos[('TF1.fr', '', '')].origin == 'https://example.org/old.png'
    assert harvest.load_rejected(db.root) == {('TF1.fr', 'https://example.org/new.png')}
    assert cli.validate(again, IPTV) == []


def test_black_drawing_inside_a_white_disc_is_not_darkened():
    from PIL import Image as PILImage
    from PIL import ImageDraw as PILDraw
    disc = PILImage.new('RGBA', (600, 600), (0, 0, 0, 0))
    d = PILDraw.Draw(disc)
    d.ellipse((0, 0, 599, 599), fill=(255, 255, 255, 255))
    d.rectangle((200, 150, 400, 450), fill=(0, 0, 0, 255))                                   # thick black "10"
    main, white = image.variants(disc)
    assert main is disc and white is None


def test_wikidata_logos_keep_only_the_current_one():
    from worldwide_tv_logos import sources

    def claim(file, start='', end='', rank='normal'):
        quals = {}
        if start:
            quals['P580'] = [{'datavalue': {'value': {'time': f'+{start}T00:00:00Z'}}}]
        if end:
            quals['P582'] = [{'datavalue': {'value': {'time': f'+{end}T00:00:00Z'}}}]
        return {'rank': rank, 'mainsnak': {'datavalue': {'value': file}}, 'qualifiers': quals}
    item = sources.parse_entity({'id': 'Q1', 'labels': {'es': {'value': 'Canal Sur'}}, 'claims': {
        'P154': [claim('Canal Sur 2011-2017 logo.svg'), claim('Old.png', '2008-01-01', '2011-01-01'),
                 claim('New.png', '2017-01-01'), claim('New.svg', '2017-01-01')],
        'P31': [{'rank': 'normal', 'mainsnak': {'datavalue': {'value': {'id': 'Q2001305'}}}}]}})
    assert item['names'] == ['Canal Sur'] and item['types'] == ['Q2001305']
    assert sources.current_logos(item) == [sources.COMMONS_FILE + 'New.svg', sources.COMMONS_FILE + 'New.png']


def test_website_logos_and_old_file_names():
    from worldwide_tv_logos import sources
    html = ('<header><img class="site-logo" src="/img/brand.svg"><img src="/photo.jpg" alt="news">'
            '<img src="data:image/png;base64,xx" class="logo"><link rel="icon" href="/favicon.svg"></header>')
    assert sources.website_logos('https://example.org/', html) == ['https://example.org/img/brand.svg',
                                                                    'https://example.org/favicon.svg']
    cand = harvest.Candidate('iptv-org', 'https://upload.wikimedia.org/x/Canal_Sur_2011-2017_logo.svg')
    assert harvest.evaluate(cand, lambda url: b'').error.startswith('old branding')


def test_move_channel_moves_logos_sources_and_aliases(db):
    later = IptvOrg({**IPTV.channels, 'TF1New.fr': {'id': 'TF1New.fr', 'name': 'TF1', 'country': 'FR'}}, IPTV.feeds)
    ops.set_logo(db, 'TF1.fr', '', png(800, 300), 'x', IPTV)
    ops.set_alias(db, 'TF1-HD.fr', 'iptv-epg-fr', 'TF1.fr', '', IPTV)
    db.save()
    ops.move_channel(db, 'TF1.fr', 'TF1New.fr', later)
    db.save()
    again = Database(db.root).load()
    assert ('TF1New.fr', '', '') in again.logos and ('TF1.fr', '', '') not in again.logos
    assert next(iter(again.aliases.values())).channel == 'TF1New.fr'
    assert cli.validate(again, later) == []
    with pytest.raises(ops.RequestError):
        ops.move_channel(db, 'TF1New.fr', 'Nope.fr', later)


def test_navy_letters_get_a_white_variant_but_not_a_gradient():
    from PIL import Image as PILImage
    from PIL import ImageDraw as PILDraw
    navy = PILImage.new('RGBA', (800, 300), (0, 0, 0, 0))
    PILDraw.Draw(navy).rectangle((0, 0, 500, 299), fill=(5, 20, 80, 255))                       # navy letters
    PILDraw.Draw(navy).rectangle((550, 0, 799, 299), fill=(220, 50, 40, 255))                   # red part
    white = image.white_variant(navy)
    assert white is not None and white.getpixel((10, 10))[:3] == (255, 255, 255)
    assert white.getpixel((700, 10))[:3] == (220, 50, 40)
    gradient = PILImage.new('RGBA', (800, 300), (0, 0, 0, 0))
    d = PILDraw.Draw(gradient)
    for x in range(800):                                                                        # navy to blue
        d.line((x, 0, x, 299), fill=(0, 10 + x // 10, 60 + x // 5, 255))
    assert image.white_variant(gradient) is None


def test_editions_are_harvest_units_except_quality_versions():
    iptv = IptvOrg({'France3.fr': {'id': 'France3.fr', 'name': 'France 3', 'country': 'FR'}},
                   {('France3.fr', 'National'): {'id': 'National', 'is_main': True},
                    ('France3.fr', 'Alsace'): {'id': 'Alsace', 'name': 'Alsace'},
                    ('France3.fr', 'HD'): {'id': 'HD', 'name': 'HD'}})
    units = harvest.units(iptv, 'fr')
    assert [(u['id'], u['name']) for u in units] == [('France3.fr', 'France 3'),
                                                     ('France3.fr@Alsace', 'France 3 Alsace')]
    assert harvest.channel_keys(units[1]) == {'france3alsace'}            # never the key of the channel itself


def test_fingerprint_sees_the_same_drawing_through_resizing():
    big = Image.open(io.BytesIO(png(1000, 400))).convert('RGBA')
    small = big.resize((500, 200))
    other = Image.new('RGBA', (1000, 400), (0, 0, 0, 0))
    other.paste((0, 0, 255, 255), (0, 0, 300, 400))
    assert image.same_drawing(image.fingerprint(big), image.fingerprint(small))
    assert not image.same_drawing(image.fingerprint(big), image.fingerprint(other))


def test_iptv_epg_guide_logos_by_alias_id_and_name(tmp_path):
    import gzip
    from types import SimpleNamespace

    from worldwide_tv_logos import sources
    xml = (b'<?xml version="1.0"?><tv>'
           b'<channel id="La1.es"><display-name>ES - La 1</display-name><icon src="https://e/la1"/></channel>'
           b'<channel id="Tele5Guide"><display-name>Telecinco</display-name><icon src="https://e/t5"/></channel>'
           b'<channel id="Cuatro.es"><display-name>Cuatro</display-name></channel>'
           b'<channel id="Mega.es"><display-name>ES - Mega</display-name><icon src="https://e/mega"/></channel>'
           b'<programme channel="La1.es"><title>x</title></programme>'
           b'<channel id="Late.es"><icon src="https://e/late"/></channel></tv>')
    channels = sources.parse_iptv_epg(gzip.compress(xml))
    assert [c['id'] for c in channels] == ['La1.es', 'Tele5Guide', 'Cuatro.es', 'Mega.es']
    assert channels[2]['icon'] == ''
    assert channels[0]['names'] == ['La 1']
    assert sources.load_iptv_epg(tmp_path, 'es', lambda *a, **k: gzip.compress(xml)) == channels
    assert sources.load_iptv_epg(tmp_path, 'es', lambda *a, **k: b'') == channels  # cached one day

    alias = SimpleNamespace(epg_id='Mega.es', source='iptv-epg.org', channel='MegaTV.es', feed='')
    epg = sources.EpgIndex(channels, [alias], harvest.key)
    assert epg.logos({'id': 'La1.es'}, set()) == ['https://e/la1']
    assert epg.logos({'id': 'Telecinco.es'}, {harvest.key('Telecinco')}) == ['https://e/t5']
    assert epg.logos({'id': 'MegaTV.es', 'channel': 'MegaTV.es', 'feed': ''}, set()) == ['https://e/mega']
    assert epg.logos({'id': 'Other.es'}, {harvest.key('Other')}) == []
    assert epg.logos({'id': 'Cuatro.es'}, set()) == []                                          # no icon
    assert epg.match({'id': 'Telecinco.es'}, {harvest.key('Telecinco')}) == 'Tele5Guide'
    assert epg.match({'id': 'La1.es'}, {harvest.key('La 1')}) is None                          # same ID

    def missing(*a, **k):
        raise sources.net.DownloadError('HTTP 404')
    assert sources.load_iptv_epg(tmp_path / 'x', 'zz', missing) == []


def test_drawing_of_another_family_is_a_doubt():
    assert harvest.family('Eurosport6.fr') == harvest.family('Eurosport8.fr') == 'eurosport'
    assert harvest.family('ComedyCentral.es') == harvest.family('ComedyCentral.fr@Paris')
    assert harvest.family('BlueAction.ch') != harvest.family('Action.fr')
    fp = (1 << 200) - 1
    drawings = [('Action.fr', 'Action.fr', fp), ('Eurosport6.fr', 'Eurosport6.fr', 12345)]
    assert harvest.drawing_of_other('BlueAction.ch', fp ^ 0b111, drawings) == 'Action.fr'      # 3 bits apart
    assert harvest.drawing_of_other('BlueAction.ch', fp ^ ((1 << 10) - 1), drawings) is None   # 10 bits apart
    assert harvest.drawing_of_other('Action.fr', fp, drawings) is None                         # itself
    assert harvest.drawing_of_other('Eurosport8.fr', 12345, drawings) is None                  # same family
    assert harvest.shared_drawings('ch', drawings + [('BlueAction.ch', 'BlueAction.ch', fp)]) == \
        [('BlueAction.ch', 'Action.fr')]
    kept, doubts = harvest.split_duplicates(
        [({'id': 'BlueAction.ch', 'channel': 'BlueAction.ch', 'name': 'Blue Action'},
          harvest.Candidate('iptv-epg', 'https://e/x', fp=fp))], {}, drawings)
    assert kept == [] and doubts[0][1] == 'Action.fr'


def test_preview_of_a_request_shows_the_proposed_logo(db, monkeypatch):
    req = issues.parse(15, ['logos:add'], BODY)
    monkeypatch.setattr(cli.net, 'download', lambda url, **kw: png(1000, 400))
    cli._preview(db, req)
    assert (db.root / 'temp' / 'preview' / 'sheet-01.png').is_file()


def test_white_version_rules_for_dark_logos():
    from PIL import ImageDraw

    def logo(draw):
        im = Image.new('RGBA', (600, 200), (0, 0, 0, 0))
        draw(ImageDraw.Draw(im))
        return im
    navy = logo(lambda d: d.rectangle((20, 60, 420, 140), fill=(48, 48, 128, 255)))            # Val TV, Telecinco
    assert image.white_variant(navy) is not None
    badge = logo(lambda d: (d.rectangle((20, 60, 420, 140), fill=(16, 0, 64, 255)),           # Eurosport 6: white
                            d.rectangle((460, 40, 580, 160), fill=(224, 0, 48, 255)),         # digit in a red box
                            d.rectangle((500, 70, 540, 130), fill=(245, 245, 245, 255))))
    assert image.white_variant(badge) is not None
    block = logo(lambda d: (d.rectangle((20, 40, 200, 160), fill=(0, 0, 0, 255)),             # CNEWS: white C on
                            d.rectangle((60, 70, 160, 130), fill=(250, 250, 250, 255)),       # a black block, and
                            d.rectangle((230, 40, 580, 160), fill=(224, 0, 30, 255)),         # white text in red
                            d.rectangle((260, 70, 560, 130), fill=(250, 250, 250, 255))))
    assert image.white_variant(block) is None


def test_sharper_version_says_whether_it_is_the_same_drawing(tmp_path):
    src = tmp_path / 'X.fr.png'
    src.write_bytes(png(512, 200))
    logo = Logo('X.fr', '', '', 512, 200, 'https://example.org/x.png')
    current = 0x5A5A5A5A5A5A5A5A                                           # fingerprint of the current logo
    same = harvest.Candidate('website', 'https://x.fr/logo.svg', data=SVG, svg=True, size=(1200, 400), fp=current)
    assert harvest.update_reason(logo, src, same, set(), [current]) == 'vector (SVG) version found, same drawing'
    other = harvest.Candidate('iptv-epg', 'https://e.org/x.png', data=b'x', size=(1000, 400), fp=~current & (2**256 - 1))
    assert 'DIFFERENT drawing' in harvest.update_reason(logo, src, other, set(), [current])
    small = harvest.Candidate('iptv-epg', 'https://e.org/x.png', data=b'x', size=(600, 240), fp=current)
    assert harvest.update_reason(logo, src, small, set(), [current]) is None        # not clearly larger
    assert cli._slice(['a', 'b', 'c'], 1, 2) == ['c', 'a'] and cli._slice([], 1, 2) == []


def test_logo_copied_from_a_page_as_a_data_uri():
    from worldwide_tv_logos import net
    svg = net.download('data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%2F%3E')
    assert svg == b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    assert net.download('data:image/png;base64,iVBORw0KGgo=') == b'\x89PNG\r\n\x1a\n'
    with pytest.raises(net.DownloadError, match='only https'):
        net.download('http://example.org/logo.png')


def test_seen_on_finds_a_logo_drawn_or_shown_in_a_page():
    from worldwide_tv_logos import seen
    logo = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><path d="M10 10 L90 10 L90 30 L50 38 '
            b'L10 30 Z M20 15 L80 15 L80 25 L20 25 Z"/></svg>')
    pages = {'https://tv.example/': b'<header><svg viewBox="0 0 100 40"><path d="M10 10 L90 10 L90 30 L50 38 L10 30 Z '
                                     b'M20 15 L80 15 L80 25 L20 25 Z"/></svg></header>',
             'https://other.example/': b'<img src="/a.png">', 'https://other.example/a.png': png(300, 300)}
    get = lambda url, **kw: pages[url]
    assert 'written in the page' in seen.seen_on('https://tv.example/', logo, get, pause=0)
    assert seen.seen_on('https://other.example/', logo, get, pause=0) is None
    red = png(600, 200)
    pages['https://other.example/a.png'] = png(300, 100)                                    # same drawing, smaller
    assert 'image https://other.example/a.png' in seen.seen_on('https://other.example/', red, get, pause=0)


def test_guide_aliases_only_for_channels_with_a_logo(db, monkeypatch):
    import argparse

    from worldwide_tv_logos import iptvorg, sources
    ops.set_logo(db, 'France3.fr', '', SVG, 'https://example.org/f3.svg', IPTV)
    guide = [{'id': 'F3guide', 'names': ['France 3'], 'icon': ''}, {'id': 'TF1guide', 'names': ['TF1'], 'icon': ''}]
    monkeypatch.setattr(iptvorg, 'load', lambda root: IPTV)
    monkeypatch.setattr(harvest, 'load_epg', lambda db, cc, dl, log: sources.EpgIndex(guide, [], harvest.key))
    cli.cmd_guide_aliases(argparse.Namespace(country='fr'), db)
    assert [(a.epg_id, a.channel) for a in db.aliases.values()] == [('F3guide', 'France3.fr')]   # TF1: no logo
    assert cli.validate(Database(db.root).load(), IPTV) == []


def test_bulk_adds_the_iptv_org_logos_that_pass_the_rules(db):
    logos = [{'channel': 'TF1.fr', 'feed': '', 'url': 'https://x.org/tf1.svg', 'format': 'SVG'},
             {'channel': 'France3.fr', 'feed': '', 'url': 'https://x.org/f3.png', 'format': 'PNG', 'width': 300,
              'height': 100}]
    files = {'https://x.org/tf1.svg': SVG}
    stats = harvest.bulk(db, IPTV, 'fr', logos, pause=0, downloader=lambda url, **kw: files[url], log=lambda s: None)
    assert stats == {'todo': 4, 'added': 1, 'doubts': 0}                  # France 3 (too small) and its 2 editions
    assert ('TF1.fr', '', '') in db.logos and db.logos[('TF1.fr', '', '')].origin == 'https://x.org/tf1.svg'
    assert cli.validate(Database(db.root).load(), IPTV) == []


def test_epg_sure_match_and_newer_guide_logo_replaced_when_the_website_shows_it(db, tmp_path, monkeypatch):
    from worldwide_tv_logos import sources
    guide = [{'id': 'TF1guide', 'names': ['TF1'], 'icon': 'https://g.org/tf1.png'},
             {'id': 'A', 'names': ['France 3'], 'icon': ''}, {'id': 'B', 'names': ['France 3'], 'icon': ''}]
    epg = sources.EpgIndex(guide, [], harvest.key)
    assert epg.sure({'id': 'TF1.fr'}, {harvest.key('TF1')})['id'] == 'TF1guide'
    assert epg.sure({'id': 'France3.fr'}, {harvest.key('France 3')}) is None              # two guide channels
    old = Image.new('RGBA', (800, 300), (200, 0, 0, 255))
    old.paste((0, 0, 200, 255), (0, 0, 300, 300))                                         # blue block on the left
    new = old.transpose(Image.Transpose.FLIP_LEFT_RIGHT)                                   # another drawing
    old, new = _png(old), _png(new)
    ops.set_logo(db, 'TF1.fr', '', old, 'https://x.org/old.png', IPTV)
    iptv = IptvOrg({'TF1.fr': {'id': 'TF1.fr', 'name': 'TF1', 'country': 'FR', 'website': 'https://tf1.fr/'}}, {})
    monkeypatch.setattr(harvest, 'load_epg', lambda db, cc, dl, log: epg)
    get = {'https://g.org/tf1.png': new}.__getitem__
    run = lambda out, seen: harvest.epg_check(db, iptv, 'fr', tmp_path / out, downloader=lambda u, **k: get(u),
                                              pause=0, log=lambda s: None, seen_on=seen)
    assert run('a', lambda page, data, dl: None) == {'checked': 1, 'replaced': 0, 'review': 1}   # website: no proof
    assert (tmp_path / 'a' / 'sheet-01.png').is_file()
    assert run('b', lambda page, data, dl: 'found' if data == new else None) == {'checked': 1, 'replaced': 1, 'review': 0}
    assert db.logos[('TF1.fr', '', '')].origin == 'https://g.org/tf1.png'
    assert run('c', lambda page, data, dl: None)['checked'] == 0                   # now the guide's URL: nothing to do


def test_merge_rows_keeps_the_upstream_version_of_rows_this_commit_did_not_change():
    from worldwide_tv_logos.db import merge_rows
    base = {'W9': 'old', 'TF1': 'a', 'M6': 'x'}
    upstream = {'W9': 'new', 'TF1': 'a', 'M6': 'x', 'Arte': 'up'}       # W9 updated, Arte added on main meanwhile
    ours = {'W9': 'old', 'TF1': 'b', 'Gulli': 'ours'}                     # TF1 changed, M6 removed, Gulli added here
    assert merge_rows(base, upstream, ours) == {'W9': 'new', 'TF1': 'b', 'Arte': 'up', 'Gulli': 'ours'}


def test_download_quotes_spaces_and_reports_malformed_urls():
    from worldwide_tv_logos import net
    seen = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout):
        seen.append(req.full_url)
        return Resp(b'ok')

    assert net.download('https://a.example/img/LOGO nautical WHITE.svg', opener=opener) == b'ok'
    assert seen == ['https://a.example/img/LOGO%20nautical%20WHITE.svg']

    def bad(req, timeout):
        raise ValueError('bad url')

    with pytest.raises(net.DownloadError):
        net.download('https://a.example/x.png', opener=bad)


def _git_repo(root):
    import subprocess

    def git(*args):
        return subprocess.run(['git', *args], cwd=root, capture_output=True, check=True, text=True).stdout.strip()
    git('init', '-q', '-b', 'main')
    git('config', 'user.email', 't@t')
    git('config', 'user.name', 't')
    return git


def _write(root, rel, data):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


HEADER = 'channel,feed,variant,width,height,origin,added,updated\n'


def test_merge_data_files_applies_our_logo_files_on_top_of_main_without_a_rebase(tmp_path):
    git = _git_repo(tmp_path)
    _write(tmp_path, 'data/logos.csv', HEADER + 'TF1.fr,,,10,10,a,2026-01-01,\n')
    _write(tmp_path, 'data/rejected.csv', 'channel,url,reason,date\n')
    _write(tmp_path, 'logos/fr/TF1.fr.png', b'tf1')
    git('add', '-A')
    git('commit', '-qm', 'base')
    base = git('rev-parse', 'HEAD')
    # main meanwhile: Telesambre added with a PNG source, TF1 untouched
    _write(tmp_path, 'data/logos.csv', HEADER + 'Telesambre.be,,,10,10,main,2026-02-01,\nTF1.fr,,,10,10,a,2026-01-01,\n')
    _write(tmp_path, 'logos/be/Telesambre.be.png', b'main')
    _write(tmp_path, 'sources/be/Telesambre.be.png', b'main source')
    _write(tmp_path, 'data/rejected.csv', 'channel,url,reason,date\nA.fr,u1,r,2026-02-01\n')
    git('add', '-A')
    git('commit', '-qm', 'main')
    upstream = git('rev-parse', 'HEAD')
    # our change, from base: the same logo from a JPG source, and a rejection
    git('checkout', '-q', base)
    _write(tmp_path, 'data/logos.csv', HEADER + 'Telesambre.be,,,10,10,ours,2026-02-02,\nTF1.fr,,,10,10,a,2026-01-01,\n')
    _write(tmp_path, 'logos/be/Telesambre.be.png', b'ours')
    _write(tmp_path, 'sources/be/Telesambre.be.jpg', b'ours source')
    _write(tmp_path, 'data/rejected.csv', 'channel,url,reason,date\nB.fr,u2,r,2026-02-02\n')
    git('add', '-A')
    git('commit', '-qm', 'ours')
    ours = git('rev-parse', 'HEAD')
    git('checkout', '-q', upstream)                    # the working tree holds main (git reset --hard origin/main)
    assert cli.main(['--root', str(tmp_path), 'merge-data', base, ours, upstream, '--files']) == 0
    assert (tmp_path / 'logos/be/Telesambre.be.png').read_bytes() == b'ours'
    assert sorted(p.name for p in (tmp_path / 'sources/be').iterdir()) == ['Telesambre.be.jpg']   # one source
    assert 'Telesambre.be,,,10,10,ours,' in (tmp_path / 'data/logos.csv').read_text()
    assert (tmp_path / 'data/rejected.csv').read_text().splitlines()[1:] == ['A.fr,u1,r,2026-02-01',
                                                                               'B.fr,u2,r,2026-02-02']


def test_regress_check_fails_when_an_older_version_of_a_logo_comes_back(tmp_path):
    git = _git_repo(tmp_path)
    _write(tmp_path, 'data/logos.csv', HEADER + 'W9.fr,,,10,10,new,2025-01-01,2026-11-22\nTF1.fr,,,10,10,a,2026-01-01,\n')
    git('add', '-A')
    git('commit', '-qm', 'main')
    root = ['--root', str(tmp_path)]
    assert cli.main([*root, 'regress-check', 'HEAD']) == 0
    _write(tmp_path, 'data/logos.csv', HEADER + 'W9.fr,,,10,10,old,2025-01-01,2026-03-01\nTF1.fr,,,10,10,b,2026-01-01,2026-11-23\n')
    assert cli.main([*root, 'regress-check', 'HEAD']) == 1


def test_one_image_for_numbered_channels_is_a_brand_logo_without_the_number():
    def ch(cid, name):
        return {'id': cid, 'channel': cid, 'name': name}
    generic = b'generic sky sport'
    kept, doubts = harvest.split_duplicates([
        (ch('SkySport1.de', 'Sky Sport 1'), harvest.Candidate('iptv-epg', 'https://e/sky.png', data=generic, fp=7)),
        (ch('SkySport2.de', 'Sky Sport 2'), harvest.Candidate('iptv-epg', 'https://e/sky.png', data=generic, fp=7)),
        (ch('SkySport.de', 'Sky Sport'), harvest.Candidate('iptv-epg', 'https://e/sky.png', data=generic, fp=7)),
    ])
    assert [c['id'] for c, _ in kept] == ['SkySport.de']                    # the brand keeps its logo
    assert sorted(c['id'] for c, _ in doubts) == ['SkySport1.de', 'SkySport2.de']
    assert 'without the channel number' in doubts[0][1]
    # their own logos differ by the digit only (same fingerprint): each channel keeps its own
    kept, doubts = harvest.split_duplicates([
        (ch('Eurosport1.fr', 'Eurosport 1'), harvest.Candidate('wikidata', 'https://w/1.svg', data=b'1', fp=7)),
        (ch('Eurosport2.fr', 'Eurosport 2'), harvest.Candidate('wikidata', 'https://w/2.svg', data=b'2', fp=7)),
    ])
    assert len(kept) == 2 and doubts == []


def test_a_wikipedia_file_page_gives_the_image_itself():
    from worldwide_tv_logos import net
    assert net.image_url('https://fr.wikipedia.org/wiki/Le_Figaro_TV#/media/Fichier:Le_Figaro_TV_IDF_(2023).png') == \
        'https://fr.wikipedia.org/wiki/Special:FilePath/Le_Figaro_TV_IDF_(2023).png'
    assert net.image_url('https://commons.wikimedia.org/wiki/File:TF1_logo_2013.svg') == \
        'https://commons.wikimedia.org/wiki/Special:FilePath/TF1_logo_2013.svg'
    assert net.image_url('https://fr.wikipedia.org/wiki/TF1') == 'https://fr.wikipedia.org/wiki/TF1'
    assert net.image_url('https://example.org/wiki/File:x.png') == 'https://example.org/wiki/File:x.png'
