#!/usr/bin/env python3
"""Text in the executable (SLPM_656.02): menu strings, title histories, results, messages.

  elftext.py dump [--force]    translation/text/elf.txt (refuses to overwrite)
  elftext.py list              every string found, with its slot

Strings are found in the data area (from file offset 0x22a000): NUL-terminated runs of full-width
Shift-JIS text. English replaces each one IN PLACE - nothing is moved and no pointer changes:
- single-line strings are written as ASCII (drawn by the text patch, docs/PATCHES.md), so they
  get one byte per letter - about twice the room of the Japanese;
- multi-line strings are written full-width (the dialogs' line splitting needs it, see
  docs/TECHNICAL.md), so they must not be longer than the Japanese in bytes.
The slot is the string's own bytes, plus the zeros after it when the next non-zero byte starts
another string (padding between strings - it can't belong to a number or pointer), except in the
title-history records (0x230000-0x236000: 84-byte records, the champion's name in the first 74
bytes), where a name may use 73. The build stops on anything that doesn't fit.

Short strings the scan can't tell from data (fewer than two double-byte characters, or kanji
only: 邪道, 10分, %d人 ...) are listed by offset in INCLUDE; their slot follows the same padding
rule (the zeros up to the next non-zero byte, keeping one NUL). INCLUDE also replaces a scanned
run that starts inside one of them (0x2af420 Sハード: its half-width S isn't stray).

Left out (scope): the name-entry keyboards (0x2abc10-0x2ac600), the Dojo token tables
(0x2acdb0-0x2ace50, compared by code), the sort order and kana lists at
0x2a7200-0x2a7400, and the credit line at 0x2af078 (kept like the copyright picture). A run that
begins with stray ASCII bytes from the data before it starts at its first full-width character.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import elf  # noqa: E402
import font  # noqa: E402
import paths  # noqa: E402
import pools  # noqa: E402

FILE = '/SLPM_656.02'
SCAN_FROM = 0x22a000
EXCLUDE = [(0x2a7200, 0x2a7400), (0x2abc10, 0x2ac600), (0x2af078, 0x2af0b0),
           # the Dojo line splitter's token tables (「 」, ○ △ □ ×, Ｒ１ Ｒ２ Ｌ１ Ｌ２): compared by the
           # code to place button icons; build.py data-patches their first entries - never translate
           (0x2acdb0, 0x2ace50)]
RECORDS = (0x230000, 0x236000, 73)
# short strings found by hand (file offsets): champion names in the title-history records (a tag
# team record holds two 37-byte names, so these get the padding rule, not 73), time and score
# formats, match-settings values (time limits, points), Match Maker counters and labels, and the
# difficulty S-Hard (whose leading half-width S made the scan start one byte late)
INCLUDE = [0x231bf6, 0x231da4, 0x231dc9, 0x231ef4, 0x231f19, 0x231f9c, 0x231fc1, 0x233657,
           0x233b57, 0x233b86, 0x233bda, 0x233d4f,
           0x2af420, 0x2b02c0, 0x2d7a08,
           0x2e6180, 0x2e6188, 0x2e6190, 0x2e6198, 0x2e61a0, 0x2e61a8, 0x2e61b8, 0x2e61c0,
           0x2e6240, 0x2e6248, 0x2e6250, 0x2e6258, 0x2e6260, 0x2e6268, 0x2e6270,
           0x2e6300, 0x2e6328, 0x2e6480, 0x2e64b0, 0x2e6520, 0x2e6548, 0x2e6550, 0x2e6560,
           0x2e6578, 0x2e6970,
           0x2e5b50]   # ・ joining a foreign wrestler's names (0x1169e0, name type 2) - a space


def is_text(raw):
    try:
        t = raw.decode('cp932')
    except UnicodeDecodeError:
        return None
    if any(0xff61 <= ord(c) <= 0xff9f or (ord(c) < 0x20 and c != '\n') or ord(c) == 0x7f
           or 0xe000 <= ord(c) < 0xf900 for c in t):
        return None
    dbl = [c for c in t if ord(c) > 0x2000]
    if len(dbl) < 2:
        return None
    kana = sum(1 for c in dbl if 0x3040 <= ord(c) <= 0x30ff or 0xff01 <= ord(c) <= 0xff5e
               or c in '　、。・ー（）「」！？：％')
    if kana == 0 and len(dbl) < 3:
        return None
    return t


def find(data):
    """[(file offset, Japanese text, slot bytes)] for every display string."""
    out = []
    i = SCAN_FROM
    while i < len(data):
        if data[i] == 0:
            i += 1
            continue
        j = data.index(b'\0', i)
        t = is_text(bytes(data[i:j]))
        start = i
        if t and t[0].isascii() and t[0] not in '%':     # stray bytes before the text
            k = i
            while k < j and data[k] < 0x81:
                k += 1
            start, t = k, is_text(bytes(data[k:j]))
            i_ok = True
        else:
            i_ok = data[i - 1] == 0
        if t and i_ok and not any(a <= start < b for a, b in EXCLUDE):
            i, j0 = start, j
            slot = j - i
            if RECORDS[0] <= i < RECORDS[1]:
                slot = RECORDS[2]
            out.append((i, t, slot))
        i = j + 1
    # the INCLUDE strings, replacing any scanned run that starts inside one of them
    spans = [(o, data.index(b'\0', o)) for o in INCLUDE]
    out = [x for x in out if not any(a <= x[0] < b for a, b in spans)]
    out += [(o, bytes(data[o:e]).decode('cp932'), e - o) for o, e in spans]
    out.sort()
    # a string's padding is free when the next non-zero byte starts another string (string
    # arrays with fixed strides): the slot then runs up to that string, keeping one NUL
    starts = {o for o, _, _ in out}
    widened = []
    for o, t, slot in out:
        end = data.index(b'\0', o)
        k = end
        while k < len(data) and data[k] == 0:
            k += 1
        if o in INCLUDE:
            slot = max(slot, k - o - 1)
        elif k in starts and not RECORDS[0] <= o < RECORDS[1]:
            slot = max(slot, k - o - 1)
        widened.append((o, t, slot))
    return widened


def text_path():
    return paths.TEXT / 'elf.txt'


def dump(force=False):
    out = text_path()
    if out.exists() and not force:
        print(f'{paths.show(out)} exists - kept (--force to dump again and lose its English)')
        return
    data = (paths.EXTRACTED / FILE.lstrip('/')).read_bytes()
    lines = ['# Text in the executable (SLPM_656.02) - see tools/elftext.py.',
             '# Replaced in place. Single-line strings are stored as ASCII (1 byte a letter), multi-line ones',
             '# full-width (2 bytes). The block id is the file offset; "slot=N" is the room in bytes.', '']
    for off, t, slot in find(data):
        lines.append(f'@ {off:x} slot={slot}')
        lines += [f'JP {ln}' if ln else 'JP' for ln in t.split('\n')]
        lines.append('')
    out.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    print(f'{paths.show(out)}: {len(find(data))} strings')


def encode(text, glyphs, where):
    """Bytes for the English: ASCII if single-line (needs the text patch), else full-width."""
    if '\n' in text:
        return pools.encode(text, glyphs, where)
    if all(0x20 <= ord(c) < 0x7f for c in text):
        return text.encode('ascii')
    return pools.encode(text, glyphs, where)      # non-ASCII characters (symbols): full-width


def step(path, files):
    """build.py text step: write elf.txt's English into the executable in place."""
    data = files.get(FILE)
    bf = blocks.BlockFile(path)
    glyphs = pools.font_codes(files.packs)
    problems, done = [], 0
    for b in bf.blocks:
        if not b.english:
            continue
        off = int(b.id, 16)
        slot = int(b.meta.split('slot=')[1].split()[0])
        j = data.index(b'\0', off)
        if bytes(data[off:j]).decode('cp932', 'replace') != '\n'.join(bf.source(b)):
            problems.append(f'block {b.id}: the executable holds different text there - dump again')
            continue
        new = encode('\n'.join(b.english), glyphs, f'{paths.show(path)}:{b.line}')
        if len(new) > slot:
            problems.append(f'block {b.id}: {len(new)} bytes, room for {slot}: {" / ".join(b.english)!r}')
            continue
        old_len = j - off
        data[off:off + max(old_len, len(new))] = new + bytes(max(old_len, len(new)) - len(new))
        done += 1
    if problems:
        sys.exit(f'{paths.show(path)}:\n  ' + '\n  '.join(problems[:20]))
    files.put(FILE, data)
    print(f'text: {paths.show(path)}: {done} strings')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('dump'); s.add_argument('--force', action='store_true')
    sub.add_parser('list')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'dump':
        dump(args.force)
    else:
        data = (paths.EXTRACTED / FILE.lstrip('/')).read_bytes()
        e = elf.Elf(data)
        for off, t, slot in find(data):
            print(f'{off:#08x} (RAM {e.addr(off):#x}) slot {slot:3d}  {t[:60]!r}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
