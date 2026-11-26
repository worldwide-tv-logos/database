import io
import json

import pytest
from PIL import Image

from worldwide_tv_logos import cli, guides, harvest, image, issues, ops, registry, site
from worldwide_tv_logos.db import Channel, Database, ExternalId, Logo
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


F3, ALS, TF1, BIS = 'ch_france3000', 'ch_f3a5ace000', 'ch_tf1000000a', 'ch_tf1b000000'   # channels of the test registry


@pytest.fixture
def bare(tmp_path):
    """A repository with an empty registry."""
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data' / 'countries.csv').write_text('code,name\nfr,France\n', encoding='utf-8')
    return Database(tmp_path).load()


@pytest.fixture
def db(bare):
    """France 3 with its edition France 3 Alsace, TF1, and TF1 Bis (no iptv-org ID), in the registry."""
    for cid, slug, name, parent, source, ext in (
            (F3, 'france-3.fr', 'France 3', '', 'iptv-org', 'France3.fr'),
            (ALS, 'france-3-alsace.fr', 'France 3 Alsace', F3, 'iptv-org-feed', 'France3.fr@Alsace'),
            (TF1, 'tf1.fr', 'TF1', '', 'iptv-org', 'TF1.fr'),
            (BIS, 'tf1-bis.fr', 'TF1 Bis', '', '', '')):
        bare.channels[cid] = Channel(cid, slug, name, '', 'fr', 'active', parent, '', '2026-11-23', '')
        if source:
            bare.external_ids[(source, ext)] = ExternalId(cid, source, ext, 'import', '2026-11-23')
    bare.save()
    return Database(bare.root).load()


def test_names_are_derived_from_our_channel_id():
    logo = Logo(ALS, 'white')
    assert (logo.file, logo.logo_id) == (f'logos/{ALS}.white.png', ALS)
    assert Logo(TF1).file == f'logos/{TF1}.png'


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
    changes = ops.set_logo(db, ALS, SVG, 'https://example.org/f3.svg', today='2026-11-21')
    assert len(changes) == 2
    db.save()
    assert (db.root / f'logos/{ALS}.png').is_file()
    assert (db.root / f'logos/{ALS}.white.png').is_file()
    assert (db.root / f'sources/{ALS}.svg').read_bytes() == SVG
    assert cli.validate(Database(db.root).load(), IPTV) == []
    # replacement by a coloured logo: same file names, no white variant any more, dates kept / updated
    ops.set_logo(db, ALS, png(900, 300), 'issue #3', today='2026-12-01')
    db.save()
    again = Database(db.root).load()
    logo = again.logos[(ALS, '')]
    assert (logo.added, logo.updated, logo.origin) == ('2026-11-21', '2026-12-01', 'issue #3')
    assert (ALS, 'white') not in again.logos
    assert not (db.root / f'logos/{ALS}.white.png').exists()
    assert [p.name for p in (db.root / 'sources').iterdir()] == [f'{ALS}.png']
    assert cli.validate(again, IPTV) == []


def test_unknown_ids_are_refused(db):
    with pytest.raises(ops.RequestError, match='not a channel ID of our registry'):
        ops.set_logo(db, 'ch_0000000000', png(800, 300), 'x')
    with pytest.raises(ops.NotRegistered, match='not a channel of our registry yet'):
        ops.channel_of(db, 'Nope.fr')                                   # an iptv-org ID: may come, waits
    with pytest.raises(ops.RequestError, match='unknown channel') as exc:
        ops.channel_of(db, 'France 3')
    assert not isinstance(exc.value, ops.NotRegistered)
    assert ops.channel_of(db, 'France3.fr@Alsace').id == ALS and ops.channel_of(db, 'tf1.fr').id == TF1


def test_validate_finds_stray_and_misnamed_files(db):
    ops.set_logo(db, TF1, png(800, 300), 'x')
    db.save()
    (db.root / 'logos/tf1-fr.png').write_bytes(png(800, 300))
    (db.root / 'sources/Old.fr.png').write_bytes(b'x')
    errors = cli.validate(Database(db.root).load(), IPTV)
    assert any('tf1-fr.png: not listed' in e for e in errors)
    assert any('Old.fr.png: original of no logo' in e for e in errors)


BODY = """### Channel ID

ch_f3a5ace000

### Logo URL

https://example.org/f3-alsace.png

### Notes (optional)

_No response_
"""


def test_issue_form_is_parsed_validated_and_applied(db):
    req = issues.parse(12, ['logos:add', 'approved'], BODY)
    assert (req.kind, req.get('channel'), req.get('notes')) == ('logos:add', ALS, '')
    fake = {'https://example.org/f3-alsace.png': png(1000, 400)}
    assert issues.validate(req, db, downloader=fake.__getitem__) == []
    changes = issues.apply(req, db, downloader=fake.__getitem__)
    assert changes[0].startswith(f'added logos/{ALS}.png')
    assert db.logos[(ALS, '')].origin == 'issue #12'
    alias = issues.parse(14, ['aliases:add'], '### EPG ID\n\nFrance3-Alsace.fr\n\n### EPG source\n\niptv-epg-fr\n\n'
                                               f'### Channel ID\n\n{ALS.upper()}\n')
    assert issues.apply(alias, db) == [f'added alias iptv-epg-fr:France3-Alsace.fr -> {ALS}']


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
    bad = {'number': 2, 'labels': [{'name': 'logos:add'}, {'name': 'approved'}], 'body': BODY.replace(ALS, 'France 3')}
    gh = FakeGitHub([good, bad])
    monkeypatch.setattr(cli.net, 'GitHub', lambda: gh)
    monkeypatch.setattr(cli.iptvorg, 'load', lambda root: IPTV)
    monkeypatch.setattr(issues.net, 'download', lambda url: png(1000, 400))
    monkeypatch.setattr(issues, 'apply', lambda req, db_, downloader=None, _a=issues.apply:
                        _a(req, db_, downloader=lambda u: png(1000, 400)))
    assert cli.main(['--root', str(db.root), 'update']) == 0
    assert (db.root / 'temp/processed.txt').read_text() == 'Closes #1'
    assert gh.comments[0][0] == 2 and (2, ['check:failed']) in gh.labels
    assert list(json.loads((db.root / 'temp/changes.json').read_text())) == ['1']
    assert cli.validate(Database(db.root).load(), IPTV) == []


def test_every_form_action(db):
    fake = {'https://example.org/f3-alsace.png': png(1000, 400)}
    get = fake.__getitem__
    add = issues.parse(1, ['logos:add'], BODY)
    issues.apply(add, db, downloader=get)
    assert 'use the logos/edit form' in issues.validate(add, db, downloader=get)[0]
    edit = issues.parse(2, ['logos:edit'], BODY)
    assert issues.validate(edit, db, downloader=get) == []
    assert issues.apply(edit, db, downloader=get)[0].startswith(f'replaced logos/{ALS}.png')
    new_edit = issues.parse(3, ['logos:edit'], BODY.replace(ALS, TF1))
    assert 'use the logos/add form' in issues.validate(new_edit, db, downloader=get)[0]
    request = issues.parse(4, ['logos:request'], f'### Channel ID\n\n{TF1}\n')
    assert issues.validate(request, db) == []
    with pytest.raises(ops.RequestError, match='fulfilled by a logos/add'):
        issues.apply(request, db)
    alias = f'### EPG ID\n\nF3A.fr\n\n### EPG source\n\nx\n\n### Channel ID\n\n{ALS}\n'
    issues.apply(issues.parse(5, ['aliases:add'], alias), db)
    ops.set_logo(db, TF1, png(800, 300), 'x')
    other = issues.parse(8, ['aliases:add'], alias.replace(ALS, TF1))
    assert 'already the alias of' in issues.validate(other, db)[0]          # a guide ID points to one channel
    assert 'no alias' in issues.validate(issues.parse(9, ['aliases:remove'], alias.replace(ALS, TF1)), db)[0]
    remove = issues.parse(6, ['aliases:remove'], alias)
    assert issues.validate(remove, db) == []
    assert issues.apply(remove, db) == ['removed alias x:F3A.fr']
    assert 'no alias' in issues.validate(remove, db)[0]
    gone = issues.parse(7, ['logos:remove'], BODY)
    assert issues.apply(gone, db)[0] == f'removed logos/{ALS}.png'


