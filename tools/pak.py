#!/usr/bin/env python3
"""The game's own packs (KC2FIRE.000, .001, .MVS): table, LZSS compression, unpack and repack.

  pak.py info <pack>                       entry count, types, compressed share
  pak.py unpack <pack> <dir> [--raw]       entry k -> <dir>/NNNNN.<ext> (decompressed), plus pak.json
  pak.py get <pack> <index> <out>          one entry, decompressed
  pak.py verify <pack> [--lz N]            repack with nothing changed == original; and LZSS
                                           compress -> decompress == input on every Nth entry (default 50)

Layout (u32 LE): 0x800, count N, N x (offset, stored size, size, flags); the table is zero-padded to
the next 0x800 boundary (the data base) and offsets count from there. Entries are contiguous in
index order, each 0x80-aligned and zero-padded. flags: low u16 = group size - the game loads that
many consecutive entries with one read from the first one's offset (0x28aff8 / 0x28b178), so a
group must stay contiguous. Every group starts on a 0x800 boundary and spans whole sectors (the
last entry's stored size carries the padding; 23,082 of 23,082 groups) - the game reads groups
in whole sectors into a buffer of the stored size, so breaking this overruns it (crashed at boot
in a test build). bit 16 = LZSS-compressed, in which case `size` is the unpacked size
(what the game allocates). *From the code.*

LZSS (the game's decoder is 0x28a338): a flag byte, low bit first, 1 = literal byte, 0 = two
bytes a, b: copy (b >> 4) + 2 bytes from ring position a | (b & 0x0f) << 8. 4 KB ring,
zero-filled, written from position **1** (output byte i sits at position (i + 1) & 0xfff), so
position 0 is never written: a copy from it is the end marker. Every original stream ends with
one (20,182 of 20,182). In about half the entries it comes before `size` bytes (size is then
the length rounded up to 0x80) and the rest is zero. *From the code*, checked on the data.
unpack writes the full `size` bytes, zero-filled; uncompressed entries are cut to `size` (the
rest of the stored block is padding).

Repacking (pack()) keeps every unchanged entry's bytes and offset, so an unchanged pack is
byte-identical; changed entries are compressed by compress() (not the original encoder) and stay
in their slot when they fit, otherwise they go after the last entry (offsets are free-form, the
game reads each entry through the table - *from the data, not verified in game*).
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

COMPRESSED = 0x10000
END = b'\x00\x00\x00'   # a flag byte whose first op is a copy from ring position 0: end of data
ENTRY_ALIGN = 0x80
BASE_ALIGN = 0x800
SECTOR = 0x800        # every load group starts on a sector and spans whole sectors


def align(n, a):
    return (n + a - 1) & ~(a - 1)


def decompress(src, size):
    ring = bytearray(4096)
    r = 1                               # the game writes from position 1 (0x28a338)
    out = bytearray()
    i, n = 0, len(src)
    while i < n and len(out) < size:
        flag = src[i]
        i += 1
        for _ in range(8):
            if i >= n or len(out) >= size:
                break
            if flag & 1:
                c = src[i]
                i += 1
                out.append(c)
                ring[r] = c
                r = (r + 1) & 0xfff
            else:
                if i + 1 >= n:
                    i = n
                    break
                a, b = src[i], src[i + 1]
                i += 2
                pos = a | (b & 0x0f) << 8
                if pos == 0:                    # end marker
                    i = n
                    break
                for k in range((b >> 4) + 2):
                    c = ring[(pos + k) & 0xfff]
                    out.append(c)
                    ring[r] = c
                    r = (r + 1) & 0xfff
            flag >>= 1
    del out[size:]
    out += bytes(size - len(out))
    return bytes(out)


def compress(data, max_chain=64):
    """Greedy LZSS for decompress(). Encodes all of `data`: stopping early would let the block's zero
    padding decode as copies from ring position 0, not as zeros."""
    end = len(data)
    max_dist = 4096 - 18      # the copy must not read ring slots it has already overwritten
    out = bytearray()
    chains = {}
    p = 0
    while p < end:
        flag_at = len(out)
        out.append(0)
        flag = 0
        for bit in range(8):
            if p >= end:
                break
            best_len, best_pos = 0, 0
            if p + 2 <= end:
                key = data[p:p + 2]
                limit = min(17, end - p)
                for q in reversed(chains.get(key, ())[-max_chain:]):
                    if p - q > max_dist:
                        break
                    if (q + 1) & 0xfff == 0:    # ring position 0 is the end marker
                        continue
                    ln = 2
                    while ln < limit and data[q + ln] == data[p + ln]:
                        ln += 1
                    if ln > best_len:
                        best_len, best_pos = ln, q
                        if ln == limit:
                            break
            if best_len >= 2:
                pos = (best_pos + 1) & 0xfff    # output byte q sits at ring position q + 1
                out += bytes((pos & 0xff, (best_len - 2) << 4 | pos >> 8))
                step = best_len
            else:
                flag |= 1 << bit
                out.append(data[p])
                step = 1
            for k in range(p, p + step):
                if k + 2 <= end:
                    chains.setdefault(data[k:k + 2], []).append(k)
            p += step
        out[flag_at] = flag
    return bytes(out) + END


class Pak:
    """A pack's table: entries [(offset, stored, size, flags)] with offsets from `base`.
    `source` is a file path or the pack's bytes (the build works on bytes)."""

    def __init__(self, source):
        if isinstance(source, (bytes, bytearray, memoryview)):
            self.path, self.data = None, memoryview(source)
            head = bytes(self.data[:8])
        else:
            self.path, self.data = Path(source), None
            if not self.path.exists():
                sys.exit(f'{self.path} not found - run tools/extract.py first')
            with open(self.path, 'rb') as f:
                head = f.read(8)
        self.word0, n = struct.unpack('<II', head)
        table = self._read(8, 16 * n)
        if self.word0 != 0x800 or len(table) != 16 * n:
            sys.exit(f'{self.path or "pack"}: not one of the game\'s packs (expected u32 0x800 and a table at the start)')
        self.entries = [struct.unpack_from('<4I', table, 16 * i) for i in range(n)]
        self.base = align(8 + 16 * n, BASE_ALIGN)

    def _read(self, pos, n, f=None):
        if self.data is not None:
            return bytes(self.data[pos:pos + n])
        if f is None:
            with open(self.path, 'rb') as f:
                f.seek(pos)
                return f.read(n)
        f.seek(pos)
        return f.read(n)

    def raw(self, k, f=None):
        o, stored, size, flags = self.entries[k]
        return self._read(self.base + o, stored, f)

    def get(self, k, f=None):
        o, stored, size, flags = self.entries[k]
        raw = self.raw(k, f)
        return decompress(raw, size) if flags & COMPRESSED else raw[:size]

    def end(self):
        return max(self.base + o + stored for o, stored, size, flags in self.entries)


