#!/usr/bin/env python3
"""Side-by-side sheets: original | the English version the build will use (needs Pillow).

  compare.py [--filter TEXT] [--category CAT] [--status S] [--keep] [--scale 2]
      -> review/compare/compare_NNN.png (filtered runs: review/compare/filtered/)

Each pair is labelled with its id and where the English side comes from:
  HAND  translation/images-handmade/    DONE  translation/images-approved/
  AUTO  automatic render                TODO  nothing yet (original shown twice)
  KEEP  stays original (only with --keep)
Run tools/render.py first if renders are out of date (this tool says so).
"""
import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import paths  # noqa: E402

COLOURS = {'HAND': (120, 255, 120), 'DONE': (255, 255, 255), 'AUTO': (200, 220, 255),
           'TODO': (255, 140, 120), 'KEEP': (150, 150, 150)}
CHECKER = ((70, 70, 78), (90, 90, 98))


def checker(w, h, cell=4):
    im = Image.new('RGBA', (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = CHECKER[(x // cell + y // cell) % 2] + (255,)
    return im


def crop(sheet, bg=(40, 40, 48, 255), gap=10):
    """The sheet cut down to what's drawn on it."""
    box = ImageChops.difference(sheet, Image.new('RGBA', sheet.size, bg)).getbbox()
    return sheet.crop((0, 0, min(sheet.width, box[2] + gap), min(sheet.height, box[3] + gap))) if box else sheet


def tile(img, scale):
    img = img.convert('RGBA')
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    bg = checker(img.width, img.height)
    bg.alpha_composite(img)
    return bg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--filter', default='', help='only images whose id/original/English contains this')
    ap.add_argument('--category', default='')
    ap.add_argument('--status', default='', help='only rows with this status (todo, done, ...)')
    ap.add_argument('--keep', action='store_true', help='also show images that stay original')
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--width', type=int, default=1600)
    ap.add_argument('--height', type=int, default=1800)
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))

    missing, changed, _ = catalog.stale()
    if missing or changed:
        print(f'note: {len(missing) + len(changed)} automatic renders are out of date - run tools/render.py')
    table = catalog.rows()
    by_id = catalog.by_id(table)
    items = []
    for r in table:
        if r['dup_of'] or (r['status'] == 'keep' and not args.keep):
            continue
        if args.category and r['category'] != args.category or args.status and r['status'] != args.status:
            continue
        if args.filter and args.filter.lower() not in ' '.join((r['image'], r['japanese'], r['english'])).lower():
            continue
        src = catalog.original_png(r['image'])
        if not src.exists():
            continue
        tag, p = catalog.source(r, by_id)
        tag = 'KEEP' if r['status'] == 'keep' else tag or 'TODO'
        items.append((r['image'], tag, Image.open(src), Image.open(p) if p else Image.open(src)))

    out = paths.COMPARE / 'filtered' if (args.filter or args.category or args.status) else paths.COMPARE
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    s, gap, label = args.scale, 10, 14
    sheets, cur, x, y, rowh = [], None, gap, gap, 0
    # never crop a pair: a sheet is at least as large as its widest / tallest pair
    width = max([args.width] + [2 * jp.width * s + 6 + 2 * gap for _, _, jp, _ in items])
    height = max([args.height] + [jp.height * s + label + 2 * gap for _, _, jp, _ in items])

    def new_sheet():
        return Image.new('RGBA', (width, height), (40, 40, 48, 255))
    for name, tag, jp, en in items:
        w, h = jp.width * s, jp.height * s
        tw = 2 * w + 6
        if cur is None:
            cur = new_sheet()
        if x + tw + gap > width and x > gap:
            x, y, rowh = gap, y + rowh + label + gap, 0
        if y + h + label + gap > height and y > gap:
            sheets.append(cur)
            cur, x, y, rowh = new_sheet(), gap, gap, 0
        d = ImageDraw.Draw(cur)
        d.text((x, y), f'{name} {tag}', fill=COLOURS[tag] + (255,))
        cur.paste(tile(jp, s), (x, y + label))
        cur.paste(tile(en, s), (x + w + 6, y + label))
        x += tw + gap
        rowh = max(rowh, h)
    if cur is not None:
        sheets.append(cur)
    for i, sh in enumerate(sheets):
        crop(sh).save(out / f'compare_{i:03d}.png')
    print(f'{len(items)} images on {len(sheets)} sheet(s) in {paths.show(out)}')


if __name__ == '__main__':
    main()
