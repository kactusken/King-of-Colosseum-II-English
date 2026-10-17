"""Shared helpers for the "banners" hand-edit pixel scripts (build/work/hand/<id>.py).

Draws English lettering into a picture in one of the game's banner styles, each a stack of
layers around the text: dark text with a cream outline and glow (league/tournament/show banners),
red text with a thick yellow outline (attendance plates), white text with a soft shadow (captions).

  img = load('000_01628')                       # RGBA original
  line = Line(text, ink_rect, ...)               # one label replacing the Japanese in ink_rect
  draw_lines(img, [line, ...], STYLE)            # clears each Japanese label, draws the English
  save(img, '000_01628')                         # build/work/hand/out/<id>.png

Run with .venv/bin/python from the project root (Pillow)."""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / 'tools' / 'fonts'
BOLD = FONTS / 'BarlowCondensed-Bold.ttf'
ITALIC = FONTS / 'BarlowCondensed-ExtraBoldItalic.ttf'
SCALE = 4                      # supersampling for anti-aliased text


def load(ident):
    return Image.open(ROOT / 'review' / 'images-original' / f'{ident}.png').convert('RGBA')


def save(img, ident):
    out = ROOT / 'build' / 'work' / 'hand' / 'out'
    out.mkdir(parents=True, exist_ok=True)
    img.save(out / f'{ident}.png')
    preview(img, ident)


def preview(img, ident):
    """build/work/hand/preview/<id>.png: original | English, on a dark blue background, 2x when small."""
    o = load(ident)
    t = Image.new('RGBA', (o.width * 2 + 8, o.height), (30, 40, 70, 255))
    t.alpha_composite(o, (0, 0))
    t.alpha_composite(img, (o.width + 8, 0))
    k = 2 if o.width <= 512 else 1
    if o.width <= 128:
        k = 3
    p = ROOT / 'build' / 'work' / 'hand' / 'preview'
    p.mkdir(parents=True, exist_ok=True)
    t.resize((t.width * k, t.height * k), Image.NEAREST).save(p / f'{ident}.png')


# ---------------------------------------------------------------- text

def font_for_cap(file, cap_h):
    """A font (at SCALE) whose capital H is cap_h pixels tall (at 1x)."""
    for size in range(200 * SCALE, 4, -1):
        f = ImageFont.truetype(str(file), size)
        b = f.getbbox('H')
        if b[3] - b[1] <= cap_h * SCALE:
            return f
    raise ValueError(cap_h)