def test_forms_take_our_channel_id_only(db):
    fake = {'https://example.org/f3-alsace.png': png(1000, 400)}
    for other in ('France3.fr@Alsace', 'france-3-alsace.fr', 'France 3 Alsace'):  # iptv-org ID, slug, name
        req = issues.parse(9, ['logos:add'], BODY.replace(ALS, other))
        assert 'not a channel ID' in issues.validate(req, db, downloader=fake.__getitem__)[0]
    req = issues.parse(10, ['logos:add'], BODY.replace(ALS, 'ch_0000000000'))
    assert 'channels/add form' in issues.validate(req, db, downloader=fake.__getitem__)[0]
    db.channels[TF1].status, db.channels[TF1].parent = 'merged', BIS          # merged: the current one is named
    req = issues.parse(11, ['logos:add'], BODY.replace(ALS, TF1))
    assert f'is now `{BIS}`' in issues.validate(req, db, downloader=fake.__getitem__)[0]


def test_iptv_org_changes_are_warnings_and_aliases_follow_their_logo(db):
    ops.set_logo(db, TF1, png(800, 300), 'x')
    ops.set_alias(db, 'TF1-HD.fr', 'iptv-epg-fr', TF1)
    db.save()
    later = IptvOrg({'TF1.fr': {'id': 'TF1.fr', 'country': 'FR', 'replaced_by': 'TF1New.fr'}}, {})
    warnings = []
    assert cli.validate(Database(db.root).load(), later, warnings) == []          # never blocking
    assert 'replaced by `TF1New.fr`' in warnings[0]
    gone = IptvOrg({}, {})
    warnings = []
    assert cli.validate(Database(db.root).load(), gone, warnings) == []
    assert 'no longer in iptv-org' in warnings[0]
    assert ops.remove_logo(db, TF1) == [f'removed logos/{TF1}.png', 'removed alias iptv-epg-fr:TF1-HD.fr']
    db.save()
    assert cli.validate(Database(db.root).load(), IPTV) == []


def test_second_addition_the_same_night_is_refused(db):
    fake = {'https://example.org/f3-alsace.png': png(1000, 400)}
    first, second = issues.parse(1, ['logos:add'], BODY), issues.parse(2, ['logos:add'], BODY)
    assert issues.validate(second, db, downloader=fake.__getitem__) == []    # valid when submitted
    issues.apply(first, db, downloader=fake.__getitem__)
    with pytest.raises(ops.RequestError, match='already has a logo'):
        issues.apply(second, db, downloader=fake.__getitem__)


def test_changes_issue_body_lists_each_warning():
    body = cli.changes_body(['data/logos.csv Syfy.fr: `Syfy.fr` is replaced by `SciFi.fr` in iptv-org'])
    assert '- [ ] data/logos.csv Syfy.fr: `Syfy.fr` is replaced by `SciFi.fr`' in body


def test_site_data(db, tmp_path):
    from worldwide_tv_logos import site
    ops.set_logo(db, TF1, png(800, 300), 'x')
    ops.set_logo(db, ALS, png(800, 300), 'y')
    db.save()
    out = tmp_path / 'api'
    stats = site.build(db, IPTV, [{'code': 'FR', 'name': 'France', 'flag': ''}], out)
    assert stats['with_logo'] == 2                                           # TF1, and France 3 by its edition
    import json
    fr = json.loads((out / 'countries' / 'fr.json').read_text(encoding='utf-8'))
    tf1 = next(c for c in fr['channels'] if c['id'] == TF1)
    assert tf1['logos'][0]['url'].endswith(f'logos/{TF1}.png') and tf1['iptv'] == 'TF1.fr'
    f3 = next(c for c in fr['channels'] if c['id'] == F3)
    assert [f['id'] for f in f3['feeds']] == [ALS] and f3['logos'][0]['feed'] == ALS
    assert ALS not in {c['id'] for c in fr['channels']}                      # listed with its channel
    assert json.loads((out / 'countries.json').read_text(encoding='utf-8'))[0]['name'] == 'France'


def test_logos_json_gives_our_id_its_slug_and_iptv_org_id(db):
    ops.set_logo(db, ALS, png(800, 300), 'x')
    rec = cli.logo_record(db, db.logos[(ALS, '')])
    assert (rec['channel'], rec['slug'], rec['iptv'], rec['parent']) == (ALS, 'france-3-alsace.fr', 'France3.fr@Alsace', F3)
    assert rec['url'] == f'https://worldwide-tv-logos.github.io/database/logos/{ALS}.png'
    assert rec['country'] == 'fr' and rec['format'] == 'PNG' and rec['variant'] is None


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
    ops.set_logo(db, TF1, png(800, 300), 'https://example.org/old.png')
    db.save()
    base = tmp_path_factory.mktemp('base')
    shutil.copytree(db.root, base, dirs_exist_ok=True)
    ops.set_logo(db, TF1, png(1000, 300), 'https://example.org/new.png')   # proposed update
    db.save()
    assert cli.main(['--root', str(db.root), 'reject', 'tf1.fr', '--reason', 'old branding',
                     '--base', str(base)]) == 0
    again = Database(db.root).load()
    assert again.logos[(TF1, '')].origin == 'https://example.org/old.png'
    assert harvest.load_rejected(db.root) == {(TF1, 'https://example.org/new.png')}
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


def test_move_logos_to_another_channel_moves_logos_sources_and_aliases(db):
    ops.set_logo(db, TF1, png(800, 300), 'x')
    ops.set_alias(db, 'TF1-HD.fr', 'iptv-epg-fr', TF1)
    db.save()
    ops.move_logos(db, TF1, BIS)
    db.save()
    again = Database(db.root).load()
    assert (BIS, '') in again.logos and (TF1, '') not in again.logos
    assert next(iter(again.aliases.values())).channel == BIS
    assert cli.validate(again, IPTV) == []
    with pytest.raises(ops.RequestError):
        ops.move_logos(db, BIS, 'ch_0000000000')


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


def test_harvest_units_come_from_the_registry():
    iptv = IptvOrg({'France3.fr': {'id': 'France3.fr', 'name': 'France 3', 'country': 'FR'}},
                   {('France3.fr', 'National'): {'id': 'National', 'is_main': True},
                    ('France3.fr', 'Alsace'): {'id': 'Alsace', 'name': 'Alsace'},
                    ('France3.fr', 'HD'): {'id': 'HD', 'name': 'HD'}})
    assert [(u['id'], u['name']) for u in registry.iptv_units(iptv, 'fr')] == [
        ('France3.fr', 'France 3'), ('France3.fr@Alsace', 'France 3 Alsace')]     # quality versions left out


