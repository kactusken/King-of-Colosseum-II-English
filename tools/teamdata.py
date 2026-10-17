#!/usr/bin/env python3
"""Promotion and team tables, title holders, the Secret Shop list and two notices in KC2FIRE.000.

  teamdata.py dump [--force]   translation/text/teamdata.csv: one row per unique (table, field, value)
  teamdata.py verify           layouts, round trip, and the English: room, width, keys that must match

Two kinds of entries. *From the data* unless marked.

Record tables - u32 record count, 12 zero bytes, then fixed records; each starts with a NUL-padded
Shift-JIS name:
  2000 / 2017  promotions (41 records of 40 bytes, name 36): the Match Maker list, 新規団体 slots
  2003 / 2020  promotions (24 records of 40 bytes, name 36)
  2001         Elimination teams (44 records of 48 bytes, name 31 - byte 31 is data in two
               records - then five wrestler numbers)
2000/2001 load with roster 1999 at start-up (0x116540), 2017/2020 with the other rosters; 2003 (a
byte copy of 2020) has no load we could find. The Match Maker compares its promotion names with
the list in the executable (0x1d1af8, strcmp against 0x3aec48...; *from the code*), so the names
here must be the same English as those elf.txt strings - `verify` and the build step check it.

Text sheets - Shift-JIS text, lines ending in CR LF, cells separated by tabs; the game parses them
when loaded (*from the code*):
  2829-2836    title belts per promotion (2836 = all), read by 0x1d2a80+ (entry 2829 + promotion):
               9 lines a title - name (copied into a 32-byte slot), three holder lines (one or two
               names, each copied into a 16-byte buffer and looked up with strstr() in the
               wrestlers' full names: a holder is a KEY, not shown), five ○/× flags (kept)
  2396         Secret Shop items, read by 0x1bf340: number, name (64-byte slot), category (matched
               by prefix against 2397), price, description (64-byte slot), promotion (matched
               against 2400), number, difficulty (matched against the executable's イージー /
               ノーマル / ハード / Sハード / マスター at 0x3ae3f0, so it must be elf.txt's English),
               wrestler number
  2397         shop categories: name (64-byte slot), description (64-byte slot)
  2400         promotion short names (16-byte slots, 0x1bebf0)
  2398 / 2399  notices drawn as one multi-line text (0x1b275c / 0x1b2768 -> 0x1b1410)
English cells are written as ASCII (the text patch draws them, docs/PATCHES.md), at most the slot
size - 1; the notices as full-width text like other multi-line strings (tools/pools.py encode).
Not translated: 2032 (variant -> wrestler mapping, full names), 2049 / 2050 (motion and move-slot
enum names ending in 最大数), 2380 (show-condition names) - no load of them found in the executable.

teamdata.csv columns: table, field, japanese, english, ascii_max (room in bytes; empty for the
notices), notes. A row covers every cell with that table, field and Japanese text (shop categories and
promotions are shared between the files that must agree). Rows without English keep the Japanese.
"""
import argparse
import csv
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import elftext  # noqa: E402
import paths  # noqa: E402
import pools  # noqa: E402

PACK = '/DATA/KC2FIRE.000'
HEADER = 16
# entry: (table, record stride, name size)
RECORDS = {
    2000: ('promotions', 40, 36), 2017: ('promotions', 40, 36),
    2003: ('promotions', 40, 36), 2020: ('promotions', 40, 36),
    2001: ('teams', 48, 31),
}
SHEETS = {**{e: 'titles' for e in range(2829, 2837)}, 2396: 'shop', 2397: 'shop_categories',
          2400: 'shop_promotions', 2398: 'notice', 2399: 'notice'}
# sheet kind -> {column: (table, field, slot bytes)}
COLUMNS = {
    'shop': {1: ('shop', 'name', 64), 2: ('shop', 'category', 64), 4: ('shop', 'description', 64),
             5: ('shop', 'promotion', 16), 7: ('shop', 'difficulty', 16)},
    'shop_categories': {0: ('shop', 'category', 64), 1: ('shop', 'category_help', 64)},
    'shop_promotions': {0: ('shop', 'promotion', 16)},
}
TITLE_LINES = 9
# keys that must equal elf.txt's English for the same Japanese: (table, field) -> block range
ELF_KEYS = {('shop', 'difficulty'): (0x2af3f0, 0x2af440),
            # item names found by strcmp: the two courses, SUPER HARD, MASTER, Edit P+50 (0x1c9390)
            ('shop', 'name'): (0x2af460, 0x2af600),
            ('promotions', 'name'): (0x2afc48, 0x2afdc8)}
