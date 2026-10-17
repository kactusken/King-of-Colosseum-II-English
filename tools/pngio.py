#!/usr/bin/env python3
"""Minimal PNG reader and indexed PNG writer (no dependencies), so build.py needs no Pillow.

read(path) -> Png with .width, .height, .rows (lists of pixel values),
.palette (list of (r, g, b) for indexed images, else None) and .alpha
(per-palette-entry alpha from tRNS, else None).

Pixel values are palette indices for indexed images and (r, g, b, a) tuples
for everything else. Supports colour types 0, 2, 3, 4, 6 at 8 bits (indexed
and grey also at 1/2/4 bits); no interlacing.

write(path, rows, palette, alpha=None) writes an 8-bit indexed PNG (rows of palette indices,
palette of (r, g, b), alpha per palette entry -> tRNS). Every frozen image in translation/ is an
indexed PNG in the game's palette, so the build imports pixel values directly.
"""
import struct
import zlib

CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class Png:
    pass


def _unfilter(raw, width, height, bpp, stride):
    rows, prev, p = [], bytearray(stride), 0
    for _ in range(height):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            elif f:
                raise ValueError(f'bad PNG filter {f}')
        rows.append(line)
        prev = line
    return rows


def read(path):
    d = open(path, 'rb').read()
    if d[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path}: not a PNG')
    i, idat, png = 8, b'', Png()
    png.palette = png.alpha = None
    while i < len(d):
        n, t = struct.unpack('>I4s', d[i:i + 8])
        c = d[i + 8:i + 8 + n]
        if t == b'IHDR':
            w, h, depth, ctype, _, _, interlace = struct.unpack('>IIBBBBB', c)
        elif t == b'PLTE':
            png.palette = [tuple(c[k:k + 3]) for k in range(0, len(c), 3)]
        elif t == b'tRNS' and ctype == 3:
            png.alpha = list(c)
        elif t == b'IDAT':
            idat += c
        i += 12 + n
    if interlace:
        raise ValueError(f'{path}: interlaced PNGs are not supported; save without interlacing')
    if depth != 8 and not (ctype in (0, 3) and depth in (1, 2, 4)):
        raise ValueError(f'{path}: {depth}-bit colour type {ctype} is not supported')
    ch = CHANNELS[ctype]
    stride = (w * ch * depth + 7) // 8
    lines = _unfilter(zlib.decompress(idat), w, h, max(1, ch * depth // 8), stride)
    rows = []
    for line in lines:
        if depth < 8:
            per, mask = 8 // depth, (1 << depth) - 1
            vals = [(line[x // per] >> (8 - depth * (x % per + 1))) & mask for x in range(w)]
        else:
            vals = list(line)
        if ctype == 3:
            rows.append(vals[:w])
        elif ctype == 0:
            scale = 255 // ((1 << depth) - 1)
            rows.append([(v * scale,) * 3 + (255,) for v in vals[:w]])
        elif ctype == 4:
            rows.append([(vals[k],) * 3 + (vals[k + 1],) for k in range(0, 2 * w, 2)])
        elif ctype == 2:
            rows.append([tuple(vals[k:k + 3]) + (255,) for k in range(0, 3 * w, 3)])
        else:
            rows.append([tuple(vals[k:k + 4]) for k in range(0, 4 * w, 4)])
    png.width, png.height, png.rows, png.indexed = w, h, rows, ctype == 3
    return png


def _chunk(t, c):
    return struct.pack('>I', len(c)) + t + c + struct.pack('>I', zlib.crc32(t + c))


def write(path, rows, palette, alpha=None):
    h, w = len(rows), len(rows[0]) if rows else 0
    raw = b''.join(b'\0' + bytes(r) for r in rows)
    out = b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 3, 0, 0, 0))
    out += _chunk(b'PLTE', b''.join(bytes(c[:3]) for c in palette))
    if alpha is not None:
        last = max((i for i, a in enumerate(alpha) if a != 255), default=-1)
        if last >= 0:
            out += _chunk(b'tRNS', bytes(alpha[:last + 1]))
    out += _chunk(b'IDAT', zlib.compress(raw, 9)) + _chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(out)
