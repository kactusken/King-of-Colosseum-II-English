#!/usr/bin/env python3
"""The game's fonts: CMP1 (byte pair encoding) glyphs, the PiW code table, the game's width rule.

  font.py info                        both fonts: glyph count, code range
  font.py sheet <out.png> [--font F]  every glyph, 64 per row from code 0x8140 (indexed PNG)
  font.py preview <out.png> <text>... render lines as the game lays them out (--fixed: no
                                      measuring); ASCII is shown as full-width, spaces stay 0x20
  font.py verify [--font F]           every glyph: decode, encode -> decode gives it back

Fonts (pack KC2FIRE.000, loaded as pairs by 0x197be8): `sys` = table 1436 + glyphs 1437 (7,352
glyphs, the whole of Shift-JIS plus button icons), `dojo` = 1438 + 1439 (617 glyphs).

Table (PiW file): from 0xc0, one u32 per code: the glyph's offset in the glyph file, or -1.
Index = code - 0x8140 for codes up to 0x9fff, code - 0xc180 above (routine 0x10cc20).
Glyph: "CMP1", u32 unpacked size (0x200), then byte pair encoding blocks (Philip Gage's expander,
routine 0x10a408) until that many bytes are out. A block: the pair table (a count byte > 127
skips count - 127 codes and then reads one entry, otherwise count + 1 entries follow; an entry
is `left`, plus `right` when left != the code), a u16 BE length, then that many bytes, each
expanded recursively. Unpacked glyph: 32 x 32, 4bpp (low nibble = left pixel), 16 bytes a row.

Widths (routine 0x10ccf0, in 2-pixel units): with the text's proportional flag set, a glyph is
measured from its leftmost lit byte-column - 1 to its rightmost + 2 (a nibble counts as lit
from value 2 up), capped at 12 for kana, kanji and some symbol blocks and at 8 for everything
else (Latin included); otherwise 12 or 8 fixed. 0x8140 = 8, single byte 0x20 = 4, single byte
0x0a = new line; any other single byte draws nothing and takes no room. *From the code.*
"""
import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
import pngio  # noqa: E402

FONTS = {'sys': (1436, 1437), 'dojo': (1438, 1439)}
TABLE_AT = 0xc0
GLYPH_SIZE = 0x200
NONE = 0xffffffff


def code_index(code):
    return code - 0x8140 if code <= 0x9fff else code - 0xc180


def index_code(i):
    return i + 0x8140 if i + 0x8140 <= 0x9fff else i + 0xc180


def expand(src, size, i=0):
    """Byte pair decoding as the game does it; returns (bytes, end offset in src)."""
    out = bytearray()
    while len(out) < size:
        left = list(range(256))
        right = [0] * 256
        c = 0
        while True:
            count = src[i]
            i += 1
            if count > 127:
                c += count - 127
                count = 0
            if c == 256:
                break
            for _ in range(count + 1):
                left[c] = src[i]
                i += 1
                if left[c] != c:
                    right[c] = src[i]
                    i += 1
                c += 1
            if c == 256:
                break
        n = src[i] << 8 | src[i + 1]
        i += 2
        for _ in range(n):
            stack = [src[i]]
            i += 1
            while stack:
                b = stack.pop()
                if left[b] == b:
                    out.append(b)
                else:
                    stack.append(right[b])
                    stack.append(left[b])
    return bytes(out), i


