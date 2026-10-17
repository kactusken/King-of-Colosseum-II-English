#!/usr/bin/env python3
"""Estimate which addresses past a module's end its code touches (BSS).

Follows `lui reg, hi` through derivations of reg (addu/addiu with an index)
until reg is overwritten, collecting hi+lo for every load/store/addiu that
uses it as a base. Returns the referenced addresses above `end`.
"""
import struct


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def beyond_end(img, base, end, limit=0x80200000):
    n = len(img) // 4
    ws = struct.unpack_from(f'<{n}I', img, 0)
    found = set()
    for i, w in enumerate(ws):
        if w >> 26 != 15:
            continue
        regs = {(w >> 16) & 31}
        hi = (w & 0xFFFF) << 16
        for j in range(i + 1, min(i + 32, n)):
            w2 = ws[j]
            op, rs, rt, rd = w2 >> 26, (w2 >> 21) & 31, (w2 >> 16) & 31, (w2 >> 11) & 31
            if rs in regs and op in (9, 32, 33, 34, 35, 36, 37, 40, 41, 42, 43, 46):
                a = (hi + s16(w2 & 0xFFFF)) & 0xFFFFFFFF
                if end <= a < limit:
                    found.add(a)
            # derivation: addu d, reg, x  /  addu d, x, reg  keeps tracking d
            if op == 0 and (w2 & 63) in (33, 32) and (rs in regs or rt in regs):
                regs.add(rd)
                continue
            dst = rt if (op in range(8, 16) or op in range(32, 38)) else (rd if op == 0 else None)
            if dst is not None and dst in regs and not (op == 9 and rs in regs):
                regs.discard(dst)
            if not regs:
                break
    return sorted(found)
