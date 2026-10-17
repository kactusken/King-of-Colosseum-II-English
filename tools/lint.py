#!/usr/bin/env python3
"""Check the translation text: python3 tools/lint.py [--missing] [--warnings] [file...]

Errors (check.py and the build fail on these):
  source       source-language characters (kana, kanji) left in the English
  codes        control codes in the source missing from the English, or extra ones (CODE)
  lines        more lines than a block file's `# limit lines=N`
  chars        a line longer than `# limit chars=N` (characters; pixel widths need the game's
               own layout check)
  bytes        English longer than a fixed table string's max_bytes (refs == 0), as encoded by
               encoded_length() - adjust it to how the build stores English
  listwidth    a roster.csv surname 128 px or wider (tools/font.py widths): the wrestler list
               draws each name into a 128 px canvas and wraps it, shifting every later name
               (docs/TECHNICAL.md "Wrestler-list width"); skipped until tools/extract.py has run
Warnings (shown with --warnings; counted by status.py):
  glossary     the source contains a glossary term but the English doesn't use its translation
               (translation/glossary.csv: japanese, english, notes; several accepted English forms
               separated by ' | '; put [glossary-ok] in a block comment or row note to silence; a
               glossary row noted [exact] only applies when the source is just that term)
  spacing      trailing spaces or double spaces in the English (leading spaces are left alone:
               continuation lines are often indented; [spacing-ok] in a comment / note when meant)
--missing also lists untranslated entries (status.py counts them). An entry left untranslated on
purpose carries [keep] and the reason in a block comment or the row's notes (already English,
number formats, keys the game compares, the name-entry password): it counts as done.
"""
import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
import textdb  # noqa: E402

SOURCE_CHARS = re.compile(r'[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]')
CODE = re.compile(r'%[-0-9.]*[sdx]')  # the game's control codes: printf formats (new lines are real lines)


def encoded_length(text):
    """Bytes the build stores for `text` (tools/font.py encode_text): 1 for spaces, new lines and
    printf formats, 2 for everything else."""
    plain = CODE.sub('', text)
    if '\n' in text:            # multi-line strings get full-width spaces (tools/pools.py encode)
        return len(text) - len(plain) + sum(1 if ch == '\n' else 2 for ch in plain)
    return len(text) - len(plain) + sum(1 if ch in ' \n' else 2 for ch in plain)


def glossary():
    if not paths.GLOSSARY.exists():
        return []
    with open(paths.GLOSSARY, encoding='utf-8', newline='') as f:
        return [(('=' if '[exact]' in (r.get('notes') or '') else '') + r['japanese'].strip(),
                 [e.strip() for e in r['english'].split(' | ') if e.strip()])
                for r in csv.DictReader(f) if (r.get('japanese') or '').strip() and (r.get('english') or '').strip()]


KEEP = '[keep]'


def done(e):
    """Translated, or deliberately kept as the original ([keep] in its comment / notes)."""
    return bool(e.english) or KEEP in e.notes


def check_entry(e, terms):
    """[(severity, kind, message)] for one entry."""
    out = []
    en = e.english
    if not en:
        return out
    m = SOURCE_CHARS.search(en)
    if m:
        out.append(('error', 'source', f'source-language text left in the English: {m.group()!r}'))
    a, b = Counter(CODE.findall(e.source)), Counter(CODE.findall(en))
    if a != b:
        miss, extra = list((a - b).elements()), list((b - a).elements())
        out.append(('error', 'codes', 'control codes ' + '; '.join(
            x for x in (f'missing {miss}' if miss else '', f'extra {extra}' if extra else '') if x)))
    lines = en.split('\n')
    if 'lines' in e.limits and len(lines) > e.limits['lines']:
        out.append(('error', 'lines', f'{len(lines)} lines, limit {e.limits["lines"]}'))
    if 'chars' in e.limits:
        for ln in lines:
            plain = CODE.sub('', ln)
            if len(plain) > e.limits['chars']:
                out.append(('error', 'chars', f'{len(plain)} characters, limit {e.limits["chars"]}: {ln!r}'))
    if 'max_bytes' in e.limits and e.limits.get('refs', 0) == 0 and encoded_length(en) > e.limits['max_bytes']:
        out.append(('error', 'bytes', f'{encoded_length(en)} bytes, room for {e.limits["max_bytes"]} (fixed string)'))
    if '[spacing-ok]' not in e.notes and any(ln != ln.rstrip() or '  ' in ln.strip() for ln in lines):
        out.append(('warning', 'spacing', f'trailing or double spaces: {en!r}'))
    for jp, accepted in terms:
        hit = e.source.strip() == jp[1:] if jp.startswith('=') else jp in e.source   # '=': [exact] term
        if hit and not any(x.lower() in en.lower() for x in accepted):
            out.append(('warning', 'glossary', f'{jp.lstrip("=")} should be "{" | ".join(accepted)}"'))
    return out


LIST_WIDTH = 128    # wrestler-list name canvas: a name this wide or wider wraps


def roster_width_errors(path):
    """[(line, surname, px)] for roster.csv surnames that wrap in the wrestler list."""
    import font
    try:
        f = font.Font('sys')
    except SystemExit:
        return []           # fonts not extracted yet
    out = []
    with open(path, encoding='utf-8', newline='') as fh:
        for n, row in enumerate(csv.DictReader(fh), 2):
            en = (row.get('english') or '').strip()
            if row.get('field') == 'surname' and en:
                px = sum(f.width(c)[1] * 2 for c in font.encode_text(en))
                if px >= LIST_WIDTH:
                    out.append((n, en, px))
    return out


class _Where:
    def __init__(self, path, line):
        self.where = f'{paths.show(path)}:{line} [surname]'


def run(files=None, missing=False):
    """{'error': n, 'warning': n, 'missing': n, 'total': n} plus the printed lines."""
    terms = glossary()
    ents = []
    for p in files or textdb.text_files():
        ents += textdb.read_file(p)
    report, counts = [], Counter()
    for e in ents:
        counts['total'] += 1
        if not e.english:
            if done(e):
                continue
            counts['missing'] += 1
            if missing:
                report.append(('missing', e, 'no English yet'))
            continue
        for sev, kind, msg in check_entry(e, [] if '[glossary-ok]' in e.notes else terms):
            counts[sev] += 1
            report.append((sev, e, f'{kind}: {msg}'))
    roster = [p for p in (files or textdb.text_files()) if Path(p).name == 'roster.csv']
    for p in roster:
        for n, en, px in roster_width_errors(p):
            counts['error'] += 1
            report.append(('error', _Where(p, n), f'listwidth: {en!r} is {px} px, the wrestler list wraps at {LIST_WIDTH}'))
    return counts, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='*', type=Path, help='only these text files (default: all)')
    ap.add_argument('--missing', action='store_true', help='also list untranslated entries')
    ap.add_argument('--warnings', action='store_true', help='also list warnings')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    counts, report = run(args.files or None, args.missing)
    for sev, e, msg in report:
        if sev == 'warning' and not args.warnings:
            continue
        print(f'{e.where}: {"! " if sev == "error" else ""}{msg}')
    print(f'{counts["total"]} entries, {counts["total"] - counts["missing"]} translated: '
          f'{counts["error"]} error(s), {counts["warning"]} warning(s)'
          + ('' if args.warnings or not counts['warning'] else ' (--warnings to list them)'))
    return 1 if counts['error'] else 0


if __name__ == '__main__':
    sys.exit(main())
