#!/usr/bin/env python3
"""Build the translated image from the original. Standard library only.

  python3 build.py [--name NAME] [--unlocks all|none|GROUP,...] [--clean]
      -> build/NAME.<ext> (default NAME: "<game> (English)")

Steps (default folders shown; move any of them with the folder options - see --help):
  1. verify the original in rom/ (size + SHA-1; --skip-verify skips the hash)
  2. prepare build/NAME: a fresh copy of the original, or - much faster for big images - the last
     build with every range it wrote restored from the original (tools/image.py; --clean copies)
  3. text: translation/script/ and translation/text/ into the game's files (TEXT_STEPS)
  4. code patches picked by --unlocks (CODE_PATCHES, tools/codepatch.py)
  5. images: for every catalogued image the English file the catalogue picks (hand-made >
     approved > rendered), imported by tools/gfx.py; the final set is copied to review/images-english/
  6. write every changed file back into the image (files that fit in place first)

Test builds: --boot PART starts the game straight in PART (BOOT_PATCHES, once known);
--no-translation skips text and images, and gameplay patches unless --unlocks is given - on its
own the result is byte-identical to the original (tools/check.py --control proves it).
Developer flags (never for releases): --no-text FILE skips one text file.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'tools'))
import catalog  # noqa: E402
import elf  # noqa: E402
import hashlib
import textpatch  # noqa: E402
import codepatch  # noqa: E402
import disc  # noqa: E402
import gfx  # noqa: E402
import image  # noqa: E402
import pak  # noqa: E402
import paths  # noqa: E402
import pools  # noqa: E402
import tables  # noqa: E402
import teamdata  # noqa: E402
import dojo  # noqa: E402
import mmdata  # noqa: E402
import mmtalk  # noqa: E402
import records  # noqa: E402
import elftext  # noqa: E402
import unlockpatch  # noqa: E402

# Gameplay patches: (group, file, address, original, new, description) - see tools/codepatch.py.
CODE_PATCHES = [
    # The game's own unlock-all routine (reached only by a name-entry password) runs at boot and
    # after every save load: tools/unlockpatch.py, docs/PATCHES.md "Everything unlocked".
    *unlockpatch.patches('all'),
    # Developer group (DEV_GROUPS, only when named): the camera test viewer before the last
    # title-menu item.
    *unlockpatch.debug_patches('debugview'),
]
UNLOCK_GROUPS = sorted({p[0] for p in CODE_PATCHES})
DEV_GROUPS = {'debugview'}     # only when named (--unlocks all,debugview): never in `all` or releases
PLAY_GROUPS = sorted(set(UNLOCK_GROUPS) - DEV_GROUPS)

# --boot: (part, file, address, original, new) - patches that start the game in a given part.
BOOT_PATCHES = {
}


FILES = None
_ELF_CACHE = {}


def to_offset(name, addr, files=None):
    """File offset of a RAM address in the executable (ELF segments)."""
    if name.lstrip('/') != textpatch.FILE:
        raise SystemExit(f'build.py to_offset(): no address mapping for {name}')
    if name not in _ELF_CACHE:
        _ELF_CACHE[name] = elf.Elf(bytes(FILES.get('/' + textpatch.FILE)))
    return _ELF_CACHE[name].offset(addr)


# Data patches that belong to the translation (group 'text'): the Dojo line splitter 0x191290
# draws a run from the first token table's entry to the second's in yellow (「…」 in Japanese);
# English uses “…”, so the first entries become “ / ” (docs/PATCHES.md). (group, file, address,
# original, new, description)
TEXT_DATA_PATCHES = [
    ('text', '/SLPM_656.02', 0x3abdb0, b'\x81\x75', b'\x81\x67', 'Dojo: “ opens a yellow run (was 「)'),
    ('text', '/SLPM_656.02', 0x3abe00, b'\x81\x76', b'\x81\x68', 'Dojo: ” closes a yellow run (was 」)'),
]


def text_code_patches(files):
    """Code patches that belong to the translation itself (applied unless --no-translation):
    the renderer's single-byte ASCII support (tools/textpatch.py, docs/PATCHES.md) and
    TEXT_DATA_PATCHES."""
    patches = list(TEXT_DATA_PATCHES)
    for group, name, addr, orig, new, what in textpatch.patches():
        if orig is None:      # the cave: check the routine it replaces by SHA-1
            off = to_offset(name, addr)
            cur = bytes(files.get('/' + name)[off:off + len(new)])
            if hashlib.sha1(cur).hexdigest() != textpatch.CAVE_SHA1:
                sys.exit(f'{name}: unexpected code at 0x{addr:x} (textpatch cave) - is this the right executable?')
            orig = cur
        patches.append((group, '/' + name, addr, orig, new, what))
    codepatch.apply(files, patches, {'text'}, to_offset)


# Text steps: (text file or folder under translation/, function(path, files)). Each inserts the
# English into the game's files through `files` and stops with a clear message if anything doesn't fit.
TEXT_STEPS = [
    ('text/messages.txt', pools.step),
    ('text/actions.txt', pools.step),
    ('text/matches.txt', pools.step),
    ('text/moves.txt', tables.step),
    ('text/wrestlers.txt', tables.step),
    ('text/movelist.txt', tables.step),
    ('text/roster.csv', records.step),
    ('text/fields.csv', records.step),
    ('text/dojo.txt', dojo.step),
    ('text/mmtalk.txt', mmtalk.step),
    ('text/teamdata.csv', teamdata.step),
    ('text/mmdata.txt', mmdata.step),      # after teamdata: team lists follow the team tables
    ('text/elf.txt', elftext.step),
]

# Zero-padding files a grown file may take space from (disc.py take_from_padding): the disc is
# nearly full, and KC2FIRE.000 has no room to grow where it is.
PADDING_DONORS = ['/DATA/GOOD.BYE', '/DATA/HELLO.FOR']


class Packs:
    """Entries of the game's packs (tools/pak.py) for this build: decompressed on first use, every
    changed pack rebuilt once by finish()."""

    def __init__(self, files):
        self.files, self.cache, self.changed = files, {}, {}

    def get(self, name, k):
        if (name, k) not in self.cache:
            self.cache[name, k] = pak.Pak(self.files.get(name)).get(k)
        return self.cache[name, k]

    def put(self, name, k, data):
        self.cache[name, k] = bytes(data)
        self.changed.setdefault(name, {})[k] = bytes(data)

    def finish(self):
        for name, entries in self.changed.items():
            data = pak.pack(bytes(self.files.get(name)), entries)
            errors = pak.layout_errors(data)
            if errors:
                sys.exit(f'pack {name}: the rebuilt pack breaks the layout the game needs - fix tools/pak.py:\n  '
                         + '\n  '.join(errors[:10]))
            self.files.put(name, data)
            print(f'pack {name}: {len(entries)} entries rebuilt')
        self.changed = {}


class Files:
    """The game's files for this build: read from the image on first use, written back at the end."""

    def __init__(self, d):
        self.d, self.data, self.changed = d, {}, set()
        self.packs = Packs(self)

    def get(self, name):
        if name not in self.data:
            self.data[name] = bytearray(self.d.read_file(self.d.find(name)))
        return self.data[name]

    def put(self, name, data):
        self.data[name] = bytearray(data)
        self.changed.add(name)