def test_registry_units_are_channels_then_their_editions(db):
    units = harvest.units(db, 'fr')
    assert [u['id'] for u in units] == [F3, ALS, TF1, BIS]
    f3, als = units[0], units[1]
    assert (als['parent'], als['iptv'], als['channel'], als['feed']) == (F3, 'France3.fr@Alsace', 'France3.fr', 'Alsace')
    assert harvest.iptv_key(als) == ('France3.fr', 'Alsace') and harvest.iptv_key(units[3]) == ('', '')
    assert units[3]['channel'] == 'tf1bis.fr'                                   # family name made from the slug
    assert harvest.channel_keys(als) == {'france3alsace'}            # never the key of the channel itself
    assert 'france3' in harvest.channel_keys(f3)


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

    alias = SimpleNamespace(epg_id='Mega.es', source='iptv-epg.org', channel='ch_mega000000')
    epg = sources.EpgIndex(channels, [alias], harvest.key)
    assert epg.logos({'id': 'La1.es'}, set()) == ['https://e/la1']
    assert epg.logos({'id': 'Telecinco.es'}, {harvest.key('Telecinco')}) == ['https://e/t5']
    assert epg.logos({'id': 'ch_mega000000', 'iptv': 'MegaTV.es'}, set()) == ['https://e/mega']
    assert epg.logos({'id': 'ch_1a1000000a', 'iptv': 'La1.es'}, set()) == ['https://e/la1']          # same ID
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


