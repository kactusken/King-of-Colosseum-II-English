#!/usr/bin/env python3
"""Match Maker dialogue in KC2FIRE.000: the presidents' briefings, their verdicts after a show,
their advice, and the loading-screen tips.

  mmtalk.py dump [--force]     translation/text/mmtalk.txt (refuses to overwrite)
  mmtalk.py verify             every file: split -> join gives the original bytes, and the
                               game's parser (simulated) finds the expected items and pages
  mmtalk.py check [file]       the English: pages, lines, pixel widths and bytes (the build
                               step stops on the same problems), the widest line, and entries
                               that outgrow their sectors

Entries (one per promotion slot: New Japan, New Japan, NOAH, All Japan, ZERO-ONE, WJ, Pancrase,
New Japan - the copies are identical):
  2853-2860  briefings: what a Match Maker is, then each show's briefing   (parser 0x1d5600)
  2861-2876  verdicts after a show, 6 per show from best to worst           (parser 0x1df5a0)
  2877-2884  advice (the Advice menu): answers per topic, なし = no answer  (parser 0x1d58c4)
  2901       loading tips, one picked at random                             (reader 0x1b27ac)

Format (*from the code*): plain Shift-JIS text with CR LF. An item is a "quoted string" or an
unquoted line (headers such as 新日本（蝶野・藤波）, and なし, which the code compares against -
left as they are); blank lines between items don't count. In a string:
  ↓            ends a page (the CR LF after it is skipped); the player presses a button
  （笑）（怒）（気）  the speaker's expression for that page (1/2/3); any other （...） is skipped,
  （藤波）（井上）   the page is spoken by the second president (Fujinami / Masao Inoue)
  <...>        drawn in yellow (the draw routine 0x1cdf20 splits the line there)
  ○ × △ □      drawn as the controller button icons (20 px)
Pages are copied to 0xC0-byte buffers with no terminator of their own (the buffers start zeroed),
so a page holds at most 191 bytes; 16 pages per briefing string (0xC00 slots), 8 per verdict
(0x600; advice not traced - the English keeps the Japanese page count anyway). The page is
drawn line by line at 24 px spacing through 0x1b1410, which turns half-width letters, digits,
space and + - * / , . ' : ; ( ) into their full-width glyphs itself - so English goes in as ASCII,
one byte a letter (! ? and other punctuation full-width: 0x1b1410 copies an unlisted byte as half
of a two-byte character, and drops it at the end of a run). A tip is copied to a 128-byte buffer
(at most 127 bytes) and drawn through 0x1b1410 directly. The original text already uses
single-byte spaces in all of these.

Text file: one block per distinct string (the first place it occurs is the id, the other places are
listed after it; the build writes the English to every copy). The English is the text only - the
build puts each Japanese page's tags back at the end of the same English page, so the English
must have the same number of pages: end a page with ↓. "<...>" marks yellow text as in the
Japanese, opened and closed on the same line (the draw routine reads a yellow run up to the
">", across line ends). Limits (`check`): 3 lines a page (or as many as the Japanese page has),
624 px a line (the widest Japanese lines), 191 bytes a page; tips 2 lines, 570 px, 127 bytes.
An entry that grows past its sectors moves to the end of the pack (the loader allocates the
stored size from the pack table); a zero is kept after the text, where the parsers stop.
"""
import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import font  # noqa: E402
import paths  # noqa: E402
import pools  # noqa: E402

PACK = '/DATA/KC2FIRE.000'
# entry -> (kind, max pages)
ENTRIES = {**{k: ('briefing', 16) for k in range(2853, 2861)},
           **{k: ('verdict', 8) for k in range(2861, 2877)},
           **{k: ('advice', 16) for k in range(2877, 2885)},
           2901: ('tip', 1)}
PAGE_BYTES = 191            # 0xC0 buffer, zero-filled, no terminator written
TIP_BYTES = 127             # 128-byte buffer
LINE_PX, TIP_PX = 624, 570  # the widest Japanese lines
LINES, TIP_LINES = 3, 2
BUTTON_PX = 20              # ○ × △ □ are drawn as icons, 0x14 apart

DOWN = '↓'.encode('cp932')
OPEN, CLOSE = '（'.encode('cp932'), '）'.encode('cp932')
EMOTIONS = {'（笑）'.encode('cp932'): 1, '（怒）'.encode('cp932'): 2, '（気）'.encode('cp932'): 3}
SPEAKERS = ('（藤波）'.encode('cp932'), '（井上）'.encode('cp932'))
BUTTONS = '○×△□'
GAME_HALF = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 +-*/,.\':;()')
FONT_TABLE, FONT_GLYPHS = font.FONTS['sys']


