#!/usr/bin/env python3
"""Hand-edit the game's text images (needs Pillow: run with .venv/bin/python). See docs/EDITING.md.

  edit.py list [text]          find images in graphics.csv (by id, original or English text)
  edit.py start <image>...     put <image>.png (the current English version - edit this) and
                               <image>_original.png (reference) in translation/images-handmade/
  edit.py refs <image>...      only write references to review/edit/: _original, _english, _palette
  edit.py check <image>...     validate the edit; writes <image>_check.png (original above, yours below)
  edit.py approve <image>... [--force]
                               final: check, snap to the game's palette, move to
                               translation/images-approved/, mark done in graphics.csv, clean up.
                               With no hand edit, approves the automatic render as it is.
  edit.py reset <image>...     undo: remove the hand edit and/or approved file and go back to the
                               automatic render (or the original); the row goes back to todo
  edit.py sheet start <sheet> <image>...   edit several images as one sheet (original | English pairs)
  edit.py sheet check <sheet>              preview the changed pieces after palette snapping
  edit.py sheet split <sheet> [--force]    write changed pieces to translation/images-handmade/
  edit.py sheet approve <sheet>            split, approve every changed piece, remove the sheet
  edit.py sheet list

Images: ids, comma lists, ranges (0017_020-0017_052, 0017_020..0017_052, 0017_020-052) or
patterns (0013_*). Ranges and patterns leave out duplicates (they follow their original).

Rules for an edited PNG: same size as the original; indexed with the original palette is best,
RGB/RGBA also works and is snapped to the palette on approve; transparent stays transparent.
On sheets, magenta (255,0,255) means transparent. Reference files (_original, _check, _palette,
_english) are ignored by the build.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import paths  # noqa: E402

KEY = (255, 0, 255)          # transparent on sheets and previews
SHEET_GAP, SHEET_LABEL, SHEET_MID, SHEET_MAX_W = 8, 12, 4, 1024
SHEET_BG = (40, 40, 48, 255)


# ---------------------------------------------------------------- palette helpers

def original(name):
    p = catalog.original_png(name)
    if not p.exists():
        sys.exit(f'{paths.show(p)} not found (run tools/extract.py so {paths.show(paths.ORIGINAL_IMAGES)} is filled)')
    return Image.open(p)


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


def palette(im):
    pal = im.getpalette() or []
    return [tuple(pal[i:i + 3]) for i in range(0, len(pal), 3)]


def snap(rgba, orig):
    """An RGBA image converted to orig's palette: nearest colour, alpha < 128 -> transparent index."""
    pal, clear = palette(orig), transparent_indices(orig)
    t = min(clear) if clear else None
    choices = [(i, c) for i, c in enumerate(pal) if i not in clear]
    cache, out, lost = {}, [], 0
    for p in pixels(rgba.convert('RGBA')):
        if p[3] < 128:
            if t is None:
                lost += 1
                p = (0, 0, 0, 255)
            else:
                out.append(t)
                continue
        c = p[:3]
        if c not in cache:
            cache[c] = min(choices, key=lambda ic: sum((a - b) ** 2 for a, b in zip(ic[1], c)))[0]
        out.append(cache[c])
    im = Image.new('P', rgba.size)
    im.putpalette([v for c in pal for v in c])
    im.putdata(out)
    if 'transparency' in orig.info:
        im.info['transparency'] = orig.info['transparency']
    if lost:
        print(f'  note: {lost} transparent pixels, but the original has no transparent colour - made opaque')
    return im


