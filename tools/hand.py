#!/usr/bin/env python3
"""Pixel-script hand edits: regenerate and approve them (needs Pillow: run with .venv/bin/python).

  hand.py [image ...]      run translation/hand/<image>.py (all if none given), then put each
                           result in translation/images-handmade/ and approve it (tools/edit.py
                           approve: snapped to the game's palette, frozen in images-approved/)

Some pictures can't be drawn by tools/render.py: lettering that is part of artwork (banners,
stamps, icons, button bars). Their edits are written as small scripts in translation/hand/ -
code, so they're in git and can be re-run on any machine with the original images exported
(tools/extract.py) - instead of keeping hand-painted PNGs, which are game art and stay out of
git. Each script reads review/images-original/<image>.png and writes build/work/hand/out/<image>.png.
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

SCRIPTS = paths.TRANSLATION / 'hand'
OUT = paths.WORK / 'hand' / 'out'


def main(argv=None):
    argv = paths.configure(sys.argv[1:] if argv is None else argv)
    if any(a in ('-h', '--help') for a in argv):
        print(__doc__)
        return 0
    if not paths.ORIGINAL_IMAGES.exists():
        sys.exit(f'{paths.show(paths.ORIGINAL_IMAGES)} is empty - run tools/extract.py first')
    names = argv or sorted(p.stem for p in SCRIPTS.glob('000_*.py'))
    done = []
    for name in names:
        script = SCRIPTS / f'{name}.py'
        if not script.exists():
            sys.exit(f'{paths.show(script)} not found')
        r = subprocess.run([sys.executable, str(script)], cwd=paths.PROJECT)
        out = OUT / f'{name}.png'
        if r.returncode or not out.exists():
            sys.exit(f'{name}: the script failed or wrote no {paths.show(out)}')
        paths.HANDMADE.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, paths.HANDMADE / f'{name}.png')
        done.append(name)
    r = subprocess.run([sys.executable, str(Path(__file__).with_name('edit.py')), 'approve', *done, '--force'],
                       cwd=paths.PROJECT)
    return r.returncode


if __name__ == '__main__':
    sys.exit(main())