def text_path():
    return paths.TEXT / 'mmtalk.txt'


def split(data):
    """[(is_string, bytes)]: string contents (between the quotes) and everything else, in order;
    joining the parts gives the data back."""
    out, i, raw = [], 0, bytearray()
    while i < len(data):
        if data[i] == 0x22:
            j = data.index(b'"', i + 1)
            raw.append(0x22)
            out.append((False, bytes(raw)))
            out.append((True, data[i + 1:j]))
            raw = bytearray(b'"')
            i = j + 1
        else:
            raw.append(data[i])
            i += 1
    out.append((False, bytes(raw)))
    return out


def join(parts):
    return b''.join(p for _, p in parts)


def strings(data):
    return [p for s, p in split(data) if s]


def game_items(data):
    """The items as the game's parser sees them: ('line', bytes) or ('string', pages), a page being
    (text bytes, emotion, second speaker). A byte-for-byte model of the loops at 0x1d5600/0x1df5a0."""
    items, i, n = [], 0, len(data)
    while i < n and data[i]:
        if data[i] == 0x22:
            i += 1
            pages, text, emo, spk = [], bytearray(), 0, 0
            while i < n and data[i] != 0x22:
                if data[i:i + 2] == DOWN:
                    i += 2
                    while i < n and data[i] in (0x0d, 0x0a):
                        i += 1
                    pages.append((bytes(text), emo, spk))
                    text, emo, spk = bytearray(), 0, 0
                elif data[i:i + 2] == OPEN:
                    if data[i:i + 6] in EMOTIONS:
                        emo = EMOTIONS[data[i:i + 6]]
                    elif data[i:i + 8] in SPEAKERS:
                        spk = 1
                    while data[i:i + 2] != CLOSE:
                        if i >= n:
                            raise ValueError('a （ without ）')
                        i += 1
                    i += 2
                else:
                    text.append(data[i])
                    i += 1
            pages.append((bytes(text), emo, spk))
            items.append(('string', pages))
            i += 1
        elif data[i] in (0x0d, 0x0a):
            i += 1
            continue
        else:
            j = i
            while j < n and data[j] not in (0x0d, 0x0a, 0):
                j += 1
            items.append(('line', data[i:j]))
            i = j
            continue
        while i < n and data[i] in (0x0d, 0x0a):
            i += 1
    return items


def decode(b):
    return b.decode('cp932').replace('\r\n', '\n')


def jp_pages(text):
    """Japanese string (decoded) -> [(page text, [tags])] as written (tags = the （...） runs in order)."""
    out = []
    for page in text.split('↓'):
        tags = re.findall('（[^）]*）', page)
        out.append((re.sub('（[^）]*）', '', page), tags))
    return out


def en_pages(english):
    pages = english.split('↓')
    return [p[1:] if k and p.startswith('\n') else p for k, p in enumerate(pages)]


def load_font(get):
    """The system font from the build's own KC2FIRE.000 (get(entry) -> bytes), for glyph widths."""
    f = font.Font.__new__(font.Font)
    f.table, f.glyphs = get(FONT_TABLE), get(FONT_GLYPHS)
    n = (len(f.table) - font.TABLE_AT) // 4
    f.offsets = struct.unpack_from(f'<{n}I', f.table, font.TABLE_AT)
    return f


def width(line, fnt):
    """Pixels a line takes as the game draws it (yellow markers dropped, buttons as icons)."""
    px = 0
    for ch in line.replace('<', '').replace('>', ''):
        if ch in BUTTONS:
            px += BUTTON_PX
        else:
            px += sum(2 * fnt.width(c)[1] for c in font.encode_text(ch.replace('"', '\u201d')))
    return px


def encode(text, glyphs, where):
    """English page text -> bytes: half-width where the game converts it itself, else Shift-JIS."""
    out, quotes = bytearray(), 0
    for ch in text:
        if ch == '\n':
            out += b'\r\n'
            continue
        if ch in GAME_HALF or ch in '<>':
            out.append(ord(ch))
            fw = [] if ch in ' <>' else font.encode_text(ch)
        else:
            if ch == '"':
                ch = '“' if quotes % 2 == 0 else '”'
                quotes += 1
            if ch in '（）↓':
                sys.exit(f'{where}: {ch!r} is a control character in this text - leave it out')
            try:
                fw = font.encode_text(ch)
            except ValueError as e:
                sys.exit(f'{where}: {e} - use another character')
            for c in fw:
                out += c.to_bytes(2, 'big') if c > 0xff else bytes([c])
        for c in fw:
            if c > 0xff and c not in glyphs:
                sys.exit(f'{where}: no glyph for {font.code_char(c)!r} in the game font - use another character')
    return bytes(out)


