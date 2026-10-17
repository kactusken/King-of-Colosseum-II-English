#!/usr/bin/env python3
"""Automatic English renders of the catalogue images (needs Pillow: run with .venv/bin/python).

  render.py                 (re)draw only what's out of date: rows whose english/font/align/boxes,
                            original image or RENDERER_VERSION changed since they were drawn
  render.py <image>...      draw these (ids, ranges or patterns, see tools/edit.py) if out of date
  render.py --all           redraw every row the renderer is responsible for
  render.py --regen <image>...
                            redraw on purpose, even approved (done) images - which are re-frozen in
                            translation/images-approved/; writes review/edit/<image>_regen.png
                            (original | before | after)

The renderer is responsible for rows with status todo, an English text and no dup_of. It writes
translation/images-rendered/<image>.png (indexed, in the original's palette) and records a
fingerprint in translation/renders.json. Approved images are never redrawn except with --regen;
bump RENDERER_VERSION after changing how images are drawn so todo rows are refreshed.

Styles (STYLES, first match wins):
  lettered  the game's menu lettering: anti-aliased white text with a dark outline (menu labels)
            or a soft drop shadow (name plates, font 'plate' by default). Read once per picture:
            kind, fill and edge colours, and the label height - every label of a picture gets
            the same text size, set from the original lettering height (so equal Japanese sizes
            give equal English sizes across screens). A label too wide for its box is squeezed
            horizontally down to SQUEEZE_MIN, then drawn smaller (reported). Pixels are snapped
            to the picture's own palette (premultiplied RGBA).
  solid     one background + one text colour (+ outline), 1-bit - for pixel-font pictures
            (font hint 'solid').
Rows whose image matches no style, or whose English doesn't fit, are reported (hand edit them, or
add a style); they count as up to date until the row or the renderer changes.

graphics.csv hints:
  font    a key of FONTS (default: 'default'); 'hand' = never drawn automatically (hand edit)
  align   left | center | right       (default center)
  boxes   x,y,w,h;x,y,w,h             one box per label, english items separated by ' | ';
                                      only the boxes are cleared and redrawn
  ' / ' in the English forces a line break; an empty item (' |  | ') clears that label and
  '=' leaves it untouched (digits, COM, START... already fine).
  align may also hold one hint per label (' | '-separated like english, empty = automatic), and
  'left+N' insets a left-aligned label by N pixels.
  Without an align hint, each label follows the original: left-aligned if another label of the
  picture starts at the same x (a left-aligned list), centred otherwise.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import paths  # noqa: E402

RENDERER_VERSION = 34  # bump when a change to this file changes what gets drawn

FONT_DIRS = [Path(__file__).resolve().parent / 'fonts', Path('/usr/share/fonts/truetype/dejavu'),
             Path('/mnt/c/Windows/Fonts'), Path('C:/Windows/Fonts')]
FONTS = {  # graphics.csv `font` -> font file (searched in FONT_DIRS); decided 2026-10-15 (docs/TRANSLATION.md)
    'default': 'BarlowCondensed-Bold.ttf',              # menu labels (outlined)
    'plate': 'BarlowCondensed-ExtraBoldItalic.ttf',     # slanted name plates (drop shadow)
    'heavy': 'BarlowCondensed-Black.ttf',               # next to the original's heavy capitals (SINGLE / TAG)
    'symbols': 'DejaVuSans-Bold.ttf',                   # fallback for ○ △ □ ➡ ▲ ... (not in Barlow)
}
SIZES = range(40, 5, -1)        # tried largest first; text is drawn without anti-aliasing
MARGIN = 1                      # pixels kept free around the text when there are no boxes


# ---------------------------------------------------------------- text layout

def load_font(name, size, cache={}):
    key = (name, size)
    if key not in cache:
        file = FONTS.get(name or 'default')
        if file is None:
            raise KeyError(f'unknown font {name!r} (known: {", ".join(FONTS)})')
        path = next((d / file for d in FONT_DIRS if (d / file).exists()), None)
        if path is None:
            sys.exit(f'font file {file} not found in {", ".join(map(str, FONT_DIRS))}; '
                     f'put it in tools/fonts/ or change FONTS in render.py')
        cache[key] = ImageFont.truetype(str(path), size)
    return cache[key]


def text_width(font, s):
    return font.getlength(s)


def wrap(font, text, width):
    """Lines for `text` within `width`: ' / ' forces a break, otherwise greedy by word."""
    lines = []
    for part in text.split(' / '):
        cur = ''
        for word in part.split():
            cand = word if not cur else cur + ' ' + word
            if text_width(font, cand) <= width:
                cur = cand
            elif not cur or text_width(font, word) > width:
                return None
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def fit(text, w, h, fontname):
    """(font, lines, line_height) at the largest size that fits a w x h box, or None."""
    for size in SIZES:
        font = load_font(fontname, size)
        asc, desc = font.getmetrics()
        lh = asc + desc
        if lh * 0.8 > h:
            continue
        lines = wrap(font, text, w)
        if lines is not None and lh * len(lines) <= h + desc:
            return font, lines, lh
    return None


def text_mask(size, box, text, fontname, align):
    """A 1-bit mask of `text` laid out in `box` (x, y, w, h) of an image of `size`; None if it doesn't fit."""
    x0, y0, w, h = box
    got = fit(text, w, h, fontname)
    if got is None:
        return None
    font, lines, lh = got
    mask = Image.new('L', size, 0)
    d = ImageDraw.Draw(mask)
    d.fontmode = '1'
    # centre the ink, not the font's line box
    total = lh * len(lines)
    top = y0 + (h - total) / 2
    for i, line in enumerate(lines):
        lw = text_width(font, line)
        x = x0 + {'left': 0, 'right': w - lw}.get(align, (w - lw) / 2)
        d.text((round(x), round(top + i * lh)), line, font=font, fill=255)
    bbox = mask.getbbox()
    if bbox:  # nudge so the ink is vertically centred in the box
        dy = round((y0 + h / 2) - (bbox[1] + bbox[3]) / 2)
        if dy:
            mask = ImageChops.offset(mask, 0, dy)
    return mask


