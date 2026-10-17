"""000_02262 crowd-satisfaction panel atlas: redraw the italic panel title '観客満足度' as
'Crowd Satisfaction' and the unit glyphs 分 / 秒 as 'm' / 's' (the game writes e.g. 3分20秒 ->
3m20s). Digits, %, button icons and the gauge squares stay as drawn.
Reads review/images-original/000_02262.png, writes build/work/hand/out/000_02262.png.
Run from the project root with .venv/bin/python."""
from PIL import Image, ImageChops, ImageDraw, ImageFont

SRC = 'review/images-original/000_02262.png'
OUT = 'build/work/hand/out/000_02262.png'
TITLE_FONT = 'tools/fonts/BarlowCondensed-ExtraBoldItalic.ttf'
UNIT_FONT = 'tools/fonts/BarlowCondensed-Bold.ttf'
WHITE = (255, 255, 255, 255)
S = 4

im = Image.open(SRC).convert('RGBA')
d = ImageDraw.Draw(im)


def draw_text(text, font_file, size, x, cap_top, colour, clip=None, align='left', width=0):
    f = ImageFont.truetype(font_file, size * S)
    cap = f.getbbox('H')
    bb = f.getbbox(text)
    tw = bb[2] - bb[0]
    if align == 'center':
        x = x + (width - tw / S) / 2
    big = Image.new('L', (im.width * S, im.height * S), 0)
    ImageDraw.Draw(big).text((x * S - bb[0], cap_top * S - cap[1]), text, font=f, fill=255)
    m = big.resize(im.size, Image.LANCZOS)
    if clip:
        c = Image.new('L', im.size, 0)
        ImageDraw.Draw(c).rectangle(clip, fill=255)
        m = ImageChops.multiply(m, c)
    im.paste(Image.new('RGBA', im.size, colour), (0, 0), m)
    return tw / S


# title: clear the old lettering (panel interior is black here), redraw on the same baseline area
d.rectangle((28, 16, 160, 43), fill=(0, 0, 0, 255))
TITLE_SIZE = 25                         # cap height 17: the slanted frame edge leaves no room for more
w = draw_text('Crowd Satisfaction', TITLE_FONT, TITLE_SIZE, 24, 23, WHITE)
print('title width', round(w))

# units: 分 at x 259..276, 秒 at 283..300, rows 107..124 (transparent background)
for x0, x1 in ((259, 276), (283, 300)):
    d.rectangle((x0 - 1, 105, x1 + 1, 126), fill=(0, 0, 0, 0))
# the glyphs are white with a dark edge; draw with a 1 px dark outline
for text, x0, x1 in (('m', 259, 276), ('s', 283, 300)):
    f = ImageFont.truetype(UNIT_FONT, 22 * S)
    bb = f.getbbox(text)
    tw = (bb[2] - bb[0]) / S
    x = x0 + (x1 - x0 + 1 - tw) / 2
    xh = f.getbbox('x')
    top = 124 - (xh[3] - xh[1]) / S      # sit on the original glyphs' bottom row
    for layer, stroke, colour in ((0, 1, (16, 16, 16, 255)), (1, 0, WHITE)):
        big = Image.new('L', (im.width * S, im.height * S), 0)
        ImageDraw.Draw(big).text((x * S - bb[0], top * S - xh[1]), text, font=f, fill=255,
                                 stroke_width=stroke * S, stroke_fill=255)
        im.paste(Image.new('RGBA', im.size, colour), (0, 0), big.resize(im.size, Image.LANCZOS))
im.save(OUT)
print('wrote', OUT)
