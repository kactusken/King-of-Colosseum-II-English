"""Shared helpers for the ui group's pixel scripts (run them from the project root).

render_labels(id, english, boxes, ...)  the automatic renderer (tools/render.py) on chosen boxes,
                                         so titles match the renderer's lettering; returns RGBA
plain_text(im, rect, text, ...)          fill a rect with a flat colour and draw text on it
outlined(im, xy_centre, text, ...)       white text with a dark outline, centred on a point"""
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, 'tools')
import render, catalog  # noqa: E402

BOLD = 'tools/fonts/BarlowCondensed-Bold.ttf'


def render_labels(ident, japanese, english, boxes, align='', font=''):
    row = dict(catalog.by_id(catalog.rows())[ident])
    row.update(japanese=japanese, english=english, boxes=boxes, align=align, font=font)
    render.NOTES.clear()
    out, why = render.render(row)
    if out is None:
        sys.exit(f'{ident}: renderer failed - {why}')
    for n in render.NOTES:
        print('  ~', n)
    return out.convert('RGBA')


def font_for_cap(cap, path=BOLD):
    size = next(s for s in range(80, 5, -1)
                if (lambda b: b[3] - b[1])(ImageFont.truetype(path, s).getbbox('H')) <= cap)
    return ImageFont.truetype(path, size)


def text_mask(size, text, font, x, cy, anchor='left'):
    """1-bit-ish L mask with text whose cap height is centred on row cy; x = left edge (or centre)."""
    m = Image.new('L', size, 0)
    d = ImageDraw.Draw(m)
    hb = font.getbbox('H')
    w = font.getlength(text)
    if anchor == 'center':
        x = x - w / 2
    elif anchor == 'right':
        x = x - w
    d.text((round(x), round(cy - (hb[1] + hb[3]) / 2)), text, font=font, fill=255)
    return m


def plain_text(im, rect, text, font, bg, fill=(255, 255, 255, 255), x=None, cy=None, anchor='left'):
    x0, y0, x1, y1 = rect
    im.paste(bg, (x0, y0, x1, y1))
    m = text_mask(im.size, text, font, x0 if x is None else x, (y0 + y1) / 2 if cy is None else cy, anchor)
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    layer.paste(fill, mask=m)
    im.alpha_composite(layer)


def outlined(im, text, font, x, cy, anchor='center', fill=(255, 255, 255, 255), edge=(0, 0, 0, 255), grow=3):
    m = text_mask(im.size, text, font, x, cy, anchor)
    e = m.point(lambda v: 255 if v > 60 else v * 4).filter(ImageFilter.MaxFilter(grow))
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    layer.paste(edge, mask=e)
    layer.paste(fill, mask=m)
    im.alpha_composite(layer)


def dojo_title(im, cx, cy, text='Pro Wrestling Dojo', cap=22):
    """The Dojo title style: black letters, cream 2-pixel outline, faint dark halo (000_01712/01730)."""
    font = font_for_cap(cap)
    m = text_mask(im.size, text, font, cx, cy, 'center')
    hard = m.point(lambda v: 255 if v > 60 else v * 4)
    cream = hard.filter(ImageFilter.MaxFilter(5))
    halo = cream.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.8)).point(lambda v: v * 70 // 255)
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    layer.paste((37, 36, 33, 255), mask=halo)
    layer.paste((250, 242, 211, 255), mask=cream)
    layer.paste((0, 0, 0, 255), mask=m)
    im.alpha_composite(layer)
    return font.getlength(text)


def tracked_mask(size, text, font, cx, cy, track):
    """Text centred on (cx, cy) with `track` extra pixels between letters."""
    m = Image.new('L', size, 0)
    d = ImageDraw.Draw(m)
    hb = font.getbbox('H')
    w = sum(font.getlength(c) for c in text) + track * (len(text) - 1)
    x = cx - w / 2
    for c in text:
        d.text((round(x), round(cy - (hb[1] + hb[3]) / 2)), c, font=font, fill=255)
        x += font.getlength(c) + track
    return m


def stamp(im, cx, cy, r_clear, text, cap, bg, red=(173, 25, 9, 255), cream=(250, 243, 176, 255), grow=5, track=2):
    """Re-letter a round 済 stamp: clear the disc inside the ring (radius r_clear around cx, cy) to
    `bg`, then draw `text` in the stamp's red with a cream outline, centred."""
    px = im.load()
    for y in range(int(cy - r_clear) - 1, int(cy + r_clear) + 2):
        for x in range(int(cx - r_clear) - 1, int(cx + r_clear) + 2):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r_clear ** 2:
                px[x, y] = bg
    font = font_for_cap(cap)
    m = tracked_mask(im.size, text, font, cx + 0.5, cy + 0.5, track)
    hard = m.point(lambda v: 255 if v > 60 else v * 4)
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    layer.paste(cream, mask=hard.filter(ImageFilter.MaxFilter(grow)))
    layer.paste(red, mask=m)
    im.alpha_composite(layer)
