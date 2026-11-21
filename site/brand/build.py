"""Brand images of the website (og-image.png, avatar.png, apple-touch-icon.png in site/public/), built from the mark
(site/public/logo-mark.svg) and the Geist font: `uv run python site/brand/build.py`."""
import io
from pathlib import Path

import resvg_py
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / 'site' / 'public'
FONT = ROOT / 'temp' / 'font' / 'Geist-SemiBold.ttf'   # https://fonts.google.com/specimen/Geist (SemiBold, TTF)
DARK = (17, 20, 27, 255)

mark_svg = (PUBLIC / 'logo-mark.svg').read_text(encoding='utf-8')


def render(svg: str, width: int) -> Image.Image:
    return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width)))).convert('RGBA')



# social card 1200x630: the mark with its own glow (the mark blurred), the name and the promise below
card = Image.new('RGBA', (1200, 630), DARK)
mark = render(mark_svg, 320)
pos = ((1200 - mark.width) // 2, 110)
for radius, strength in ((60, 1.0), (24, 0.8)):
    layer = Image.new('RGBA', (1200, 630), (0, 0, 0, 0))
    layer.alpha_composite(mark, pos)
    glow = layer.filter(ImageFilter.GaussianBlur(radius))
    glow.putalpha(glow.getchannel('A').point(lambda v, s=strength: int(min(255, v * 2.2 * s))))
    card.alpha_composite(glow)
card.alpha_composite(mark, pos)
draw = ImageDraw.Draw(card)
title = ImageFont.truetype(str(FONT), 64)
sub = ImageFont.truetype(str(FONT), 30)
for text, font, y, fill in (('Worldwide TV Logos', title, 380, (255, 255, 255, 255)),
                            ('Every TV channel logo. One clean URL.', sub, 470, (196, 200, 214, 255))):
    w = draw.textlength(text, font=font)
    draw.text(((1200 - w) / 2, y), text, font=font, fill=fill)
card.convert('RGB').save(PUBLIC / 'og-image.png', optimize=True)

# square icons on the dark background: GitHub organisation avatar and Apple touch icon
for name, size, inner in (('avatar.png', 512, 0.74), ('apple-touch-icon.png', 180, 0.78)):
    icon = Image.new('RGBA', (size, size), DARK)
    m = render(mark_svg, round(size * inner))
    icon.alpha_composite(m, ((size - m.width) // 2, (size - m.height) // 2))
    icon.convert('RGB').save(PUBLIC / name, optimize=True)
print('ok')
