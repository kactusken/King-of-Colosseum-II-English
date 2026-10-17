#!/usr/bin/env python3
"""Run one build text step against the unpacked files in extracted/ - no disc image, nothing written.

  stepcheck.py <module> <text file>     e.g. stepcheck.py pools translation/text/messages.txt

Imports tools/<module>.py, calls its step(path, files) the way build.py does, and prints which files
(and pack entries) the step changed; the step's own errors exit non-zero as in a build. For testing
a new step while the build image is busy - several agents working in parallel, each on its own tool
and text file, can all test at once without touching build/ (FRAMEWORK.md, section 14).

files.get(name) / files.put(name, data) read extracted/<name> ('/SLPM_123.45' -> extracted/SLPM_123.45).
If the project's build has a Packs class (archives unpacked by tools/extract.py), list the unpacked
folders in PACK_DIRS so files.packs.get(pack, entry) / .put(...) work here too.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

# archive in the image -> its unpacked folder under extracted/, one file per entry: NNNNN.bin
PACK_DIRS = {'/DATA/KC2FIRE.000': 'DATA/KC2FIRE_000', '/DATA/KC2FIRE.001': 'DATA/KC2FIRE_001',
             '/DATA/KC2FIRE.MVS': 'DATA/KC2FIRE_MVS'}


class Packs:
    def __init__(self):
        self.cache, self.changed = {}, {}

    def get(self, name, k):
        if name not in PACK_DIRS:
            sys.exit(f'stepcheck: {name} is not in PACK_DIRS (tools/stepcheck.py)')
        if (name, k) not in self.cache:
            self.cache[name, k] = (paths.EXTRACTED / PACK_DIRS[name] / f'{k:05d}.bin').read_bytes()
        return self.cache[name, k]

    def put(self, name, k, data):
        old = self.get(name, k)
        self.cache[name, k] = bytes(data)
        if bytes(data) != old:
            self.changed.setdefault(name, {})[k] = bytes(data)


class Files:
    def __init__(self):
        self.data, self.changed = {}, set()
        self.packs = Packs()

    def get(self, name):
        if name not in self.data:
            self.data[name] = bytearray((paths.EXTRACTED / name.lstrip('/')).read_bytes())
        return self.data[name]

    def put(self, name, data):
        self.data[name] = bytearray(data)
        self.changed.add(name)


def main(argv=None):
    argv = paths.configure(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0 if argv[:1] in (['-h'], ['--help']) else 2
    mod, path = argv[0], Path(argv[1])
    files = Files()
    importlib.import_module(mod).step(path if path.is_absolute() else paths.PROJECT / path, files)
    for name, entries in files.packs.changed.items():
        print(f'changed {name}: entries {sorted(entries)}')
    for name in sorted(files.changed):
        print(f'changed {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