def text_mask(text, file, cap_h, max_w, squeeze_min=0.75):
    """(L mask at 1x, cap_top, cap_bottom) - the text's anti-aliased coverage, squeezed
    horizontally to fit max_w (down to squeeze_min, then drawn smaller)."""
    h = cap_h
    while h > 4:
        f = font_for_cap(file, h)
        bb = f.getbbox(text)
        w, hh = bb[2] - bb[0] + 4 * SCALE, f.getbbox('Hgjy')[3] + 4 * SCALE
        m = Image.new('L', (w, hh), 0)
        ImageDraw.Draw(m).text((2 * SCALE - bb[0], 2 * SCALE), text, font=f, fill=255)
        cap = f.getbbox('H')
        cap_top, cap_bot = 2 * SCALE + cap[1], 2 * SCALE + cap[3]
        ink = m.getbbox()
        m = m.crop((ink[0], 0, ink[2], hh))
        width = m.width / SCALE
        squeeze = min(1.0, max_w / width)
        if squeeze >= squeeze_min:
            nw = max(1, round(width * squeeze))
            pad = (-cap_top) % SCALE          # keep the cap top on a pixel boundary
            big = Image.new('L', (m.width, hh + pad), 0)
            big.paste(m, (0, pad))
            hh2 = -(-big.height // SCALE) * SCALE
            big2 = Image.new('L', (big.width, hh2), 0)
            big2.paste(big, (0, 0))
            small = big2.resize((nw, hh2 // SCALE), Image.BOX)
            note = '' if squeeze >= 0.999 else f'squeezed {squeeze:.0%}'
            if h < cap_h:
                note += f' cap {h}px instead of {cap_h}px'
            return small, (cap_top + pad) / SCALE, (cap_bot + pad) / SCALE, note.strip()
        h -= 1
    raise ValueError(f'{text!r} does not fit {max_w}px')


def dilate(mask, r):
    """Round dilation of an L mask by r pixels (keeps anti-aliasing)."""
    if r <= 0:
        return mask.copy()
    out = Image.new('L', mask.size, 0)
    rr = r * r + r * 0.6
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= rr:
                out = ImageChops.lighter(out, ImageChops.offset(mask, dx, dy))
    return out


def solid(size, colour):
    return Image.new('RGBA', size, tuple(colour[:3]) + (255,))


def with_alpha(colour_img, mask, alpha=255):
    a = mask.point(lambda v: v * alpha // 255)
    r, g, b, _ = colour_img.split()
    return Image.merge('RGBA', (r, g, b, a))


# ---------------------------------------------------------------- styles
# layers: outer to inner, (radius around the text, (r,g,b), alpha, offset (dx,dy)); then the fill.

CREAM = {'name': 'cream', 'fill': (1, 1, 1), 'edge_aa': None,
         'layers': [(5, (251, 242, 211), 62, (0, 0)), (4, (251, 242, 211), 154, (0, 0)),
                    (3, (251, 242, 211), 254, (0, 0))],
         'ink': lambda p: p[3] > 200 and p[0] + p[1] + p[2] < 200, 'clear_r': 6, 'keep_r': 4}

RED = {'name': 'red', 'fill': (157, 15, 7),
       'layers': [(5, (93, 86, 3), 106, (0, 1)), (3, (226, 209, 7), 255, (0, 0))],
       'ink': lambda p: p[3] > 20, 'clear_r': 8, 'keep_r': 0}

WHITE_SHADOW = {'name': 'white', 'fill': (240, 240, 244),
                'layers': [(1, (8, 6, 4), 220, (1, 1))],
                'ink': lambda p: p[3] > 200 and min(p[:3]) > 120, 'clear_r': 2, 'keep_r': 0}


class Line:
    """One English label.  ink: (x, y, w, h) of the Japanese label's ink (what is cleared - with its
    outline/glow - and where the new text is centred); cap: capital height; max_w: widest the text
    may be; align: center | left | right (left/right relative to ink rect, or to `at` x)."""

    def __init__(self, text, ink, cap, max_w=None, align='center', font=BOLD, at=None, dy=0, clear=True):
        self.text, self.ink, self.cap, self.align, self.font = text, ink, cap, align, font
        self.max_w = max_w or ink[2]
        self.at, self.dy, self.clear = at, dy, clear


def ink_mask(img, rect, style):
    """L mask of the style's ink pixels inside rect (whole picture size)."""
    m = Image.new('L', img.size, 0)
    px, mp = img.load(), m.load()
    x0, y0, w, h = rect
    for y in range(max(0, y0), min(img.height, y0 + h)):
        for x in range(max(0, x0), min(img.width, x0 + w)):
            if style['ink'](px[x, y]):
                mp[x, y] = 255
    return m


def clear_lines(img, lines, style, background, band=None):
    """Clear each line's Japanese (ink + outline/glow) to `background`, keeping pixels that belong
    to other (kept) labels: those within keep_r of ink outside every cleared rect."""
    target = Image.new('L', img.size, 0)
    for ln in lines:
        if ln.clear:
            x, y, w, h = ln.ink       # 2 px taller: stray strokes between rows belong to the label
            target = ImageChops.lighter(target, ink_mask(img, (x - 2, y - 2, w + 4, h + 4), style))
    everything = ink_mask(img, band or (0, 0) + img.size, style)
    other = ImageChops.subtract(everything, target)
    cl = dilate(target, style['clear_r'])
    if style['keep_r']:
        cl = ImageChops.subtract(cl, dilate(other, style['keep_r']))
    bg = Image.new('RGBA', img.size, background)
    img.paste(bg, (0, 0), cl)
    return cl


def render_line(size, ln, style):
    """RGBA layer (picture size) with the English for one Line, and a note."""
    m, cap_top, cap_bot, note = text_mask(ln.text, ln.font, ln.cap, ln.max_w)
    x0, y0, w, h = ln.ink
    cy = y0 + h / 2 + ln.dy
    top = round(cy - (cap_top + cap_bot) / 2)
    if ln.align == 'left':
        left = ln.at if ln.at is not None else x0
    elif ln.align == 'right':
        left = (ln.at if ln.at is not None else x0 + w) - m.width
    else:
        cx = ln.at if ln.at is not None else x0 + w / 2
        left = round(cx - m.width / 2)
    mask = Image.new('L', size, 0)
    mask.paste(m, (int(left), top))
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    for r, colour, alpha, (dx, dy) in style['layers']:
        d = dilate(mask, r)
        if dx or dy:
            d = ImageChops.offset(d, dx, dy)
        layer.alpha_composite(with_alpha(solid(size, colour), d, alpha))
    layer.alpha_composite(with_alpha(solid(size, style['fill']), mask))
    return layer, note, (int(left), top, m.width, m.height)


def merge_max(img, layer):
    """Put layer over img; where img is (semi-)transparent keep whichever is more opaque, so the
    new glow and a neighbour's glow combine instead of cutting each other."""
    over = img.copy()
    over.alpha_composite(layer)
    a_img, a_lay = img.split()[3], layer.split()[3]
    # where the layer is weaker than what is there, keep the original pixel
    keep = ImageChops.subtract(a_img, a_lay).point(lambda v: 255 if v > 0 else 0)
    out = Image.composite(img, over, keep)
    img.paste(out)


def draw_lines(img, lines, style, background=None, band=None, clear_all=False):
    """Clear the Japanese of every line (or the whole picture), then draw the English; returns notes."""
    if background is None:
        background = img.getpixel((0, 0))
    if clear_all:
        img.paste(Image.new('RGBA', img.size, background))
    else:
        clear_lines(img, lines, style, background, band)
    notes = []
    for ln in lines:
        layer, note, where = render_line(img.size, ln, style)
        merge_max(img, layer)
        notes.append(f'{ln.text!r} at {where} {note}'.rstrip())
    return notes


def inpaint(img, mask, rounds=200):
    """Fill the mask's pixels from their surroundings (repeated neighbour averaging) - for text on
    textured backgrounds (captions over art)."""
    px = img.load()
    mp = mask.load()
    todo = {(x, y) for y in range(img.height) for x in range(img.width) if mp[x, y]}
    while todo and rounds:
        rounds -= 1
        done = {}
        for x, y in todo:
            acc = [0, 0, 0, 0]
            n = 0
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                q = (x + dx, y + dy)
                if 0 <= q[0] < img.width and 0 <= q[1] < img.height and q not in todo:
                    p = px[q]
                    for i in range(4):
                        acc[i] += p[i]
                    n += 1
            if n >= 2:
                done[(x, y)] = tuple(v // n for v in acc)
        for q, v in done.items():
            px[q] = v
        todo -= set(done)

CREAM_THIN = dict(CREAM, name='cream-thin',
                  layers=[(3, (251, 242, 211), 90, (0, 0)), (2, (251, 242, 211), 254, (0, 0))])

LIGHT_ON_DARK = {'name': 'light-on-dark', 'fill': (251, 242, 212),
                 'layers': [(2, (2, 2, 2), 120, (0, 0)), (1, (2, 2, 2), 254, (0, 0))],
                 'ink': lambda p: p[3] > 200 and p[0] + p[1] + p[2] < 200, 'clear_r': 3, 'keep_r': 0}


def script(ident, lines, style, background, **kw):
    """Run one picture: draw, print notes, save output and preview."""
    img = load(ident)
    for n in draw_lines(img, lines, style, background=background, **kw):
        print(ident, n)
    save(img, ident)
    return img
