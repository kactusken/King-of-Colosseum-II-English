#!/usr/bin/env python3
"""How far along the translation is: python3 tools/status.py [--files]

Text: entries and translated entries per folder (--files: per file), lint errors and warnings.
Images: graphics.csv rows by status, where the todo rows stand (automatic render, hand edit in
progress, nothing yet), out-of-date renders. No dependencies.
"""
import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import lint  # noqa: E402
import paths  # noqa: E402
import textdb  # noqa: E402


def pct(a, b):
    return f'{100 * a / b:3.0f}%' if b else '  -'


def text_status(per_file=False):
    groups = defaultdict(lambda: [0, 0])
    for e in textdb.entries():
        rel = e.file.relative_to(paths.TRANSLATION) if e.file.is_relative_to(paths.TRANSLATION) else e.file
        key = str(rel) if per_file else str(rel.parent)
        groups[key][0] += 1
        groups[key][1] += lint.done(e)
    return dict(sorted(groups.items()))


def image_status():
    table = catalog.rows()
    by_id = catalog.by_id(table)
    counts = Counter(r['status'] or '(blank)' for r in table)
    todo = Counter()
    missing, changed, unsupported = catalog.stale(table)
    out_of_date = set(missing) | set(changed)
    auto = 0                  # todo rows whose up-to-date automatic render is what the build uses
    for r in table:
        if r['status'] == 'todo':
            tag, _ = catalog.source(r, by_id)
            todo[{'HAND': 'hand edit in progress', 'AUTO': 'automatic render', 'DONE': 'approved file but todo',
                  None: 'nothing yet'}[tag]] += 1
            auto += tag == 'AUTO' and r['image'] not in out_of_date
    return len(table), counts, todo, missing, changed, unsupported, auto


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--files', action='store_true', help='text per file instead of per folder')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))

    print(f'{paths.GAME} - translation status\n')
    groups = text_status(args.files)
    total = [sum(v[0] for v in groups.values()), sum(v[1] for v in groups.values())]
    print(f'{"Text":40} {"entries":>8} {"done":>8}')
    for k, (n, d) in groups.items():
        print(f'  {k:38} {n:8} {d:8} {pct(d, n)}')
    print(f'  {"total":38} {total[0]:8} {total[1]:8} {pct(total[1], total[0])}')
    counts, _ = lint.run()
    print(f'  lint: {counts["error"]} error(s), {counts["warning"]} warning(s)\n')

    n, by_status, todo, missing, changed, unsupported, auto = image_status()
    print(f'Images ({paths.show(paths.GRAPHICS_CSV)}: {n} rows)')
    print('  ' + ('   '.join(f'{s} {by_status[s]}' for s in ('done', 'todo', 'keep', 'dup') if by_status[s])
                  or 'none catalogued yet')
          + ''.join(f'   {s} {c} (unknown status!)' for s, c in by_status.items() if s not in catalog.STATUSES))
    if todo:
        print('  todo: ' + ', '.join(f'{c} {what}' for what, c in todo.most_common()))
    if unsupported:
        print(f'  renderer can\'t draw {len(unsupported)} (hand edit them): {" ".join(unsupported[:12])}'
              + (' ...' if len(unsupported) > 12 else ''))
    if missing or changed:
        print(f'  out-of-date renders: {len(missing) + len(changed)} - run tools/render.py')
    wip = catalog.handmade_in_progress()
    if wip:
        print(f'  hand edits not yet approved: {len(wip)}')

    img_total = by_status['done'] + by_status['todo']
    if auto:
        print(f'  in English: {by_status["done"] + auto} of {img_total} '
              f'({by_status["done"]} approved, {auto} up-to-date automatic renders in the build)')
    # an up-to-date automatic render is in the build: it counts as finished (approve it to freeze it)
    parts = [('text', total[1], total[0]), ('images', by_status['done'] + auto, img_total)]
    done = sum(p[1] for p in parts)
    alln = sum(p[2] for p in parts)
    print(f'\nOverall: {pct(done, alln).strip()} finished ('
          + ', '.join(f'{name} {pct(a, b).strip()}' for name, a, b in parts) + ')')


if __name__ == '__main__':
    main()
