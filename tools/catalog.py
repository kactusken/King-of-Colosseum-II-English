#!/usr/bin/env python3
"""The image catalogue (translation/graphics.csv): rows, sources, fingerprints. No dependencies.

  catalog.py sources [id...]     which file the build uses for each image (HAND/DONE/AUTO/orig)
  catalog.py stale               automatic renders that are out of date (run tools/render.py)

Columns (only `image` and `status` are required; add the rest as the game needs them):
  image                stable id, matching review/images-original/<image>.png and the contact sheets
  source, x, y, w, h   where it lives (archive entry, file; region of a larger texture) - for gfx.py
  width, height, bpp   size and colour depth, for reference
  category             groups for filtering (title, menu, button, dialog, ...)
  japanese, english    transcription / English; ' / ' in the English forces a line break
  font, align, boxes   renderer hints; boxes = 'x,y,w,h;...' one rectangle per label (english
                       items separated by ' | ')
  dup_of               exact duplicate of another image; follows it (status dup)
  status               todo (not finished) / done (approved) / keep (stays original) / dup
  notes, review        why / notes from looking at the result

Where the English version of an image comes from, in priority order:
  HAND  translation/images-handmade/   work in progress always wins (and covers its duplicates)
  DONE  translation/images-approved/   finished, frozen - never redrawn automatically
  AUTO  translation/images-rendered/   automatic render, frozen until its inputs change
  (none)                               the original stays
All three folders hold indexed PNGs in the game's palette.

Fingerprints: translation/renders.json maps each rendered image to a hash of what it was drawn
from (the row's english/font/align/boxes, the original PNG, render.RENDERER_VERSION). A render
is stale when the hash no longer matches - see stale().
"""
import csv
import fnmatch
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

COLUMNS = ['image', 'source', 'x', 'y', 'w', 'h', 'width', 'height', 'bpp', 'category', 'japanese',
           'english', 'notes', 'font', 'align', 'boxes', 'dup_of', 'status', 'review']
STATUSES = ('todo', 'done', 'keep', 'dup')
RENDER_FIELDS = ('english', 'font', 'align', 'boxes')
REF_SUFFIXES = ('_original', '_check', '_palette', '_english')


def rows():
    if not paths.GRAPHICS_CSV.exists():
        return []
    with open(paths.GRAPHICS_CSV, encoding='utf-8', newline='') as f:
        out = list(csv.DictReader(f))
    for r in out:
        for c in COLUMNS:
            r.setdefault(c, '')
            r[c] = r[c] or ''
    return out


