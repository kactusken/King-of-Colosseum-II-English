#!/usr/bin/env python3
"""String pools in KC2FIRE.000: a pool of strings plus a separate table of u32 offsets into it.

  pools.py dump [--force]      translation/text/<name>.txt for every pool (refuses to overwrite)
  pools.py verify              every pool: read -> write gives the original bytes

Pools (entry numbers in KC2FIRE.000; strings / offsets):
  messages  1441 / 1442   system messages, title history, belt names
  actions   1443 / 1444   move categories and edit-mode help
  matches   1445 / 1446   match types, title matches, tournaments, rounds

Layout: the offset table has one u32 per string; the pool holds the strings in table order, each
NUL-terminated and padded to an even length (empty strings included). Strings are Shift-JIS with
0x0a for a new line and printf formats (%d). *From the data* - writing the pool back the same
way reproduces all three byte for byte (`verify`).

Text files: one block per non-empty string, id = its index in the table. A string's lines are the
block's lines; a final empty line (`EN` alone) is a trailing new line. English is stored as the
renderer needs it (tools/font.py encode_text): letters and punctuation full-width (2 bytes), spaces
and new lines 1 byte, %d formats as they are.
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import font  # noqa: E402
import paths  # noqa: E402

PACK = '/DATA/KC2FIRE.000'
POOLS = {
    'messages': (1441, 1442, 'System messages, title history, belt names'),
    'actions': (1443, 1444, 'Move categories and edit-mode help'),
    'matches': (1445, 1446, 'Match types, title matches, tournaments, rounds'),
}
FONT_TABLE = font.FONTS['sys'][0]


def read(pool, table):
    """The pool's strings (bytes, without the NUL) in table order."""
    offs = struct.unpack(f'<{len(table) // 4}I', table)
    return [bytes(pool[o:pool.index(0, o)]) for o in offs]


def write(strings):
    """(pool, table) bytes for a list of strings."""
    pool, offs = bytearray(), []
    for s in strings:
        offs.append(len(pool))
        pool += s + b'\0'
        if len(pool) % 2:
            pool += b'\0'
    return bytes(pool), struct.pack(f'<{len(offs)}I', *offs)


def text_path(name):
    return paths.TEXT / f'{name}.txt'


def dump(force=False):
    pak_dir = paths.EXTRACTED / 'DATA' / 'KC2FIRE_000'
    for name, (pk, tk, what) in POOLS.items():
        out = text_path(name)
        if out.exists() and not force:
            print(f'{paths.show(out)} exists - kept (--force to dump again and lose its English)')
            continue
        pool, table = (pak_dir / f'{pk:05d}.bin').read_bytes(), (pak_dir / f'{tk:05d}.bin').read_bytes()
        lines = [f'# {what}.', f'# KC2FIRE.000 entry {pk} (strings) / {tk} (offsets) - see tools/pools.py.',
                 '# Letters are stored full-width (2 bytes), spaces and new lines as 1 byte; keep %d codes.',
                 '# A block\'s lines are the string\'s lines; a final empty line is a trailing new line.', '']
        n = 0
        for i, s in enumerate(read(pool, table)):
            if not s:
                continue
            lines.append(f'@ {i}')
            lines += [f'JP {ln}' if ln else 'JP' for ln in s.decode('cp932').split('\n')]
            lines.append('')
            n += 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
        print(f'{paths.show(out)}: {n} strings')


def encode(text, glyphs, where):
    out = bytearray()
    if '\n' in text:
        # multi-line strings: full-width spaces. The game's line splitting for multi-line dialogs
        # breaks on single-byte spaces (lines merge and shift - verified in game, message 551).
        text = text.replace(' ', '\u3000')
    try:
        codes = font.encode_text(text)
    except ValueError as e:
        sys.exit(f'{where}: {e} - use another character')
    for k, code in enumerate(codes):
        if code >= 0x100:
            if code not in glyphs:
                sys.exit(f'{where}: no glyph for {font.code_char(code)!r} (0x{code:04x}) in the game font - use another character')
            nxt = codes[k + 1] if k + 1 < len(codes) else 0
            if code in GRID_TOKENS or code in GRID_PAIRS and nxt in GRID_PAIRS[code]:
                align(out)
            out += code.to_bytes(2, 'big')
        else:
            out.append(code)
    return bytes(out)


