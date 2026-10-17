#!/usr/bin/env python3
"""Fixed-record text tables: names, items, menus of records - text fields at fixed offsets in
records at a fixed stride (NUL-padded, in the game's codec).

  records.py dump                  write / extend each table's CSV in translation/text/: one row per
                                   distinct (table, field, value); English already there is kept
  records.py verify                every table's layout (fields decode, padding is zero, records fit),
                                   a no-English write is byte-identical, every English fits its field
                                   (and, with WIDTH set, isn't wider than the widest original)
  records.py measure <file> [--entry N] [--first OFS]
                                   suggest a TABLES entry for unknown data: stride, fields, sizes

Tables are described in TABLES (below) - data, not code:

  'name': {'source': ('file', '/DATA/ITEMS.BIN')            a file in the image, or
                     ('pack', '/DATA/GAME.PAK', [12, 40]),  pack entries (copies share translations;
                                                            unpacked folders: stepcheck.PACK_DIRS)
           'first': 0x10,            offset of the first record
           'stride': 40,             record size
           'count': 120 | ('u32', 0) | 'fit',
                                     fixed, read from the data (u16/u32 at an offset), or as many
                                     records as fit (a last record cut short still counts if its
                                     fields are whole)
           'variants': (4, 0x8ed),   optional: blocks inside a record, each with the fields below
           'fields': [('name', 0, 36), ('help', 36, 84)],   (field, offset in the block, size)
           'csv': 'items.csv',       several tables may share a CSV (a new one gets a `table`
                                     column; one without it shares translations between tables)
           'encoding': 'ascii' | 'fullwidth' | 'auto'}

Encodings: `ascii` - one byte a letter (the renderer must draw single-byte text - check, or patch it;
FRAMEWORK.md section 3); `fullwidth` - two bytes a letter, for renderers that only draw two-byte
codes; `auto` - ASCII unless the English holds other characters (button symbols), then full-width.
Room in a field = its size - 1 (a NUL stays). Set ENCODE to the project's own encoder (glyph checks,
quote handling), WIDTH to its text-width function, LOOKUPS to checks of strings other data compares
with these values (FRAMEWORK.md section 5, "Text that is also a key") - the build stops on any
problem they report.

CSV columns: [table,] field, japanese, english, room. Rows without English keep the original.
"""
import argparse
import csv
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

CODEC = 'cp932'
PACK = '/DATA/KC2FIRE.000'
NAMES = [('surname', 0x00, 15), ('given', 0x0f, 21), ('nickname', 0x24, 33), ('move', 0x45, 49)]
ROSTER = {'stride': 0x23b4, 'variants': (4, 0x8ed), 'fields': NAMES, 'csv': 'roster.csv', 'encoding': 'ascii'}
TABLES = {   # *from the data* - docs/TECHNICAL.md "Roster data", "Fixed-record text tables", "Edit-mode templates"
    # the wrestler rosters: six copies, records of four variants (Type 1-4); the select screen and
    # profile read these. English as ASCII (the renderer patch draws it, docs/PATCHES.md)
    'roster_111': dict(ROSTER, source=('pack', PACK, [1999, 2016]), first=0x3fd4, count=111),
    'roster_150': dict(ROSTER, source=('pack', PACK, [2002, 2018]), first=0x4d94, count=150),
    'roster_150b': dict(ROSTER, source=('pack', PACK, [2004, 2019]), first=0x6694, count=150),
    # Edit-mode templates (wrestler types, samples): one variant block per record, the last 4 bytes short
    'templates': {'source': ('pack', PACK, [2005]), 'first': 0x26d4, 'stride': 0x8ed, 'count': 157,
                  'fields': NAMES, 'csv': 'roster.csv', 'encoding': 'ascii'},
    # font-drawn tables: ASCII, or full-width when the English holds symbols (□ △ ○)
    'appearance': {'source': ('pack', PACK, [1448]), 'first': 0, 'stride': 32, 'count': 'fit',
                   'fields': [('name', 0, 28)], 'csv': 'fields.csv', 'encoding': 'auto'},
    'logic_situations': {'source': ('pack', PACK, [1450]), 'first': 0, 'stride': 36, 'count': 'fit',
                         'fields': [('name', 0, 28)], 'csv': 'fields.csv', 'encoding': 'auto'},
    'logic_actions': {'source': ('pack', PACK, [1451]), 'first': 0, 'stride': 48, 'count': 'fit',
                      'fields': [('name', 0, 32)], 'csv': 'fields.csv', 'encoding': 'auto'},
    'wrestler_types': {'source': ('pack', PACK, [1452]), 'first': 0, 'stride': 128, 'count': 'fit',
                       'fields': [('name', 0, 40), ('help', 40, 84)], 'csv': 'fields.csv', 'encoding': 'auto'},
    'voices': {'source': ('pack', PACK, [1453]), 'first': 0, 'stride': 48, 'count': 'fit',
               'fields': [('name', 0, 44)], 'csv': 'fields.csv', 'encoding': 'auto'},
    'themes': {'source': ('pack', PACK, [1454]), 'first': 0, 'stride': 48, 'count': 'fit',
               'fields': [('name', 0, 44)], 'csv': 'fields.csv', 'encoding': 'auto'},
}


