#!/usr/bin/env python3
"""Dojo mode: the trainers' dialogue (KC2FIRE.000 entry 1455) - dump, check, build step.

  dojo.py dump [--force]    translation/text/dojo.txt: one block per page (refuses to overwrite)
  dojo.py verify            the entry has the layout below, the file's JP lines match it, every
                            English page fits, and writing no English gives the original bytes

The entry is an array of 0x58-byte records (1495), read in order by the Dojo screen (0x17ad90):
  +0x00  84 bytes  one line of text, NUL-padded Shift-JIS (empty in the marker records)
  +0x54  u16       1 = a text line, 0x63 = end of page (waits for a button),
                   0x270f = end of a section (a lesson menu / an exercise follows)
  +0x56  u16       speaker: 0 = Kotetsu Yamamoto, 1 = Kantaro Hoshino (the weapons lessons)
A page is up to three text records followed by a marker record. *From the code:* the page is
built line by line into ONE text object (each line appended as "%s\\n" through 0x1982b8, which
copies two bytes at a time), and each line is cut into segments by 0x191290, which steps through
the line two bytes at a time looking for 「 (opens a quote: the text up to 」 is drawn in yellow,
brackets included), ○ △ □ × and Ｒ１ Ｒ２ Ｌ１ Ｌ２ (drawn as button icons). So English is written
full-width, spaces included (U+3000): a single byte would shift every following token off the
two-byte grid, and this is a multi-line text object (single-byte spaces break those, docs/
TECHNICAL.md). R1/L1/R2/L2 and ○△□× in the English become icons, as in the original.

Limits per line (checked here and by the build): at most MAX_BYTES bytes (41 full-width
characters; the line must end with a NUL inside its 84 bytes and the segmenter reads the next two
bytes), and at most MAX_WIDTH pixels in the system font - the widest Japanese line. A page may
have fewer English lines than Japanese (the spare records are left empty and skipped by the game),
never more: the records and markers are not moved, because the game counts records.
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import font  # noqa: E402
import paths  # noqa: E402
import pools  # noqa: E402

PACK = '/DATA/KC2FIRE.000'
ENTRY = 1455
RECORD = 0x58
TEXT = 0x54
LINE, PAGE_END, SECTION_END = 1, 0x63, 0x270f
SPEAKERS = {0: 'Yamamoto', 1: 'Hoshino'}
ENDS = {PAGE_END: 'next', SECTION_END: 'section'}
MAX_BYTES = 82
MAX_WIDTH = 636   # pixels: the widest Japanese line (record 18), sys font, 2 * game width units

_font = None


def text_path():
    return paths.TEXT / 'dojo.txt'


def entry_data():
    return (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000' / f'{ENTRY:05d}.bin').read_bytes()


def width(text):
    """Pixel width of one line in the system font (the game's proportional width rule)."""
    global _font
    if _font is None:
        _font = font.Font('sys')
    return 2 * sum(_font.width(c)[1] for c in font.encode_text(text))


def record(data, i):
    """(text bytes, marker, speaker) of record i."""
    r = data[i * RECORD:(i + 1) * RECORD]
    marker, speaker = struct.unpack_from('<HH', r, TEXT)
    return bytes(r[:TEXT]).split(b'\0')[0], marker, speaker


def pages(data):
    """[(first record, [record indices of the text lines], speaker, end marker)]."""
    out, cur = [], []
    for i in range(len(data) // RECORD):
        _, marker, speaker = record(data, i)
        if marker == LINE:
            cur.append(i)
        else:
            if cur:
                out.append((cur[0], cur, record(data, cur[0])[2], marker))
            cur = []
    return out


def encode(text, glyphs, where):
    """English line -> bytes: everything full-width (2 bytes a character)."""
    b = pools.encode(text.replace(' ', '　'), glyphs, where)
    if len(b) % 2 or any(c < 0x81 for c in b[0::2]):
        sys.exit(f'{where}: {text!r} has a character the game can\'t store full-width - use another one')
    return b


def check_line(text, where):
    """Problems with one English line (list of strings)."""
    out = []
    n = len(font.encode_text(text.replace(' ', '　'))) * 2
    if n > MAX_BYTES:
        out.append(f'{where}: {n} bytes, room for {MAX_BYTES} ({MAX_BYTES // 2} characters): {text!r}')
    w = width(text.replace(' ', '　'))
    if w > MAX_WIDTH:
        out.append(f'{where}: {w} px wide, room for {MAX_WIDTH}: {text!r}')
    if text.count('「') != text.count('」'):
        out.append(f'{where}: unbalanced 「 」 (they mark the yellow text): {text!r}')
    return out


def dump(force=False):
    out = text_path()
    if out.exists() and not force:
        print(f'{paths.show(out)} exists - kept (--force to dump again and lose its English)')
        return
    data = entry_data()
    lines = ['# Dojo mode: the trainers\' dialogue, one block per page (Kotetsu Yamamoto; Kantaro Hoshino',
             '# teaches the weapons lessons). KC2FIRE.000 entry 1455 - see tools/dojo.py.',
             '# @ <first record> <speaker> <next = waits for a button | section = a menu or exercise follows>',
             f'# One EN line per JP line at most (fewer is fine). Each line: at most {MAX_BYTES // 2} characters',
             f'# and {MAX_WIDTH} px (python3 tools/dojo.py verify). Stored full-width; 「 」 mark yellow text',
             '# (brackets shown); R1 L1 R2 L2 ○ △ □ × are drawn as button icons.',
             f'# limit lines=3 chars={MAX_BYTES // 2}', '']
    ps = pages(data)
    for first, recs, speaker, end in ps:
        lines.append(f'@ {first} {SPEAKERS[speaker]} {ENDS[end]}')
        lines += [f'JP {record(data, i)[0].decode("cp932")}' for i in recs]
        lines.append('')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    print(f'{paths.show(out)}: {len(ps)} pages')


def apply(data, path, glyphs):
    """data with the English of `path` written in; (new data, pages done) - exits on problems."""
    data = bytearray(data)
    bf = blocks.BlockFile(path)
    by_first = {first: recs for first, recs, _, _ in pages(data)}
    problems, done = [], 0
    for b in bf.blocks:
        where = f'{paths.show(path)}:{b.line}'
        recs = by_first.get(int(b.id)) if b.id.isdigit() else None
        if recs is None:
            sys.exit(f'{where}: no page starts at record {b.id} - dump again')
        if bf.source(b) != [record(data, i)[0].decode('cp932') for i in recs]:
            sys.exit(f'{where}: page {b.id} source text differs from the game\'s - dump again or fix the JP lines')
        en = b.english
        if not en:
            continue
        if len(en) > len(recs):
            problems.append(f'{where}: {len(en)} lines, the page has {len(recs)}')
            continue
        bad = [p for t in en for p in check_line(t, where)]
        if bad:
            problems += bad
            continue
        for k, i in enumerate(recs):
            raw = encode(en[k], glyphs, where) if k < len(en) else b''
            data[i * RECORD:i * RECORD + TEXT] = raw.ljust(TEXT, b'\0')
        done += 1
    if problems:
        sys.exit('\n'.join(problems[:30]) + (f'\n... {len(problems) - 30} more' if len(problems) > 30 else ''))
    return bytes(data), done


def step(path, files):
    """build.py text step: write translation/text/dojo.txt into entry 1455."""
    packs = files.packs
    data, done = apply(packs.get(PACK, ENTRY), path, pools.font_codes(packs))
    packs.put(PACK, ENTRY, data)
    print(f'text: {paths.show(path)}: {done} pages')


class _Packs:
    def get(self, name, k):
        return (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000' / f'{k:05d}.bin').read_bytes()


def verify():
    data = entry_data()
    ok = True
    if len(data) % RECORD:
        print(f'{ENTRY}: size 0x{len(data):x} is not a multiple of 0x{RECORD:x}')
        ok = False
    widest = 0
    for i in range(len(data) // RECORD):
        r = data[i * RECORD:i * RECORD + TEXT]
        t, marker, speaker = record(data, i)
        if any(r[len(t):]) or marker not in (LINE, PAGE_END, SECTION_END) or speaker not in SPEAKERS \
                or (marker != LINE and t):
            print(f'record {i}: unexpected layout')
            ok = False
        if t:
            widest = max(widest, width(t.decode('cp932')))
    ps = pages(data)
    if any(len(recs) > 3 for _, recs, _, _ in ps):
        print('a page has more than three lines')
        ok = False
    if widest != MAX_WIDTH:
        print(f'widest Japanese line is {widest} px, MAX_WIDTH says {MAX_WIDTH}')
        ok = False
    print(f'{ENTRY}: {len(data) // RECORD} records, {len(ps)} pages, widest line {widest} px')
    p = text_path()
    if p.exists():
        glyphs = pools.font_codes(_Packs())
        bf = blocks.BlockFile(p)
        for b in bf.blocks:
            b.english = []
        tmp = paths.WORK / 'dojo_verify.txt'
        tmp.parent.mkdir(parents=True, exist_ok=True)
        bf.save(tmp)
        same, _ = apply(data, tmp, glyphs)
        tmp.unlink()
        print(f'{paths.show(p)}: no English -> ' + ('byte-identical' if same == data else 'DIFFERENT'))
        ok = ok and same == data
        new, done = apply(data, p, glyphs)
        print(f'{paths.show(p)}: {done}/{len(bf.blocks)} pages in English, all fit')
        for first, recs, _, _ in pages(data):
            for i in recs:       # the layout around the text stays as it was
                if new[i * RECORD + TEXT:(i + 1) * RECORD] != data[i * RECORD + TEXT:(i + 1) * RECORD]:
                    ok = False
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('dump')
    s.add_argument('--force', action='store_true')
    sub.add_parser('verify')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'dump':
        dump(args.force)
        return 0
    return 0 if verify() else 1


if __name__ == '__main__':
    sys.exit(main())
