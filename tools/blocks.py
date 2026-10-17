#!/usr/bin/env python3
"""Message block files (translation/script/*.txt, translation/text/*.txt): read and write.

    # What this file holds, its limits and its control codes (read before editing).
    # limit lines=3 chars=28        <- optional: checked by tools/lint.py for every block
    # tag JP                        <- optional: the source-language tag (default JP)

    @ 012
    JP 「俺は・・・勝ったのか・・・
    JP 　手に入れたのか・・・・
    EN "I... won...?
    EN  Did I really get it...?"

`@` starts a block; the rest of the `@` line is its id and, in menu files, build metadata (address,
original length, ...) that isn't for editing. Source lines are reference only. EN lines are the
translation; a block with no EN lines keeps the original. One tag + one space, then the text
exactly (leading spaces count). `#` lines inside a block are kept as comments.

  blocks.py show <file> [id...]      print blocks (all, or the given ids)
  blocks.py stats <file>...          blocks / translated per file
"""
import re
import sys
from pathlib import Path

DEFAULT_TAG = 'JP'
EN = 'EN'


class Block:
    def __init__(self, ident, meta, line):
        self.id, self.meta, self.line = ident, meta, line
        self.lines = []  # (tag, text) in file order: tag is the source tag, EN or '#'

    def tagged(self, tag):
        return [t for k, t in self.lines if k == tag]

    @property
    def english(self):
        return self.tagged(EN)

    @english.setter
    def english(self, lines):
        """Replace the EN lines (placed after the last non-EN line)."""
        rest = [(k, t) for k, t in self.lines if k != EN]
        self.lines = rest + [(EN, t) for t in lines]


class BlockFile:
    def __init__(self, path):
        self.path = Path(path)
        self.header, self.blocks, self.tag, self.limits = [], [], DEFAULT_TAG, {}
        cur = None
        for n, raw in enumerate(self.path.read_text(encoding='utf-8').splitlines(), 1):
            if raw.startswith('@'):
                ident, _, meta = raw[1:].strip().partition(' ')
                cur = Block(ident, meta.strip(), n)
                self.blocks.append(cur)
            elif cur is None:
                self.header.append(raw)
                m = re.match(r'#\s*limit\s+(.*)', raw)
                if m:
                    self.limits.update((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', m.group(1)))
                m = re.match(r'#\s*tag\s+(\S+)', raw)
                if m:
                    self.tag = m.group(1)
            elif raw.startswith('#'):
                cur.lines.append(('#', raw))
            elif raw.strip() == '':
                continue
            else:
                tag, _, text = raw.partition(' ')
                if tag not in (self.tag, EN):
                    raise ValueError(f'{self.path}:{n}: line should start with "{self.tag} ", "{EN} ", "@" or "#"')
                cur.lines.append((tag, text))
        while self.header and not self.header[-1].strip():
            self.header.pop()
        ids = [b.id for b in self.blocks]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f'{self.path}: duplicate block ids {", ".join(sorted(dup))}')

    def source(self, block):
        return block.tagged(self.tag)

    def get(self, ident):
        return next((b for b in self.blocks if b.id == ident), None)

    def text(self):
        out = self.header + ['']
        for b in self.blocks:
            out.append(f'@ {b.id} {b.meta}'.rstrip())
            out += [t if k == '#' else f'{k} {t}' for k, t in b.lines]
            out.append('')
        return '\n'.join(out)

    def save(self, path=None):
        Path(path or self.path).write_text(self.text(), encoding='utf-8', newline='\n')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) >= 2 and argv[0] == 'show':
        bf = BlockFile(argv[1])
        for b in bf.blocks:
            if argv[2:] and b.id not in argv[2:]:
                continue
            print(f'@ {b.id} {b.meta}'.rstrip())
            for k, t in b.lines:
                print(t if k == '#' else f'{k} {t}')
            print()
    elif len(argv) >= 2 and argv[0] == 'stats':
        for p in argv[1:]:
            bf = BlockFile(p)
            done = sum(1 for b in bf.blocks if b.english)
            print(f'{p}: {done}/{len(bf.blocks)} translated')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