def game_encode(text, mode, files, where):
    """ASCII as the kit does; full-width through the game's font table (glyph check, ' -> ’ ...)."""
    if mode == 'ascii' or (mode == 'auto' and all(0x20 <= ord(c) < 0x7f for c in text)):
        return encode(text, 'ascii', files, where)
    import pools
    return pools.encode(text, pools.font_codes(files.packs), where)


ENCODE = game_encode         # project encoder: f(text, mode, files, where) -> bytes; None = encode() below
WIDTH = None                 # project text width: f(encoded bytes) -> pixels; None = no width check
LOOKUPS = []                 # project checks after the step: f(files) -> [problem, ...]
SIZE_COLUMNS = ('room', 'ascii_max')    # the CSV column with the room in bytes (first one present)


def encode(text, mode, files=None, where=''):
    """Default encoder: `ascii`, `fullwidth` (ASCII letters and space shifted to U+FF01-FF5E / U+3000)
    or `auto`; a character the codec can't hold stops the build."""
    if mode == 'auto':
        mode = 'ascii' if all(0x20 <= ord(c) < 0x7f for c in text) else 'fullwidth'
    if mode == 'ascii':
        if not all(0x20 <= ord(c) < 0x7f for c in text):
            sys.exit(f'{where}: {text!r} is not printable ASCII (use encoding auto or fullwidth)')
        return text.encode('ascii')
    wide = ''.join('　' if c == ' ' else chr(ord(c) + 0xfee0) if 0x21 <= ord(c) < 0x7f else c for c in text)
    try:
        return wide.encode(CODEC)
    except UnicodeEncodeError as e:
        sys.exit(f'{where}: {text!r}: {e.reason} - use another character')


def _encode(text, mode, files, where):
    return (ENCODE or encode)(text, mode, files, where)


def copies(table):
    """[(kind, name, entry)] - every copy of a table's data."""
    src = table['source']
    if src[0] == 'file':
        return [('file', src[1], None)]
    return [('pack', src[1], k) for k in src[2]]


def get(files, copy):
    kind, name, k = copy
    return bytearray(files.get(name) if kind == 'file' else files.packs.get(name, k))


def put(files, copy, data):
    kind, name, k = copy
    if kind == 'file':
        files.put(name, data)
    else:
        files.packs.put(name, k, data)