def write_rows(table):
    fields = list(table[0].keys()) if table else COLUMNS
    with open(paths.GRAPHICS_CSV, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(table)


def by_id(table=None):
    return {r['image']: r for r in (rows() if table is None else table)}


def original_png(name):
    return paths.ORIGINAL_IMAGES / f'{name}.png'


def handmade_png(name):
    return paths.HANDMADE / f'{name}.png'


def own_source(name):
    """(tag, path) of the image's own English file, or (None, None)."""
    for tag, d in (('HAND', paths.HANDMADE), ('DONE', paths.APPROVED), ('AUTO', paths.RENDERED)):
        p = d / f'{name}.png'
        if p.exists():
            return tag, p
    return None, None


def source(row, table):
    """(tag, path) the build uses for this row: its own file, else (for duplicates) its original's."""
    tag, p = own_source(row['image'])
    if tag == 'HAND' or (tag and not row['dup_of']):
        return tag, p
    if row['dup_of'] and row['dup_of'] in table:
        ot, op = source(table[row['dup_of']], table)
        if ot == 'HAND' or not tag:
            return ot, op
    return tag, p


def final_images(table=None):
    """{image: (tag, path)} for every image whose English version replaces the original."""
    table = by_id(table)
    out = {}
    for name, r in table.items():
        if r['status'] == 'keep':
            continue
        tag, p = source(r, table)
        if tag:
            out[name] = (tag, p)
    return out


def handmade_in_progress():
    if not paths.HANDMADE.exists():
        return []
    return sorted(p.stem for p in paths.HANDMADE.glob('*.png') if not p.stem.endswith(REF_SUFFIXES))


# ---------------------------------------------------------------- fingerprints

def _file_hash(p, cache={}):
    p = Path(p)
    key = (str(p), p.stat().st_mtime_ns)
    if key not in cache:
        cache[key] = hashlib.sha1(p.read_bytes()).hexdigest()
    return cache[key]


def wants_render(row):
    """Rows the automatic renderer is responsible for."""
    return row['status'] == 'todo' and not row['dup_of'] and row['english'].strip() != ''


def fingerprint(row, version):
    src = original_png(row['image'])
    parts = {k: row[k] for k in RENDER_FIELDS}
    parts['original'] = _file_hash(src) if src.exists() else None
    parts['version'] = version
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def load_renders():
    if paths.RENDERS_JSON.exists():
        return json.loads(paths.RENDERS_JSON.read_text(encoding='utf-8'))
    return {}


def save_renders(d):
    paths.RENDERS_JSON.write_text(json.dumps(dict(sorted(d.items())), indent=1) + '\n', encoding='utf-8')


def renderer_version():
    """render.RENDERER_VERSION, read from the source so this module needs no Pillow."""
    src = (Path(__file__).resolve().parent / 'render.py').read_text(encoding='utf-8')
    for line in src.splitlines():
        if line.startswith('RENDERER_VERSION'):
            return int(line.split('=')[1].split('#')[0])
    return 0


def stale(table=None):
    """Images the renderer should (re)draw: (missing, changed, unsupported) lists of ids."""
    table = rows() if table is None else table
    version, done = renderer_version(), load_renders()
    missing, changed, unsupported = [], [], []
    for r in table:
        if not wants_render(r):
            continue
        rec = done.get(r['image'])
        if rec is None:
            missing.append(r['image'])
        elif rec.get('fp') != fingerprint(r, version):
            changed.append(r['image'])
        elif rec.get('unsupported'):
            unsupported.append(r['image'])
        elif not (paths.RENDERED / f"{r['image']}.png").exists():
            missing.append(r['image'])
    return missing, changed, unsupported


# ---------------------------------------------------------------- names and ranges

def expand(args, table=None):
    """Image ids from arguments: ids, comma lists, ranges (a-b, a..b, a-052) and patterns (0013_*).
    Ranges and patterns follow catalogue order and leave out duplicates."""
    table = rows() if table is None else table
    ids = [r['image'] for r in table]
    dup = {r['image'] for r in table if r['dup_of']}
    out = []
    for arg in args:
        for a in filter(None, arg.split(',')):
            if a in ids or not any(c in a for c in '-.*?['):
                out.append(a)
            elif any(c in a for c in '*?['):
                out += [i for i in ids if fnmatch.fnmatchcase(i, a) and i not in dup]
            else:
                lo = hi = None
                seps = [a.index('..')] if '..' in a else [i for i, c in enumerate(a) if c == '-']
                for s in seps:
                    x, y = a[:s], a[s + (2 if a[s] == '.' else 1):]
                    y = x[:len(x) - len(y)] + y if len(y) < len(x) else y
                    if x in ids and y in ids:
                        lo, hi = ids.index(x), ids.index(y)
                        break
                if lo is None:
                    sys.exit(f'{a}: not an image id or a range of them (see tools/edit.py list)')
                out += [i for i in ids[min(lo, hi):max(lo, hi) + 1] if i not in dup]
    seen = set()
    return [i for i in out if not (i in seen or seen.add(i))]


def main(argv=None):
    argv = paths.configure(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['sources']:
        table = by_id()
        for name in expand(argv[1:]) if argv[1:] else table:
            tag, p = source(table[name], table) if name in table else (None, None)
            print(f'{name:16} {tag or "orig":5} {paths.show(p) if p else ""}')
    elif argv[:1] == ['stale']:
        missing, changed, unsupported = stale()
        for label, items in (('not rendered yet', missing), ('changed since rendered', changed),
                             ('style not supported by the renderer (hand edit them)', unsupported)):
            if items:
                print(f'{label}: {len(items)}\n  ' + ' '.join(items))
        if not (missing or changed):
            print('renders are up to date')
        return 1 if missing or changed else 0
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    sys.exit(main())
