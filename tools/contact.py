#!/usr/bin/env python3
"""Contact sheets of every original image, labelled with its id (needs Pillow).

  contact.py [--filter TEXT] [--scale 1] [--catalogued | --uncatalogued]
      -> review/contact-sheets/sheet_NNN.png + index.csv (id, size, sheet, x, y)

Reads review/images-original/ (written by tools/extract.py through gfx.export_all). Use the
sheets to find images with text and add them to graphics.csv (Claude can read the sheets to
transcribe them in batches). --uncatalogued shows only images not yet in graphics.csv.
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import paths  # noqa: E402
from compare import crop, tile  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--filter', default='', help='only ids containing this')
    ap.add_argument('--scale', type=int, default=1)
    ap.add_argument('--width', type=int, default=1600)
    ap.add_argument('--height', type=int, default=1600)
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--catalogued', action='store_true', help='only images in graphics.csv')
    g.add_argument('--uncatalogued', action='store_true', help='only images not in graphics.csv')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))

    if not paths.ORIGINAL_IMAGES.exists():
        sys.exit(f'{paths.show(paths.ORIGINAL_IMAGES)} is empty - run tools/extract.py first')
    known = set(catalog.by_id())
    names = sorted(p.stem for p in paths.ORIGINAL_IMAGES.glob('*.png'))
    names = [n for n in names if args.filter in n
             and (not args.catalogued or n in known) and (not args.uncatalogued or n not in known)]
    out = paths.CONTACT_SHEETS
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    gap, label = 8, 14
    index, sheet_no, cur, x, y, rowh = [], 0, None, gap, gap, 0
    for n in names:
        im = Image.open(paths.ORIGINAL_IMAGES / f'{n}.png')
        t = tile(im, args.scale)
        w, h = min(t.width, args.width - 2 * gap), min(t.height, args.height - 2 * gap - label)
        if cur is None:
            cur = Image.new('RGBA', (args.width, args.height), (30, 30, 36, 255))
        if x + max(w, 60) + gap > args.width and x > gap:
            x, y, rowh = gap, y + rowh + label + gap, 0
        if y + h + label + gap > args.height and y > gap:
            crop(cur, (30, 30, 36, 255)).save(out / f'sheet_{sheet_no:03d}.png')
            sheet_no += 1
            cur, x, y, rowh = Image.new('RGBA', (args.width, args.height), (30, 30, 36, 255)), gap, gap, 0
        ImageDraw.Draw(cur).text((x, y), n, fill=(255, 255, 0, 255))
        cur.paste(t.crop((0, 0, w, h)), (x, y + label))
        index.append((n, f'{im.width}x{im.height}', f'sheet_{sheet_no:03d}', x, y))
        x += max(w, 60) + gap
        rowh = max(rowh, h)
    if cur is not None:
        crop(cur, (30, 30, 36, 255)).save(out / f'sheet_{sheet_no:03d}.png')
        sheet_no += 1
    with open(out / 'index.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['image', 'size', 'sheet', 'x', 'y'])
        w.writerows(index)
    print(f'{len(names)} images on {sheet_no} sheet(s) in {paths.show(out)}')


if __name__ == '__main__':
    main()