def guess_ext(data):
    if data[:4] == b'TIM2':
        return 'tm2'
    if data[:4] == b'IECS':
        return 'hd'       # Sony sound bank header
    return 'bin'


def unpack(pak_path, out_dir, raw=False):
    p = Pak(pak_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {'entries': []}
    with open(p.path, 'rb') as f:
        for k, (o, stored, size, flags) in enumerate(p.entries):
            data = p.raw(k, f) if raw else p.get(k, f)
            name = f'{k:05d}.{guess_ext(data)}'
            (out_dir / name).write_bytes(data)
            manifest['entries'].append({'file': name, 'type': flags & 0xffff, 'flags': flags,
                                        'sha1': hashlib.sha1(data).hexdigest()})
    (out_dir / 'pak.json').write_text(json.dumps(manifest, indent=0) + '\n')
    return len(p.entries)


def groups(entries):
    """[(first, last)] runs of entries the game loads together: an entry's low flag u16 is how
    many consecutive entries one load reads in a single read (routine 0x28aff8), so a group's
    entries must stay contiguous."""
    out, k = [], 0
    while k < len(entries):
        n = max(1, entries[k][3] & 0xffff)
        out.append((k, min(k + n, len(entries)) - 1))
        k += n
    return out


def layout_errors(source):
    """What breaks the rules the game relies on (empty = fine): every group contiguous, starting on
    a sector and spanning whole sectors; entries 0x80-aligned; nothing overlapping."""
    p = Pak(source)
    errors, spans = [], []
    for f, l in groups(p.entries):
        start = p.base + p.entries[f][0]
        span = p.entries[l][0] + p.entries[l][1] - p.entries[f][0]
        if start % SECTOR or span % SECTOR:
            errors.append(f'group {f}-{l}: starts at 0x{start:x}, {span:#x} bytes - not whole sectors')
        for k in range(f, l):
            if p.entries[k][0] + p.entries[k][1] != p.entries[k + 1][0]:
                errors.append(f'group {f}-{l}: entry {k + 1} does not follow entry {k}')
        spans.append((start, start + span, f))
    for o, st, size, flags in p.entries:
        if o % ENTRY_ALIGN or st % ENTRY_ALIGN:
            errors.append(f'entry at 0x{o:x}: not 0x80-aligned')
            break
    spans.sort()
    for (a, b, f), (c, d, g) in zip(spans, spans[1:]):
        if c < b:
            errors.append(f'groups at {f} and {g} overlap')
    return errors


def encode_entry(data, flags):
    """(stored block, size field) for an entry's unpacked bytes."""
    if flags & COMPRESSED:
        block = compress(data)
    else:
        block = data
    return block + bytes(align(len(block), ENTRY_ALIGN) - len(block)), len(data)


def pack(source, replace=None):
    """The pack (path or bytes) with entries replaced by {index: unpacked bytes}; returns the bytes.

    Unchanged groups keep their bytes and offsets. A group with a replaced entry is rewritten
    contiguously (replaced entries (re)compressed if they were compressed): in its old place if it
    fits there (the rest zeroed), otherwise after the last entry - so the pack only grows by what
    doesn't fit, and every group stays one contiguous read."""
    p = Pak(source)
    replace = replace or {}
    out = bytearray(p.data if p.data is not None else p.path.read_bytes())
    entries = list(p.entries)
    end = p.end()
    for first, last in groups(p.entries):
        if not any(first <= k <= last for k in replace):
            continue
        start = entries[first][0]
        span = entries[last][0] + entries[last][1] - start
        body, recs = bytearray(), []
        for k in range(first, last + 1):
            o, stored, size, flags = entries[k]
            if k in replace:
                block, size = encode_entry(replace[k], flags)
            else:
                block = p.raw(k)
            recs.append([len(body), len(block), size, flags])
            body += block
        pad = align(len(body), SECTOR) - len(body)      # a group is read in whole sectors
        recs[-1][1] += pad
        body += bytes(pad)
        out[p.base + start:p.base + start + span] = bytes(span)
        if len(body) > span:
            start = end - p.base
            end += len(body)
        out[p.base + start:p.base + start + len(body)] = body
        for k, (rel, stored, size, flags) in zip(range(first, last + 1), recs):
            entries[k] = (start + rel, stored, size, flags)
    del out[end:]
    out[8:8 + 16 * len(entries)] = b''.join(struct.pack('<4I', *e) for e in entries)
    return bytes(out)


def verify(pak_path, every=50):
    p = Pak(pak_path)
    h = hashlib.sha1(pack(pak_path)).digest()
    with open(pak_path, 'rb') as f:
        same = h == hashlib.sha1(f.read()).digest()
    print(f'{pak_path}: repack with nothing changed is ' + ('byte-identical' if same else 'DIFFERENT'))
    bad = tested = 0
    with open(pak_path, 'rb') as f:
        for k in range(0, len(p.entries), every):
            o, stored, size, flags = p.entries[k]
            if not flags & COMPRESSED:
                continue
            data = p.get(k, f)
            tested += 1
            if decompress(compress(data), len(data)) != data:
                bad += 1
                print(f'    entry {k}: compress -> decompress does not give the entry back')
    print(f'{pak_path}: LZSS round trip on {tested} compressed entries: ' + ('ok' if not bad else f'{bad} FAILED'))
    return same and not bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('info'); s.add_argument('pack')
    s = sub.add_parser('unpack'); s.add_argument('pack'); s.add_argument('dir')
    s.add_argument('--raw', action='store_true', help='write the stored (compressed) bytes')
    s = sub.add_parser('get'); s.add_argument('pack'); s.add_argument('index', type=int); s.add_argument('out')
    s = sub.add_parser('verify'); s.add_argument('pack'); s.add_argument('--lz', type=int, default=50, metavar='N')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'info':
        p = Pak(args.pack)
        types = {}
        for e in p.entries:
            types[e[3] & 0xffff] = types.get(e[3] & 0xffff, 0) + 1
        comp = sum(1 for e in p.entries if e[3] & COMPRESSED)
        print(f'{len(p.entries)} entries, data from 0x{p.base:x}, {comp} compressed')
        print('types: ' + ', '.join(f'{t}: {c}' for t, c in sorted(types.items())))
    elif args.cmd == 'unpack':
        print(f'{unpack(args.pack, args.dir, args.raw)} entries -> {args.dir}')
    elif args.cmd == 'get':
        Path(args.out).write_bytes(Pak(args.pack).get(args.index))
    elif args.cmd == 'verify':
        return 0 if verify(args.pack, args.lz) else 1


if __name__ == '__main__':
    sys.exit(main())
