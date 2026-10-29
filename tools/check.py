#!/usr/bin/env python3
"""Run every check in one go: python3 tools/check.py [--quick] [--control] [--install-hook]

  (default)        all checks in CHECKS
  --quick          only the quick ones (what the git pre-commit hook runs)
  --control        also make a control build (no translation, no patches) and compare it with the
                   original's SHA-1 - proves extract -> repack -> write-back is lossless (slow on DVDs)
  --install-hook   make `git commit` run `check.py --quick` first (skip once with git commit --no-verify)

Exit status 1 if any check fails. Add the game's own checks (layout check, emulated hook tests,
archive round trips) to CHECKS as they're written.
"""
import argparse
import py_compile
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import image  # noqa: E402
import paths  # noqa: E402

PY = sys.executable
TOOLS = Path(__file__).resolve().parent

# (name, command, quick) - commands run from the project folder; exit status != 0 = failed
CHECKS = [
    ('lint', [PY, 'tools/lint.py'], True),
    ('ascii text patch (simulated)', [PY, 'tools/test_textpatch.py'], True),
    ("player's guide up to date (docs/guide)", [PY, 'tools/guidepage.py', '--check'], True),
    # archive round trips (need tools/extract.py first); the AFS one reads 2 x 1.8 GB, about a minute
    ('afs round trip', [PY, 'tools/afs.py', 'verify', 'extracted/DATA/KC2FIRE.AFS', 'extracted/DATA/KC2FIRE_AFS'], False),
    ('pack 000 round trip', [PY, 'tools/pak.py', 'verify', 'extracted/DATA/KC2FIRE.000'], False),
    ('pack 001 round trip', [PY, 'tools/pak.py', 'verify', 'extracted/DATA/KC2FIRE.001'], False),
    ('pools round trip', [PY, 'tools/pools.py', 'verify'], False),
    ('tables round trip', [PY, 'tools/tables.py', 'verify'], False),
    ('record tables (rosters, CPU logic, voices ...)', [PY, 'tools/records.py', 'verify'], False),
    ('dojo dialogue layout', [PY, 'tools/dojo.py', 'verify'], False),
    ('match maker dialogue round trip', [PY, 'tools/mmtalk.py', 'verify'], False),
    ('team data layout', [PY, 'tools/teamdata.py', 'verify'], False),
    ('match maker data round trip', [PY, 'tools/mmdata.py', 'verify'], False),
    ('image round trip', [PY, 'tools/gfx.py', 'verify', '--every', '7'], False),
    ('font round trip', [PY, 'tools/font.py', 'verify'], False),
    ('pack MVS round trip', [PY, 'tools/pak.py', 'verify', 'extracted/DATA/KC2FIRE.MVS'], False),
    # ('layout', [PY, 'tools/storycheck.py'], False),
    # ('vwf hook', [PY, 'tools/test_vwf.py'], False),
]


def check_compile():
    """Every tool at least compiles (catches syntax errors before a long build)."""
    bad = []
    for p in sorted(TOOLS.glob('*.py')) + sorted(paths.PROJECT.glob('*.py')):
        try:
            py_compile.compile(str(p), doraise=True, cfile=str(paths.WORK / 'pycheck.pyc'))
        except py_compile.PyCompileError as e:
            bad.append(str(e))
    for b in bad:
        print(f'    {b}')
    return not bad


def check_images():
    missing, changed, unsupported = catalog.stale()
    ok = True
    if missing or changed:
        print(f'    {len(missing) + len(changed)} automatic render(s) out of date - run tools/render.py:'
              f' {" ".join((missing + changed)[:10])}')
        ok = False
    table = catalog.rows()
    ids = {r['image'] for r in table}
    for r in table:
        if r['status'] not in catalog.STATUSES:
            print(f"    {r['image']}: unknown status {r['status']!r} (use {', '.join(catalog.STATUSES)})")
            ok = False
        if r['dup_of'] and r['dup_of'] not in ids:
            print(f"    {r['image']}: dup_of {r['dup_of']} is not in graphics.csv")
            ok = False
    wip = catalog.handmade_in_progress()
    if wip:
        print(f'    note: {len(wip)} hand edit(s) not approved yet (make_patches.py refuses them)')
    if unsupported:
        print(f'    note: {len(unsupported)} image(s) the renderer can\'t draw - hand edit them')
    return ok


def check_control():
    name = 'control'
    r = subprocess.run([PY, str(paths.PROJECT / 'build.py'), '--no-translation', '--unlocks', 'none',
                        '--name', name, '--build', str(paths.BUILD)], cwd=paths.PROJECT)
    if r.returncode:
        return False
    out = paths.BUILD / (name + paths.ROM.suffix)
    got = image.sha1(out)
    if got != paths.ORIGINAL['sha1']:
        print(f'    {paths.show(out)}: SHA-1 {got}, the original is {paths.ORIGINAL["sha1"]}')
        return False
    return True


def install_hook():
    git = paths.PROJECT / '.git'
    if not git.is_dir():
        sys.exit('not a git repository (run git init first)')
    hook = git / 'hooks' / 'pre-commit'
    hook.parent.mkdir(exist_ok=True)
    hook.write_text('#!/bin/sh\n# installed by tools/check.py --install-hook\nexec python3 tools/check.py --quick\n',
                    newline='\n')
    hook.chmod(0o755)
    print(f'installed {paths.show(hook)}: git commit now runs tools/check.py --quick')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--control', action='store_true')
    ap.add_argument('--install-hook', action='store_true')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.install_hook:
        return install_hook()
    paths.WORK.mkdir(parents=True, exist_ok=True)

    steps = [('compile', check_compile), ('images', check_images)]
    for name, cmd, quick in CHECKS:
        if quick or not args.quick:
            steps.append((name, lambda cmd=cmd: subprocess.run(cmd, cwd=paths.PROJECT).returncode == 0))
    if args.control:
        steps.append(('control build', check_control))
    failed = []
    for name, fn in steps:
        print(f'--- {name}', flush=True)
        if not fn():
            failed.append(name)
    print(f'\n{len(steps) - len(failed)}/{len(steps)} checks passed' + (f' - failed: {", ".join(failed)}' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
