#!/usr/bin/env python3
"""Indexed string tables in KC2FIRE.000: records pointing into a pool of NUL-terminated strings.

  tables.py dump [--force]      translation/text/<name>.txt for every table (refuses to overwrite)
  tables.py verify              every table: read -> write gives the original bytes

Tables (entry numbers in KC2FIRE.000):
  moves      2008   move names (the moveset list)
  wrestlers  2010   wrestler names, costume parts, theme music titles, ...
  movelist   2011   a second move list (CPU logic / move slots), mostly the same names

Layout: u32 A, u32 N, u32 S (pool size), u32 0; A group records of 8 bytes (left as they are);
N item records of a fixed size R = (file size - S - 16 - 8A) / N, each starting with the u32
offset of its string in the pool; then the pool: every string NUL-terminated, in order (one or
two strings no record points at are kept too). Writing rebuilds the pool from the strings in
order and rewrites each record's offset, so strings can be any length. *From the data* -
`verify` reproduces all three tables byte for byte.

Text files: one block per pool string, id = its index in the pool. English is stored as for the
other text (tools/font.py encode_text). The tables are drawn by the font in lists (move select,
wrestler select ...): keep names about as wide as the Japanese.
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import paths  # noqa: E402
import pools  # noqa: E402

PACK = pools.PACK
TABLES = {
    'moves': (2008, 'Move names (the moveset list)'),
    'wrestlers': (2010, 'Wrestler names, costume parts, theme music titles'),
    'movelist': (2011, 'A second move list (CPU logic / move slots)'),
}


def read(data):
    """(head, group bytes, records [(offset, rest bytes)], strings [bytes]) of a table."""
    a, n, s, z = struct.unpack_from('<4I', data, 0)
    base = len(data) - s
    items = 16 + 8 * a
    if z or (base - items) % n:
        raise ValueError('not an indexed string table')
    rs = (base - items) // n
    records = [(struct.unpack_from('<I', data, items + i * rs)[0], bytes(data[items + i * rs + 4:items + (i + 1) * rs]))
               for i in range(n)]
    pool = bytes(data[base:])
    if not pool.endswith(b'\0'):
        raise ValueError('string pool does not end with NUL')
    strings = pool[:-1].split(b'\0')
    return (a, n), bytes(data[16:items]), records, strings


def write(head, groups, records, strings, old_strings):
    """Table bytes with `strings` (same count as old_strings) in place of the old ones."""
    old_offs, pos = [], 0
    for s in old_strings:
        old_offs.append(pos)
        pos += len(s) + 1
    index = {o: i for i, o in enumerate(old_offs)}
    pool, offs = bytearray(), []
    for s in strings:
        offs.append(len(pool))
        pool += s + b'\0'
    a, n = head
    out = bytearray(struct.pack('<4I', a, n, len(pool), 0)) + groups
    for off, rest in records:
        if off not in index:
            raise ValueError(f'record points at 0x{off:x}, not at a string start')
        out += struct.pack('<I', offs[index[off]]) + rest
    return bytes(out + pool)


def dump(force=False):
    pak_dir = paths.EXTRACTED / 'DATA' / 'KC2FIRE_000'
    for name, (k, what) in TABLES.items():
        out = paths.TEXT / f'{name}.txt'
        if out.exists() and not force:
            print(f'{paths.show(out)} exists - kept (--force to dump again and lose its English)')
            continue
        _, _, _, strings = read((pak_dir / f'{k:05d}.bin').read_bytes())
        lines = [f'# {what}.', f'# KC2FIRE.000 entry {k} - see tools/tables.py.',
                 '# Letters are stored full-width (2 bytes), spaces as 1 byte. Keep names about as wide as the Japanese.', '']
        n = 0
        for i, s in enumerate(strings):
            if not s:
                continue
            lines += [f'@ {i}', f'JP {s.decode("cp932")}', '']
            n += 1
        out.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
        print(f'{paths.show(out)}: {n} strings')


def step(path, files):
    """build.py text step: insert one table's English (path = translation/text/<name>.txt)."""
    name = Path(path).stem
    k, _ = TABLES[name]
    packs = files.packs
    data = packs.get(PACK, k)
    head, groups, records, strings = read(data)
    new = list(strings)
    bf = blocks.BlockFile(path)
    glyphs = pools.font_codes(packs)
    done = 0
    for b in bf.blocks:
        if not b.english:
            continue
        i = int(b.id)
        if '\n'.join(bf.source(b)) != strings[i].decode('cp932'):
            sys.exit(f'{paths.show(path)}:{b.line}: block {b.id} source text differs from the game\'s - dump again')
        new[i] = pools.encode('\n'.join(b.english), glyphs, f'{paths.show(path)}:{b.line}')
        done += 1
    packs.put(PACK, k, write(head, groups, records, new, strings))
    print(f'text: {paths.show(path)}: {done} strings')


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
    pak_dir = paths.EXTRACTED / 'DATA' / 'KC2FIRE_000'
    ok = True
    for name, (k, _) in TABLES.items():
        p = pak_dir / f'{k:05d}.bin'
        if not p.exists():
            sys.exit(f'{paths.show(p)} not found - run tools/extract.py first')
        data = p.read_bytes()
        head, groups, records, strings = read(data)
        same = write(head, groups, records, strings, strings) == data
        print(f'{name}: read -> write ' + ('byte-identical' if same else 'DIFFERENT'))
        ok = ok and same
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
