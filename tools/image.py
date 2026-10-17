#!/usr/bin/env python3
"""The output image: a copy of the original that a build writes into, kept fast to rebuild.

  image.py checksums <file>...         size, CRC32, MD5 and SHA-1 (what paths.ORIGINAL holds)
  image.py restore <original> <out>    make <out> identical to <original> again (fast if journalled)

Every build must start from an exact copy of the original. Copying a CD image is quick, a DVD image
(4+ GB) is not, so prepare() keeps the previous build and a journal of every byte range that build
wrote (<out>.journal.json). The next build copies just those ranges back from the original and
truncates anything appended, which gives the same bytes as a fresh copy. A full copy is made when
there is no journal, when the last build didn't finish (the journal is marked unclean until close),
when the original or the output changed since, or with clean=True (build.py --clean).

All writes must go through the returned file object - that's how the journal stays complete.
check.py --control proves the whole path by comparing a control build with the original's SHA-1.
"""
import hashlib
import json
import os
import shutil
import sys
import zlib
from pathlib import Path

CHUNK = 1 << 22


def checksums(path):
    """{'size', 'crc32', 'md5', 'sha1'} of a file, in the form paths.ORIGINAL uses."""
    sha1, md5, crc = hashlib.sha1(), hashlib.md5(), 0
    with open(path, 'rb') as f:
        while chunk := f.read(CHUNK):
            sha1.update(chunk)
            md5.update(chunk)
            crc = zlib.crc32(chunk, crc)
    return {'size': os.path.getsize(path), 'crc32': f'{crc:08x}', 'md5': md5.hexdigest(),
            'sha1': sha1.hexdigest()}


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _stamp(p):
    st = os.stat(p)
    return [st.st_size, st.st_mtime_ns]


def _merge(ranges):
    out = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


class JournalledFile:
    """A file opened r+b that remembers which byte ranges were written."""

    def __init__(self, path, journal, original):
        self.path, self.journal, self.original = Path(path), Path(journal), Path(original)
        self.f = open(path, 'r+b')
        self.ranges = []

    def seek(self, pos, whence=0):
        return self.f.seek(pos, whence)

    def tell(self):
        return self.f.tell()

    def read(self, n=-1):
        return self.f.read(n)

    def write(self, data):
        pos = self.f.tell()
        n = self.f.write(data)
        self.ranges.append((pos, pos + n))
        return n

    def flush(self):
        self.f.flush()

    def close(self):
        if self.f.closed:
            return
        self.f.close()
        self.journal.write_text(json.dumps({
            'clean': True, 'original': [str(self.original.resolve())] + _stamp(self.original),
            'output': _stamp(self.path), 'ranges': _merge(self.ranges)}))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def prepare(original, out, clean=False, quiet=False):
    """Make `out` an exact copy of `original` (fast when the journal allows) and open it for writing."""
    original, out = Path(original), Path(out)
    if original.resolve() == out.resolve():
        sys.exit(f'refusing to write into the original image: {original}')
    journal = out.with_name(out.name + '.journal.json')
    j = None
    if not clean and out.exists() and journal.exists():
        try:
            j = json.loads(journal.read_text())
        except ValueError:
            j = None
    fast = (j is not None and j.get('clean')
            and j.get('original') == [str(original.resolve())] + _stamp(original)
            and j.get('output') == _stamp(out))
    out.parent.mkdir(parents=True, exist_ok=True)
    if fast:
        size = original.stat().st_size
        with open(original, 'rb') as src, open(out, 'r+b') as dst:
            for a, b in j['ranges']:
                a, b = min(a, size), min(b, size)
                src.seek(a)
                dst.seek(a)
                while a < b:
                    chunk = src.read(min(CHUNK, b - a))
                    dst.write(chunk)
                    a += len(chunk)
            dst.truncate(size)
        if not quiet:
            print(f'restored {out.name} from the original ({len(j["ranges"])} ranges)')
    else:
        if not quiet:
            print(f'copying the original -> {out.name}')
        shutil.copyfile(original, out)
    journal.write_text(json.dumps({'clean': False}))
    return JournalledFile(out, journal, original)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) >= 2 and argv[0] == 'checksums':
        for p in argv[1:]:
            print(p, checksums(p))
    elif len(argv) == 3 and argv[0] == 'restore':
        prepare(argv[1], argv[2]).close()
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
