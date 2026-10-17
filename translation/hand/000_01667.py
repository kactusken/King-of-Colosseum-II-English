"""000_01667: costume-edit tabs - 試合用 / 入場用 beside L1 / R1 -> "Match" / "Entrance",
white Barlow Condensed Bold with a black outline on the tab's own colour. Run from the project root."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
SRC, DST = 'review/images-original/000_01667.png', 'build/work/hand/out/000_01667.png'
FONT = 'tools/fonts/BarlowCondensed-Bold.ttf'
CAP = 12                                     # L1/R1 glyphs are 11 rows; Japanese 15
TABS = [  # (text, cleared rows y0..y1 inclusive, tab colour, ink centre y)
    ('Match', 298, 316, (114, 42, 0, 255), 307),
    ('Entrance', 324, 342, (2, 79, 0, 255), 333),
]
X0, X1 = 37, 99                              # coloured part of the tab (x 36-99)
im = Image.open(SRC).convert('RGBA')
size = next(s for s in range(40, 6, -1)
            if (lambda b: b[3] - b[1])(ImageFont.truetype(FONT, s).getbbox('H')) <= CAP)
font = ImageFont.truetype(FONT, size)
for text, y0, y1, colour, cy in TABS:
    im.paste(colour, (X0, y0, X1 + 1, y1 + 1))
    m = Image.new('L', im.size, 0)
    d = ImageDraw.Draw(m)
    hb = font.getbbox('H')
    w = font.getlength(text)
    d.text((round((X0 + X1 + 1) / 2 - w / 2), round(cy - (hb[1] + hb[3]) / 2)), text, font=font, fill=255)
    edge = m.point(lambda v: 255 if v > 60 else v * 4).filter(ImageFilter.MaxFilter(3))
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    layer.paste((0, 0, 0, 255), mask=edge)
    layer.paste((255, 255, 255, 255), mask=m)
    im.alpha_composite(layer)
im.save(DST)
