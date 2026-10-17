#!/usr/bin/env python3
"""Code patch: the game's text renderer accepts single-byte ASCII (drawn with the full-width glyphs).

  textpatch.py show          the patch sites, the assembled cave and the ASCII -> Shift-JIS table

The renderer only draws two-byte Shift-JIS; a single byte other than space / new line draws
nothing (docs/TECHNICAL.md "How it's drawn"). Fixed-size fields (the roster names) are too small
for English at two bytes a letter, so three hooks make ASCII work, using the same glyphs:

  0x10c65c  text formatter (every drawn string is copied through it into a buffer before the draw
            loop): a printable ASCII byte 0x21-0x7e is written as its full-width two-byte code;
            other single bytes are copied as before. The draw loop then sees normal Shift-JIS.
  0x10cc20  glyph lookup, and
  0x10ccf0  glyph width: a code whose high byte is printable ASCII (a raw string measured for
            centring by one of the ~10 callers of the measure routine 0x10cf90) is mapped to the
            full-width code first, so widths match what is drawn.

The hooks jump to a cave at 0x31e2b8, an unreferenced 520-byte library routine (no call, jump,
pointer or built address anywhere in the ELF), which holds the three routines and the 94-entry
table. The mapping is tools/font.py's: ' -> ’, " -> ”, - -> －, ~ -> ～, the rest U+FF01-FF5E.
Registers: only t4-t6 (the hooked routines don't use them; t0-t3 are live in the width routine).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mips_asm  # noqa: E402

FILE = 'SLPM_656.02'
CAVE = 0x31e2b8
CAVE_SIZE = 520

FMT_SITE = 0x10c65c       # addiu s2,s2,1 / sb a2,0(v0)   (v0 = buffer + s2, a2 = the byte)
FMT_BACK = 0x10c6bc       # loop continue
LU_SITE = 0x10cc20        # srl v1,a1,8 / addiu sp,sp,-0x10
LU_BACK = 0x10cc28
W_SITE = 0x10ccf0         # srl v0,a1,8 / move t3,zero
W_BACK = 0x10ccf8

# original words at the hook sites (checked by the build before writing)
ORIGINAL = {FMT_SITE: (0x26520001, 0xa0460000), LU_SITE: (0x00051a02, 0x27bdfff0),
            W_SITE: (0x00051202, 0x0000582d)}
# the cave's original bytes (an unreferenced library routine) - SHA-1, checked by the build
CAVE_SHA1 = '301b5df49c22b1a70ef4e20169d03891ef6202c4'


def table():
    """94 Shift-JIS codes for ASCII 0x21-0x7e, as tools/font.py encodes English."""
    subst = {"'": '’', '"': '”', '-': '－', '~': '～'}
    out = []
    for c in range(0x21, 0x7f):
        ch = subst.get(chr(c), chr(c + 0xfee0))
        b = ch.encode('cp932')
        out.append(b[0] << 8 | b[1])
    return out


SOURCE = '''
fmt:                        # a2 = byte, v0 = destination
    addiu $t4, $a2, -0x21
    sltiu $t4, $t4, 0x5e
    beq $t4, $zero, fmt_plain
    nop
    addiu $t4, $a2, -0x21
    sll $t4, $t4, 1
    lui $t5, %hi(TABLE)
    addiu $t5, $t5, %lo(TABLE)
    addu $t5, $t5, $t4
    lhu $t6, 0($t5)
    srl $t5, $t6, 8
    sb $t5, 0($v0)
    sb $t6, 1($v0)
    addiu $s2, $s2, 2
    j FMT_BACK
    addiu $s1, $s1, 1
fmt_plain:
    addiu $s2, $s2, 1
    sb $a2, 0($v0)
    j FMT_BACK
    addiu $s1, $s1, 1

map:                        # a1 = code; ASCII high byte -> full-width code. Uses t4-t6.
    srl $t4, $a1, 8
    andi $t4, $t4, 0xff
    addiu $t5, $t4, -0x21
    sltiu $t5, $t5, 0x5e
    beq $t5, $zero, map_done
    sll $t5, $t4, 1
    lui $t6, %hi(TABLE-0x42)
    addiu $t6, $t6, %lo(TABLE-0x42)
    addu $t6, $t6, $t5
    lhu $a1, 0($t6)
map_done:
    jr $ra
    nop

lu:                         # replaces srl v1,a1,8 (sp already adjusted in the delay slot)
    move $t7, $ra
    jal map
    nop
    move $ra, $t7
    srl $v1, $a1, 8
    j LU_BACK
    nop

w:                          # replaces srl v0,a1,8 (t3 already cleared in the delay slot)
    move $t7, $ra
    jal map
    nop
    move $ra, $t7
    srl $v0, $a1, 8
    j W_BACK
    nop
'''


def build():
    """(cave bytes, label addresses) - the routines followed by the table."""
    src = SOURCE + '\nTABLE:\n' + '\n'.join('    .half ' + ', '.join(f'0x{c:04x}' for c in table()[i:i + 8])
                                          for i in range(0, 94, 8)) + '\n'
    blob, syms = mips_asm.assemble(src, CAVE, {'FMT_BACK': FMT_BACK, 'LU_BACK': LU_BACK, 'W_BACK': W_BACK})
    if len(blob) > CAVE_SIZE:
        raise SystemExit(f'textpatch: cave needs {len(blob)} bytes, only {CAVE_SIZE}')
    return blob, syms


def hooks(syms):
    """The three hook sites. Formatter: j fmt + nop (the cave does both original instructions).
    Lookup/width: j <hook>, keeping their original second instruction in the delay slot."""
    def j(target):
        return (2 << 26) | ((target >> 2) & 0x3ffffff)
    return {FMT_SITE: struct.pack('<II', j(syms['fmt']), 0),
            LU_SITE: struct.pack('<II', j(syms['lu']), ORIGINAL[LU_SITE][1]),
            W_SITE: struct.pack('<II', j(syms['w']), ORIGINAL[W_SITE][1])}


def patches():
    """CODE_PATCHES-style entries (group, file, address, original, new, description); the cave's
    original is checked by CAVE_SHA1 (original None)."""
    blob, syms = build()
    out = [('text', FILE, addr, struct.pack('<II', *ORIGINAL[addr]), new, None) for addr, new in hooks(syms).items()]
    out.append(('text', FILE, CAVE, None, blob, 'ASCII text: the renderer draws single-byte letters'))
    return out


def main(argv=None):
    blob, syms = build()
    print(f'cave 0x{CAVE:x}: {len(blob)}/{CAVE_SIZE} bytes, table at 0x{syms["TABLE"]:x}')
    for name in ('fmt', 'map', 'lu', 'w'):
        print(f'  {name} at 0x{syms[name]:x}')
    for addr, new in hooks(syms).items():
        print(f'  hook 0x{addr:x}: {new.hex()}')
    t = table()
    print('  table: ' + ' '.join(f'{chr(0x21 + i)}={c:04x}' for i, c in enumerate(t[:12])) + ' ...')
    return 0


if __name__ == '__main__':
    sys.exit(main())