def verify_original(original):
    """SHA-1 of the original image, once: the result is remembered with the file's size and
    modification time (build/original.verified), so later builds only re-hash a changed file."""
    st = original.stat()
    stamp = f'{original.resolve()} {st.st_size} {st.st_mtime_ns} {paths.ORIGINAL["sha1"]}'
    memo = paths.BUILD / 'original.verified'
    if memo.exists() and memo.read_text() == stamp:
        return
    print('verifying the original...')
    if image.sha1(original) != paths.ORIGINAL['sha1']:
        sys.exit(f'{original.name} does not match the expected SHA-1 {paths.ORIGINAL["sha1"]}')
    paths.BUILD.mkdir(parents=True, exist_ok=True)
    memo.write_text(stamp)


def unlock_groups(value):
    if value == 'all':
        return set(PLAY_GROUPS)
    if value == 'none':
        return set()
    groups = {g.strip() for g in value.split(',') if g.strip()}
    if groups - set(UNLOCK_GROUPS):
        raise argparse.ArgumentTypeError(f'expected all, none or some of {",".join(UNLOCK_GROUPS) or "(no groups yet)"}')
    return groups


def images_step(files):
    final = catalog.final_images()
    missing, changed, _ = catalog.stale()
    if missing or changed:
        print(f'note: {len(missing) + len(changed)} automatic renders are out of date - run tools/render.py '
              f'(building with the frozen files there are)')
    n = gfx.import_images({k: p for k, (tag, p) in final.items()}, files)
    if paths.ENGLISH_IMAGES.exists():
        shutil.rmtree(paths.ENGLISH_IMAGES)
    if final:
        paths.ENGLISH_IMAGES.mkdir(parents=True)
        for name, (tag, p) in final.items():
            shutil.copyfile(p, paths.ENGLISH_IMAGES / f'{name}.png')
        counts = {}
        for tag, _ in final.values():
            counts[tag] = counts.get(tag, 0) + 1
        print(f'images: {n} imported (' + ', '.join(f'{c} {t}' for t, c in sorted(counts.items())) + ')')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--name', default=f'{paths.GAME} (English)')
    ap.add_argument('--skip-verify', action='store_true', help="don't hash the original image")
    ap.add_argument('--clean', action='store_true', help='copy the original instead of restoring the last build')
    ap.add_argument('--no-translation', action='store_true', help='skip text and images (alone: identical to the original)')
    ap.add_argument('--unlocks', type=unlock_groups, metavar='all|none|GROUP,...',
                    help='gameplay patches: all (default; the play groups), none or some groups; none with '
                         '--no-translation; developer groups (debugview) only when named')
    ap.add_argument('--boot', choices=sorted(BOOT_PATCHES), help='TEST BUILD: start the game in this part')
    ap.add_argument('--no-text', action='append', default=[], metavar='FILE',
                    help='developer: leave this text file untranslated (repeatable)')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.unlocks is None:
        args.unlocks = set() if args.no_translation else set(PLAY_GROUPS)

    original = paths.ROM
    if not original.exists():
        sys.exit(f'put the original image in {paths.show(paths.ROM_DIR)} (or pass --rom): {paths.ORIGINAL_NAME}')
    if original.stat().st_size != paths.ORIGINAL['size']:
        sys.exit(f'{original.name}: {original.stat().st_size} bytes, expected {paths.ORIGINAL["size"]} - not the right image')
    if not args.skip_verify:
        verify_original(original)

    out = paths.BUILD / (args.name + original.suffix)
    with image.prepare(original, out, clean=args.clean) as f:
        d = disc.Disc(f, writable=True)
        files = Files(d)
        global FILES
        FILES = files

        if not args.no_translation:
            for rel, step in TEXT_STEPS:
                if rel in args.no_text:
                    print(f'text: skipped {rel} (--no-text)')
                    continue
                if (paths.TRANSLATION / rel).exists():
                    step(paths.TRANSLATION / rel, files)

        if not args.no_translation:
            text_code_patches(files)
        codepatch.apply(files, CODE_PATCHES, args.unlocks, to_offset)
        if 'all' in args.unlocks:
            unlockpatch.parts_step(files)

        if not args.no_translation:
            images_step(files)

        files.packs.finish()   # after text and images: every changed pack entry is in

        if args.boot:
            codepatch.apply(files, [(args.boot, *p, f'TEST BUILD: boots into {args.boot}') for p in BOOT_PATCHES[args.boot]],
                            {args.boot}, to_offset)

        def fits(name):
            return (len(files.data[name]) + disc.SECTOR - 1) // disc.SECTOR <= d.allocated_sectors(d.find(name))
        for name in sorted(files.changed, key=lambda n: not fits(n)):
            d.write_file(d.find(name), bytes(files.data[name]), relocate=True, donors=PADDING_DONORS)
            print(f'patched {name}')
    disc.companion_files(out)
    print(f'done: {paths.show(out)}  ({len(files.changed)} files patched)')
    return out


if __name__ == '__main__':
    main()
