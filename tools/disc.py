#!/usr/bin/env python3
"""PS2 DVD/CD image (platform pack ps2): 2048-byte sectors, ISO9660 + UDF bridge.

  disc.py list    <iso>                   files: LBA, size, sectors available, path
  disc.py extract <iso> <outdir> [--all]  every file (zero-padding files skipped unless --all)
  disc.py check   <iso>                   ISO9660 and UDF agree on every file (location and size)
  disc.py inject  <iso> <path> <file>     overwrite a file (relocated if it doesn't fit)

PS2 DVDs carry two file systems over the same data: ISO9660 (what the PS2 BIOS and PCSX2 read)
and UDF 1.02 (what PC drives prefer). write_file() keeps both in step: the ISO9660 directory record
(size, LBA) and the UDF File Entry (information length, blocks recorded, allocation descriptors,
descriptor CRC and tag checksum). There is no EDC/ECC to regenerate on 2048-byte images.

A file that outgrows its slot moves to a gap no file uses, or to the end of the image (the ISO9660
volume size and the UDF partition length grow with it; DVD-5 holds at most DVD5_SECTORS). Many games
find files through their own tables (an LBA table in the ELF or an archive index), not the file
system - check before relying on relocation. A disc with no room left can give up space from a
zero-padding file (write_file(..., donors=[...]) cuts its end off).

Interface shared by every platform's disc.py (build.py and extract.py use only this):
  SECTOR                        data bytes per sector
  Disc(path or file, writable)  .files(), .find(path), .read_file(e), .write_file(e, data, relocate),
                                .allocated_sectors(e), .is_empty(e), .extract_file(e, out), .close()
  companion_files(image)        write what an emulator needs next to the image (nothing for .iso)
"""
import struct
import sys
from pathlib import Path

SECTOR = 2048
DVD5_SECTORS = 2295104
MAX_EXTENT = 0x3FFFF800  # largest UDF extent (30-bit length, whole sectors)


