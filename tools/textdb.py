#!/usr/bin/env python3
"""Every translatable string in translation/, as one list - for lint, status and fill.

  textdb.py [--untranslated] [text]     list entries (optionally only untranslated / matching text)

Sources:
  script/*.txt, text/*.txt   message blocks (tools/blocks.py): one entry per block
  text/*.csv                 tables: a `japanese` + `english` column pair, or any `X` + `en_X` pairs
                             (one entry per filled source cell)

Entry fields: file, key (block id / row:column), source, english ('' = untranslated), limits
(from a block file's `# limit` line, or the row's max_bytes / refs), line, notes (a block's
`#` comments or the row's notes column).
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import paths  # noqa: E402

SOURCE_COLUMN, ENGLISH_COLUMN = 'japanese', 'english'


class Entry:
    def __init__(self, file, key, source, english, limits, line, notes=''):
        self.file, self.key, self.source, self.english, self.limits, self.line, self.notes = \
            file, key, source, english, limits, line, notes

    @property
    def where(self):
        return f'{paths.show(self.file)}:{self.line} [{self.key}]'


def text_files():
    out = []
    for d in (paths.SCRIPT, paths.TEXT):
        if d.exists():
            out += sorted(p for p in d.rglob('*') if p.suffix in ('.txt', '.csv'))
    return out


def column_pairs(fieldnames):
    if SOURCE_COLUMN in fieldnames and ENGLISH_COLUMN in fieldnames:
        return [(SOURCE_COLUMN, ENGLISH_COLUMN)]
    return [(f[3:], f) for f in fieldnames if f.startswith('en_') and f[3:] in fieldnames]


def read_file(p):
    p = Path(p)
    if p.suffix == '.txt':
        bf = blocks.BlockFile(p)
        return [Entry(p, b.id, '\n'.join(bf.source(b)), '\n'.join(b.english), bf.limits, b.line,
                      '\n'.join(b.tagged('#')))
                for b in bf.blocks]
    out = []
    with open(p, encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        pairs = column_pairs(r.fieldnames or [])
        for n, row in enumerate(r, 2):
            limits = {k: int(row[k], 0) for k in ('max_bytes', 'refs') if (row.get(k) or '').strip()}
            for src, en in pairs:
                if (row.get(src) or '').strip():
                    key = row.get('id') or row.get('offset') or str(n)
                    out.append(Entry(p, f'{key}' + (f':{src}' if src != SOURCE_COLUMN else ''),
                                     row[src], row.get(en) or '', limits, n, row.get('notes') or ''))
    return out


def entries():
    out = []
    for p in text_files():
        out += read_file(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('text', nargs='?', default='', help='only entries whose source or English contains this')
    ap.add_argument('--untranslated', action='store_true')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    for e in entries():
        if args.untranslated and e.english:
            continue
        if args.text and args.text.lower() not in (e.source + e.english).lower():
            continue
        print(f'{e.where}\n  {e.source!r}\n  {e.english!r}')


if __name__ == '__main__':
    main()