# Codes the Dojo line splitter 0x191290 looks for while stepping two bytes at a time (token tables
# at 0x3abdb0 / 0x3abe00: “ ” after the build's data patch, ○ △ □ ×, Ｒ１ Ｒ２ Ｌ１ Ｌ２). A token
# after an odd number of single-byte characters is missed: no button icon, or a yellow run that
# never ends (*verified in game*: Dojo goal "Rope Rebound" left the advice lines yellow). encode()
# keeps them on the grid by widening a space before them.
GRID_TOKENS = {0x8167, 0x8168, 0x819b, 0x81a2, 0x81a0, 0x817e}
GRID_PAIRS = {0x8271: {0x8250, 0x8251}, 0x826b: {0x8250, 0x8251}}


def align(out):
    """Put the next code on an even offset from the start of its line (the splitter works line by
    line): if needed, the line's last single-byte space becomes full-width. Text drawn by other
    routines doesn't care, so a line without a space to widen is left as it is."""
    line = max(out.rfind(b'\n'), out.rfind(b'\r')) + 1
    starts, j = [], line
    while j < len(out):
        starts.append(j)
        j += 2 if out[j] >= 0x81 else 1
    if (len(out) - line) % 2 == 0:
        return
    for i in reversed(starts):
        if out[i] == 0x20:
            out[i:i + 1] = b'\x81\x40'
            return


def font_codes(packs):
    """Shift-JIS codes the system font has a glyph for (from the build's own KC2FIRE.000)."""
    table = packs.get(PACK, FONT_TABLE)
    n = (len(table) - font.TABLE_AT) // 4
    offs = struct.unpack_from(f'<{n}I', table, font.TABLE_AT)
    return {font.index_code(i) for i, o in enumerate(offs) if o != font.NONE}


def step(path, files):
    """build.py text step: insert one pool's English (path = translation/text/<name>.txt)."""
    name = Path(path).stem
    pk, tk, _ = POOLS[name]
    packs = files.packs
    strings = read(packs.get(PACK, pk), packs.get(PACK, tk))
    bf = blocks.BlockFile(path)
    glyphs = font_codes(packs)
    done = 0
    for b in bf.blocks:
        if not b.english:
            continue
        i = int(b.id)
        src = strings[i].decode('cp932')
        if '\n'.join(bf.source(b)) != src:
            sys.exit(f'{paths.show(path)}:{b.line}: block {b.id} source text differs from the game\'s - '
                     f'dump again or fix the JP lines')
        en = '\n'.join(b.english)
        if src.endswith('\n') != en.endswith('\n'):
            sys.exit(f'{paths.show(path)}:{b.line}: block {b.id}: the original ' +
                     ('ends' if src.endswith('\n') else 'does not end') + ' with a new line (empty last line) - match it')
        strings[i] = encode(en, glyphs, f'{paths.show(path)}:{b.line}')
        done += 1
    pool, table = write(strings)
    packs.put(PACK, pk, pool)
    packs.put(PACK, tk, table)
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
    elif args.cmd == 'verify':
        pak_dir = paths.EXTRACTED / 'DATA' / 'KC2FIRE_000'
        ok = True
        for name, (pk, tk, _) in POOLS.items():
            if not (pak_dir / f'{pk:05d}.bin').exists():
                sys.exit(f'{paths.show(pak_dir)} not found - run tools/extract.py first')
            pool, table = (pak_dir / f'{pk:05d}.bin').read_bytes(), (pak_dir / f'{tk:05d}.bin').read_bytes()
            same = write(read(pool, table)) == (pool, table)
            print(f'{name}: read -> write ' + ('byte-identical' if same else 'DIFFERENT'))
            ok = ok and same
        return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