def blocks(table, data):
    """Offsets of every block holding the table's fields (records x variants)."""
    first, stride = table['first'], table['stride']
    nvar, vstep = table.get('variants', (1, 0))
    count = table['count']
    if isinstance(count, tuple):
        fmt = {'u16': '<H', 'u32': '<I'}[count[0]]
        count = struct.unpack_from(fmt, data, count[1])[0]
    elif count == 'fit':
        need = max(off + size for _, off, size in table['fields']) + (nvar - 1) * vstep
        count = max(0, (len(data) - first - need) // stride + 1)
    end = max(off + size for _, off, size in table['fields'])
    every = [first + r * stride + v * vstep for r in range(count) for v in range(nvar)]
    return [at for at in every if at + end <= len(data)]     # a cut-short last record: its whole blocks


def expected(table, data):
    """How many blocks the count says (blocks() leaves out those past the end of the data)."""
    count = table['count']
    if isinstance(count, tuple):
        count = struct.unpack_from({'u16': '<H', 'u32': '<I'}[count[0]], data, count[1])[0]
    elif count == 'fit':
        return len(blocks(table, data))
    return count * table.get('variants', (1, 0))[0]


def read_field(data, at, size):
    return bytes(data[at:at + size]).split(b'\0')[0]


def csv_path(table):
    return paths.TEXT / table['csv']


def tables_of(csv_name):
    return {n: t for n, t in TABLES.items() if t['csv'] == csv_name}


def keyed(csv_name):
    """Whether rows are per table (a `table` column): an existing CSV says so itself; a new one gets
    the column when several tables share it. Without it, tables sharing a CSV share translations
    (e.g. several copies of a roster laid out differently)."""
    _, columns = load(csv_name)
    return 'table' in columns if columns else len(tables_of(csv_name)) > 1


def load(csv_name):
    """{(table or '', field, japanese): row} and the CSV's column names (None if there is no CSV)."""
    p = paths.TEXT / csv_name
    if not p.exists():
        return {}, None
    with open(p, encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        rows = {(row.get('table', ''), row['field'], row['japanese']): row for row in r}
        return rows, r.fieldnames


def room(row):
    return int(next(row[c] for c in SIZE_COLUMNS if row.get(c)))


def source_files():
    import stepcheck
    return stepcheck.Files()


def dump():
    files = source_files()
    for csv_name in sorted({t['csv'] for t in TABLES.values()}):
        rows, columns = load(csv_name)
        multi = keyed(csv_name)
        columns = columns or (['table'] if multi else []) + ['field', 'japanese', 'english', SIZE_COLUMNS[0]]
        size_col = next(c for c in SIZE_COLUMNS if c in columns)
        added = 0
        for name, table in tables_of(csv_name).items():
            for copy in copies(table):
                data = get(files, copy)
                for at in blocks(table, data):
                    for field, off, size in table['fields']:
                        v = read_field(data, at + off, size)
                        key = (name if multi else '', field, v.decode(CODEC, 'replace'))
                        if v and key not in rows:
                            row = {'field': field, 'japanese': key[2], 'english': '', size_col: size - 1}
                            if multi:
                                row['table'] = name
                            rows[key] = row
                            added += 1
        p = paths.TEXT / csv_name
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows.values())
        print(f'{paths.show(p)}: {len(rows)} rows ({added} new)')


def encoded_rows(csv_name, files):
    """{key: English bytes} for the CSV's translated rows; exits listing rows that don't fit."""
    rows, _ = load(csv_name)
    out, problems = {}, []
    modes = {n: t.get('encoding', 'ascii') for n, t in tables_of(csv_name).items()}
    default = next(iter(modes.values()), 'ascii')
    for key, row in rows.items():
        en = row['english']
        if not en:
            continue
        b = _encode(en, modes.get(key[0], default), files, f'{csv_name}: {key[2]}')
        if len(b) > room(row):
            problems.append(f'{key[0] + " " if key[0] else ""}{key[1]} {key[2]!r} -> {en!r}: '
                            f'{len(b)} bytes, room for {room(row)}')
        out[key] = b
    if problems:
        sys.exit(f'{csv_name}:\n  ' + '\n  '.join(problems[:20]))
    return out


def write(files, csv_name, english):
    """Write the English into every copy of every table of a CSV; returns fields written."""
    multi = keyed(csv_name)
    done = 0
    for name, table in tables_of(csv_name).items():
        for copy in copies(table):
            data = get(files, copy)
            for at in blocks(table, data):
                for field, off, size in table['fields']:
                    jp = read_field(data, at + off, size)
                    new = english.get((name if multi else '', field, jp.decode(CODEC, 'replace'))) if jp else None
                    if new:
                        data[at + off:at + off + size] = new.ljust(size, b'\0')
                        done += 1
            put(files, copy, data)
    return done


def step(path, files):
    """build.py text step: write one CSV's English into all its tables (path = translation/text/X.csv)."""
    name = Path(path).name
    if not tables_of(name):
        sys.exit(f'{paths.show(path)}: no table in tools/records.py TABLES uses it')
    done = write(files, name, encoded_rows(name, files))
    problems = [p for check in LOOKUPS for p in check(files)]
    if problems:
        sys.exit(f'{paths.show(path)}: lookups that no longer resolve as in the original:\n  '
                 + '\n  '.join(problems[:20]))
    print(f'text: {paths.show(path)}: {done} fields in {len(tables_of(name))} table(s)')


def verify():
    files = source_files()
    ok = True
    for name, table in TABLES.items():
        for copy in copies(table):
            data = get(files, copy)
            bad = []
            offs = blocks(table, data)
            short = expected(table, data) - len(offs)
            for at in offs:
                for field, off, size in table['fields']:
                    raw = bytes(data[at + off:at + off + size])
                    v = raw.split(b'\0')[0]
                    try:
                        v.decode(CODEC)
                    except UnicodeDecodeError:
                        bad.append(f'{field} at {at + off:#x} does not decode')
                    if any(raw[len(v):]):
                        bad.append(f'{field} at {at + off:#x}: padding is not zero')
            where = copy[1] + (f' #{copy[2]}' if copy[2] is not None else '')
            print(f'{name} ({where}): {len(offs)} blocks' + (f' ({short} past the end of the data, left out)' if short else '')
                  + ', ' + ('fields ok' if not bad else f'{len(bad)} problems'))
            for b in bad[:5]:
                print('  ' + b)
            ok = ok and not bad
    for csv_name in sorted({t['csv'] for t in TABLES.values()}):
        before = {}
        for name, table in tables_of(csv_name).items():
            for copy in copies(table):
                before[copy] = bytes(get(files, copy))
        write(files, csv_name, {})
        same = all(bytes(get(files, c)) == d for c, d in before.items())
        english = encoded_rows(csv_name, files)
        print(f'{csv_name}: no English -> ' + ('byte-identical' if same else 'CHANGED')
              + f', {len(english)} translated values fit')
        ok = ok and same
        if WIDTH:
            wide = width_report(csv_name, files, english)
            for line in wide[:10]:
                print('  wider than the original: ' + line)
    return ok


def width_report(csv_name, files, english):
    """English values wider (WIDTH) than the widest original of the same table and field."""
    rows, _ = load(csv_name)
    widest = defaultdict(int)
    for key in rows:
        widest[key[:2]] = max(widest[key[:2]], WIDTH(key[2].encode(CODEC, 'replace')))
    return [f'{k[0] + " " if k[0] else ""}{k[1]} {rows[k]["english"]!r}: {WIDTH(b)} px > {widest[k[:2]]}'
            for k, b in english.items() if WIDTH(b) > widest[k[:2]]]


def strings(data, minimum=2):
    """[(offset, length)] of NUL-terminated runs of codec text with at least `minimum` two-byte chars,
    starting after a zero or control byte (record data often runs right up to a name)."""
    out, i = [], 0
    while i < len(data):
        lead = 0x81 <= data[i] <= 0x9f or 0xe0 <= data[i] <= 0xfc
        if data[i] == 0 or (i and data[i - 1] >= 0x20) or (i and data[i - 1] and not lead):
            i += 1            # after a control byte only a two-byte character starts a string
            continue
        j, wide = i, 0
        while j < len(data) and data[j]:
            if 0x81 <= data[j] <= 0x9f or 0xe0 <= data[j] <= 0xfc:
                if j + 1 >= len(data) or not 0x40 <= data[j + 1] <= 0xfc:
                    break
                wide += 1
                j += 2
            elif 0x20 <= data[j] < 0x7f:
                j += 1
            else:
                break
        if wide >= minimum and (j >= len(data) or data[j] == 0):
            out.append((i, j - i))
        i = j + 1
    return out


def measure(data, first=None):
    """Suggest stride, first record and fields for fixed-record text in `data`."""
    found = strings(data)
    if len(found) < 3:
        return None
    starts = [o for o, _ in found]
    have = set(starts)
    # the stride: the distance most strings repeat at (fields of one record sit closer than a
    # record, so try the distances to the next few strings, not only the neighbour); ties: smallest
    candidates = {b - a for i, a in enumerate(starts) for b in starts[i + 1:i + 8]}
    stride = max(candidates, key=lambda g: (sum(1 for s in starts if s + g in have), -g))
    # a field: a position in the record a fair share of the strings found start at (the scan misses
    # some strings - one-character names, names right after printable bytes - so count against the
    # strings found, not the records); the record starts at its first field
    phases = Counter(s % stride for s in starts)
    fields_at = sorted(p for p, c in phases.items() if c >= max(2, len(starts) // 8))
    if not fields_at:
        return None
    phase = fields_at[0] if first is None else first % stride
    base = first if first is not None else phase + (min(starts) - phase) // stride * stride
    offsets = sorted((p - phase) % stride for p in fields_at)
    nrec = max(1, (len(data) - base) // stride)
    fields = []
    for n, off in enumerate(offsets):
        nxt = offsets[n + 1] if n + 1 < len(offsets) else stride
        size = nxt - off
        for r in range(nrec):          # stop at the first non-zero byte after a value (data, not padding)
            at = base + r * stride + off
            v = data[at:at + size].split(b'\0')[0]
            k = at + len(v)
            while k < at + size and data[k] == 0:
                k += 1
            if k < at + size and len(v) > 0:
                size = min(size, k - at)
        fields.append((f'field{n}', off, size))
    return {'first': base, 'stride': stride, 'count': 'fit', 'fields': fields,
            'sample': [data[base + off:base + off + size].split(b'\0')[0].decode(CODEC, 'replace')
                       for _, off, size in fields]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('dump')
    sub.add_parser('verify')
    s = sub.add_parser('measure')
    s.add_argument('file', help='a file in the image (/DATA/X.BIN) or a pack (with --entry)')
    s.add_argument('--entry', type=int)
    s.add_argument('--first', type=lambda v: int(v, 0))
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'dump':
        dump()
        return 0
    if args.cmd == 'verify':
        return 0 if verify() else 1
    files = source_files()
    data = files.packs.get(args.file, args.entry) if args.entry is not None else files.get(args.file)
    m = measure(bytes(data), args.first)
    if not m:
        print('no repeating text records found')
        return 1
    src = f"('pack', {args.file!r}, [{args.entry}])" if args.entry is not None else f"('file', {args.file!r})"
    print(f"'NAME': {{'source': {src}, 'first': {m['first']:#x}, 'stride': {m['stride']}, 'count': 'fit',\n"
          f"         'fields': {m['fields']}, 'csv': 'NAME.csv', 'encoding': 'ascii'}},")
    print(f"first record: {m['sample']}  - check the stride and sizes against a few records")
    return 0


if __name__ == '__main__':
    sys.exit(main())