def entry_data(k):
    return (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000' / f'{k:05d}.bin').read_bytes()


def norm(text):
    """Source text as compared with the game's: trailing half-width spaces of a line don't count."""
    return '\n'.join(ln.rstrip(' ') for ln in text.split('\n'))


def dump(force=False):
    out = text_path()
    if out.exists() and not force:
        print(f'{paths.show(out)} exists - kept (--force to dump again and lose its English)')
        return
    seen, order = {}, []
    for k in ENTRIES:
        for i, s in enumerate(strings(entry_data(k))):
            key = norm(decode(s))
            if key not in seen:
                seen[key] = [f'{k}.{i}']
                order.append(key)
            else:
                seen[key].append(f'{k}.{i}')
    lines = ['# Match Maker dialogue: briefings, verdicts after a show, advice, loading tips.',
             '# KC2FIRE.000 entries 2853-2884 and 2901 - see tools/mmtalk.py (format, limits).',
             '# One block per distinct string; the id is where it first occurs, the rest are copies',
             '# that get the same English. Write the text only: ↓ ends a page and the English needs',
             '# as many pages as the Japanese; the build puts each page\'s tags (（笑）（怒）（気）',
             '# expression, （藤波）（井上） second speaker) back by itself. <...> = yellow text.',
             '# Limits: 3 lines a page (more only where the Japanese page has more), 624 px a line,',
             '# 191 bytes a page; tips (2901) 2 lines, 570 px, 127 bytes. python3 tools/mmtalk.py check', '']
    for key in order:
        ids = seen[key]
        lines.append(f'@ {ids[0]}' + (f' also {" ".join(ids[1:])}' if ids[1:] else ''))
        lines += [f'JP {ln}' if ln else 'JP' for ln in key.split('\n')]
        lines.append('')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    print(f'{paths.show(out)}: {len(order)} distinct strings')


def page_state(tags):
    """(emotion, second speaker) a page gets from its tags, as the parser sets them."""
    emo = spk = 0
    for t in tags:
        t = t.encode('cp932')
        if t in EMOTIONS:
            emo = EMOTIONS[t]
        elif t in SPEAKERS:
            spk = 1
    return emo, spk


def build_string(b, kind, src, glyphs, fnt, where):
    """(encoded string content, [(page bytes, emotion, speaker)] the parser must find, problems)."""
    jp = jp_pages(src)
    en = en_pages('\n'.join(b.english))
    if len(en) != len(jp):
        return None, None, [f'{len(en)} pages, the Japanese has {len(jp)} - end each page with ↓']
    tip = kind == 'tip'
    max_px, max_bytes = (TIP_PX, TIP_BYTES) if tip else (LINE_PX, PAGE_BYTES)
    problems, parts, expect = [], [], []
    for n, ((jtext, tags), etext) in enumerate(zip(jp, en), 1):
        body = encode(etext, glyphs, where)
        lines = etext.split('\n')
        max_lines = TIP_LINES if tip else max(LINES, len(jtext.strip('\n').split('\n')))
        if len(lines) > max_lines:
            problems.append(f'page {n}: {len(lines)} lines, room for {max_lines}')
        for ln in lines:
            w = width(ln, fnt)
            if w > max_px:
                problems.append(f'page {n}: {w} px, room for {max_px}: {ln!r}')
        if len(body) > max_bytes:
            problems.append(f'page {n}: {len(body)} bytes, room for {max_bytes}')
        if any(ln.count('<') != ln.count('>') for ln in lines):
            problems.append(f'page {n}: a <...> must open and close on the same line')
        parts.append(body + ''.join(tags).encode('cp932'))
        expect.append((body, *page_state(tags)))
    return (DOWN + b'\r\n').join(parts), expect, problems


def translations(path, get, glyphs, fnt):
    """{normalised Japanese: (encoded content, expected pages)} for every translated block; exits
    listing the problems if any English breaks a limit. get(entry) -> the entry's bytes."""
    bf = blocks.BlockFile(path)
    found = {f'{k}.{i}': s for k in ENTRIES for i, s in enumerate(strings(get(k)))}
    table, problems = {}, []
    for b in bf.blocks:
        where = f'{paths.show(path)}:{b.line}'
        if b.id not in found:
            sys.exit(f'{where}: block {b.id} - no such string in the game')
        src = decode(found[b.id])
        if norm(src) != '\n'.join(bf.source(b)):
            sys.exit(f'{where}: block {b.id} source text differs from the game\'s - dump again or fix the JP lines')
        if not b.english:
            continue
        content, expect, probs = build_string(b, ENTRIES[int(b.id.split('.')[0])][0], src, glyphs, fnt, where)
        problems += [f'{where} [{b.id}] {p}' for p in probs]
        if content is not None:
            table[norm(src)] = (content, expect)
    if problems:
        sys.exit('\n'.join(problems[:40]) + (f'\n... {len(problems)} problems' if len(problems) > 40 else ''))
    return table


def apply(data, table):
    """The entry with every translated string replaced; checks that the game's parser (simulated)
    finds the same items and exactly the intended pages, expressions and speakers."""
    parts, expect = split(data), []
    for n, (is_str, p) in enumerate(parts):
        if is_str:
            hit = table.get(norm(decode(p)))
            if hit:
                parts[n] = (True, hit[0])
            expect.append(hit[1] if hit else None)
    out = join(parts)
    if out != data and len(out) % 0x80 == 0:
        out += b'\0'            # the parsers stop at a zero: keep one after the text
    old, new = game_items(data), game_items(out)
    if [k for k, _ in old] != [k for k, _ in new]:
        raise ValueError('the items changed')
    got = [pg for k, pg in new if k == 'string']
    for e, g in zip(expect, got):
        if e is not None and g != e:
            raise ValueError(f'a string parses differently from what was written: {g!r}')
    return out


def step(path, files):
    """build.py text step: the Match Maker dialogue (path = translation/text/mmtalk.txt)."""
    get = lambda k: files.packs.get(PACK, k)  # noqa: E731
    table = translations(path, get, pools.font_codes(files.packs), load_font(get))
    done = moved = 0
    for k in ENTRIES:
        old = get(k)
        new = apply(old, table)
        if new != old:
            files.packs.put(PACK, k, new)
            done += 1
            moved += (len(new) + 0x7ff) // 0x800 > (len(old) + 0x7ff) // 0x800
    print(f'text: {paths.show(path)}: {len(table)} strings, {done} entries'
          + (f' ({moved} outgrow their sectors and move to the end of the pack)' if moved else ''))


def check(path):
    """The English against the limits; prints the widest line and entries that outgrow their sectors."""
    fnt = load_font(entry_data)
    glyphs = set(fnt.codes())
    table = translations(path, entry_data, glyphs, fnt)
    bf = blocks.BlockFile(path)
    lines = [ln for b in bf.blocks for ln in '\n'.join(b.english).replace('↓', '').split('\n') if b.english]
    widest = max(((width(ln, fnt), ln) for ln in lines), default=(0, ''))
    done = sum(1 for b in bf.blocks if b.english)
    print(f'{paths.show(path)}: {done}/{len(bf.blocks)} blocks translated, all within the limits; '
          f'widest line {widest[0]} px: {widest[1]!r}')
    for k in ENTRIES:
        old = entry_data(k)
        new = apply(old, table)
        if (len(new) + 0x7ff) // 0x800 > (len(old) + 0x7ff) // 0x800:
            print(f'  entry {k}: {len(old)} -> {len(new)} bytes, outgrows its sectors (moves to the end of the pack)')
    return 0


def verify():
    ok = True
    for k, (kind, max_pages) in ENTRIES.items():
        data = entry_data(k)
        same = join(split(data)) == data
        items = game_items(data)
        strs = [pg for t, pg in items if t == 'string']
        pages_ok = all(len(pg) <= max_pages for pg in strs) and \
            all(len(t) <= (TIP_BYTES if kind == 'tip' else PAGE_BYTES) for pg in strs for t, _, _ in pg)
        good = same and len(strs) == len(strings(data)) and pages_ok
        print(f'{k} {kind}: {len(items)} items ({len(strs)} strings), split -> join '
              + ('byte-identical' if same else 'DIFFERENT') + ('' if pages_ok else ', PAGE LIMITS EXCEEDED'))
        ok = ok and good
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('dump'); s.add_argument('--force', action='store_true')
    sub.add_parser('verify')
    s = sub.add_parser('check'); s.add_argument('file', nargs='?', type=Path, help='default: translation/text/mmtalk.txt')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if not (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000').exists():
        sys.exit(f'{paths.show(paths.EXTRACTED)}: no KC2FIRE_000 - run tools/extract.py first')
    if args.cmd == 'dump':
        dump(args.force)
        return 0
    if args.cmd == 'check':
        return check(args.file or text_path())
    return 0 if verify() else 1


if __name__ == '__main__':
    sys.exit(main())