def compress(data):
    """Byte pair encoding of `data` (one block, up to 0xffff bytes) for expand()."""
    if len(data) > 0xffff:
        sys.exit('font.compress: data over 0xffff bytes - split it into blocks first')
    buf = list(data)
    left = list(range(256))
    right = [0] * 256
    free = [c for c in range(256) if c not in set(buf)]
    while free:
        counts = {}
        for a, b in zip(buf, buf[1:]):
            counts[(a, b)] = counts.get((a, b), 0) + 1
        if not counts:
            break
        pair, n = max(counts.items(), key=lambda kv: (kv[1], -kv[0][0], -kv[0][1]))
        if n < 3:           # a pair costs 2-3 table bytes: not worth it below 3 uses
            break
        code = free.pop(0)
        left[code], right[code] = pair
        out, k = [], 0
        while k < len(buf):
            if k + 1 < len(buf) and (buf[k], buf[k + 1]) == pair:
                out.append(code)
                k += 2
            else:
                out.append(buf[k])
                k += 1
        buf = out
    table = bytearray()
    c = 0
    while c < 256:
        run = 0
        while c + run < 256 and left[c + run] == c + run and run < 128:
            run += 1
        if run:                                     # skip literal codes ...
            table.append(127 + run)
            c += run
            if c == 256:
                break
            n = 1                                   # ... then one entry is always read
        else:
            n = 0
            while c + n < 256 and n < 128 and not (left[c + n] == c + n and
                                                   c + n + 1 < 256 and left[c + n + 1] == c + n + 1):
                n += 1
            table.append(n - 1)
        for k in range(c, c + n):
            table.append(left[k])
            if left[k] != k:
                table.append(right[k])
        c += n
    return bytes(table) + struct.pack('>H', len(buf)) + bytes(buf)


class Font:
    def __init__(self, name='sys', table=None, glyphs=None):
        ti, gi = FONTS[name]
        d = paths.EXTRACTED / 'DATA' / 'KC2FIRE_000'
        tp, gp = Path(table or d / f'{ti:05d}.bin'), Path(glyphs or d / f'{gi:05d}.bin')
        if not tp.exists() or not gp.exists():
            sys.exit(f'{tp} or {gp} not found - run tools/extract.py first')
        self.table, self.glyphs = tp.read_bytes(), gp.read_bytes()
        n = (len(self.table) - TABLE_AT) // 4
        self.offsets = struct.unpack_from(f'<{n}I', self.table, TABLE_AT)

    def codes(self):
        return [index_code(i) for i, o in enumerate(self.offsets) if o != NONE]

    def glyph(self, code):
        i = code_index(code)
        if code < 0x100 or not 0 <= i < len(self.offsets) or self.offsets[i] == NONE:
            return None
        o = self.offsets[i]
        if self.glyphs[o:o + 4] != b'CMP1':
            sys.exit(f'font: code 0x{code:04x} points at 0x{o:x}, which is not a CMP1 record')
        return expand(self.glyphs, struct.unpack_from('<I', self.glyphs, o + 4)[0], o + 8)[0]

    def width(self, code, proportional=True):
        """(first byte-column drawn, width) in 2-pixel units, as routine 0x10ccf0."""
        cache = self.__dict__.setdefault('_widths', {})   # each glyph is unpacked once
        key = (code, proportional)
        if key not in cache:
            cache[key] = self._width(code, proportional)
        return cache[key]

    def _width(self, code, proportional):
        if code < 0x100:
            return 0, {0x20: 4}.get(code, 0)
        if code == 0x8140:
            return 0, 8
        wide = (code > 0x875e or 0 <= code - 0x829f < 0x53 or 0 <= code - 0x81b0 < 8
                or 0 <= code - 0x81c0 < 8 or 0 <= code - 0x81d0 < 10)
        cap = 12 if wide else 8
        g = self.glyph(code) if proportional else None
        if g is None:
            return 0, cap
        lit = [c for c in range(16) if any(g[r * 16 + c] & 0xee for r in range(32))]
        if not lit:
            return 0, cap
        first = max(lit[0] - 1, 0)
        return first, max(min(lit[-1] + 2, cap) - first, 0)


# ASCII characters whose full-width form (U+FF01-FF5E) isn't in the font (cp932 puts it in the IBM
# extension rows, which the font lacks): use these instead.
SUBSTITUTES = {"'": '\u2019', '-': '\uff0d', '~': '\uff5e'}   # " alternates \u201c / \u201d
FORMAT = re.compile(r'%[-0-9.]*[dsx]')