def test_painted_holes_of_letters_but_not_letters_in_a_box_are_repainted():
    from PIL import ImageDraw

    def lit(draw):
        im = Image.new('RGBA', (600, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle((260, 60, 580, 140), fill=(10, 20, 60, 255))                               # navy text: it vanishes
        draw(d)
        return image.legible(im, dark=True)
    ring = lit(lambda d: (d.ellipse((20, 20, 180, 180), fill=(10, 20, 60, 255)),              # navy "o" whose hole
                          d.ellipse((70, 70, 130, 130), fill=(255, 255, 255, 255))))           # is painted white
    assert ring.getpixel((100, 100))[:3] != (255, 255, 255)                                    # reads as a hole again
    assert ring.getpixel((40, 100))[:3] != (10, 20, 60)                                        # and the letter is lit
    box = lit(lambda d: (d.rectangle((20, 20, 220, 180), fill=(0, 0, 0, 255)),                # Cartoon Network: a
                         d.rectangle((60, 50, 180, 70), fill=(255, 255, 255, 255)),            # white C, a long
                         d.rectangle((60, 50, 80, 150), fill=(255, 255, 255, 255)),            # stroke, in a black
                         d.rectangle((60, 130, 180, 150), fill=(255, 255, 255, 255))))         # box stays white
    assert box.getpixel((70, 100))[:3] == (255, 255, 255)
    badge = lit(lambda d: (d.ellipse((20, 20, 180, 180), fill=(10, 10, 10, 255)),             # red HD disc in a
                           d.ellipse((70, 70, 130, 130), fill=(220, 30, 30, 255))))            # black badge stays red
    assert badge.getpixel((100, 100))[:3] == (220, 30, 30)


def test_sharper_version_says_whether_it_is_the_same_drawing(tmp_path):
    src = tmp_path / 'X.fr.png'
    src.write_bytes(png(512, 200))
    logo = Logo('ch_x000000000', '', 512, 200, 'https://example.org/x.png')
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

    from worldwide_tv_logos import sources
    ops.set_logo(db, F3, SVG, 'https://example.org/f3.svg')
    guide = [{'id': 'F3guide', 'names': ['France 3'], 'icon': ''}, {'id': 'TF1guide', 'names': ['TF1'], 'icon': ''}]
    monkeypatch.setattr(harvest, 'load_epg', lambda db, cc, dl, log: sources.EpgIndex(guide, [], harvest.key))
    cli.cmd_guide_aliases(argparse.Namespace(country='fr'), db)
    assert [(a.epg_id, a.channel) for a in db.aliases.values()] == [('F3guide', F3)]   # TF1: no logo
    assert cli.validate(Database(db.root).load(), IPTV) == []


def test_bulk_adds_the_iptv_org_logos_that_pass_the_rules(db):
    logos = [{'channel': 'TF1.fr', 'feed': '', 'url': 'https://x.org/tf1.svg', 'format': 'SVG'},
             {'channel': 'France3.fr', 'feed': '', 'url': 'https://x.org/f3.png', 'format': 'PNG', 'width': 300,
              'height': 100}]
    files = {'https://x.org/tf1.svg': SVG}
    stats = harvest.bulk(db, IPTV, 'fr', logos, pause=0, downloader=lambda url, **kw: files[url], log=lambda s: None)
    assert stats == {'todo': 4, 'added': 1, 'doubts': 0}                  # France 3 (too small), Alsace, TF1 Bis
    assert (TF1, '') in db.logos and db.logos[(TF1, '')].origin == 'https://x.org/tf1.svg'
    assert cli.validate(Database(db.root).load(), IPTV) == []


def test_epg_sure_match_and_newer_guide_logo_replaced_when_the_website_shows_it(db, tmp_path, monkeypatch):
    from worldwide_tv_logos import sources
    guide = [{'id': 'TF1guide', 'names': ['TF1'], 'icon': 'https://g.org/tf1.png'},
             {'id': 'A', 'names': ['France 3'], 'icon': ''}, {'id': 'B', 'names': ['France 3'], 'icon': ''}]
    epg = sources.EpgIndex(guide, [], harvest.key)
    assert epg.sure({'id': TF1, 'iptv': 'TF1.fr'}, {harvest.key('TF1')})['id'] == 'TF1guide'
    assert epg.sure({'id': F3, 'iptv': 'France3.fr'}, {harvest.key('France 3')}) is None      # two guide channels
    old = Image.new('RGBA', (800, 300), (200, 0, 0, 255))
    old.paste((0, 0, 200, 255), (0, 0, 300, 300))                                         # blue block on the left
    new = old.transpose(Image.Transpose.FLIP_LEFT_RIGHT)                                   # another drawing
    old, new = _png(old), _png(new)
    ops.set_logo(db, TF1, old, 'https://x.org/old.png')
    db.channels[TF1].website = 'https://tf1.fr/'
    iptv = IptvOrg({'TF1.fr': {'id': 'TF1.fr', 'name': 'TF1', 'country': 'FR', 'website': 'https://tf1.fr/'}}, {})
    monkeypatch.setattr(harvest.run, 'load_epg', lambda db, cc, dl, log: epg)
    get = {'https://g.org/tf1.png': new}.__getitem__
    run = lambda out, seen: harvest.epg_check(db, iptv, 'fr', tmp_path / out, downloader=lambda u, **k: get(u),
                                              pause=0, log=lambda s: None, seen_on=seen)
    assert run('a', lambda page, data, dl: None) == {'checked': 1, 'replaced': 0, 'review': 1}   # website: no proof
    assert (tmp_path / 'a' / 'sheet-01.png').is_file()
    assert run('b', lambda page, data, dl: 'found' if data == new else None) == {'checked': 1, 'replaced': 1, 'review': 0}
    assert db.logos[(TF1, '')].origin == 'https://g.org/tf1.png'
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

    def cut(req, timeout):              # a site that cuts its response (bad chunked encoding): one logo lost, not the run
        import http.client
        raise http.client.IncompleteRead(b'')

    with pytest.raises(net.DownloadError):
        net.download('https://a.example/x.png', opener=cut)


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


HEADER = 'channel,variant,width,height,origin,added,updated\n'
TS, W9 = 'ch_te1esamb00', 'ch_w9w9w9w9w9'


def test_merge_data_files_applies_our_logo_files_on_top_of_main_without_a_rebase(tmp_path):
    git = _git_repo(tmp_path)
    _write(tmp_path, 'data/logos.csv', HEADER + f'{TF1},,10,10,a,2026-01-01,\n')
    _write(tmp_path, 'data/rejected.csv', 'channel,url,reason,date\n')
    _write(tmp_path, f'logos/{TF1}.png', b'tf1')
    git('add', '-A')
    git('commit', '-qm', 'base')
    base = git('rev-parse', 'HEAD')
    # main meanwhile: Telesambre added with a PNG source, TF1 untouched
    _write(tmp_path, 'data/logos.csv', HEADER + f'{TS},,10,10,main,2026-02-01,\n{TF1},,10,10,a,2026-01-01,\n')
    _write(tmp_path, f'logos/{TS}.png', b'main')
    _write(tmp_path, f'sources/{TS}.png', b'main source')
    _write(tmp_path, 'data/rejected.csv', 'channel,url,reason,date\nA.fr,u1,r,2026-02-01\n')
    git('add', '-A')
    git('commit', '-qm', 'main')
    upstream = git('rev-parse', 'HEAD')
    # our change, from base: the same logo from a JPG source, and a rejection
    git('checkout', '-q', base)
    _write(tmp_path, 'data/logos.csv', HEADER + f'{TS},,10,10,ours,2026-02-02,\n{TF1},,10,10,a,2026-01-01,\n')
    _write(tmp_path, f'logos/{TS}.png', b'ours')
    _write(tmp_path, f'sources/{TS}.jpg', b'ours source')
    _write(tmp_path, 'data/rejected.csv', 'channel,url,reason,date\nB.fr,u2,r,2026-02-02\n')
    git('add', '-A')
    git('commit', '-qm', 'ours')
    ours = git('rev-parse', 'HEAD')
    git('checkout', '-q', upstream)                    # the working tree holds main (git reset --hard origin/main)
    assert cli.main(['--root', str(tmp_path), 'merge-data', base, ours, upstream, '--files']) == 0
    assert (tmp_path / f'logos/{TS}.png').read_bytes() == b'ours'
    assert sorted(p.name for p in (tmp_path / 'sources').iterdir()) == [f'{TS}.jpg']   # one source
    assert f'{TS},,10,10,ours,' in (tmp_path / 'data/logos.csv').read_text()
    assert (tmp_path / 'data/rejected.csv').read_text().splitlines()[1:] == ['A.fr,u1,r,2026-02-01',
                                                                               'B.fr,u2,r,2026-02-02']


def test_regress_check_fails_when_an_older_version_of_a_logo_comes_back(tmp_path):
    git = _git_repo(tmp_path)
    _write(tmp_path, 'data/logos.csv', HEADER + f'{W9},,10,10,new,2025-01-01,2026-11-22\n{TF1},,10,10,a,2026-01-01,\n')
    git('add', '-A')
    git('commit', '-qm', 'main')
    root = ['--root', str(tmp_path)]
    assert cli.main([*root, 'regress-check', 'HEAD']) == 0
    _write(tmp_path, 'data/logos.csv', HEADER + f'{W9},,10,10,old,2025-01-01,2026-03-01\n{TF1},,10,10,b,2026-01-01,2026-11-23\n')
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


def test_one_brand_shares_its_logo_across_countries_and_differences_are_listed():
    harvest.set_countries([{'name': 'South Africa'}, {'name': 'Poland'}])
    assert harvest.brand('HGTVSouthAfrica.za') == harvest.brand('HGTV.be') == 'hgtv'
    assert harvest.brand('BlueAction.ch') != harvest.brand('Action.fr')
    assert harvest.brand('TF1SeriesFilms.fr') != harvest.brand('TF1.fr')
    fp = (1 << 200) - 1
    nick = 12345
    drawings = [('HGTV.be', 'HGTV.be', fp), ('NickJr.pl', 'NickJr.pl', nick)]
    assert harvest.drawing_of_other('HGTVSouthAfrica.za', fp, drawings) is None        # the same brand: not a doubt
    kept = [({'id': 'NickJr.fr', 'channel': 'NickJr.fr', 'name': 'Nick Jr'},
             harvest.Candidate('iptv-epg', 'https://e/old.png', fp=nick ^ ((1 << 60) - 1)))]    # another drawing
    assert harvest.brand_differences(kept, drawings) == [('NickJr.fr', ['NickJr.pl'])]
    kept[0][1].fp = nick
    assert harvest.brand_differences(kept, drawings) == []
    assert harvest.logo_url(ALS).endswith(f'/logos/{ALS}.png')


def _ctx(tmp_path, responses, **kw):
    from worldwide_tv_logos import sources

    def get(url, **_):
        for part, value in responses.items():
            if part in url:
                return value if isinstance(value, bytes) else json.dumps(value).encode()
        raise sources.net.DownloadError('HTTP 404')
    return sources.Context(root=tmp_path, cc=kw.pop('cc', 'us'), downloader=get, log=lambda s: None, pause=0, **kw)


def test_wikipedia_gives_the_logo_of_the_article_of_the_item_or_of_the_name(tmp_path):
    from worldwide_tv_logos.sources import wikipedia
    ctx = _ctx(tmp_path, {'titles=WABC-TV': {'query': {'pages': {'1': {
        'title': 'WABC-TV', 'original': {'source': 'https://upload.wikimedia.org/wikipedia/en/a/ab/WABC_7_logo.svg'},
        'pageprops': {'wikibase_item': 'Q1'}}}}},
        'titles=Telecinco': {'query': {'pages': {'2': {
            'title': 'Telecinco', 'original': {'source': 'https://upload.wikimedia.org/x/Telecinco_building.jpg'}}}}}})
    ctx._items['WABC.us'] = [{'qid': 'Q1', 'sitelinks': {'en': 'WABC-TV', 'fr': 'WABC'}, 'logos': [], 'website': ''}]
    assert wikipedia.find({'id': 'WABC.us', 'name': 'WABC'}, ctx) == \
        ['https://upload.wikimedia.org/wikipedia/en/a/ab/WABC_7_logo.svg']
    ctx._items['Telecinco.es'] = []
    assert wikipedia.find({'id': 'Telecinco.es', 'name': 'Telecinco'}, ctx) == []    # a photo, not a logo
    assert not wikipedia.plausible('https://u/x/Canal_Sur_2011-2017_logo.svg')        # an old branding


def test_commons_keeps_files_named_after_the_channel_with_logo(tmp_path):
    from worldwide_tv_logos.sources import commons
    ctx = _ctx(tmp_path, {'commons.wikimedia.org': {'query': {'search': [
        {'title': 'File:Antena 3 logo 2023.svg'}, {'title': 'File:Antena 3 Noticias logo.png'},
        {'title': 'File:Antena 3 building.jpg'}, {'title': 'File:Antena 3 logo 2004-2010.svg'},
        {'title': 'File:Logo of Neox.svg'}]}}})
    urls = commons.find({'id': 'Antena3.es', 'name': 'Antena 3'}, ctx)
    assert urls[0].endswith('Antena_3_logo_2023.svg') and len(urls) == 2
    assert not any('2004-2010' in u or 'building' in u or 'Neox' in u for u in urls)
    assert not commons.named_after('Huaju Film Co production logo from Lustrous Pearls, 1927', 'Film&Co')
    assert commons.named_after('LaLiga TV Hypermotion 2023 Logo', 'LaLiga TV')
    assert commons.named_after('Series por Movistar Plus+ 2022 logo', 'Series por Movistar Plus+')
    assert commons.named_after('Logo of America Teve', 'America TeVe')
    assert not commons.named_after('Thoma Bravo logo 2024', 'Bravo')
    assert not commons.named_after('AMC Networks logo', 'AMC')
    assert not commons.named_after('Boomerang HD Logo 2015', 'Boomerang')


def test_picons_and_xmltvse_match_by_name(tmp_path):
    from worldwide_tv_logos.sources import picons, xmltvse
    ctx = _ctx(tmp_path, {'api.github.com': {'tree': [
        {'path': 'bbcone.default.svg', 'type': 'blob'}, {'path': 'bbcone.white.svg', 'type': 'blob'},
        {'path': 'antena3.default.png', 'type': 'blob'}]},
        'utf8snp.index': b'bbc one=bbcone\nbbc one hd=bbcone\n',
        'gitlab.com': [{'name': '1.bluemovie.de_color.svg', 'type': 'blob'},
                       {'name': '1.bluemovie.de_blackwhite.svg', 'type': 'blob'}]})
    assert picons.find({'id': 'BBCOne.uk', 'name': 'BBC One'}, ctx) == [picons.RAW + 'logos/bbcone.default.svg']
    assert picons.find({'id': 'Antena3.es', 'name': 'Antena 3'}, ctx) == [picons.RAW + 'logos/antena3.default.png']
    assert picons.find({'id': 'Nothing.es', 'name': 'Nothing'}, ctx) == []
    assert xmltvse.keys_of('1.bluemovie.de') == ('de', {'1bluemovie', 'bluemovie1'})
    assert xmltvse.find({'id': 'BlueMovie1.de', 'name': 'Blue Movie 1'}, ctx) == \
        [xmltvse.RAW + '1.bluemovie.de_color.svg']
    assert xmltvse.find({'id': 'BlueMovie1.at', 'name': 'Blue Movie 1'}, ctx) == []    # another country


def test_collect_asks_the_costly_sources_for_missing_channels_only(tmp_path, monkeypatch):
    from worldwide_tv_logos import sources
    asked = []
    fake = tuple(sources.Source(s.name, s.rank, s.asked, lambda u, c, n=s.name: asked.append(n) or [f'https://{n}/x.svg'])
                 for s in sources.SOURCES)
    monkeypatch.setattr(sources, 'SOURCES', fake)
    ctx = _ctx(tmp_path, {}, have={'TF1.fr'})
    sources.collect({'id': 'TF1.fr', 'name': 'TF1'}, ctx)
    assert set(asked) == {'wikidata', 'iptv-org', 'iptv-epg', 'picons', 'xmltv-se'}      # has a logo: cheap ones
    asked.clear()
    found = sources.collect({'id': 'M6.fr', 'name': 'M6'}, ctx)
    assert {'wikipedia', 'commons'} <= set(asked) and 'website' not in asked
    assert found[0] == ('wikidata', 'https://wikidata/x.svg')
    asked.clear()
    ctx.deep = True
    sources.collect({'id': 'TF1.fr', 'name': 'TF1'}, ctx)
    assert set(asked) == {s.name for s in fake}


def test_the_website_of_a_channel_is_found_and_confirmed(tmp_path):
    from worldwide_tv_logos import sites, web
    pages = {
        'https://ceutatv.com/pag/directo': web.Page('https://ceutatv.com/pag/directo', status=404, error='HTTP 404'),
        'https://ceutatv.com/': web.Page('https://ceutatv.com/', html='<title>Ceuta TV - Inicio</title>', status=200),
        'https://www.gol.com/': web.Page('https://www.gol.com/', html='<title>Golf shop</title>', status=200),
    }
    fetch = lambda url, **kw: pages.get(url, web.Page(url, error='URLError'))
    ctx = _ctx(tmp_path, {}, cc='es')
    ctx._items['CeutaTV.es'] = []
    site = sites.find({'id': 'CeutaTV.es', 'name': 'Ceuta TV', 'website': 'http://ceutatv.com/pag/directo'}, ctx, fetch)
    assert (site.url, site.how, site.confirmed) == ('https://ceutatv.com/', 'home page', True)
    ctx._items['Gol.es'] = []
    assert sites.find({'id': 'Gol.es', 'name': 'Gol'}, ctx, fetch) is None      # gol.com: the name is not in its title
    assert sites.guesses({'name': 'Ceuta TV'}, 'es')[:2] == ['https://www.ceutatv.es/', 'https://www.ceutatv.com/']
    assert sites.guesses({'name': 'Dave'}, 'uk')[:2] == ['https://www.dave.co.uk/', 'https://www.dave.com/']


def test_picons_skip_names_shared_by_channels_of_several_countries(tmp_path):
    from worldwide_tv_logos.sources import names, picons
    iptv = IptvOrg({'TV4.se': {'id': 'TV4.se', 'name': 'TV4', 'country': 'SE'},
                    'TV4.es': {'id': 'TV4.es', 'name': 'TV4', 'country': 'ES'},
                    'Neox.es': {'id': 'Neox.es', 'name': 'Neox', 'country': 'ES'}}, {})
    ambiguous = names.ambiguous_keys(iptv)
    assert 'tv4' in ambiguous and 'neox' not in ambiguous
    ctx = _ctx(tmp_path, {'api.github.com': {'tree': [{'path': 'tv4.default.svg', 'type': 'blob'},
                                                       {'path': 'neox.default.svg', 'type': 'blob'}]},
                          'utf8snp.index': b''}, ambiguous=ambiguous)
    assert picons.find({'id': 'TV4.es', 'name': 'TV4'}, ctx) == []
    assert picons.find({'id': 'Neox.es', 'name': 'Neox'}, ctx) == [picons.RAW + 'logos/neox.default.svg']


def test_harvest_proof_says_where_the_logo_was_seen(tmp_path, monkeypatch):
    from worldwide_tv_logos import sites
    from worldwide_tv_logos.harvest import proofs
    monkeypatch.setattr(sites, 'find', lambda unit, ctx: sites.Site('https://www.canalcostatv.es/', 'iptv-org', True))
    monkeypatch.setattr(proofs.seen, 'seen_on', lambda url, data, log=None: 'same drawing as the image x')
    monkeypatch.setattr(proofs.web, 'screenshot', lambda url: None)
    proof = proofs.check({'id': 'CanalCosta.es', 'name': 'CanalCosta'}, harvest.Candidate('picons', 'u', b'x'),
                         _ctx(tmp_path, {}))
    assert proof.text() == 'FOUND on www.canalcostatv.es'
    monkeypatch.setattr(sites, 'find', lambda unit, ctx: None)
    assert proofs.check({'id': 'X.es', 'name': 'X'}, harvest.Candidate('picons', 'u', b'x'),
                        _ctx(tmp_path, {})).text() == 'no website found'


def test_unreject_proposes_again_the_logos_set_aside(db):
    path = db.root / 'data' / 'rejected.csv'
    path.write_text('channel,url,reason,date\nA.es,u1,picons logo not confirmed as current,2026-11-23\n'
                    'B.es,u2,wrong channel,2026-11-23\nC.es,u3,not confirmed,2026-11-20\n', encoding='utf-8')
    assert cli.main(['--root', str(db.root), 'unreject', '--date', '2026-11-23', '--reason-contains', 'not confirmed']) == 0
    assert [r.split(',')[0] for r in path.read_text(encoding='utf-8').splitlines()[1:]] == ['B.es', 'C.es']


def test_silhouette_tells_the_same_logo_shifted_from_another_one():
    from PIL import ImageDraw
    def logo(text, dx=0):
        img = Image.new('RGBA', (400, 100), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle((10 + dx, 10, 90 + dx, 90), fill=(200, 0, 0, 255))
        d.text((110 + dx, 30), text, fill=(0, 0, 0, 255), font_size=40)
        return image.trim(img)
    assert image.silhouette(logo('ceuta tv'), logo('ceuta tv', 3)) > 0.9
    assert image.silhouette(logo('ceuta tv'), logo('mar tv', 0)) < image.silhouette(logo('ceuta tv'), logo('ceuta tv', 3))
    assert image.silhouette(logo('ceuta tv'), Image.new('RGBA', (100, 300), (0, 0, 0, 255))) == 0.0   # proportions


def test_site_check_slices_and_compares_logos():
    from worldwide_tv_logos.harvest import sitecheck
    assert sitecheck.weekly_slice(list(range(10)), 1, 4) == [4, 5, 6, 7]
    assert sitecheck.weekly_slice(list(range(10)), 2, 4) == [8, 9, 0, 1]
    a = png(800, 300, (200, 0, 0, 255))
    b = Image.new('RGBA', (800, 300), (0, 0, 0, 0))
    ImageDraw = __import__('PIL.ImageDraw', fromlist=['ImageDraw'])
    ImageDraw.Draw(b).ellipse((0, 0, 300, 300), fill=(0, 0, 200, 255))
    assert sitecheck.same_logo(a, a) and not sitecheck.same_logo(a, _png(b))


# --- channel registry (roadmap/01-channel-registry.md) ---

REG_IPTV = IptvOrg({'France3.fr': {'id': 'France3.fr', 'name': 'France 3', 'country': 'FR', 'alt_names': ['FR3']},
                    'TF1.fr': {'id': 'TF1.fr', 'name': 'TF1', 'country': 'FR', 'website': 'https://www.tf1.fr'},
                    'OldTV.fr': {'id': 'OldTV.fr', 'name': 'Old TV', 'country': 'FR', 'closed': '2020-01-01',
                                 'replaced_by': 'NewTV.fr'},
                    'NewTV.fr': {'id': 'NewTV.fr', 'name': 'New TV', 'country': 'FR'},
                    'ZDF.de': {'id': 'ZDF.de', 'name': 'ZDF', 'country': 'DE'}},
                   {('France3.fr', 'Alsace'): {'name': 'Alsace', 'broadcast_area': ['c/FR']},
                    ('TF1.fr', 'HD'): {'name': 'HD'},
                    ('TF1.fr', 'Belgique'): {'name': 'Belgique', 'broadcast_area': ['c/BE']},
                    ('ZDF.de', 'Europe'): {'name': 'Europe', 'broadcast_area': ['r/EUR']}})


def test_registry_ids_and_slugs():
    taken = set()
    for _ in range(200):
        cid = registry.new_id(taken)
        assert registry.ID_RE.match(cid) and cid not in taken
        taken.add(cid)
    assert registry.slug_base('Canal+ Sport') == 'canal-plus-sport'
    assert registry.slug_base('Télé Monte-Carlo') == 'tele-monte-carlo'
    assert registry.make_slug('TF1', 'fr', {'tf1.fr'}) == 'tf1-2.fr'
    assert registry.make_slug('الجزيرة', 'qa', set(), fallback='AlJazeera') == 'aljazeera.qa'


def test_registry_init_is_complete_and_can_run_again(bare):
    db = bare
    stats = registry.init(db, REG_IPTV, ['fr', 'de'])
    # TF1@HD is a quality feed: not an edition; Old TV is closed
    assert stats == {'channels': 4, 'editions': 3, 'already': 0, 'country changed': 0}
    assert registry.resolve(db, 'OldTV.fr') is None
    # an edition broadcast in one other country takes it; a region keeps its channel's
    assert registry.resolve(db, 'TF1.fr@Belgique').slug == 'tf1-belgique.be'
    assert registry.resolve(db, 'ZDF.de@Europe').country == 'de'
    f3 = registry.resolve(db, 'France3.fr')
    alsace = registry.resolve(db, 'France3.fr@Alsace')
    assert (f3.slug, f3.alias_list, alsace.slug, alsace.parent) == ('france-3.fr', ['FR3'], 'france-3-alsace.fr', f3.id)
    assert registry.resolve(db, 'zdf.de').name == 'ZDF'
    assert registry.resolve(db, f3.id) is f3 and registry.resolve(db, 'nothing') is None
    assert registry.check(db) == []
    before = dict(db.channels)
    assert registry.init(db, REG_IPTV, ['fr', 'de'])['already'] == 7 and db.channels == before
    # an edition loaded before with its channel's country follows its broadcast country
    be = registry.resolve(db, 'TF1.fr@Belgique')
    be.country, be.slug = 'fr', 'tf1-belgique.fr'
    assert registry.refresh_editions(db, REG_IPTV) == 1 and be.slug == 'tf1-belgique.be'
    be.country, be.updated = 'fr', '2026-11-23'                    # edited here: left alone
    assert registry.refresh_editions(db, REG_IPTV) == 0


def test_registry_check_and_merge(bare, tmp_path):
    db = bare
    registry.init(db, REG_IPTV, ['fr'])
    db.save()
    tf1 = registry.resolve(db, 'TF1.fr')
    other = registry.resolve(db, 'France3.fr')
    tf1.slug = other.slug
    db.external_ids[('iptv-epg', 'TF1.fr')] = registry.ExternalId(tf1.id, 'iptv-epg', 'TF1.fr', 'match', '2026-11-23')
    errors = registry.check(db)
    assert any('already used' in e for e in errors) and any('guide IDs are not stored' in e for e in errors)
    # three-way merge: a channel renamed on one side, another added on the other side, both kept
    base = Database(db.root).load()
    up, ours = Database(db.root).load(), Database(db.root).load()
    c = registry.resolve(up, 'TF1.fr')
    c.name = 'TF1 renamed'
    added = registry.add_channel(ours, 'Brand New', 'fr')
    for name, d in (('base', base), ('up', up), ('ours', ours)):
        d.root = tmp_path / name
        (d.root / 'data').mkdir(parents=True)
        d.save()
    db.merge(base.root, up.root, ours.root)
    assert registry.resolve(db, 'TF1.fr').name == 'TF1 renamed' and added.id in db.channels


def test_registry_commands(bare):
    db = bare
    registry.init(db, REG_IPTV, ['fr'])
    db.save()
    root = ['--root', str(db.root)]
    assert cli.main([*root, 'channel-add', 'TF1', '--country', 'fr']) == 1            # same name in the country
    assert cli.main([*root, 'channel-add', 'Brand New', '--country', 'fr']) == 0
    assert cli.main([*root, 'channel-add', 'Brand New', '--country', 'es']) == 1      # country not followed
    d = Database(db.root).load()
    new = registry.resolve(d, 'brand-new.fr')
    assert new is not None and new.status == 'active'
    assert cli.main([*root, 'channel-edit', 'brand-new.fr', '--name', 'Brand Newer']) == 0
    assert cli.main([*root, 'channel-map', 'brand-newer.fr', 'wikidata', 'Q42']) == 0
    assert cli.main([*root, 'channel-map', 'TF1.fr', 'wikidata', 'Q42']) == 1         # already mapped elsewhere
    assert cli.main([*root, 'channel-map', 'TF1.fr', 'wikidata', 'TF1']) == 1         # malformed
    d = Database(db.root).load()
    assert registry.resolve(d, 'Q42').id == new.id and registry.resolve(d, new.id).slug == 'brand-newer.fr'


# --- iptv-org watch (roadmap/03-iptvorg-watch.md) ---

def test_watch_keeps_the_channel_through_a_rename_with_its_editions(db):
    from worldwide_tv_logos import watch
    ops.set_logo(db, F3, png(800, 300), 'x')
    new = registry.add_channel(db, 'France 3 New', 'fr')                    # registered by an earlier night, empty
    registry.map_id(db, new, 'iptv-org', 'France3New.fr', 'import')
    iptv = IptvOrg({'France3.fr': {'id': 'France3.fr', 'name': 'France 3', 'country': 'FR',
                                   'replaced_by': 'France3New.fr', 'closed': '2026-11-01'},
                    'France3New.fr': {'id': 'France3New.fr', 'name': 'France 3 New', 'country': 'FR'},
                    'TF1.fr': {'id': 'TF1.fr', 'name': 'TF1', 'country': 'FR'}},
                   {('France3New.fr', 'Alsace'): {'name': 'Alsace'}})
    out = watch.watch(db, iptv)
    assert out['renamed'] == 1 and out['decisions'] == []
    assert new.id not in db.channels                                         # absorbed: nothing of its own
    f3 = registry.resolve(db, 'France3New.fr')
    assert f3.id == F3 and (f3.name, f3.slug, f3.status) == ('France 3 New', 'france-3-new.fr', 'active')
    assert registry.resolve(db, 'France3.fr').id == F3                       # the former ID still finds it
    assert registry.iptv_id(db, F3) == 'France3New.fr'
    assert registry.iptv_id(db, ALS) == 'France3New.fr@Alsace'                # its edition followed
    assert (F3, '') in db.logos and registry.check(db) == []
    assert 'France 3 New' in watch.renamed_logos(db)[0]                       # its logo to check this week
    assert watch.watch(db, iptv)['renamed'] == 0                             # applied once
    assert registry.init(db, iptv, ['fr'])['channels'] == 0                  # never registered again


def test_watch_merges_into_a_successor_with_its_own_logo_and_follows_closures(db):
    from worldwide_tv_logos import watch
    ops.set_logo(db, TF1, png(800, 300), 'old')
    other = registry.add_channel(db, 'TF1 Plus', 'fr')
    registry.map_id(db, other, 'iptv-org', 'TF1Plus.fr', 'import')
    ops.set_logo(db, other.id, png(900, 300), 'new')
    iptv = IptvOrg({'TF1.fr': {'id': 'TF1.fr', 'name': 'TF1', 'country': 'FR', 'replaced_by': 'TF1Plus.fr'},
                    'TF1Plus.fr': {'id': 'TF1Plus.fr', 'name': 'TF1 Plus', 'country': 'FR'},
                    'France3.fr': {'id': 'France3.fr', 'name': 'France Trois', 'country': 'FR',
                                   'closed': '2026-11-20', 'website': 'https://f3.fr'}}, {})
    out = watch.watch(db, iptv)
    assert (db.channels[TF1].status, db.channels[TF1].parent) == ('merged', other.id)
    assert (TF1, '') in db.logos and (other.id, '') in db.logos                # each keeps its logo
    f3 = db.channels[F3]
    assert (f3.status, f3.name, f3.website, out['closed']) == ('closed', 'France Trois', 'https://f3.fr', 1)
    iptv.channels['France3.fr'].pop('closed')
    assert watch.watch(db, iptv)['reopened'] == 1 and db.channels[F3].status == 'active'
    db.channels[F3].updated, db.channels[F3].name = '2026-11-23', 'France 3'  # edited here: left alone
    iptv.channels['France3.fr']['closed'] = '2026-11-25'
    watch.watch(db, iptv)
    assert (db.channels[F3].status, db.channels[F3].name) == ('active', 'France 3')
    gone = watch.watch(db, IptvOrg({}, {}))
    assert gone['removed'] >= 1 and any('no longer in iptv-org' in x for x in gone['lines'])
    assert registry.check(db) == []


def test_coming_requests_of_the_followed_countries():
    from worldwide_tv_logos import watch
    issues_ = [{'title': 'Add: Canal 13', 'labels': [{'name': 'channels:add'}], 'html_url': 'u1',
                'body': '### Channel Name\n\nCanal 13\n\n### Country\n\nFR\n\n### NSFW\n\nFALSE\n'},
               {'title': 'Remove: Zeta 93', 'labels': [{'name': 'channels:remove'}], 'html_url': 'u2',
                'body': '### Channel ID\n\nZeta93.pr\n\n### Reason\n\nradio\n'},
               {'title': 'Edit: TF1', 'labels': [{'name': 'channels:edit'}], 'html_url': 'u3',
                'body': '### Channel ID (required)\n\nTF1.fr\n\n### Country\n\n_No response_\n'},
               {'title': 'Logo', 'labels': [{'name': 'logos:add'}], 'body': '### Country\n\nFR\n'}]
    assert watch.coming(issues_, {'fr'}) == ['- add (fr): [Add: Canal 13](u1)', '- edit (fr): [Edit: TF1](u3)']


# --- requests on our registry (roadmap/04-requests.md) ---

ADD_CHANNEL = """### Channel name

Alsace 20 Plus

### Country

FR

### Website

https://www.alsace20.tv/

### Other names (optional)

A20 Plus; Alsace20+

### Main channel (optional)

_No response_

### iptv-org ID (optional)

_No response_

### Wikidata ID (optional)

Q42

### Notes (optional)

_No response_
"""


def test_a_channel_can_be_added_and_edited_by_a_request(db):
    req = issues.parse(20, ['channels:add', 'approved'], ADD_CHANNEL)
    assert (req.get('name'), req.get('country'), req.get('wikidata')) == ('Alsace 20 Plus', 'FR', 'Q42')
    assert issues.validate(req, db) == []
    out = issues.apply(req, db)
    c = registry.resolve(db, 'alsace-20-plus.fr')
    assert out == [f'{c.id}: added channel {c.id} (alsace-20-plus.fr), wikidata ID Q42']
    assert (c.alias_list, c.website, registry.resolve(db, 'Q42').id) == (['A20 Plus', 'Alsace20+'], 'https://www.alsace20.tv/', c.id)
    assert registry.check(db) == []
    # the same channel again, by another of its names
    again = issues.parse(21, ['channels:add'], ADD_CHANNEL.replace('Alsace 20 Plus', 'A20 Plus').replace('Q42', 'Q43'))
    assert 'already this channel here' in issues.validate(again, db)[0]
    # an edition of France 3, with its iptv-org ID already taken
    edition = ADD_CHANNEL.replace('Alsace 20 Plus', 'France 3 Lorraine').replace('Q42', '_No response_')
    edition = edition.replace('### Main channel (optional)\n\n_No response_', f'### Main channel (optional)\n\n{F3}')
    taken = edition.replace('### iptv-org ID (optional)\n\n_No response_', '### iptv-org ID (optional)\n\nFrance3.fr@Alsace')
    assert 'already the channel' in issues.validate(issues.parse(22, ['channels:add'], taken), db)[0]
    issues.apply(issues.parse(23, ['channels:add'], edition), db)
    assert registry.resolve(db, 'france-3-lorraine.fr').parent == F3
    bad = ADD_CHANNEL.replace('FR', 'France').replace('https://www.alsace20.tv/', 'alsace20')
    problems = issues.validate(issues.parse(24, ['channels:add'], bad), db)
    assert any('two-letter code' in x for x in problems) and any('web address' in x for x in problems)
    named_id = ADD_CHANNEL.replace('Alsace 20 Plus', 'ch_abcdefghjk')            # the ID is made here, never given
    assert any('automatically' in x for x in issues.validate(issues.parse(28, ['channels:add'], named_id), db))
    slug_parent = ADD_CHANNEL.replace('### Main channel (optional)\n\n_No response_', '### Main channel (optional)\n\nfrance-3.fr')
    assert any('not a channel ID' in x for x in issues.validate(issues.parse(29, ['channels:add'], slug_parent), db))
    # an edit: renamed, closed; the ID and the logo stay, iptv-org no longer overwrites it
    ops.set_logo(db, c.id, png(800, 300), 'x')
    edit = (f'### Channel ID\n\n{c.id}\n\n### Channel name (optional)\n\nAlsace 20 Max\n\n### Status (optional)\n\n'
            'closed\n\n### Reason\n\nrenamed in 2026: https://www.alsace20.tv/\n')
    req = issues.parse(25, ['channels:edit'], edit)
    assert issues.validate(req, db) == []
    issues.apply(req, db)
    c = db.channels[c.id]
    assert (c.name, c.slug, c.status, bool(c.updated)) == ('Alsace 20 Max', 'alsace-20-max.fr', 'closed', True)
    assert (c.id, '') in db.logos
    empty = issues.parse(26, ['channels:edit'], f'### Channel ID\n\n{c.id}\n\n### Reason\n\nx\n')
    assert 'Nothing to change' in issues.validate(empty, db)[0]
    loop = issues.parse(27, ['channels:edit'], f'### Channel ID\n\n{F3}\n\n### Main channel (optional)\n\n{F3}\n\n### Reason\n\nx\n')
    assert 'its own main channel' in issues.validate(loop, db)[0]


def test_a_logo_for_an_unknown_channel_points_to_the_channel_form(db):
    req = issues.parse(30, ['logos:add'], BODY.replace(ALS, 'Some Channel'))
    assert 'not a channel ID' in issues.validate(req, db, downloader=lambda u: png(1000, 400))[0]


def test_guide_channels_are_matched_by_alias_id_and_name(db):
    ops.set_alias(db, 'F3-Alsace.fr', 'iptv-epg-fr', ALS)
    found = guides.match(db, 'iptv-epg-fr', 'fr', [
        {'id': 'F3-Alsace.fr', 'names': ['France 3 Alsace']},                 # confirmed alias
        {'id': 'tf1.fr', 'names': ['Something else']},                         # same iptv-org ID, case aside
        {'id': 'TF1Bis.fr', 'names': ['TF1 BIS HD']},                          # by name, quality mark aside
        {'id': 'France3+1.fr', 'names': ['France 3 + 1']},                     # timeshift: the channel itself
        {'id': 'Unknown.fr', 'names': ['Nothing Like It']},
        {'id': 'TF1Bis2.fr'},                                                  # no name: the ID gives it
    ])
    assert {g: [(m['channel'], m['score']) for m in ms] for g, ms in found.items()} == {
        'F3-Alsace.fr': [(ALS, 1.0)], 'tf1.fr': [(TF1, 0.95)], 'TF1Bis.fr': [(BIS, 0.9)],
        'France3+1.fr': [(F3, 0.9)]}
    db.channels[BIS].aliases = 'Télé Une'                                      # another name only: lower score
    assert guides.match(db, 'g', 'fr', [{'id': 'x', 'names': ['Tele Une']}])['x'][0]['score'] == 0.7
    db.channels[F3].aliases = 'Télé Une'                                       # two channels: ambiguous
    assert [m['score'] for m in guides.match(db, 'g', 'fr', [{'id': 'x', 'names': ['Tele Une']}])['x']] == [0.5, 0.5]


def test_guides_json_lookup_and_publication(db, tmp_path):
    ops.set_logo(db, F3, png(800, 300), 'x')
    ops.set_alias(db, 'Old.fr', 'other-guide', TF1)                            # a guide not read: still published
    data = guides.build(db, [('iptv-epg-fr', 'fr', [{'id': 'France3.fr', 'names': ['France 3']},
                                                    {'id': 'TF1BIS.fr', 'names': ['TF1 Bis']}])])
    assert data['guides']['other-guide'] == {'Old.fr': [{'channel': TF1, 'score': 1.0, 'how': 'confirmed'}]}
    assert guides.lookup(db, 'france3.fr@alsace')[0]['channel'] == ALS                 # an iptv-org ID
    assert guides.lookup(db, 'TF1BIS.fr', guides_data=data)[0]['channel'] == BIS        # a guide ID
    assert guides.lookup(db, 'TF1 Bis', 'fr')[0]['channel'] == BIS                      # a name
    db.channels[BIS].aliases = 'La Deux'
    assert guides.lookup(db, 'la deux') == [{'channel': BIS, 'score': 0.7, 'how': 'other name'}]
    channels = {c['id']: c for c in site.channels_json(db)['channels']}
    assert channels[ALS]['logo'] == channels[F3]['logo'] and channels[ALS]['logo_from'] == F3   # the channel's logo
    assert channels[F3]['iptv'] == 'France3.fr' and channels[BIS]['logo'] is None


def _drawing(fill, box=None, outline=None, size=(400, 160)):
    """A test logo on a transparent background: thick bars standing for letters, optionally inside a box."""
    from PIL import ImageDraw
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if box:
        d.rectangle([0, 0, size[0] - 1, size[1] - 1], fill=box)
    for x in range(40, 360, 60):
        d.rectangle([x, 40, x + 30, 120], fill=fill, outline=outline, width=4 if outline else 0)
    return img


def test_legibility_finds_what_vanishes_on_its_screen():
    white, black, yellow, navy = (255, 255, 255, 255), (0, 0, 0, 255), (255, 230, 0, 255), (20, 30, 70, 255)
    assert image.vanishing(_drawing(white)) > 0.9                          # white letters on a light screen
    assert image.vanishing(_drawing(black)) == 0
    assert image.vanishing(_drawing(black, box=white)) == 0                # a white frame around black letters
    assert image.vanishing(_drawing(white, outline=black)) == 0            # white letters edged in black
    assert image.vanishing(_drawing(yellow)) == 0                          # hue: yellow stays visible
    assert image.vanishing(_drawing(navy), dark=True) > 0.9                # navy on a dark screen
    assert image.vanishing(_drawing(white), dark=True) == 0


def test_what_vanishes_is_made_legible_keeping_the_rest():
    white, black, red, navy = (255, 255, 255, 255), (0, 0, 0, 255), (220, 20, 30, 255), (20, 30, 70, 255)
    fixed = image.legible(_drawing(white))
    assert image.vanishing(fixed) < image.VANISH_ALERT
    assert image.legible(_drawing(red)) is not None and image.vanishing(_drawing(red)) == 0
    same = _drawing(black)
    assert image.legible(same) is same                                     # nothing vanishes: unchanged
    assert image.vanishing(image.legible(_drawing(navy), dark=True), dark=True) < image.VANISH_ALERT


def test_variants_give_a_logo_readable_on_light_and_a_white_variant_readable_on_dark():
    for colour in ((255, 255, 255, 255), (200, 200, 205, 255), (20, 30, 70, 255)):   # white, silver, navy letters
        logo, white = image.variants(_drawing(colour))
        assert image.vanishing(logo) < image.VANISH_ALERT
        assert image.vanishing(white if white is not None else logo, dark=True) < image.VANISH_ALERT
