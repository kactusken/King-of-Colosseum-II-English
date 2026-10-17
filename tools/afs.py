#!/usr/bin/env python3
"""CRI AFS archives (KC2FIRE.AFS): unpack, repack, and prove the round trip.

  afs.py info <afs>                       entry count, layout, a few names
  afs.py unpack <afs> <dir>               every entry -> <dir>/NNNN_<name>, plus <dir>/afs.json
  afs.py pack <dir> <afs>                 rebuild an archive from an unpacked folder
  afs.py verify <afs> <dir>               pack <dir> in memory and compare with <afs> (SHA-1, streamed)

Layout (all u32 LE): "AFS\\0", count N, N x (offset, size), then the name table's (offset, size).
The rest of the header up to the first entry is padding - in KC2FIRE.AFS it holds 1,567 bytes of
leftover buffer contents, kept verbatim in afs.json. Entries follow in index order, each at the
next 0x800 boundary, zero-filled between. The name table follows the last entry: N x 0x30 bytes =
name (0x20, zero-padded), u16 year, month, day, hour, minute, second, and a u32 that the mastering
tool filled with header word k+1 (count, offset 0, size 0, offset 1, ...) instead of the entry's
size; pack() writes it the same way. The file ends zero-padded to 0x800.

Names are not unique (345 repeats), so unpacked files are prefixed with the entry index; pack
takes each entry from the file named in afs.json. The game finds entries by index (CRI ADX/SFD
libraries), so entries can grow: everything after them moves and the table is rewritten.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

ALIGN = 0x800
NAME_SIZE = 0x30
CHUNK = 1 << 22


def align(n, a=ALIGN):
    return (n + a - 1) & ~(a - 1)


class Afs:
    """The table of an AFS archive: entries [(offset, size)], names [(name, date)], header padding."""

    def __init__(self, path):
        self.path = Path(path)
        with open(self.path, 'rb') as f:
            head = f.read(8)
            if head[:4] != b'AFS\0':
                sys.exit(f'{self.path}: not an AFS archive (no "AFS\\0" at the start)')
            n = struct.unpack_from('<I', head, 4)[0]
            table = f.read(8 * n + 8)
            self.entries = [struct.unpack_from('<II', table, 8 * i) for i in range(n)]
            self.names_at, self.names_size = struct.unpack_from('<II', table, 8 * n)
            first = min(o for o, s in self.entries)
            self.header_pad = f.read(first - f.tell())
            if self.names_size != n * NAME_SIZE:
                sys.exit(f'{self.path}: name table size 0x{self.names_size:x} is not {n} x 0x30 - '
                         'this archive has a layout afs.py does not handle yet')
            f.seek(self.names_at)
            raw = f.read(self.names_size)
        self.names = []
        for k in range(n):
            r = raw[k * NAME_SIZE:(k + 1) * NAME_SIZE]
            self.names.append((r[:0x20].rstrip(b'\0').decode('ascii'), list(struct.unpack_from('<6H', r, 0x20))))

    def read(self, k):
        o, s = self.entries[k]
        with open(self.path, 'rb') as f:
            f.seek(o)
            return f.read(s)

    def filename(self, k):
        return f'{k:04d}_{self.names[k][0]}'


def unpack(afs_path, out_dir):
    a = Afs(afs_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {'header_pad': a.header_pad.hex(), 'entries': []}
    with open(a.path, 'rb') as f:
        for k, (o, s) in enumerate(a.entries):
            f.seek(o)
            (out_dir / a.filename(k)).write_bytes(f.read(s))
            manifest['entries'].append({'file': a.filename(k), 'name': a.names[k][0], 'date': a.names[k][1]})
    (out_dir / 'afs.json').write_text(json.dumps(manifest, indent=0) + '\n')
    return len(a.entries)


def pack_stream(src_dir, write):
    """Rebuild the archive from an unpacked folder, passing the bytes to write() in order."""
    src_dir = Path(src_dir)
    if not (src_dir / 'afs.json').exists():
        sys.exit(f'{src_dir}/afs.json not found - unpack the archive first (tools/extract.py or afs.py unpack)')
    m = json.loads((src_dir / 'afs.json').read_text())
    ents = m['entries']
    n = len(ents)
    pad = bytes.fromhex(m['header_pad'])
    first = 8 + 8 * n + 8 + len(pad)
    if first % ALIGN:
        sys.exit(f'{src_dir}/afs.json: header padding ends at 0x{first:x}, not on a 0x800 boundary')
    sizes = [(src_dir / e['file']).stat().st_size for e in ents]
    offsets, pos = [], first
    for s in sizes:
        offsets.append(pos)
        pos = align(pos + s)
    names_at = pos
    words = [n] + [w for o_s in zip(offsets, sizes) for w in o_s]
    write(b'AFS\0' + struct.pack('<%dI' % (1 + 2 * n), *words) + struct.pack('<II', names_at, n * NAME_SIZE) + pad)
    for e, o, s in zip(ents, offsets, sizes):
        with open(src_dir / e['file'], 'rb') as f:
            while True:
                b = f.read(CHUNK)
                if not b:
                    break
                write(b)
        write(bytes(align(o + s) - o - s))
    table = bytearray()
    for k, e in enumerate(ents):
        name = e['name'].encode('ascii')
        if len(name) > 0x20:
            sys.exit(f'{src_dir}/afs.json: entry {k} name {e["name"]!r} is longer than 32 characters')
        table += name.ljust(0x20, b'\0') + struct.pack('<6HI', *e['date'], words[k])
    write(bytes(table) + bytes(align(len(table)) - len(table)))
    return names_at + align(len(table))


def pack(src_dir, out_path):
    with open(out_path, 'wb') as f:
        return pack_stream(src_dir, f.write)


def verify(afs_path, src_dir):
    """Pack src_dir without writing it out and compare the SHA-1 with afs_path. True if identical."""
    h = hashlib.sha1()
    size = pack_stream(src_dir, h.update)
    want = hashlib.sha1()
    with open(afs_path, 'rb') as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            want.update(b)
    ok = h.digest() == want.digest() and size == Path(afs_path).stat().st_size
    print(f'{afs_path}: repack of {src_dir} is ' + ('byte-identical' if ok else
          f'DIFFERENT ({size} bytes, SHA-1 {h.hexdigest()}; original {want.hexdigest()})'))
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('info'); p.add_argument('afs')
    p = sub.add_parser('unpack'); p.add_argument('afs'); p.add_argument('dir')
    p = sub.add_parser('pack'); p.add_argument('dir'); p.add_argument('afs')
    p = sub.add_parser('verify'); p.add_argument('afs'); p.add_argument('dir')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'info':
        a = Afs(args.afs)
        exts = {}
        for name, _ in a.names:
            ext = name.rsplit('.', 1)[-1]
            exts[ext] = exts.get(ext, 0) + 1
        print(f'{len(a.entries)} entries, first at 0x{a.entries[0][0]:x}, name table at 0x{a.names_at:x}')
        print('types: ' + ', '.join(f'{v} .{k}' for k, v in sorted(exts.items())))
        for k in range(min(5, len(a.entries))):
            print(f'  {k:4d} 0x{a.entries[k][0]:08x} {a.entries[k][1]:9d} {a.names[k][0]}')
    elif args.cmd == 'unpack':
        print(f'{unpack(args.afs, args.dir)} entries -> {args.dir}')
    elif args.cmd == 'pack':
        print(f'{pack(args.dir, args.afs)} bytes -> {args.afs}')
    elif args.cmd == 'verify':
        return 0 if verify(args.afs, args.dir) else 1


if __name__ == '__main__':
    sys.exit(main())
