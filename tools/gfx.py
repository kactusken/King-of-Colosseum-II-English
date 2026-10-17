#!/usr/bin/env python3
"""Game images: export every original and import the English ones.

  gfx.py export                 every image -> review/images-original/ (what extract.py does)
  gfx.py id <id>                where an image lives
  gfx.py verify [--every N]     PNG -> picture write-back gives the original bytes (every Nth entry)

Images are the TIM2 pictures in KC2FIRE.000 (menus, labels, text windows, ...): whole entries
and TIM2s embedded in other entries. KC2FIRE.001 holds wrestler and ring textures - out of scope
(art stays as designed) and not exported.

Image ids: `000_NNNNN` = entry NNNNN of KC2FIRE.000, first TIM2, first picture; `_tK` = the K-th
TIM2 found in the entry (counting from 0, in file order), `_pK` = its K-th picture. Ids come
from where the picture lives, so they are stable and the build needs nothing else to find it.

export_all(extracted, out) -> count
    out/<id>.png: indexed PNG in the picture's own palette (transparent colours as tRNS alpha),
    out/<id>.json: source, entry, TIM2 offset, picture, size, bpp, swizzled.
import_images(images, files) -> count
    images: {id: indexed PNG}; the PNG must have the picture's size and only use its palette's
    indices. Written back through tim2.put_indices (swizzled pictures re-swizzled) into the
    entry, which the build repacks (build.py Packs).

Standard library only (the build imports this).
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
import pngio  # noqa: E402
import tim2  # noqa: E402

PACK = '/DATA/KC2FIRE.000'
PACK_DIR = 'KC2FIRE_000'
ID = re.compile(r'^000_(\d{5})(?:_t(\d+))?(?:_p(\d+))?$')


def make_id(entry, t, p):
    return f'000_{entry:05d}' + (f'_t{t}' if t else '') + (f'_p{p}' if p else '')


def parse_id(ident):
    m = ID.match(ident)
    if not m:
        sys.exit(f'image id {ident!r}: expected 000_NNNNN[_tK][_pK]')
    return int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)


def pictures(data):
    """[(t, offset, picture index, Picture)] for every indexed picture in an entry's bytes."""
    out = []
    for t, off in enumerate(tim2.find(data)):
        try:
            pics = tim2.parse(data, off)
        except (ValueError, struct.error):
            continue
        for p, pic in enumerate(pics):
            if pic.palette and pic.width and pic.height and pic.pixels_at + pic.image_size <= len(data):
                out.append((t, off, p, pic))
    return out



def export_all(extracted, out):
    src = Path(extracted) / 'DATA' / PACK_DIR
    manifest = src / 'pak.json'
    if not manifest.exists():
        return 0
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for k, e in enumerate(json.loads(manifest.read_text())['entries']):
        f = src / e['file']
        data = f.read_bytes()
        if b'TIM2' not in data:
            continue
        for t, off, p, pic in pictures(data):
            ident = make_id(k, t, p)
            try:
                tim2.to_png(data, pic, out / f'{ident}.png')
            except ValueError as err:
                print(f'  {ident}: skipped - {err}')
                continue
            (out / f'{ident}.json').write_text(json.dumps({
                'source': PACK, 'entry': k, 'tim2': t, 'offset': off, 'picture': p,
                'width': pic.width, 'height': pic.height, 'bpp': pic.bpp, 'swizzled': pic.swizzled,
                'colours': len(pic.palette)}) + '\n')
            n += 1
    return n


def import_images(images, files):
    n = 0
    for ident, path in sorted(images.items()):
        entry, t, p = parse_id(ident)
        data = bytearray(files.packs.get(PACK, entry))
        found = [x for x in pictures(data) if x[0] == t and x[2] == p]
        if not found:
            sys.exit(f'{ident}: no such picture in KC2FIRE.000 entry {entry}')
        _, _, _, pic = found[0]
        png = pngio.read(path)
        if (png.width, png.height) != (pic.width, pic.height):
            sys.exit(f'{path}: {png.width}x{png.height}, the original is {pic.width}x{pic.height}')
        if not png.indexed:
            sys.exit(f'{path}: not an indexed PNG - approve it with tools/edit.py to snap it to the palette')
        top = len(pic.palette)
        if any(v >= top for r in png.rows for v in r):
            sys.exit(f'{path}: uses palette indices >= {top} - the picture has {top} colours')
        tim2.put_indices(data, pic, png.rows)
        files.packs.put(PACK, entry, data)
        n += 1
    return n


def verify(every=1):
    """Every exported PNG of every Nth entry, written back into a copy of its entry, must give the
    original bytes (proves import for plain and swizzled 4/8bpp pictures)."""
    src = paths.EXTRACTED / 'DATA' / PACK_DIR
    if not (src / 'pak.json').exists() or not paths.ORIGINAL_IMAGES.exists():
        sys.exit('run tools/extract.py first (it unpacks the packs and exports the images)')
    entries = json.loads((src / 'pak.json').read_text())['entries']
    tested = bad = 0
    for k, e in enumerate(entries):
        if k % every:
            continue
        data = (src / e['file']).read_bytes()
        if b'TIM2' not in data:
            continue
        copy = bytearray(data)
        for t, off, p, pic in pictures(copy):
            png = paths.ORIGINAL_IMAGES / f'{make_id(k, t, p)}.png'
            if not png.exists():
                continue
            tim2.put_indices(copy, pic, pngio.read(png).rows)
            tested += 1
        if bytes(copy) != data:
            bad += 1
            print(f'    entry {k}: write-back differs from the original')
    print(f'{tested} pictures written back: ' + ('identical' if not bad else f'{bad} entries DIFFER'))
    return not bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('export')
    s = sub.add_parser('id'); s.add_argument('id')
    s = sub.add_parser('verify'); s.add_argument('--every', type=int, default=1)
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'export':
        print(f'{export_all(paths.EXTRACTED, paths.ORIGINAL_IMAGES)} images -> {paths.show(paths.ORIGINAL_IMAGES)}')
    elif args.cmd == 'verify':
        return 0 if verify(args.every) else 1
    else:
        entry, t, p = parse_id(args.id)
        print(f'KC2FIRE.000 entry {entry}, TIM2 #{t} in it, picture {p}')


if __name__ == '__main__':
    sys.exit(main())
