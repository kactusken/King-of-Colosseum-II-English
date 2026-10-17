"""000_01679: move-slot icons 必 / 得1-4 / 声1-2 -> F / S1-S4 / V1-V2 (Finisher, Signature,
Voice). Each 25x21 bevelled tile is rebuilt without its lettering (per-row tile colour, bevel kept
where it is not covered by the old glyph) and relettered in white Barlow Condensed Bold with a
dark 1-pixel outline like the original digits. Run from the project root."""
from collections import Counter
from PIL import Image, ImageDraw, ImageFont, ImageFilter
SRC, DST = 'review/images-original/000_01679.png', 'build/work/hand/out/000_01679.png'
FONT = 'tools/fonts/BarlowCondensed-Bold.ttf'
W, H = 25, 21
TILES = [('F', 82, 258), ('S1', 82, 282), ('S2', 114, 282), ('S3', 146, 282), ('S4', 178, 282),
         ('V1', 82, 306), ('V2', 82, 330)]
CAP = 13                     # the original digits are 13 rows tall
im = Image.open(SRC).convert('RGBA')
px = im.load()


def lum(p):
    return (p[0] * 3 + p[1] * 6 + p[2]) / 10


def textlike(p):
    """Glyph pixels: greys/whites of the lettering and its near-black outline."""
    r, g, b = p[:3]
    sat = max(r, g, b) - min(r, g, b)
    return sat <= 13 or lum(p) < 30


def mode(cands, need=1):
    c = Counter(cands).most_common(1)
    return c[0][0] if c and c[0][1] >= need else None


def fill_gaps(vals):
    return [v if v is not None else next(vals[k] for d in range(1, len(vals)) for k in (i - d, i + d)
                                         if 0 <= k < len(vals) and vals[k] is not None)
            for i, v in enumerate(vals)]


for _, x0, y0 in TILES:
    # stray outline pixels of the old glyph just outside the tile
    for y in range(y0 - 1, y0 + H + 1):
        for x in (x0 - 1, x0 + W):
            px[x, y] = (0, 0, 0, 0)
    for x in range(x0 - 1, x0 + W + 1):
        for y in (y0 - 1, y0 + H):
            px[x, y] = (0, 0, 0, 0)
    tile = [[px[x0 + c, y0 + r] for c in range(W)] for r in range(H)]
    # body: one colour per row (blue tiles have a vertical gradient), from clean bright pixels
    body = fill_gaps([mode([p for p in tile[r][2:W - 2] if not textlike(p) and lum(p) >= 45], 3)
                      for r in range(2, H - 2)])
    rows = {r: mode([p for p in tile[r][2:W - 2] if not textlike(p)]) or body[min(max(r - 2, 0), H - 5)]
            for r in (0, 1, H - 2, H - 1)}
    cols = {c: mode([tile[r][c] for r in range(2, H - 2) if not textlike(tile[r][c])]) for c in (0, 1, W - 2, W - 1)}
    for r in range(H):
        for c in range(W):
            p = tile[r][c]
            if r in rows:                     # bevel rows: keep, mend glyph pixels
                new = p if not textlike(p) and (c in (0, W - 1) or lum(p) >= lum(rows[r]) * 0.7) else rows[r]
                if c in (0, W - 1) and textlike(p):
                    new = rows[r]
            elif c in cols:                   # bevel columns
                new = cols[c] or body[r - 2]
            else:
                new = body[r - 2]
            px[x0 + c, y0 + r] = new

size = next(s for s in range(40, 6, -1)
            if (lambda b: b[3] - b[1])(ImageFont.truetype(FONT, s).getbbox('H')) <= CAP)
font = ImageFont.truetype(FONT, size)
hb = font.getbbox('H')
for text, x0, y0 in TILES:
    m = Image.new('L', im.size, 0)
    d = ImageDraw.Draw(m)
    w = font.getlength(text)
    d.text((round(x0 + W / 2 - w / 2), round(y0 + H / 2 - (hb[1] + hb[3]) / 2)), text, font=font, fill=255)
    edge = m.point(lambda v: 255 if v > 60 else v * 4).filter(ImageFilter.MaxFilter(3))
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    layer.paste((15, 15, 9, 255), mask=edge)
    layer.paste((255, 255, 255, 255), mask=m)
    im.alpha_composite(layer)
im.save(DST)
