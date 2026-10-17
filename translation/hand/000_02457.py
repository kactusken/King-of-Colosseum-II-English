"""000_02457 round headers with a number slot: 決勝トーナメント第[N]回戦 / 予選リーグ第[N]試合.
The game draws the round/match number into the gap, so the English ends right before the gap
("Tournament Round [N]", "League Match [N]") and the words after the gap are cleared.
Cream lettering with a black outline, as the original. The digit strip is untouched.
Reads review/images-original/000_02457.png, writes build/work/hand/out/000_02457.png.
Run from the project root with .venv/bin/python."""
from PIL import Image, ImageChops, ImageDraw, ImageFont

SRC = 'review/images-original/000_02457.png'
OUT = 'build/work/hand/out/000_02457.png'
FONT = 'tools/fonts/BarlowCondensed-Bold.ttf'
FILL, EDGE, BG = (249, 240, 210, 255), (0, 0, 0, 255), (0, 0, 0, 6)
# (text, clear boxes (x0, y0, x1, y1) inclusive, right edge of the text (before the gap), ink rows)
LABELS = [
    ('Tournament Round', [(56, 0, 345, 32), (383, 0, 455, 32)], 341, (1, 31)),
    ('League Match', [(104, 65, 299, 98), (240, 58, 299, 64), (336, 62, 409, 98)], 295, (66, 96)),
]
CAP_MAX = 26
STROKE = 2
S = 4                                   # supersampling for anti-aliased edges

im = Image.open(SRC).convert('RGBA')
d = ImageDraw.Draw(im)
for _, boxes, _, _ in LABELS:
    for b in boxes:
        d.rectangle(b, fill=BG)


def cap_height(size):
    b = ImageFont.truetype(FONT, size).getbbox('H')
    return b[3] - b[1]


size = max(s for s in range(8, 80) if cap_height(s) <= CAP_MAX)
for text, boxes, right, (top, bottom) in LABELS:
    room = right - boxes[0][0] - 2 * STROKE
    while ImageFont.truetype(FONT, size).getlength(text) > room:
        size -= 1
print('size', size)

for text, boxes, right, (top, bottom) in LABELS:
    f = ImageFont.truetype(FONT, size * S)
    bb = f.getbbox(text)
    cap = f.getbbox('H')
    w = bb[2] - bb[0]
    x = right * S - STROKE * S - w - bb[0]
    mid = (top + bottom + 1) / 2 * S
    y = mid - (cap[1] + cap[3]) / 2
    W, H = im.width * S, im.height * S
    fill = Image.new('L', (W, H), 0)
    edge = Image.new('L', (W, H), 0)
    ImageDraw.Draw(edge).text((x, y), text, font=f, fill=255, stroke_width=STROKE * S, stroke_fill=255)
    ImageDraw.Draw(fill).text((x, y), text, font=f, fill=255)
    fill, edge = (m.resize(im.size, Image.LANCZOS) for m in (fill, edge))
    im.paste(Image.new('RGBA', im.size, EDGE), (0, 0), edge)
    im.paste(Image.new('RGBA', im.size, FILL), (0, 0), fill)
im.save(OUT)
print('wrote', OUT)