def encode_text(s):
    """English text -> game codes: printable ASCII as full-width Shift-JIS, spaces, new lines and
    printf formats (%d) as single bytes. Non-ASCII characters are taken as they are (Shift-JIS)."""
    out = []
    pos = 0
    quotes = 0
    for m in list(FORMAT.finditer(s)) + [None]:
        part = s[pos:m.start() if m else len(s)]
        for ch in part:
            if ch in ' \n':
                out.append(ord(ch))
                continue
            if ch == '\u3000':               # explicit full-width space (2 bytes)
                out.append(0x8140)
                continue
            if ch == '"':
                ch = '\u201c' if quotes % 2 == 0 else '\u201d'
                quotes += 1
            ch = SUBSTITUTES.get(ch, ch)
            if 0x21 <= ord(ch) < 0x7f:
                ch = chr(ord(ch) + 0xfee0)
            try:
                b = ch.encode('cp932')
            except UnicodeEncodeError:
                raise ValueError(f'{ch!r} has no Shift-JIS code')
            out.append(b[0] << 8 | b[1] if len(b) == 2 else b[0])
        if m:
            out += m.group().encode('ascii')
            pos = m.end()
    return out


def code_char(code):
    return code.to_bytes(2, 'big').decode('cp932', 'replace') if code > 0xff else chr(code)


PALETTE = [(255 - v * 17,) * 3 for v in range(16)]


def draw(font, codes, img, x0, y0, proportional=True):
    x = x0
    for code in codes:
        first, w = font.width(code, proportional)
        g = font.glyph(code)
        if g:
            for y in range(32):
                for c in range(first, min(first + w, 16)):
                    for k in (0, 1):
                        px = x + (c - first) * 2 + k
                        if 0 <= px < len(img[0]):
                            img[y0 + y][px] = max(img[y0 + y][px], g[y * 16 + c] >> 4 * k & 15)
        x += w * 2
    return x - x0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('info')
    s = sub.add_parser('sheet'); s.add_argument('out'); s.add_argument('--font', default='sys', choices=FONTS)
    s = sub.add_parser('preview'); s.add_argument('out'); s.add_argument('text', nargs='+')
    s.add_argument('--font', default='sys', choices=FONTS); s.add_argument('--fixed', action='store_true')
    s = sub.add_parser('verify'); s.add_argument('--font', choices=FONTS)
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'info':
        for name in FONTS:
            codes = Font(name).codes()
            print(f'{name}: {len(codes)} glyphs, codes 0x{codes[0]:04x}-0x{codes[-1]:04x}')
    elif args.cmd == 'sheet':
        f = Font(args.font)
        idx = [code_index(c) for c in f.codes()]
        rows = idx[-1] // 64 + 1
        img = [[0] * (64 * 33) for _ in range(rows * 33)]
        for code in f.codes():
            i = code_index(code)
            g = f.glyph(code)
            for y in range(32):
                for x in range(32):
                    img[i // 64 * 33 + y][i % 64 * 33 + x] = g[y * 16 + x // 2] >> 4 * (x & 1) & 15
        pngio.write(args.out, img, PALETTE, [255] * 16)
        print(f'{len(idx)} glyphs -> {args.out} (row r, column c = index 64r + c; code = index + 0x8140, '
              f'+ 0xc180 from index 0x1ec0)')
    elif args.cmd == 'preview':
        f = Font(args.font)
        lines = [encode_text(t) for t in args.text]
        width = max(sum(f.width(c, not args.fixed)[1] for c in ln) for ln in lines) * 2 + 8
        img = [[0] * width for _ in range(36 * len(lines))]
        for n, ln in enumerate(lines):
            px = draw(f, ln, img, 4, n * 36, not args.fixed)
            print(f'{px:4d} px  {args.text[n]}')
        pngio.write(args.out, img, PALETTE, [255] * 16)
    elif args.cmd == 'verify':
        ok = True
        for name in [args.font] if args.font else FONTS:
            f = Font(name)
            bad = 0
            for code in f.codes():
                g = f.glyph(code)
                if len(g) != GLYPH_SIZE or expand(compress(g), len(g))[0] != g:
                    bad += 1
            print(f'{name}: {len(f.codes())} glyphs, encode -> decode ' + ('ok' if not bad else f'{bad} FAILED'))
            ok = ok and not bad
        return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