# ---------------------------------------------------------------- styles

def pixels(im):
    """Pixel values as a flat sequence (Pillow 12 renamed getdata)."""
    return im.get_flattened_data() if hasattr(im, 'get_flattened_data') else im.getdata()


def transparent_indices(im):
    t = im.info.get('transparency')
    if t is None:
        return set()
    if isinstance(t, int):
        return {t}
    return {i for i, a in enumerate(t) if a < 128}


def detect_solid(im, region=None):
    """{'background', 'fill', 'outline'} if the region is one background + one or two ink colours."""
    crop = im.crop(region) if region else im
    counts = Counter(pixels(crop))
    clear = transparent_indices(im)
    bg = next((i for i, _ in counts.most_common() if i in clear), None)
    if bg is None:
        bg = counts.most_common(1)[0][0]
    ink = [i for i in counts if i != bg and i not in clear]
    if len(ink) == 0 or len(ink) > 2:
        return None
    if len(ink) == 1:
        return {'background': bg, 'fill': ink[0], 'outline': None}
    # outline = the ink colour that touches the background most
    w, h = crop.size
    px = crop.load()
    edge = Counter()
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if c in ink and any(0 <= x + dx < w and 0 <= y + dy < h and px[x + dx, y + dy] == bg
                                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                edge[c] += 1
    a, b = ink
    ra, rb = edge[a] / counts[a], edge[b] / counts[b]
    return {'background': bg, 'fill': b if ra >= rb else a, 'outline': a if ra >= rb else b}


def draw_solid(im, box, text, row, style, clear):
    mask = text_mask(im.size, box, text, row['font'], row['align'] or 'center')
    if mask is None:
        return False
    im.paste(style['background'], clear)
    if style['outline'] is not None:
        grown = mask.filter(ImageFilter.MaxFilter(3))
        im.paste(style['outline'], mask=grown.point(lambda v: 255 if v >= 128 else 0))
    im.paste(style['fill'], mask=mask.point(lambda v: 255 if v >= 128 else 0))
    return True


# ---------------------------------------------------------------- the game's lettering

# Where the game cuts each label's sprite (*verified in game*, 2026-10-15):
# - list menus (category 'menu'): each label's sprite runs from the middle of the gap above its
#   lettering to the middle of the gap below, and the texture filter shows a sprite's last row on
#   the next sprite's top edge (probe build, Match Maker company select: rows 88-95 showed in
#   ZERO-ONE, 95-105 in WJ). The English, outline included, stays inside its sprite and off its
#   last row;
# - FIXED_ATLASES: atlases whose sprites are cut to each label's own width ("Delet", "Rand",
#   "Souls Neede") - never widened; other atlases showed widened labels whole (e.g. 01668 "Chest");
# - LIST_ATLASES: atlases holding a list like a menu (labels kept on the original's rows).
FIXED_ATLASES = {'000_01474', '000_02473'}
LIST_ATLASES = {'000_02473', '000_03010'}
# atlases whose labels of one size group are all drawn at the size of the one that needed the
# smallest (as list menus are), so a label that fits doesn't stand out bigger than its neighbours
UNIFORM_ATLASES = {'000_01519', '000_01520', '000_01530', '000_01537', '000_01696', '000_01743',
                   '000_01749', '000_01750', '000_01760', '000_01761', '000_01762', '000_01763',
                   '000_02445'}
SPRITE_GAP = 1          # rows kept free (outline included) at the bottom of a list label's sprite
SQUEEZE_MIN = 0.75      # narrowest horizontal squeeze before a label is drawn smaller
CAP_RATIO = 0.92        # English cap height / Japanese lettering height
NOTES = []              # labels squeezed hard or drawn smaller - printed by run()


def _lum(p):
    return (p[0] * 3 + p[1] * 6 + p[2]) / 10


def analyse_picture(im, boxes):
    """{'kind', 'fill', 'edge', 'ink_h'} for a picture's lettering (all its label boxes together)."""
    rgba = im.convert('RGBA')
    fills, edges, heights = Counter(), Counter(), []
    bands = [Counter() for _ in range(8)]          # fill colour by relative height (gradients)
    shift = 0.0
    for x, y, w, h in boxes:
        px = list(pixels(rgba.crop((x, y, x + w, y + h))))
        white = [i for i, p in enumerate(px) if p[3] > 200 and _lum(p) > 200]
        bright = [i for i, p in enumerate(px) if p[3] > 200 and _lum(p) > 110]
        light = white if len(white) >= 0.4 * len(bright) else bright     # white, else a coloured fill
        dark = [i for i, p in enumerate(px) if p[3] > 150 and _lum(p) < 60]
        fills.update(px[i][:3] for i in light)
        edges.update(px[i][:3] for i in dark)
        if light:
            rows = [i // w for i in light]
            heights.append(max(rows) - min(rows) + 1)
            top, span = min(rows), max(rows) - min(rows) + 1
            for i in light:
                bands[min(7, (i // w - top) * 8 // span)][px[i][:3]] += 1
            if dark:
                cl = (sum(i % w for i in light) / len(light), sum(rows) / len(light))
                cd = (sum(i % w for i in dark) / len(dark), sum(i // w for i in dark) / len(dark))
                shift += (cd[0] - cl[0]) + (cd[1] - cl[1])
    if not heights:
        return None
    heights.sort()
    return {'kind': 'shadow' if shift / len(heights) > 1.2 else 'outline',
            'fill': fills.most_common(1)[0][0] if fills else (255, 255, 255),
            'edge': edges.most_common(1)[0][0] if edges else (0, 0, 0),
            'ink_h': heights[len(heights) // 2],
            'gradient': [b.most_common(1)[0][0] if b else None for b in bands]}


def family_key(row):
    return (row['width'], row['height'], row['category'])


def family_style(row, style, cache={}):
    """One lettering height for single-label pictures of a family (same size and category - the
    name plates, title plates ...), so similar labels look the same on every screen: the family's
    median height, used when within 25 % of the picture's own lettering (otherwise its own - a
    family can mix plate sizes). Kind and colours stay the picture's own. Pictures with several
    labels keep their own sizes (size_groups)."""
    key = family_key(row)
    if not cache:
        groups = {}
        for r in catalog.rows():
            if r['status'] not in ('todo', 'done') or not r['boxes'].strip() or ';' in r['boxes']:
                continue
            src = catalog.original_png(r['image'])
            if not src.exists():
                continue
            a = analyse_picture(Image.open(src), parse_boxes(r['boxes']))
            if a:
                groups.setdefault(family_key(r), []).append(a)
        for k, v in groups.items():
            hs = sorted(a['ink_h'] for a in v)
            kind = Counter(a['kind'] for a in v).most_common(1)[0][0]
            cache[k] = {'ink_h': hs[len(hs) // 2], 'kind': kind}
        cache['_'] = True
    fam = cache.get(key)
    if fam and abs(fam['ink_h'] - style['ink_h']) <= 0.25 * style['ink_h']:
        return dict(style, ink_h=fam['ink_h'])      # close to the family: share its size
    return style                                    # an outlier keeps its own lettering size


def lettered_size(fontname, ink_h, cache={}):
    """Font size whose cap height is CAP_RATIO x the original lettering height."""
    key = (fontname, ink_h)
    if key not in cache:
        size = 6
        for sz in range(80, 5, -1):
            b = load_font(fontname, sz).getbbox('H')
            if b[3] - b[1] <= ink_h * CAP_RATIO:
                size = sz
                break
        cache[key] = size
    return cache[key]


def has_glyph(font, ch, cache={}):
    key = (id(font), ch)
    if key not in cache:
        cache[key] = font.getmask(ch).getbbox() != font.getmask('\uffff').getbbox()
    return cache[key]


def draw_runs(draw, xy, text, font, fallback):
    """Draw text, taking each character the font lacks from `fallback`; returns the advance."""
    x, y = xy
    for ch in text:
        f = fallback if ord(ch) >= 0x2000 and not has_glyph(font, ch) else font
        if draw is not None:
            draw.text((x, y), ch, font=f, fill=255)
        x += f.getlength(ch)
    return x - xy[0]


def lettered_mask(text, fontname, size, width, centre_caps=True):
    """(L mask of one line of text at `size` squeezed into `width`, note or ''); None if impossible.
    The mask is the font's full line frame (cap top to descender bottom); with centre_caps the top is
    padded so the capitals sit in the middle."""
    for sz in range(size, max(5, size - 8), -1):
        font = load_font(fontname, sz)
        fallback = load_font('symbols', sz)
        m = Image.new('L', (int(draw_runs(None, (0, 0), text, font, fallback)) + 4 * sz, 3 * sz), 0)
        if all(ord(ch) < 0x2000 or has_glyph(font, ch) for ch in text):
            ImageDraw.Draw(m).text((2 * sz, sz // 2), text, font=font, fill=255)   # keeps kerning
        else:
            draw_runs(ImageDraw.Draw(m), (2 * sz, sz // 2), text, font, fallback)
        bb = m.getbbox()
        if bb is None:
            return None
        ref = font.getbbox('Hgjy')            # one vertical frame for every line: same baselines
        m = m.crop((bb[0], sz // 2 + ref[1], bb[2], sz // 2 + ref[3]))
        # centre on the capitals (cap top to baseline), not on the frame: pad the top so the cap
        # band sits in the middle and descenders hang below, as the eye reads it
        cap = font.getbbox('H')
        pad = max(0, (ref[3] - ref[1]) - (cap[3] - ref[1]) - (cap[1] - ref[1])) if centre_caps else 0
        if pad:
            padded = Image.new('L', (m.width, m.height + pad), 0)
            padded.paste(m, (0, pad))
            m = padded
        squeeze = min(1.0, width / m.width)
        if squeeze >= SQUEEZE_MIN:
            note = (f'drawn at size {sz} instead of {size} (squeezed {squeeze:.0%})' if sz < size else
                    f'squeezed to {squeeze:.0%}' if squeeze < 0.85 else '')
            if squeeze < 1:
                m = m.resize((max(1, round(m.width * squeeze)), m.height), Image.LANCZOS)
            return m, note
    return None


def auto_align(box, boxes):
    """How the original lays a label out: 'left' if more labels share its left edge (within 8 px -
    a left-aligned list) than share its centre within 6 px (centred lines - ink is not
    symmetric), else 'center'."""
    x, y, w, h = box
    lefts = sum(1 for b in boxes if b != box and abs(b[0] - x) <= 8)
    centres = sum(1 for b in boxes if b != box and abs((b[0] + b[2] / 2) - (x + w / 2)) <= 6)
    return 'left' if lefts > centres else 'center'


def column_box(box, boxes):
    """A left-aligned label's slot: from its column's left edge (the leftmost label starting within
    8 pixels - Japanese glyphs differ in side bearing) to the column's right edge (the space right
    of a short label is free in the atlas)."""
    col = [b for b in boxes if abs(b[0] - box[0]) <= 8]
    left = min(b[0] for b in col)
    right = max(b[0] + b[2] for b in col)
    for b in boxes:   # never over a label further right on the same row
        if b != box and b[0] >= box[0] + box[2] and b[1] < box[1] + box[3] and box[1] < b[1] + b[3]:
            right = min(right, b[0] - 2)
    return (left, box[1], max(box[0] + box[2], right) - left, box[3])


def box_ink_heights(im, boxes, nlines=None):
    """Lettering height of each label: the tallest run of rows holding light pixels, so a label of
    several lines is measured per line."""
    rgba = im.convert('RGBA')
    out = []
    for x, y, w, h in boxes:
        px = list(pixels(rgba.crop((x, y, x + w, y + h))))
        white = {i // w for i, p in enumerate(px) if p[3] > 200 and _lum(p) > 200}
        bright = {i // w for i, p in enumerate(px) if p[3] > 200 and _lum(p) > 110}
        rows = sorted(white if len(white) >= 0.6 * len(bright) else bright)
        best = run = 0
        for i, r in enumerate(rows):
            run = run + 1 if i and r <= rows[i - 1] + 2 else 1
            best = max(best, run + (r - rows[i - 1] - 1 if i and run > 1 else 0))
        n = nlines[len(out)] if nlines else 1
        out.append(min(best or h, h / n * 0.85) if n > 1 else (best or h))   # lines may touch
    return out


def size_groups(heights, slots):
    """Labels of a picture grouped by slot (box) height, within 50 % (capitals-only labels have
    shorter slots than kana/kanji at the same size; real size tiers differ ~2x); each group gets the median
    lettering height of its labels, so a picture with small and large labels keeps two consistent
    sizes."""
    order = sorted(range(len(heights)), key=lambda i: slots[i])
    groups, cur = [], []
    for i in order:
        if cur and slots[i] > slots[cur[0]] * 1.5:
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    out = [0] * len(heights)
    for g in groups:
        hs = sorted(heights[i] for i in g)
        for i in g:
            out[i] = hs[len(hs) // 2]
    return out


def centre_column_box(box, boxes):
    """A label in a centred column (other labels share its centre) may use the column's widest
    label's width, kept clear of labels beside it on the same row."""
    x, y, w, h = box
    c = x + w / 2
    col = [b for b in boxes if abs((b[0] + b[2] / 2) - c) <= 3]
    if len(col) < 2:
        return box
    half = max(b[2] for b in col) / 2
    for b in boxes:
        if b != box and b[1] < y + h and y < b[1] + b[3]:
            if b[0] >= x + w:
                half = min(half, b[0] - 2 - c)
            elif b[0] + b[2] <= x:
                half = min(half, c - (b[0] + b[2]) - 2)
    half = max(half, w / 2)
    return (round(c - half), y, round(2 * half), h)


def list_pitch(extents):
    """Row pitch of a list (the median step between the tops of its labels' lettering), or None."""
    tops = sorted(e[0] for e in extents if e)
    steps = sorted(b - a for a, b in zip(tops, tops[1:]) if b > a)
    return steps[len(steps) // 2] if steps else None


def sprite_start(bottom, top, pitch):
    """First row of the sprite of a label whose lettering starts at `top`, below a label ending at
    `bottom`: the first multiple of the list's pitch after `bottom` (the game cuts list sprites
    on a fixed grid - *verified in game*: 24-row Match Maker company list, cut at 72 between
    lettering at 71 and 76), else the middle of the gap."""
    if pitch:
        k = -(-(bottom + 1) // pitch) * pitch
        if k <= top:
            return k
    return (bottom + top) // 2


def ink_rows(im, box, outline=False):
    """(top, bottom) picture rows of the lettering in a box of the original (with its outline if
    `outline`), or None."""
    x, y, w, h = box
    rgba = im.convert('RGBA')
    px = list(pixels(rgba.crop((x, y, x + w, y + h))))
    rows = sorted({i // w for i, p in enumerate(px) if (p[3] > 40 if outline else p[3] > 200 and _lum(p) > 110)})
    return (y + rows[0], y + rows[-1]) if rows else None


def grow_vertically(box, boxes, height, room=3):
    """Up to `room` pixels above and below for descenders/accents, where no other label is."""
    x, y, w, h = box
    up = down = room
    for b in boxes:
        if b != box and b[0] < x + w and x < b[0] + b[2]:
            if b[1] + b[3] <= y:
                up = min(up, y - (b[1] + b[3]) - 1)
            elif b[1] >= y + h:
                down = min(down, b[1] - (y + h) - 1)
    up, down = max(0, min(up, y)), max(0, min(down, height - y - h))
    return (x, y - up, w, h + up + down)


def centre_box(box, boxes, width):
    """A label centred on the picture's middle with nothing else on its row (a centred list such as
    the help lines) may widen symmetrically to the picture width, keeping a margin."""
    x, y, w, h = box
    if abs((x + w / 2) - width / 2) > 3:
        return box
    if any(b != box and b[1] < y + h and y < b[1] + b[3] for b in boxes):
        return box
    m = max(4, width // 32)
    return (m, y, width - 2 * m, h) if width - 2 * m > w else box


def draw_lettered(out, box, text, row, style, clear, align=None, ink=None, size_cap=None):
    """ink: (top, bottom, lo, hi) - rows of the original label's lettering, and the rows the
    English lettering may use (list menus: the game filters textures, so ink next to the boundary
    with the next label's sprite shows on its edge, *verified in game*). Centred on the original's
    rows within lo..hi, drawn smaller only if it doesn't fit. size_cap: largest size to use.
    Returns the size drawn at (True for '=' and empty labels), False if it doesn't fit."""
    x0, y0, w, h = box
    if text == '=':                     # '=': the label stays as it is (digits, button names, ...)
        return True
    cx0, cy0, cx1, cy1 = (min(x0, clear[0]), min(y0, clear[1]), max(x0 + w, clear[0] + clear[2]),
                          max(y0 + h, clear[1] + clear[3])) if clear else (x0, y0, x0 + w, y0 + h)
    if not text:                        # an empty English item: the label is just cleared
        out.paste(clear_index(out), (cx0, cy0, cx1, cy1))
        return True
    plate = style.get('single') and row.get('category') in ('label', 'title')   # slanted plates only
    fontname = row['font'] or ('plate' if plate else 'default')
    size = lettered_size(fontname, style['ink_h'])
    if size_cap:
        size = min(size, size_cap)
    small = style['ink_h'] < 16             # small legends have a 1-pixel outline
    pad = (1 if small else 2) if style['kind'] == 'outline' else 0
    off = 3 if style['kind'] == 'shadow' else 0
    side = pad + (max(4, w // 32) if (w, h) == out.size else 0)   # whole-picture label: side margin
    lines = [ln.strip() for ln in text.split(' / ')]
    for sz in range(size, max(5, size // 2), -1):       # smaller only if the lines are too tall
        got = [lettered_mask(ln, fontname, sz, w - 2 * side - off, centre_caps=ink is None) for ln in lines]
        masks = [g[0] if g else None for g in got]
        if any(m is None for m in masks):
            return False
        lh = max(m.height for m in masks)
        gap = max(1, lh // 4)
        total = lh * len(masks) + gap * (len(masks) - 1)
        if ink is None:
            fits = total <= h - 2 * pad - off + 2
        else:                               # list menus: only the letters' own rows count
            rows = [m.getbbox() for m in masks]
            act = (min(b[1] for b in rows if b), (len(masks) - 1) * (lh + gap) + max(b[3] for b in rows if b))
            fits = act[1] - act[0] <= ink[3] - ink[2] + 1
        if fits:
            if sz < size:
                NOTES.append(f'{row["image"]}: "{text}" drawn at size {sz} instead of {size} (too tall)')
            NOTES.extend(f'{row["image"]}: "{ln}" {g[1]}' for ln, g in zip(lines, got) if g[1])
            break
    else:
        return False
    canvas = Image.new('L', (w, h), 0)
    top = (h - off - total) // 2
    if ink is not None:                 # on the original lettering's rows
        top = ink[0] + (ink[1] - ink[0] + 1 - total) // 2          # frame centred on the original's rows,
        top = max(ink[2] - act[0], min(ink[3] + 1 - act[1], top)) - y0   # letters within the allowed rows
    align = row['align'] or align or 'center'
    for i, m in enumerate(masks):
        free = w - off - m.width
        x = {'left': side, 'right': free - side}.get(align, free // 2)
        canvas.paste(m, (x, top + i * (lh + gap) + (lh - m.height)))
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    if style['kind'] == 'outline':
        edge = canvas.point(lambda v: 255 if v > 60 else v * 4).filter(ImageFilter.MaxFilter(3 if small else 5)) \
                     .filter(ImageFilter.GaussianBlur(0.4))
    else:
        edge = ImageChops.offset(canvas, off, off).filter(ImageFilter.GaussianBlur(1.6)).point(lambda v: int(v * 0.85))
    layer.alpha_composite(Image.merge('RGBA', [Image.new('L', (w, h), c) for c in style['edge']] + [edge]))
    fill = Image.new('RGB', (w, h), style['fill'])
    grad = [c for c in style.get('gradient') or [] if c]
    if len(grad) == 8 and len(set(grad)) > 1:      # the original's fill changes top to bottom
        bbox = canvas.getbbox() or (0, 0, w, h)
        d = ImageDraw.Draw(fill)
        for yy in range(h):
            k = min(7, max(0, (yy - bbox[1]) * 8 // max(1, bbox[3] - bbox[1])))
            d.line([(0, yy), (w, yy)], fill=grad[k])
    layer.alpha_composite(Image.merge('RGBA', list(fill.split()) + [canvas]))
    out.paste(clear_index(out), (cx0, cy0, cx1, cy1))   # the original label and the new one
    snap_into(out, layer, (x0, y0))
    return sz


def clear_index(im):
    """The picture's background: its most common palette index (set once per picture by render())."""
    if 'background' not in im.info:
        im.info['background'] = Counter(pixels(im)).most_common(1)[0][0]
    return im.info['background']


def snap_into(im, rgba, at):
    """Write an RGBA layer into an indexed image, each pixel as the nearest palette colour
    (compared premultiplied, so transparent colours match by alpha)."""
    pal = im.getpalette()[:768]
    t = im.info.get('transparency', b'')
    n = len(pal) // 3
    alpha = [t[i] if isinstance(t, (bytes, bytearray)) and i < len(t) else 255 for i in range(n)]
    entries = [(pal[3 * i] * alpha[i] / 255, pal[3 * i + 1] * alpha[i] / 255, pal[3 * i + 2] * alpha[i] / 255,
                alpha[i]) for i in range(n)]
    cache = {}
    src, dst = rgba.load(), im.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            p = src[x, y]
            if p not in cache:
                r, g, b, a = p
                q = (r * a / 255, g * a / 255, b * a / 255, a)
                cache[p] = min(range(n), key=lambda i: (q[0] - entries[i][0]) ** 2 + (q[1] - entries[i][1]) ** 2
                               + (q[2] - entries[i][2]) ** 2 + (q[3] - entries[i][3]) ** 2)
            dst[at[0] + x, at[1] + y] = cache[p]


# (name, detect(im, region) -> style or None, draw(out, box, text, row, style, clear) -> fits)
STYLES = [('solid', detect_solid, draw_solid)]


def parse_boxes(s):
    return [tuple(int(v) for v in b.split(',')) for b in s.split(';') if b.strip()]


def render(row):
    """The English image for a row, or (None, reason)."""
    if row['font'] == 'hand':
        return None, 'marked for a hand edit (font = hand) - see docs/EDITING.md'

    src = catalog.original_png(row['image'])
    if not src.exists():
        return None, f'no original image {paths.show(src)} (run tools/extract.py)'
    im = Image.open(src)
    if im.mode != 'P':
        return None, f'original is {im.mode}, expected an indexed PNG'
    im.load()
    out = im.copy()
    out.info = dict(im.info)
    out.info.pop('background', None)
    out.info['background'] = Counter(pixels(im)).most_common(1)[0][0]
    if row['boxes'].strip():
        boxes = parse_boxes(row['boxes'])
        texts = [t.strip() for t in row['english'].split(' | ')]
        if len(texts) != len(boxes):
            return None, f'{len(boxes)} boxes but {len(texts)} english items (separate them with " | ")'
    else:
        boxes = [(MARGIN, MARGIN, im.width - 2 * MARGIN, im.height - 2 * MARGIN)]
        texts = [row['english'].strip()]
    if row['font'] != 'solid':
        style = analyse_picture(im, boxes)
        if style is None:
            return None, 'no white lettering found in the boxes (hand edit it, or use font solid)'
        style['single'] = len(boxes) == 1
        if len(boxes) == 1:
            style = family_style(row, style)
        nlines = [len(t.split(' / ')) for t in row['japanese'].split(' | ')] if row.get('japanese') else [1] * len(boxes)
        nlines = nlines if len(nlines) == len(boxes) else [1] * len(boxes)
        groups = size_groups(box_ink_heights(im, boxes, nlines), [b[3] / n for b, n in zip(boxes, nlines)]) if len(boxes) > 1 else None
        if len(boxes) == 1 and nlines[0] > 1:     # one label of several lines: size from one line
            style = dict(style, ink_h=min(style['ink_h'], boxes[0][3] / nlines[0] * 0.85))
        hints = [a.strip() for a in row['align'].split(' | ')] if ' | ' in row['align'] else None
        inks = [ink_rows(im, b) for b in boxes]
        outs = [ink_rows(im, b, outline=True) for b in boxes]
        listed = len(boxes) > 1 and (row.get('category') == 'menu' or row['image'] in LIST_ATLASES)
        caps = {}
        for attempt in ((1, 2) if listed or row['image'] in UNIFORM_ATLASES else (2,)):
            # list menus: a first pass finds the size each label needs; the second draws every label
            # of a size group at the smallest of them, so the labels of a list match
            sizes = {}
            target = out.copy() if attempt == 1 else out
            target.info = dict(out.info)
            mark = len(NOTES)
            for n, (box, text) in enumerate(zip(boxes, texts)):
                original = box
                if groups:                               # each label's size group (line height)
                    style = dict(style, ink_h=groups[n])
                hint = hints[n] if hints and n < len(hints) else ('' if hints else row['align'])
                align, inset = (hint.split('+') + ['0'])[:2] if hint else (auto_align(box, boxes), '0')
                fixed = row['image'] in FIXED_ATLASES   # sprites cut to each label: no wider
                if fixed:
                    pass
                elif align == 'left' and (not hint or hints):
                    box = column_box(box, boxes)
                elif align == 'center' and (not hint or hints) and len(boxes) > 1:
                    wide = centre_box(box, boxes, im.width)
                    box = wide if wide != box else centre_column_box(box, boxes)
                if len(boxes) > 1:
                    box = grow_vertically(box, boxes, im.height)
                if int(inset):
                    box = (box[0] + int(inset), box[1], box[2] - int(inset), box[3])
                ink = inks[n] if listed else None
                if ink and outs[n]:                      # the rows the English may use: SPRITE_GAP rows
                    same = [k for k, b in enumerate(boxes)    # clear of the boundary with the labels above/below
                            if k != n and outs[k] and b[0] < original[0] + original[2] and original[0] < b[0] + b[2]]
                    above = [outs[k][1] for k in same if outs[k][1] < outs[n][0]]
                    below = [outs[k][0] for k in same if outs[k][0] > outs[n][1]]
                    edge = 2 if style['ink_h'] >= 16 else 1          # the outline around the bright ink
                    # sprites are cut on the list's row grid; a sprite's last row also shows on the
                    # next sprite's top edge
                    pitch = list_pitch([outs[k] for k in same + [n]])
                    lo = sprite_start(max(above), outs[n][0], pitch) + edge if above else box[1] + edge
                    hi = sprite_start(outs[n][1], min(below), pitch) - 1 - SPRITE_GAP - edge if below else box[1] + box[3] - 1 - edge
                    ink = (ink[0], ink[1], lo, hi)
                else:
                    ink = None
                key = groups[n] if groups else 0
                sz = draw_lettered(target, box, text, dict(row, align=align), style, original, align, ink, caps.get(key))
                if not sz:
                    return None, f'"{text}" does not fit {box[2]}x{box[3]} even at a smaller size - shorten it'
                if sz is not True:
                    sizes.setdefault(key, []).append(sz)
            if attempt == 1:
                del NOTES[mark:]
                caps = {k: min(v) for k, v in sizes.items()}
        return out, None
    for box, text in zip(boxes, texts):
        region = (box[0], box[1], box[0] + box[2], box[1] + box[3]) if row['boxes'].strip() else None
        for name, detect, draw in STYLES:
            style = detect(im, region)
            if style is not None:
                if not draw(out, box, text, row, style, region or (0, 0, im.width, im.height)):
                    return None, f'"{text}" does not fit {box[2]}x{box[3]}'
                break
        else:
            return None, 'no style matches the art (hand edit it, or add a style to STYLES)'
    return out, None


def save(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    kw = {'transparency': im.info['transparency']} if 'transparency' in im.info else {}
    im.save(path, optimize=False, **kw)


def regen_preview(name, before, after):
    orig = Image.open(catalog.original_png(name)).convert('RGBA')
    tiles = [orig, Image.open(before).convert('RGBA') if before else orig, after]
    w, h = orig.size
    sheet = Image.new('RGBA', (w * 3 + 8, h), (255, 0, 255, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * (w + 4), 0), t)
    paths.EDIT_REFS.mkdir(parents=True, exist_ok=True)
    out = paths.EDIT_REFS / f'{name}_regen.png'
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(out)
    return out


def run(names=None, everything=False, regen=()):
    table = catalog.rows()
    by_id = catalog.by_id(table)
    version = catalog.renderer_version()
    done = catalog.load_renders()
    drawn, problems = [], []

    for name in regen:
        r = by_id.get(name)
        if r is None:
            sys.exit(f'{name}: not in {paths.show(paths.GRAPHICS_CSV)}')
        im, why = render(r)
        if im is None:
            problems.append((name, why))
            continue
        target = (paths.APPROVED if r['status'] == 'done' else paths.RENDERED) / f'{name}.png'
        before = paths.show(target) if target.exists() else None
        preview = regen_preview(name, target if target.exists() else None, im.convert('RGBA'))
        save(im, target)
        if r['status'] != 'done':
            done[name] = {'fp': catalog.fingerprint(r, version)}
        print(f'regenerated {name} -> {paths.show(target)} (was {before or "the original"}); {paths.show(preview)}')

    wanted = [r for r in table if catalog.wants_render(r)]
    if names is not None:
        wanted = [r for r in wanted if r['image'] in set(names)]
    for r in wanted:
        if r['image'] in regen:
            continue
        fp = catalog.fingerprint(r, version)
        rec = done.get(r['image'], {})
        out = paths.RENDERED / f"{r['image']}.png"
        if not everything and rec.get('fp') == fp and (rec.get('unsupported') or out.exists()):
            continue
        im, why = render(r)
        if im is None:
            done[r['image']] = {'fp': fp, 'unsupported': why}
            out.unlink(missing_ok=True)
            problems.append((r['image'], why))
            continue
        save(im, out)
        done[r['image']] = {'fp': fp}
        drawn.append(r['image'])

    # forget renders of rows the renderer is no longer responsible for (approved, keep, emptied)
    responsible = {r['image'] for r in table if catalog.wants_render(r)}
    for name in list(done):
        if name not in responsible:
            del done[name]
    if paths.RENDERED.exists():
        for p in paths.RENDERED.glob('*.png'):
            if p.stem not in responsible:
                p.unlink()
    catalog.save_renders(done)

    if drawn:
        print(f'rendered {len(drawn)}: ' + ' '.join(drawn[:20]) + (' ...' if len(drawn) > 20 else ''))
    for name, why in problems:
        print(f'  ! {name}: {why}')
    for note in NOTES:
        print(f'  ~ {note}')
    if not drawn and not problems and not regen:
        print('renders are up to date')
    return drawn, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('images', nargs='*', help='only these images (ids, ranges or patterns)')
    ap.add_argument('--all', action='store_true', help='redraw every row, not just the out-of-date ones')
    ap.add_argument('--regen', nargs='+', default=[], metavar='IMAGE', help='redraw these on purpose, even approved ones')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    names = catalog.expand(args.images) if args.images else None
    run(names, args.all, catalog.expand(args.regen) if args.regen else ())


if __name__ == '__main__':
    main()
