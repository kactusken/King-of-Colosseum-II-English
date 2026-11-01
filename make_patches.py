#!/usr/bin/env python3
"""Build the release variants and make a verified xdelta patch for each.

  python3 make_patches.py [--version v1.0] [--allow-handmade] [--any-rom]
      -> release/<GAME> English Patch <version>/ (patches, README.txt) + .zip

For each variant in VARIANTS this runs build.py, makes an xdelta3 patch from the clean original to
the result, applies it again and checks that it reproduces the build exactly. Patches never stack:
each applies to the clean original on its own (say so in the README).

Refuses to run while translation/images-handmade/ holds unapproved images (--allow-handmade) or
automatic renders are out of date (run tools/render.py), and when rom/ isn't the expected original
(--any-rom). Every variant is built into the same staging image (build/release/staging.<ext>), so
after the first one each build only restores what the previous one changed (tools/image.py).
Needs the xdelta3 program (Debian/Ubuntu: apt install xdelta3), or give its path with --xdelta.
"""
import argparse
import shutil
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
import catalog  # noqa: E402
import image  # noqa: E402
import paths  # noqa: E402

# (output name, build.py options, description for the README)
VARIANTS = [
    (f'{paths.GAME} (English)', ['--unlocks', 'none'], 'The English translation.'),
    (f'{paths.GAME} (English) (All Unlocked)', ['--unlocks', 'all'],
     'The English translation with everything unlocked from the start, including content the game '
     'never unlocks (hidden wrestlers, the cut Pancrase parts, rings and options).'),
    (f'{paths.GAME} (Japan) (All Unlocked)', ['--no-translation', '--unlocks', 'all'],
     'The original Japanese game with the same unlocks.'),
]

# -S none: no secondary compression, which some patchers (Rom Patcher JS) can't read.
# -A=: no application header (it would record local file paths).
# Add '-B', str(1 << 30) for DVD images if a patch comes out large because data moved far.
XDELTA_ENCODE = ['-e', '-9', '-S', 'none', '-A=', '-f']

APPLY_HELP = '''\
How to apply
------------
You need your own copy of the original disc image:
  {name}
  {size} bytes, CRC32 {crc32}, MD5 {md5}
  SHA-1 {sha1}

1. Pick one of the .xdelta patches below (each applies to the original on its own).
2. Apply it to the original image with an xdelta tool:
     - Delta Patcher (Windows, macOS, Linux)
     - Rom Patcher JS in a web browser (fine for CD images; DVD images may be too big for it)
     - command line: xdelta3 -d -s "original{ext}" "patch.xdelta" "patched{ext}"
3. Load the patched image in your emulator.

Patches
-------
'''

LEGAL = '''
Legal
-----
A non-commercial fan project. {game} and its contents belong to their
respective owners. These patches contain no game data and no playable image;
you need your own copy of the original disc. The tools and documentation are
released under the MIT License.
'''


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--version', default='dev')
    ap.add_argument('--xdelta', default='xdelta3', metavar='PROGRAM')
    ap.add_argument('--any-rom', action='store_true', help="skip the check that rom/ is the expected original")
    ap.add_argument('--allow-handmade', action='store_true', help='build even with unapproved hand edits')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))

    if args.version != 'dev' and not paths.AI_DISCLOSURE.strip():
        sys.exit('tools/paths.py AI_DISCLOSURE is empty: set a short line such as '
                 '"AI assisted with the translation."')
    wip = catalog.handmade_in_progress()
    if wip and not args.allow_handmade:
        sys.exit(f'{paths.show(paths.HANDMADE)} has unapproved images, which the build would include:\n  '
                 + ', '.join(wip) + '\napprove or reset them (docs/EDITING.md), or pass --allow-handmade')
    missing, changed, _ = catalog.stale()
    if missing or changed:
        sys.exit(f'{len(missing) + len(changed)} automatic renders are out of date - run tools/render.py first')
    if not shutil.which(args.xdelta):
        sys.exit(f'{args.xdelta} not found; install xdelta3 or pass --xdelta PATH')

    rom = paths.ROM
    print(f'checking {paths.show(rom)}')
    source = image.checksums(rom)
    if source != paths.ORIGINAL and not args.any_rom:
        sys.exit(f'{rom} is not the expected original:\n  got      {source}\n  expected {paths.ORIGINAL}\n'
                 '(--any-rom makes patches for it anyway)')

    title = f'{paths.GAME} English Patch {args.version}'
    out = paths.RELEASE / title
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    stage = paths.BUILD / 'release'
    notes = APPLY_HELP.format(name=paths.ORIGINAL_NAME, ext=rom.suffix, **source)
    for name, options, description in VARIANTS:
        print(f'\n=== {name}')
        subprocess.run([sys.executable, str(ROOT / 'build.py'), '--rom', str(rom), '--build', str(stage),
                        '--name', 'staging', '--skip-verify', *options], check=True)
        built = stage / ('staging' + rom.suffix)
        patch = out / (name + '.xdelta')
        subprocess.run([args.xdelta, *XDELTA_ENCODE, '-s', str(rom), str(built), str(patch)], check=True)
        check = stage / 'staging.check'
        subprocess.run([args.xdelta, '-d', '-f', '-s', str(rom), str(patch), str(check)], check=True)
        target = image.checksums(built)
        if image.checksums(check) != target:
            sys.exit(f'{patch} does not reproduce {built}')
        check.unlink()
        cue = stage / 'staging.cue'
        if cue.exists():  # CD images: a .cue naming the patched image
            (out / f'{name}.cue').write_text(cue.read_text().replace(built.name, name + rom.suffix))
        print(f'{paths.show(patch)}: {patch.stat().st_size} bytes, verified')
        notes += (f'\n{name}.xdelta\n{textwrap.fill(description, 78, initial_indent="  ", subsequent_indent="  ")}\n'
                  f'  Result: {target["size"]} bytes, CRC32 {target["crc32"]}, SHA-1 {target["sha1"]}\n')

    if paths.AI_DISCLOSURE.strip():
        notes += '\nAI disclosure\n-------------\n' + textwrap.fill(paths.AI_DISCLOSURE.strip(), 78) + '\n'
    notes += LEGAL.format(game=paths.GAME)
    (out / 'README.txt').write_text(f'{title}\n\n{notes}', encoding='utf-8', newline='\r\n')
    zip_path = paths.RELEASE / f'{title}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(out.iterdir()):
            z.write(f, f.name)
    print(f'\n{paths.show(zip_path)}: {zip_path.stat().st_size} bytes')


if __name__ == '__main__':
    main()