ROSTERS = (1999, 2002, 2004)          # the three roster contents (2016/2018/2019 are copies)
CSV_COLUMNS = ['table', 'field', 'japanese', 'english', 'ascii_max', 'notes']
# never drawn as text (no width limit): holders are lookup keys; title names stay in the load
# buffer (only tested for being there - the screens draw belt pictures); the difficulty and
# promotion cells are matched against other lists (the promotion list 2400 holds the Survival Road
# course keys - no drawing of it found, *open*)
NOT_KEY_WIDTH = {('titles', 'holder'), ('titles', 'name'), ('shop', 'difficulty'), ('shop', 'promotion')}


def csv_path():
    return paths.TEXT / 'teamdata.csv'


def entry_data(entry):
    return (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000' / f'{entry:05d}.bin').read_bytes()


# ---- record tables

def record_names(data, entry):
    """[(offset, name bytes)] of one record table."""
    _, stride, size = RECORDS[entry]
    n = struct.unpack_from('<I', data)[0]
    return [(HEADER + i * stride, bytes(data[HEADER + i * stride:HEADER + i * stride + size]).split(b'\0')[0])
            for i in range(n)]


# ---- text sheets

def split_sheet(data):
    """Lines (without CR LF) as lists of cells (bytes); the last element is what follows the last CR LF."""
    lines = bytes(data).split(b'\r\n')
    return [ln.split(b'\t') for ln in lines]


def join_sheet(lines):
    return b'\r\n'.join(b'\t'.join(cells) for cells in lines)


def sheet_cells(entry, lines):
    """[(line, column, table, field, slot)] of the translatable cells of one sheet."""
    kind = SHEETS[entry]
    out = []
    if kind == 'titles':
        body = lines[:-1] if lines and lines[-1] == [b''] else lines
        if len(body) % TITLE_LINES:
            sys.exit(f'KC2FIRE.000 entry {entry}: {len(body)} lines, not {TITLE_LINES} a title - layout changed?')
        for i, cells in enumerate(body):
            k = i % TITLE_LINES
            if k == 0:
                out.append((i, 0, 'titles', 'name', 32))
            elif k <= 3:
                out += [(i, c, 'titles', 'holder', 16) for c in range(min(len(cells), 2)) if cells[c]]
    elif kind in COLUMNS:
        for i, cells in enumerate(lines):
            out += [(i, c, *COLUMNS[kind][c]) for c in COLUMNS[kind] if c < len(cells) and cells[c]]
    return [x for x in out if any(b >= 0x80 for b in lines[x[0]][x[1]])]


def notice_text(data):
    return bytes(data).decode('cp932').replace('\r\n', '\n')


# ---- all translatable strings of the original files

def originals():
    """[(entry, where, table, field, japanese, max_bytes)]: where = record offset, (line, col) or None."""
    out = []
    for entry, (table, _, size) in RECORDS.items():
        for at, v in record_names(entry_data(entry), entry):
            if v:
                out.append((entry, at, table, 'name', v.decode('cp932'), size - 1))
    for entry, kind in SHEETS.items():
        data = entry_data(entry)
        if kind == 'notice':
            out.append((entry, None, 'notice', str(entry), notice_text(data), ''))
            continue
        lines = split_sheet(data)
        for i, c, table, field, slot in sheet_cells(entry, lines):
            out.append((entry, (i, c), table, field, lines[i][c].decode('cp932'), slot - 1))
    return out


def dump(force=False):
    out = csv_path()
    if out.exists() and not force:
        print(f'{paths.show(out)} exists - kept (--force to dump again and lose its English)')
        return
    seen, rows = set(), []
    for entry, where, table, field, jp, room in originals():
        if (table, field, jp) not in seen:
            seen.add((table, field, jp))
            rows.append({'table': table, 'field': field, 'japanese': jp, 'english': '', 'ascii_max': room, 'notes': ''})
    with open(out, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f'{paths.show(out)}: {len(rows)} rows')


def load(path=None):
    with open(path or csv_path(), encoding='utf-8', newline='') as f:
        return {(r['table'], r['field'], r['japanese']): r for r in csv.DictReader(f)}


# ---- checks on the English

def elf_english():
    """{file offset: (japanese, english)} of elf.txt."""
    bf = blocks.BlockFile(elftext.text_path())
    return {int(b.id, 16): ('\n'.join(bf.source(b)), '\n'.join(b.english)) for b in bf.blocks}


def roster_names():
    """[(japanese parts, english parts)] per wrestler variant of the original rosters, from roster.csv."""
    import records
    with open(paths.TEXT / 'roster.csv', encoding='utf-8', newline='') as f:
        en = {(r['field'], r['japanese']): r['english'] for r in csv.DictReader(f)}
    out = set()
    for entry in ROSTERS:
        data = entry_data(entry)
        table = next(t for t in records.TABLES.values() if entry in t['source'][2] and t['csv'] == 'roster.csv')
        for at in records.blocks(table, data):
            s = records.read_field(data, at, 15).decode('cp932')
            g = records.read_field(data, at + 15, 21).decode('cp932')
            if s or g:
                out.add(((s, g), (en.get(('surname', s)) or s, en.get(('given', g)) or g)))
    return sorted(out)


def holder_matches(name, parts):
    """Does the game's strstr() find `name` in a full name made of these parts (any order/separator)?"""
    s, g = parts
    return any(name in full for full in (s, g, s + '　' + g, g + '　' + s, s + g, g + s,
                                          s + ' ' + g, g + ' ' + s, s + '・' + g, g + '・' + s))


def problems(table, glyphs):
    """[message] for English that doesn't fit, is too wide, or breaks a key."""
    import font
    out = []
    f = font.Font('sys')

    def width(text):
        return max(2 * sum(f.width(c)[1] for c in font.encode_text(ln)) for ln in text.split('\n'))
    widest = {}
    for (t, fld, jp) in table:
        widest[t, fld] = max(widest.get((t, fld), 0), width(jp))
    elf = elf_english()
    wrestlers = roster_names()
    for key, r in table.items():
        t, fld, jp = key
        en = r['english']
        if not en:
            continue
        b = encode(t, en, glyphs, f'{paths.show(csv_path())}: {jp}')
        if r['ascii_max'] and len(b) > int(r['ascii_max']):
            out.append(f'{t} {fld} {jp!r} -> {en!r}: {len(b)} bytes, room for {r["ascii_max"]}')
        limit = width(jp) if t == 'notice' else widest[t, fld]
        if (t, fld) not in NOT_KEY_WIDTH and width(en) > limit:
            out.append(f'{t} {fld} {jp!r} -> {en!r}: {width(en)} px wide, the Japanese reaches {limit}')
        if (t, fld) in ELF_KEYS:
            lo, hi = ELF_KEYS[t, fld]
            want = {e for o, (j, e) in elf.items() if lo <= o < hi and j == jp}
            if want and en not in want:
                out.append(f'{t} {fld} {jp!r} -> {en!r}: the executable\'s copy says {" / ".join(sorted(want))!r} (elf.txt) - they must match')
        if (t, fld) == ('titles', 'holder'):
            jp_hits = {w for w in wrestlers if holder_matches(jp, w[0])}
            en_hits = {w for w in wrestlers if holder_matches(en, w[1])}
            wrong = en_hits - jp_hits
            if wrong or (jp_hits and not en_hits):
                out.append(f'title holder {jp!r} -> {en!r}: finds ' + (', '.join(' '.join(w[1]) for w in sorted(wrong)[:3]) if wrong else 'no wrestler')
                           + f' (the Japanese finds {", ".join(" ".join(w[1]) for w in sorted(jp_hits)[:3]) or "none"})')
    return out


# ---- writing

def encode(table, text, glyphs, where):
    """Bytes for one English cell: ASCII (single line), full-width for the notices (CR LF lines)."""
    if table == 'notice':
        return pools.encode(text, glyphs, where).replace(b'\n', b'\r\n')
    if '\n' in text:
        sys.exit(f'{where}: a new line in a one-line cell')
    return elftext.encode(text, glyphs, where)


def rebuild(entry, data, english):
    """The entry with English written in; english = {(table, field, japanese): bytes}."""
    if entry in RECORDS:
        table, _, size = RECORDS[entry]
        data = bytearray(data)
        for at, v in record_names(data, entry):
            new = english.get((table, 'name', v.decode('cp932'))) if v else None
            if new:
                data[at:at + size] = new.ljust(size, b'\0')
        return bytes(data)
    if SHEETS[entry] == 'notice':
        return english.get(('notice', str(entry), notice_text(data)), bytes(data))
    lines = split_sheet(data)
    for i, c, table, field, _ in sheet_cells(entry, lines):
        new = english.get((table, field, lines[i][c].decode('cp932')))
        if new:
            lines[i][c] = new
    return join_sheet(lines)


def step(path, files):
    """build.py text step: teamdata.csv's English into the record tables and text sheets."""
    table = load(path)
    glyphs = pools.font_codes(files.packs)
    bad = problems(table, glyphs)
    if bad:
        sys.exit(f'{paths.show(path)}:\n  ' + '\n  '.join(bad[:20]))
    english = {k: encode(k[0], r['english'], glyphs, f'{paths.show(path)}: {k[2]}')
               for k, r in table.items() if r['english']}
    done = 0
    for entry in list(RECORDS) + list(SHEETS):
        old = files.packs.get(PACK, entry)
        new = rebuild(entry, old, english)
        if new != bytes(old):
            files.packs.put(PACK, entry, new)
            done += 1
    print(f'text: {paths.show(path)}: {sum(1 for r in table.values() if r["english"])} strings in {done} entries')


def verify():
    ok = True
    for entry, (table, stride, size) in RECORDS.items():
        data = entry_data(entry)
        n = struct.unpack_from('<I', data)[0]
        good = len(data) == HEADER + n * stride and not any(data[4:HEADER])
        for at, v in record_names(data, entry):
            try:
                v.decode('cp932')
            except UnicodeDecodeError:
                good = False
            good = good and not any(data[at + len(v):at + size])
        print(f'{entry} {table}: {n} records of {stride} bytes, ' + ('ok' if good else 'LAYOUT DIFFERS'))
        ok = ok and good
    for entry, kind in SHEETS.items():
        data = entry_data(entry)
        same = (kind == 'notice' or join_sheet(split_sheet(data)) == data) and rebuild(entry, data, {}) == data
        print(f'{entry} {kind}: split -> join ' + ('byte-identical' if same else 'DIFFERENT'))
        ok = ok and same
    if csv_path().exists():
        table = load()
        missing = {(t, f, j) for _, _, t, f, j, _ in originals()} - set(table)
        if missing:
            print(f'{paths.show(csv_path())}: {len(missing)} strings not in it, e.g. {sorted(missing)[0]} - dump again')
            ok = False
        glyphs = None
        try:
            import font
            d = paths.EXTRACTED / 'DATA' / 'KC2FIRE_000'
            raw = (d / f'{font.FONTS["sys"][0]:05d}.bin').read_bytes()
            n = (len(raw) - font.TABLE_AT) // 4
            offs = struct.unpack_from(f'<{n}I', raw, font.TABLE_AT)
            glyphs = {font.index_code(i) for i, o in enumerate(offs) if o != font.NONE}
        except OSError as e:
            sys.exit(f'font table not found ({e}) - run tools/extract.py first')
        bad = problems(table, glyphs)
        for m in bad:
            print('  ' + m)
        done = sum(1 for r in table.values() if r['english'])
        print(f'{paths.show(csv_path())}: {done} of {len(table)} rows in English' + (f', {len(bad)} problems' if bad else ', all fit'))
        ok = ok and not bad
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('dump'); s.add_argument('--force', action='store_true')
    sub.add_parser('verify')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'dump':
        dump(args.force)
        return 0
    return 0 if verify() else 1


if __name__ == '__main__':
    sys.exit(main())