def crc_itu(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc


def fix_tag(desc, length):
    """Recompute a UDF descriptor tag's CRC (over `length` bytes after the tag) and checksum."""
    struct.pack_into('<HH', desc, 8, crc_itu(desc[16:16 + length]), length)
    desc[4] = sum(desc[i] for i in range(16) if i != 4) & 0xFF


class Entry:
    def __init__(self, path, lba, size, is_dir, rec_sector, rec_offset):
        self.path, self.lba, self.size, self.is_dir = path, lba, size, is_dir
        self.rec_sector, self.rec_offset = rec_sector, rec_offset  # the ISO9660 directory record
        self.udf = None  # sector of the UDF File Entry, if the image has UDF

    @property
    def sectors(self):
        return (self.size + SECTOR - 1) // SECTOR


class Disc:
    def __init__(self, path, writable=False):
        self.own = not hasattr(path, 'read')
        self.f = open(path, 'r+b' if writable else 'rb') if self.own else path
        self.f.seek(0, 2)
        self.total_sectors = self.f.tell() // SECTOR
        self.entries = []
        pvd = self.read(16)
        if pvd[1:6] != b'CD001':
            raise ValueError('no ISO9660 primary volume descriptor at sector 16')
        root = pvd[156:190]
        self._walk(struct.unpack_from('<I', root, 2)[0], struct.unpack_from('<I', root, 10)[0], '/')
        self.entries.sort(key=lambda e: e.lba)
        self.partition = None
        self._udf()

    def close(self):
        if self.own:
            self.f.close()

    def read(self, lba, count=1):
        self.f.seek(lba * SECTOR)
        return bytearray(self.f.read(SECTOR * count))

    def write(self, lba, data):
        self.f.seek(lba * SECTOR)
        self.f.write(data)

    # ------------------------------------------------------------ ISO9660

    def _walk(self, lba, size, path):
        for s in range((size + SECTOR - 1) // SECTOR):
            data = self.read(lba + s)
            i = 0
            while i < SECTOR:
                ln = data[i]
                if ln == 0:
                    break
                r = data[i:i + ln]
                name = r[33:33 + r[32]]
                if name not in (b'\0', b'\1'):
                    e = Entry(path + name.decode('ascii').split(';')[0], struct.unpack_from('<I', r, 2)[0],
                              struct.unpack_from('<I', r, 10)[0], bool(r[25] & 2), lba + s, i)
                    self.entries.append(e)
                    if e.is_dir:
                        self._walk(e.lba, e.size, e.path + '/')
                i += ln

    def files(self):
        return [e for e in self.entries if not e.is_dir]

    def find(self, path):
        path = '/' + path.lstrip('/')
        for e in self.entries:
            if e.path.upper() == path.upper():
                return e
        raise KeyError(path)

    # ------------------------------------------------------------ UDF

    def _udf(self):
        if self.total_sectors <= 256:
            return
        avdp = self.read(256)
        if struct.unpack_from('<H', avdp, 0)[0] != 2:
            return
        length, loc = struct.unpack_from('<II', avdp, 16)
        fsd_lbn = None
        for s in range(loc, loc + length // SECTOR):
            d = self.read(s)
            tag = struct.unpack_from('<H', d, 0)[0]
            if tag == 5:
                self.partition = struct.unpack_from('<I', d, 188)[0]
                self.partition_desc = s
            elif tag == 6:
                fsd_lbn = struct.unpack_from('<I', d, 252)[0]
            elif tag == 8:
                break
        if self.partition is None or fsd_lbn is None:
            self.partition = None
            return
        fsd = self.read(self.partition + fsd_lbn)
        root_lbn = struct.unpack_from('<I', fsd, 404)[0]
        by_path = {e.path.upper(): e for e in self.entries}
        self._udf_walk(self.partition + root_lbn, '/', by_path)

    def _fe(self, sector):
        """(file type, information length, [(extent length, lba)]) of a UDF File Entry."""
        fe = self.read(sector)
        if struct.unpack_from('<H', fe, 0)[0] != 261:
            raise ValueError(f'no UDF File Entry at sector {sector}')
        ftype = fe[16 + 11]
        adtype = struct.unpack_from('<H', fe, 16 + 18)[0] & 7
        size = struct.unpack_from('<Q', fe, 56)[0]
        lea, lad = struct.unpack_from('<II', fe, 168)
        ads, p = [], 176 + lea
        step = 8 if adtype == 0 else 16
        for i in range(lad // step):
            ln, pos = struct.unpack_from('<II', fe, p + i * step)
            ads.append((ln & 0x3FFFFFFF, self.partition + pos))
        return ftype, size, ads

    def _udf_walk(self, fe_sector, path, by_path):
        ftype, size, ads = self._fe(fe_sector)
        data = bytearray()
        for ln, lba in ads:
            data += self.read(lba, (ln + SECTOR - 1) // SECTOR)[:ln]
        i = 0
        while i + 38 <= len(data):
            if struct.unpack_from('<H', data, i)[0] != 257:
                break
            chars, lfi = data[i + 18], data[i + 19]
            icb_lbn = struct.unpack_from('<I', data, i + 24)[0]
            liu = struct.unpack_from('<H', data, i + 36)[0]
            raw = data[i + 38 + liu:i + 38 + liu + lfi]
            i += (38 + liu + lfi + 3) & ~3
            if chars & 8 or not raw:
                continue  # parent
            name = raw[1:].decode('latin-1') if raw[0] == 8 else raw[1:].decode('utf-16-be')
            full = path + name
            e = by_path.get(full.upper())
            if e is not None:
                e.udf = self.partition + icb_lbn
            if chars & 2:
                self._udf_walk(self.partition + icb_lbn, full + '/', by_path)

    def check(self):
        """Lines describing every file where ISO9660 and UDF disagree (empty = consistent)."""
        out = []
        if self.partition is None:
            return ['no UDF file system (ISO9660 only)']
        for e in self.files():
            if e.udf is None:
                out.append(f'{e.path}: not in UDF')
                continue
            _, size, ads = self._fe(e.udf)
            if size != e.size or not ads or ads[0][1] != e.lba:
                out.append(f'{e.path}: ISO9660 LBA {e.lba} size {e.size}, UDF {ads[0][1] if ads else "-"} size {size}')
        return out

    def _set_udf(self, e, lba, size):
        fe = self.read(e.udf)
        lea, lad = struct.unpack_from('<II', fe, 168)
        if struct.unpack_from('<H', fe, 16 + 18)[0] & 7 != 0:
            raise ValueError(f'{e.path}: UDF allocation descriptors are not short_ad - not supported')
        old_size, old_ads = struct.unpack_from('<Q', fe, 56)[0], lad // 8
        if old_size == size and struct.unpack_from('<I', fe, 176 + lea + 4)[0] == lba - self.partition:
            return  # unchanged
        if old_ads == 1:
            # keep the mastering tool's layout: one extent, even when the length overflows 30 bits
            # (PS2 discs commonly do this for files over 1 GB; the console reads ISO9660 anyway)
            ads = [struct.pack('<II', size & 0xFFFFFFFF, lba - self.partition)]
        else:
            ads, left, pos = [], size, lba - self.partition
            while left > 0 or not ads:
                ln = min(left, MAX_EXTENT)
                ads.append(struct.pack('<II', ln, pos))
                left -= ln
                pos += (ln + SECTOR - 1) // SECTOR
        new = b''.join(ads)
        end = 176 + lea
        if end + len(new) > SECTOR:
            raise ValueError(f'{e.path}: UDF File Entry too small for {len(ads)} extents')
        fe[end:end + max(lad, len(new))] = new.ljust(max(lad, len(new)), b'\0')
        struct.pack_into('<I', fe, 172, len(new))
        struct.pack_into('<QQ', fe, 56, size, (size + SECTOR - 1) // SECTOR)
        fix_tag(fe, end + len(new) - 16)
        self.write(e.udf, fe)

    # ------------------------------------------------------------ reading and writing

    def allocated_sectors(self, e):
        """Sectors available before the next thing on the disc."""
        later = [x.lba for x in self.entries if x.lba > e.lba]
        return (min(later) if later else self.total_sectors) - e.lba

    def read_file(self, e):
        return bytes(self.read(e.lba, e.sectors)[:e.size])

    def is_empty(self, e, samples=64):
        """True if the file looks like zero padding (checks up to `samples` spread-out sectors)."""
        step = max(1, e.sectors // samples)
        return e.size > 0 and not any(any(self.read(e.lba + s)) for s in range(0, e.sectors, step))

    def extract_file(self, e, out):
        with open(out, 'wb') as f:
            left, lba = e.size, e.lba
            while left > 0:
                n = min(left, 1 << 24)
                f.write(self.read(lba, (n + SECTOR - 1) // SECTOR)[:n])
                left -= n
                lba += (n + SECTOR - 1) // SECTOR

    def find_gap(self, need):
        """First run of `need` sectors between or after the files, or None."""
        used = sorted((x.lba, x.lba + max(x.sectors, 1)) for x in self.entries)
        cur = min(x.lba for x in self.files()) if self.files() else 300  # nothing goes before the first file
        for a, b in used:
            if a - cur >= need:
                return cur
            cur = max(cur, b)
        return cur if self.total_sectors - cur >= need else None

    def _grow(self, sectors):
        """Extend the image to `sectors`: zero fill, ISO9660 volume size, UDF partition length."""
        if sectors > DVD5_SECTORS:
            raise ValueError(f'image would be {sectors} sectors, more than a single-layer DVD ({DVD5_SECTORS})')
        self.f.seek(self.total_sectors * SECTOR)
        self.f.write(bytes((sectors - self.total_sectors) * SECTOR))
        pvd = self.read(16)
        struct.pack_into('<I', pvd, 80, sectors)
        struct.pack_into('>I', pvd, 84, sectors)
        self.write(16, pvd)
        if self.partition is not None:
            pd = self.read(self.partition_desc)
            struct.pack_into('<I', pd, 192, sectors - self.partition)
            fix_tag(pd, struct.unpack_from('<H', pd, 10)[0])
            self.write(self.partition_desc, pd)
        self.total_sectors = sectors

    def set_extent(self, e, lba, size):
        """Point a file at `lba` with `size` bytes in both file systems (no data written)."""
        rec = self.read(e.rec_sector)
        struct.pack_into('<I', rec, e.rec_offset + 2, lba)
        struct.pack_into('>I', rec, e.rec_offset + 6, lba)
        struct.pack_into('<I', rec, e.rec_offset + 10, size)
        struct.pack_into('>I', rec, e.rec_offset + 14, size)
        self.write(e.rec_sector, rec)
        if e.udf is not None:
            self._set_udf(e, lba, size)
        e.lba, e.size = lba, size
        self.entries.sort(key=lambda x: x.lba)

    def take_from_padding(self, donors, need):
        """Free `need` sectors by cutting the end off the first zero-padding file in `donors` (paths)
        that has room; the freed sectors become a gap find_gap() can use. Returns True if done."""
        for path in donors:
            try:
                e = self.find(path)
            except KeyError:
                continue
            if e.sectors - need >= 1 and self.is_empty(e):
                print(f'  taking {need} sectors from the end of {e.path} (zero padding)')
                self.set_extent(e, e.lba, (e.sectors - need) * SECTOR)
                return True
        return False

    def write_file(self, e, data, relocate=False, donors=()):
        """Write a file's data; if it outgrows its slot and `relocate`, move it to a gap (made by
        take_from_padding(donors) if there is none) or to the end of the image."""
        need = max(1, (len(data) + SECTOR - 1) // SECTOR)
        avail = self.allocated_sectors(e)
        lba = e.lba
        if need > avail:
            if not relocate:
                raise ValueError(f'{e.path}: {len(data)} bytes needs {need} sectors, only {avail} available')
            lba = self.find_gap(need)
            if lba is None and self.take_from_padding(donors, need):
                lba = self.find_gap(need)
            if lba is None:
                lba = self.total_sectors
                self._grow(lba + need)
            print(f'  relocating {e.path}: LBA {e.lba} -> {lba} ({need} sectors)')
        self.write(lba, bytes(data).ljust(need * SECTOR, b'\0'))
        self.set_extent(e, lba, len(data))


def companion_files(image):
    """Nothing to write: emulators load the .iso directly."""


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == 'list':
        d = Disc(argv[1])
        for e in d.files():
            print(f'{e.lba:8d} {e.size:11d} {d.allocated_sectors(e):8d}  {e.path}')
    elif cmd == 'check':
        problems = Disc(argv[1]).check()
        print('\n'.join(problems) or 'ISO9660 and UDF agree on every file')
        return 1 if problems and problems[0] != 'no UDF file system (ISO9660 only)' else 0
    elif cmd == 'extract':
        d = Disc(argv[1])
        out = Path(argv[2])
        for e in d.files():
            if '--all' not in argv and d.is_empty(e):
                print(f'skipped {e.path} (padding)')
                continue
            p = out / e.path.lstrip('/')
            p.parent.mkdir(parents=True, exist_ok=True)
            d.extract_file(e, p)
            print('extracted', e.path)
    elif cmd == 'inject':
        d = Disc(argv[1], writable=True)
        e = d.find(argv[2])
        data = Path(argv[3]).read_bytes()
        d.write_file(e, data, relocate=True)
        d.close()
        print(f'injected {argv[3]} -> {e.path} ({len(data)} bytes)')
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
