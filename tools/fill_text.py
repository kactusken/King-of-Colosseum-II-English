#!/usr/bin/env python3
"""Fill untranslated entries from a source -> English table: python3 tools/fill_text.py <table> [file...] [--overwrite]

<table> is a module in translation/fill/ (name, e.g. `menus` for menus_en.py, or a path) defining
EN = {"source": "English"}.
Every message block (source lines joined with newlines) or table cell whose source is a key gets
its English, unless it already has some (--overwrite replaces it). Without files, every text file
in translation/ is filled. The text files stay the source of truth; the table is a shortcut for
strings that repeat (menu labels, names).
"""
import argparse
import csv
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import paths  # noqa: E402
import textdb  # noqa: E402


def load_table(arg):
    p = Path(arg)
    for cand in (arg, f'{arg}.py', f'{arg}_en.py'):
        if not p.exists():
            p = paths.FILL / cand
    if not p.exists():
        sys.exit(f'{arg}: no such table (looked in {paths.show(paths.FILL)})')
    spec = importlib.util.spec_from_file_location(p.stem, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.EN


def fill_blocks(p, table, overwrite):
    bf = blocks.BlockFile(p)
    n = 0
    for b in bf.blocks:
        src = '\n'.join(bf.source(b))
        if src in table and (overwrite or not b.english):
            b.english = table[src].split('\n')
            n += 1
    if n:
        bf.save()
    return n


def fill_csv(p, table, overwrite):
    with open(p, encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        fields, rows = r.fieldnames, list(r)
    n = 0
    for row in rows:
        for src, en in textdb.column_pairs(fields):
            if row[src] in table and (overwrite or not row[en]):
                row[en] = table[row[src]]
                n += 1
    if n:
        with open(p, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('table')
    ap.add_argument('files', nargs='*', type=Path)
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    table = load_table(args.table)
    total = 0
    for p in args.files or textdb.text_files():
        n = (fill_blocks if p.suffix == '.txt' else fill_csv)(p, table, args.overwrite)
        if n:
            print(f'{paths.show(p)}: filled {n}')
        total += n
    print(f'{total} entries filled from {len(table)} table entries')


if __name__ == '__main__':
    main()
