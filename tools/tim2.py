#!/usr/bin/env python3
"""PS2 TIM2 (.tm2) images: read, export to indexed PNG, write pixels back. No dependencies.

  tim2.py info <file> [offset]               pictures: size, depth, palette
  tim2.py png <file> <out_prefix> [offset]   each picture -> <out_prefix>_<n>.png
  tim2.py find <file>...                     offsets of "TIM2" headers inside files (archives)

Layout: "TIM2" u8 version, u8 format (0: pictures start at 16, 1: at 128), u16 picture count; then
per picture a header (u32 total size, u32 CLUT size, u32 image size, u16 header size, u16 CLUT
colours, u8 picture format, u8 mipmaps, u8 CLUT type, u8 image type, u16 width, u16 height,
u64 GsTex0, u64 GsTex1, u32 GsRegs, u32 GsTexClut, user data up to header size), the pixels, the CLUT.
Image types: 1 = 16-bit, 2 = 24-bit, 3 = 32-bit, 4 = 4bpp indexed, 5 = 8bpp indexed. 4bpp pixels
are low nibble first. CLUT colours are 16- or 32-bit; alpha 0x80 means opaque (scaled to 255 here).
8-bit CLUTs in CSM1 order (CLUT type bit 0x80 clear) swap entries 8-15 and 16-23 of every 32 - the
palette given here is in index order, so PNG index n is pixel value n.

Only indexed pictures (4/8bpp) are exported and written back; mipmaps are left alone.

Swizzled pictures (King of Colosseum II's writer; image type 9 = 4bpp, 10 = 8bpp): the pixels are
stored as the GS would hold them after uploading the picture as PSMT4/PSMT8 and reading the same
memory back as PSMCT32 rows (w/2 x h/4, resp. w/2 x h/2). swizzle_map() models GS memory with the
standard block/column tables. 4bpp pictures with 32 CLUT entries and CLUT type bit 0x40 keep
their 16 colours in entries 0-7 and 16-23 (CSM1 layout).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pngio  # noqa: E402


class Picture:
    pass


def csm1(i):
    """CSM1 storage position of palette index i (8bpp)."""
    return i ^ ((i & 0x18) in (8, 16)) * 0x18

# --- GS memory layout (PSMCT32 / PSMT8 / PSMT4), for swizzled pictures -----------------------
_B32 = [[0, 1, 4, 5, 16, 17, 20, 21], [2, 3, 6, 7, 18, 19, 22, 23], [8, 9, 12, 13, 24, 25, 28, 29],
        [10, 11, 14, 15, 26, 27, 30, 31]]
_C32 = [[0, 1, 4, 5, 8, 9, 12, 13], [2, 3, 6, 7, 10, 11, 14, 15], [16, 17, 20, 21, 24, 25, 28, 29],
        [18, 19, 22, 23, 26, 27, 30, 31], [32, 33, 36, 37, 40, 41, 44, 45], [34, 35, 38, 39, 42, 43, 46, 47],
        [48, 49, 52, 53, 56, 57, 60, 61], [50, 51, 54, 55, 58, 59, 62, 63]]
_C8 = [[0, 4, 16, 20, 32, 36, 48, 52, 2, 6, 18, 22, 34, 38, 50, 54],
       [8, 12, 24, 28, 40, 44, 56, 60, 10, 14, 26, 30, 42, 46, 58, 62],
       [33, 37, 49, 53, 1, 5, 17, 21, 35, 39, 51, 55, 3, 7, 19, 23],
       [41, 45, 57, 61, 9, 13, 25, 29, 43, 47, 59, 63, 11, 15, 27, 31],
       [96, 100, 112, 116, 64, 68, 80, 84, 98, 102, 114, 118, 66, 70, 82, 86],
       [104, 108, 120, 124, 72, 76, 88, 92, 106, 110, 122, 126, 74, 78, 90, 94],
       [65, 69, 81, 85, 97, 101, 113, 117, 67, 71, 83, 87, 99, 103, 115, 119],
       [73, 77, 89, 93, 105, 109, 121, 125, 75, 79, 91, 95, 107, 111, 123, 127]]
_C8 += [[v + 128 for v in r] for r in _C8]
_B4 = [[0, 2, 8, 10], [1, 3, 9, 11], [4, 6, 12, 14], [5, 7, 13, 15], [16, 18, 24, 26], [17, 19, 25, 27],
       [20, 22, 28, 30], [21, 23, 29, 31]]
_C4 = [[0, 8, 32, 40, 64, 72, 96, 104, 2, 10, 34, 42, 66, 74, 98, 106, 4, 12, 36, 44, 68, 76, 100, 108, 6, 14,
        38, 46, 70, 78, 102, 110],
       [16, 24, 48, 56, 80, 88, 112, 120, 18, 26, 50, 58, 82, 90, 114, 122, 20, 28, 52, 60, 84, 92, 116, 124, 22,
        30, 54, 62, 86, 94, 118, 126],
       [65, 73, 97, 105, 1, 9, 33, 41, 67, 75, 99, 107, 3, 11, 35, 43, 69, 77, 101, 109, 5, 13, 37, 45, 71, 79,
        103, 111, 7, 15, 39, 47],
       [81, 89, 113, 121, 17, 25, 49, 57, 83, 91, 115, 123, 19, 27, 51, 59, 85, 93, 117, 125, 21, 29, 53, 61, 87,
        95, 119, 127, 23, 31, 55, 63]]
_C4 += [[192, 200, 224, 232, 128, 136, 160, 168, 194, 202, 226, 234, 130, 138, 162, 170, 196, 204, 228, 236, 132,
         140, 164, 172, 198, 206, 230, 238, 134, 142, 166, 174],
        [208, 216, 240, 248, 144, 152, 176, 184, 210, 218, 242, 250, 146, 154, 178, 186, 212, 220, 244, 252, 148,
         156, 180, 188, 214, 222, 246, 254, 150, 158, 182, 190],
        [129, 137, 161, 169, 193, 201, 225, 233, 131, 139, 163, 171, 195, 203, 227, 235, 133, 141, 165, 173, 197,
         205, 229, 237, 135, 143, 167, 175, 199, 207, 231, 239],
        [145, 153, 177, 185, 209, 217, 241, 249, 147, 155, 179, 187, 211, 219, 243, 251, 149, 157, 181, 189, 213,
         221, 245, 253, 151, 159, 183, 191, 215, 223, 247, 255]]
_C4 += [[v + 256 for v in r] for r in _C4]
_SWIZZLE_CACHE = {}


def _addr32(x, y, bw):
    page = (y // 32) * bw + x // 64
    return (page * 2048 + _B32[(y % 32) // 8][(x % 64) // 8] * 64 + _C32[y % 8][x % 8]) * 4


def swizzle_map(w, h, bpp):
    """For a swizzled picture: list m with m[y * w + x] = position of that pixel in the stored data
    (a byte index for 8bpp, a nibble index for 4bpp)."""
    key = (w, h, bpp)
    if key in _SWIZZLE_CACHE:
        return _SWIZZLE_CACHE[key]
    w32, h32 = w // 2, (h // 2 if bpp == 8 else h // 4)
    bw = max(1, (w32 + 63) // 64)
    mem_to_stored = {}
    i = 0
    for y in range(h32):
        for x in range(w32):
            a = _addr32(x, y, bw)
            for b in range(4):
                mem_to_stored[a + b] = i + b
            i += 4
    bwp = max(2, (w + 63) // 64)
    m = []
    for y in range(h):
        for x in range(w):
            if bpp == 8:
                page = (y // 64) * (bwp // 2) + x // 128
                a = page * 8192 + _B32[(y % 64) // 16][(x % 128) // 16] * 256 + _C8[y % 16][x % 16]
                m.append(mem_to_stored.get(a, -1))
            else:
                page = (y // 128) * (bwp // 2) + x // 128
                n = page * 16384 + _B4[(y % 128) // 16][(x % 128) // 32] * 512 + _C4[y % 16][x % 32]
                m.append(mem_to_stored[n >> 1] * 2 + (n & 1) if (n >> 1) in mem_to_stored else -1)
    if -1 in m:
        raise ValueError(f'{w}x{h} {bpp}bpp: swizzled layout not known for this size')
    _SWIZZLE_CACHE[key] = m
    return m



def parse(data, off=0):
    if data[off:off + 4] != b'TIM2':
        raise ValueError(f'no TIM2 header at {off:#x}')
    fmt, count = data[off + 5], struct.unpack_from('<H', data, off + 6)[0]
    p = off + (128 if fmt else 16)
    pics = []
    for n in range(count):
        pic = Picture()
        (pic.total, pic.clut_size, pic.image_size, pic.header_size, pic.colours, pic.format, pic.mipmaps,
         pic.clut_type, pic.image_type, pic.width, pic.height) = struct.unpack_from('<IIIHHBBBBHH', data, p)
        pic.header_at = p
        pic.pixels_at = p + pic.header_size
        pic.clut_at = pic.pixels_at + pic.image_size
        pic.bpp = {1: 16, 2: 24, 3: 32, 4: 4, 5: 8, 9: 4, 10: 8}.get(pic.image_type, 0)
        pic.swizzled = pic.image_type in (9, 10)
        pic.palette = None
        if pic.bpp in (4, 8) and pic.colours:
            depth = pic.clut_type & 0x3F
            size = {1: 2, 2: 3, 3: 4}.get(depth, 4)
            raw = []
            for i in range(pic.colours):
                q = pic.clut_at + i * size
                if size == 2:
                    c = struct.unpack_from('<H', data, q)[0]
                    raw.append(((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31,
                                255 if c & 0x8000 else 0))
                else:
                    r, g, b = data[q:q + 3]
                    a = min(255, data[q + 3] * 2) if size == 4 else 255
                    raw.append((r, g, b, a))
            swizzled = pic.bpp == 8 and not pic.clut_type & 0x80 and pic.colours >= 32
            if pic.bpp == 4 and pic.colours == 32 and pic.clut_type & 0x40:
                pic.palette = [raw[i if i < 8 else i + 8] for i in range(16)]
            else:
                pic.palette = [raw[csm1(i)] for i in range(pic.colours)] if swizzled else raw
        pics.append(pic)
        p += pic.total
    return pics


def indices(data, pic):
    """Rows of palette indices (4/8bpp pictures)."""
    w, h, at = pic.width, pic.height, pic.pixels_at
    if getattr(pic, 'swizzled', False):
        m = swizzle_map(w, h, pic.bpp)
        if pic.bpp == 8:
            flat = [data[at + i] for i in m]
        else:
            flat = [(data[at + (n >> 1)] >> (4 * (n & 1))) & 15 for n in m]
        return [flat[y * w:(y + 1) * w] for y in range(h)]
    if pic.bpp == 8:
        return [list(data[at + y * w:at + (y + 1) * w]) for y in range(h)]
    stride = (w + 1) // 2
    rows = []
    for y in range(h):
        line = data[at + y * stride:at + (y + 1) * stride]
        rows.append([(line[x // 2] >> (4 * (x & 1))) & 15 for x in range(w)])
    return rows


def put_indices(data, pic, rows):
    """Write rows of palette indices back into `data` (a bytearray) for a 4/8bpp picture."""
    if len(rows) != pic.height or any(len(r) != pic.width for r in rows):
        raise ValueError(f'picture is {pic.width}x{pic.height}, got {len(rows[0])}x{len(rows)}')
    top = 1 << pic.bpp
    if max(max(r) for r in rows) >= top:
        raise ValueError(f'pixel value >= {top} in a {pic.bpp}bpp picture')
    w, at = pic.width, pic.pixels_at
    if getattr(pic, 'swizzled', False):
        m = swizzle_map(w, pic.height, pic.bpp)
        flat = [v for r in rows for v in r]
        if pic.bpp == 8:
            for i, v in zip(m, flat):
                data[at + i] = v
        else:
            for n, v in zip(m, flat):
                q = at + (n >> 1)
                data[q] = (data[q] & (0xf0 if n & 1 == 0 else 0x0f)) | (v << (4 * (n & 1)))
        return
    if pic.bpp == 8:
        for y, r in enumerate(rows):
            data[at + y * w:at + (y + 1) * w] = bytes(r)
        return
    stride = (w + 1) // 2
    for y, r in enumerate(rows):
        line = bytearray(stride)
        for x, v in enumerate(r):
            line[x // 2] |= v << (4 * (x & 1))
        data[at + y * stride:at + (y + 1) * stride] = line


def to_png(data, pic, path):
    pngio.write(path, indices(data, pic), [c[:3] for c in pic.palette], [c[3] for c in pic.palette])


def find(data):
    i = data.find(b'TIM2')
    while i >= 0:
        if data[i + 4] in (3, 4) and data[i + 5] in (0, 1):
            yield i
        i = data.find(b'TIM2', i + 4)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == 'find':
        for p in argv[1:]:
            for off in find(Path(p).read_bytes()):
                print(f'{p}\t{off:#x}')
        return 0
    data = Path(argv[1]).read_bytes()
    off = int(argv[3 if cmd == 'png' else 2], 0) if len(argv) > (3 if cmd == 'png' else 2) else 0
    pics = parse(data, off)
    if cmd == 'info':
        for n, p in enumerate(pics):
            print(f'{n}: {p.width}x{p.height} {p.bpp}bpp, {p.colours} colours (CLUT type {p.clut_type:#x}), '
                  f'{p.mipmaps} mipmap(s)')
    elif cmd == 'png':
        for n, p in enumerate(pics):
            if p.palette is None:
                print(f'{n}: {p.bpp}bpp direct colour - skipped')
                continue
            out = f'{argv[2]}_{n}.png'
            to_png(data, p, out)
            print(out)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
