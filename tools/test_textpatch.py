#!/usr/bin/env python3
"""Offline test of the ASCII text patch (tools/textpatch.py): runs the cave's routines in a tiny
EE-accurate interpreter (branch delay slots, no load delay - the R5900 interlocks loads).

  test_textpatch.py        every printable ASCII byte through the formatter hook, the lookup
                           and width hooks; other bytes must pass through unchanged

Exit status 1 on any mismatch. In check.py's CHECKS.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font  # noqa: E402
import textpatch  # noqa: E402

REG = {n: i for i, n in enumerate(
    ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3', 't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
     's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra'])}


class EE:
    """Just the integer instructions the cave uses."""

    def __init__(self, code, base):
        self.mem = {}
        for i, b in enumerate(code):
            self.mem[base + i] = b
        self.r = [0] * 32

    def lw(self, a):
        return sum(self.mem.get(a + i, 0) << (8 * i) for i in range(4))

    def run(self, pc, stop, limit=200):
        delay = None
        for _ in range(limit):
            if pc in stop and delay is None:
                return pc
            w = self.lw(pc)
            nxt = pc + 4 if delay is None else delay
            delay = None
            op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
            rd, sh, fn, imm = (w >> 11) & 31, (w >> 6) & 31, w & 63, w & 0xffff
            simm = imm - 0x10000 if imm & 0x8000 else imm
            r = self.r
            target = None
            if op == 0:
                if fn == 0:
                    r[rd] = (r[rt] << sh) & 0xffffffff
                elif fn == 2:
                    r[rd] = r[rt] >> sh
                elif fn in (0x21, 0x2d):           # addu / daddu (move)
                    r[rd] = (r[rs] + r[rt]) & 0xffffffff
                elif fn == 8:                      # jr
                    target = r[rs]
                else:
                    raise RuntimeError(f'unsupported funct {fn:#x} at {pc:#x}')
            elif op == 2 or op == 3:
                if op == 3:
                    r[31] = pc + 8
                target = (pc & 0xf0000000) | ((w & 0x3ffffff) << 2)
            elif op == 4:
                if r[rs] == r[rt]:
                    target = pc + 4 + (simm << 2)
            elif op == 9:
                r[rt] = (r[rs] + simm) & 0xffffffff
            elif op == 11:
                r[rt] = 1 if r[rs] < (simm & 0xffffffff) else 0
            elif op == 12:
                r[rt] = r[rs] & imm
            elif op == 15:
                r[rt] = (imm << 16) & 0xffffffff
            elif op == 37:                         # lhu
                a = (r[rs] + simm) & 0xffffffff
                r[rt] = self.mem.get(a, 0) | self.mem.get(a + 1, 0) << 8
            elif op == 40:                         # sb
                self.mem[(r[rs] + simm) & 0xffffffff] = r[rt] & 0xff
            else:
                raise RuntimeError(f'unsupported opcode {op:#x} at {pc:#x}')
            r[0] = 0
            if target is not None:
                delay = target
            pc = nxt
        raise RuntimeError('did not finish')


def expected(byte):
    codes = font.encode_text(chr(byte))
    return codes[0] if codes and codes[0] > 0xff else None


def main(argv=None):
    blob, syms = textpatch.build()
    bad = 0
    for byte in range(1, 0x100):
        want = expected(byte) if 0x21 <= byte <= 0x7e else None
        if byte == ord('"'):
            want = 0x8168      # single-byte " always draws the closing quote
        # formatter hook: a2 = byte, v0 = destination, s1 / s2 = source / output index
        ee = EE(blob, textpatch.CAVE)
        R = ee.r
        R[REG['a2']], R[REG['v0']], R[REG['s1']], R[REG['s2']] = byte, 0x7000, 0x5000, 10
        pc = ee.run(syms['fmt'], {textpatch.FMT_BACK})
        out = bytes(ee.mem.get(0x7000 + i, 0) for i in range(2))
        if want is None:
            ok = out[0] == byte and R[REG['s2']] == 11 and R[REG['s1']] == 0x5001
        else:
            ok = out == bytes((want >> 8, want & 0xff)) and R[REG['s2']] == 12 and R[REG['s1']] == 0x5001
        # lookup and width hooks: a1 = (byte << 8) | next byte; v1 / v0 = high byte of the result
        for name, back, res in (('lu', textpatch.LU_BACK, 'v1'), ('w', textpatch.W_BACK, 'v0')):
            ee2 = EE(blob, textpatch.CAVE)
            R2 = ee2.r
            R2[REG['a1']], R2[REG['ra']], R2[REG['t3']] = (byte << 8) | 0x41, 0x123450, 0
            ee2.run(syms[name], {back})
            code = want if want is not None else (byte << 8) | 0x41
            if R2[REG['a1']] != code or R2[REG[res]] != code >> 8 or R2[REG['ra']] != 0x123450 or R2[REG['t3']]:
                ok = False
        if not ok:
            bad += 1
            print(f'  byte 0x{byte:02x}: wrong result')
    print(f'ASCII text patch: 255 bytes through the formatter, lookup and width hooks - '
          + ('ok' if not bad else f'{bad} FAILED'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