def save_indexed(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    kw = {'transparency': im.info['transparency']} if 'transparency' in im.info else {}
    im.save(path, **kw)


def same_palette(a, b):
    return a.mode == b.mode == 'P' and palette(a) == palette(b)


def current_english(name):
    table = catalog.by_id()
    tag, p = catalog.source(table[name], table) if name in table else catalog.own_source(name)
    return p


def remove_handmade(name):
    removed = []
    for s in ('',) + catalog.REF_SUFFIXES:
        f = paths.HANDMADE / f'{name}{s}.png'
        if f.exists():
            f.unlink()
            removed.append(f.name)
    return removed


def dups_of(name, table=None):
    return [r['image'] for r in (table or catalog.rows()) if r['dup_of'] == name]


# ---------------------------------------------------------------- single images

def find(text=''):
    for r in catalog.rows():
        if r['dup_of']:
            continue
        if text.lower() in ' '.join((r['image'], r['japanese'], r['english'])).lower():
            print(f"{r['image']:14} [{r['status']:4}] {r['japanese'][:30]} | {r['english'][:50]}")


def refs(name):
    orig = original(name)
    paths.EDIT_REFS.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(catalog.original_png(name), paths.EDIT_REFS / f'{name}_original.png')
    en = current_english(name)
    if en:
        shutil.copyfile(en, paths.EDIT_REFS / f'{name}_english.png')
    pal = palette(orig)
    sw = Image.new('RGB', (len(pal) * 12, 12))
    for i, c in enumerate(pal):
        sw.paste(c, (i * 12, 0, i * 12 + 12, 12))
    sw.save(paths.EDIT_REFS / f'{name}_palette.png')
    print(f'  references in {paths.show(paths.EDIT_REFS)}: {name}_original.png'
          + (f', {name}_english.png (from {paths.show(en.parent)})' if en else ' (no English version yet)')
          + f', {name}_palette.png')


def start(name):
    orig = original(name)
    paths.HANDMADE.mkdir(parents=True, exist_ok=True)
    target = catalog.handmade_png(name)
    if target.exists():
        print(f'{paths.show(target)} already exists - not overwriting')
    else:
        src = current_english(name) or catalog.original_png(name)
        shutil.copyfile(src, target)
        print(f'copied {paths.show(src)} -> {paths.show(target)}')
    shutil.copyfile(catalog.original_png(name), paths.HANDMADE / f'{name}_original.png')
    table = catalog.rows()
    r = catalog.by_id(table).get(name)
    print(f'{name}: {orig.width}x{orig.height}, {len(palette(orig))} colours')
    if r:
        print(f"  original: {r['japanese']}\n  english:  {r['english']}\n  notes:    {r['notes']}")
    d = dups_of(name, table)
    if d:
        print(f'  your edit will also be used for {len(d)} duplicate(s): {", ".join(d[:8])}{"..." if len(d) > 8 else ""}')
    print(f'  edit {paths.show(target)}; when done: .venv/bin/python tools/edit.py check {name}')


def check(name):
    print(f'{name}:')
    f = catalog.handmade_png(name)
    if not f.exists():
        print(f'  ! {paths.show(f)} not found (run: edit.py start {name})')
        return ['missing']
    orig, new = original(name), Image.open(f)
    problems, notes = [], []
    if new.size != orig.size:
        problems.append(f'size {new.size[0]}x{new.size[1]}, the original is {orig.size[0]}x{orig.size[1]}')
    if new.mode != 'P':
        notes.append(f'saved as {new.mode}: fine - colours are snapped to the palette on approve')
    elif not same_palette(new, orig):
        n = len(palette(orig))
        hi = max(pixels(new))
        if hi >= n:
            problems.append(f'uses palette index {hi}, but the image only has {n} colours')
        else:
            notes.append('palette differs from the original: colours are snapped on approve')
    if not problems:
        s = 3
        a = orig.convert('RGBA').resize((orig.width * s, orig.height * s), Image.NEAREST)
        b = snap(new, orig).convert('RGBA').resize((new.width * s, new.height * s), Image.NEAREST)
        prev = Image.new('RGBA', (a.width, a.height * 2 + 6), KEY + (255,))
        prev.alpha_composite(a, (0, 0))
        prev.alpha_composite(b, (0, a.height + 6))
        prev.save(paths.HANDMADE / f'{name}_check.png')
    for n in notes:
        print(f'  note: {n}')
    print('\n'.join(f'  ! {p}' for p in problems) or '  OK')
    if not problems:
        print(f'  preview (original above, yours as it will look below): {paths.show(paths.HANDMADE / (name + "_check.png"))}')
    return problems


def mark_done(name, how):
    table = catalog.rows()
    row = catalog.by_id(table).get(name)
    if row is None:
        orig = original(name)
        row = {k: '' for k in (table[0].keys() if table else catalog.COLUMNS)}
        row.update(image=name, width=str(orig.width), height=str(orig.height), category='other',
                   notes='hand-made (no text originally listed)')
        table.append(row)
        table.sort(key=lambda r: r['image'])
    row['status'] = 'done'
    if how == 'hand' and 'hand-made' not in row['notes']:
        row['notes'] = (row['notes'] + '; ' if row['notes'] else '') + 'hand-made'
    catalog.write_rows(table)
    renders = catalog.load_renders()
    if renders.pop(name, None) is not None:
        catalog.save_renders(renders)
    (paths.RENDERED / f'{name}.png').unlink(missing_ok=True)
    return dups_of(name, table)


def approve(name, force=False):
    target = paths.APPROVED / f'{name}.png'
    if catalog.handmade_png(name).exists():
        problems = check(name)
        if problems and not force:
            print('  not approved - fix the problems above, or approve anyway with --force')
            return False
        orig, new = original(name), Image.open(catalog.handmade_png(name))
        final = new if same_palette(new, orig) else snap(new, orig)
        save_indexed(final, target)
        remove_handmade(name)
        d = mark_done(name, 'hand')
        what = 'hand edit'
    elif (paths.RENDERED / f'{name}.png').exists():
        print(f'{name}:')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(paths.RENDERED / f'{name}.png', target)
        d = mark_done(name, 'render')
        what = 'automatic render'
    else:
        print(f'{name}:\n  ! nothing to approve: no hand edit and no automatic render (edit.py start {name})')
        return False
    print(f'  approved the {what} -> {paths.show(target)}' + (f' (also used for {len(d)} duplicate(s))' if d else ''))
    return True


def reset(name):
    removed = remove_handmade(name)
    approved = paths.APPROVED / f'{name}.png'
    table = catalog.rows()
    row = catalog.by_id(table).get(name)
    if approved.exists():
        approved.unlink()
        removed.append(paths.show(approved))
    if row is not None and row['english'].strip() == '' and 'hand-made' in row['notes']:
        table.remove(row)  # a row that only existed because of a hand edit
    elif row is not None and row['status'] == 'done':
        row['status'] = 'todo'
        row['notes'] = '; '.join(n for n in row['notes'].split('; ') if n != 'hand-made')
    catalog.write_rows(table)
    print(f'{name}: ' + (f'removed {", ".join(removed)}' if removed else 'no hand edit or approved file')
          + ' - run tools/render.py to redraw the automatic version')


# ---------------------------------------------------------------- sheets

def sheets_dir():
    return paths.HANDMADE / 'sheets'


def sheet_files(sheet):
    d = sheets_dir()
    return d / f'{sheet}.png', d / f'{sheet}.sheet.json', d / f'{sheet}_check.png'


def _layout(names):
    pos, x, y, rowh = {}, SHEET_GAP, SHEET_GAP, 0
    for n in names:
        w, h = original(n).size
        tile = max(2 * w + SHEET_MID, 60)
        if x + tile + SHEET_GAP > SHEET_MAX_W and x > SHEET_GAP:
            x, y, rowh = SHEET_GAP, y + rowh + SHEET_LABEL + SHEET_GAP, 0
        pos[n] = (x + w + SHEET_MID, y + SHEET_LABEL, w, h)
        x += tile + SHEET_GAP
        rowh = max(rowh, h)
    return pos, max(p[0] + p[2] for p in pos.values()) + SHEET_GAP, max(p[1] + p[3] for p in pos.values()) + SHEET_GAP


def _compose(pos, size, pick):
    sheet = Image.new('RGBA', size, SHEET_BG)
    d = ImageDraw.Draw(sheet)
    for n, (x, y, w, h) in pos.items():
        ox = x - w - SHEET_MID
        d.text((ox, y - SHEET_LABEL + 1), n, fill=(255, 255, 0, 255))
        for px, img in ((ox, original(n)), (x, pick(n))):
            sheet.paste(Image.new('RGBA', (w, h), KEY + (255,)), (px, y))
            sheet.alpha_composite(img.convert('RGBA'), (px, y))
    return sheet


def _norm(img):
    return [(0, 0, 0, 0) if p[3] == 0 else p for p in pixels(img)]


def _pieces(sheet):
    png, manifest, _ = sheet_files(sheet)
    if not manifest.exists():
        sys.exit(f'no sheet "{sheet}" (see: edit.py sheet list)')
    m = json.loads(manifest.read_text())
    img = Image.open(png).convert('RGBA')
    out = []
    for n, (x, y, w, h) in m['images'].items():
        piece = img.crop((x, y, x + w, y + h))
        piece.putdata([(0, 0, 0, 0) if p[:3] == KEY or p[3] == 0 else p[:3] + (255,) for p in pixels(piece)])
        before = Path(m['started_from'][n])
        before = Image.open(before).convert('RGBA') if before.exists() else None
        out.append((n, piece, before is None or _norm(piece) != _norm(before)))
    return m, out


def sheet_start(sheet, names):
    png, manifest, _ = sheet_files(sheet)
    if manifest.exists():
        sys.exit(f'sheet "{sheet}" already exists ({paths.show(manifest)}) - pick another name')
    pos, w, h = _layout(names)
    sources = {n: current_english(n) or catalog.original_png(n) for n in names}
    sheets_dir().mkdir(parents=True, exist_ok=True)
    _compose(pos, (w, h), lambda n: Image.open(sources[n])).save(png)
    hand = {n: hashlib.sha1(catalog.handmade_png(n).read_bytes()).hexdigest()
            for n in names if catalog.handmade_png(n).exists()}
    manifest.write_text(json.dumps({'images': {n: list(p) for n, p in pos.items()},
                                    'started_from': {n: str(sources[n].resolve()) for n in names},
                                    'handmade_at_start': hand}, indent=1))
    print(f'sheet "{sheet}": {len(names)} images, {w}x{h}\n  edit {paths.show(png)} (original left, English right)'
          f'\n  then: edit.py sheet check {sheet} / sheet split {sheet} / sheet approve {sheet}')


def sheet_check(sheet):
    m, pieces = _pieces(sheet)
    png, _, check_png = sheet_files(sheet)
    snapped = {n: snap(p, original(n)) for n, p, changed in pieces if changed}
    pos = {n: tuple(p) for n, p in m['images'].items()}
    _compose(pos, Image.open(png).size,
             lambda n: snapped[n] if n in snapped else Image.open(m['started_from'][n])).save(check_png)
    print(f'sheet "{sheet}": {len(snapped)} of {len(pieces)} images changed; after palette snapping: {paths.show(check_png)}')
    return list(snapped)


def sheet_split(sheet, force=False):
    m, pieces = _pieces(sheet)
    at_start = m.get('handmade_at_start', {})
    clash = [n for n, _, changed in pieces if changed and catalog.handmade_png(n).exists()
             and at_start.get(n) != hashlib.sha1(catalog.handmade_png(n).read_bytes()).hexdigest()]
    if clash and not force:
        print(f'sheet "{sheet}": not split - edited individually since the sheet was made: {", ".join(clash)}'
              f'\n  (--force overwrites them)')
        return None
    written = []
    for n, piece, changed in pieces:
        if changed:
            save_indexed(snap(piece, original(n)), catalog.handmade_png(n))
            written.append(n)
    print(f'sheet "{sheet}": wrote {len(written)} changed image(s) to {paths.show(paths.HANDMADE)}')
    return written


def sheet_list():
    found = sorted(sheets_dir().glob('*.sheet.json')) if sheets_dir().exists() else []
    for mf in found:
        names = list(json.loads(mf.read_text())['images'])
        print(f'{mf.name[:-11]}: {len(names)} images ({names[0]} ... {names[-1]})')
    if not found:
        print('no sheets')


# ---------------------------------------------------------------- command line

def main(argv=None):
    argv = paths.configure(sys.argv[1:] if argv is None else argv)
    force = '--force' in argv
    argv = [a for a in argv if a != '--force']
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == 'list':
        find(' '.join(rest))
    elif cmd in ('start', 'refs', 'check', 'approve', 'reset'):
        names = catalog.expand(rest)
        if not names:
            sys.exit(f'edit.py {cmd}: which image(s)?')
        bad = []
        for n in names:
            if cmd == 'start':
                start(n)
            elif cmd == 'refs':
                refs(n)
            elif cmd == 'check':
                bad += [n] if check(n) else []
            elif cmd == 'approve':
                bad += [] if approve(n, force) else [n]
            else:
                reset(n)
        if len(names) > 1 and cmd in ('check', 'approve'):
            print(f'{len(names) - len(bad)}/{len(names)} OK' + (f' - needs attention: {", ".join(bad)}' if bad else ''))
        return 1 if bad else 0
    elif cmd == 'sheet' and rest[:1] == ['list']:
        sheet_list()
    elif cmd == 'sheet' and len(rest) >= 2:
        sub, name = rest[0], rest[1]
        if sub == 'start':
            sheet_start(name, catalog.expand(rest[2:]))
        elif sub == 'check':
            sheet_check(name)
        elif sub == 'split':
            sheet_split(name, force)
        elif sub == 'approve':
            written = sheet_split(name, force)
            if written is None:
                return 1
            ok = [n for n in written if approve(n, force)]
            if len(ok) == len(written):
                for f in sheet_files(name):
                    f.unlink(missing_ok=True)
                if not any(sheets_dir().iterdir()):
                    sheets_dir().rmdir()
                print(f'sheet "{name}" approved and removed')
        else:
            sys.exit(__doc__)
    else:
        sys.exit(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
