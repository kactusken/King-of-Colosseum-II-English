#!/usr/bin/env python3
"""Match Maker data in KC2FIRE.000: the show sheets, the shows and their team lists.

  mmdata.py dump [--force]     translation/text/mmdata.txt: every string to translate, once
  mmdata.py verify             every entry parses as below and writes back byte for byte; the
                               build step with no English changes nothing; every setting value
                               is one the game knows

These entries are Shift-JIS text files (CRLF lines, tab-separated columns) that the game parses
when Match Maker starts; the buffers they are copied into are freed afterwards. Strings can grow
(the files are re-read whole), but the game copies some fields into fixed buffers and compares
others with key strings in the executable - which tools/elftext.py may have translated - so this
step writes each kind of field differently. *From the code* (parsers named below):

- show sheets 2403-2422 (loader 0x1beb48), 2813-2820 (0x1ceaf4), 2837-2844 (0x1d2a50): 30 lines
  "value<TAB>○|×" per match, read by 0x1b4208. The value is never drawn: it is turned into a
  number by comparing it with the executable's keys for that setting (SETTING_KEYS, a jump table
  of 30 cases at 0x3adc70) after three prefix checks (PREFIX_KEYS: "set by the show", "as on the
  previous screen", "※ see ..."). This step writes each value as the executable's key reads after
  elf.txt (ASCII, as elftext.py writes it); a prefix key shorter than its compare length is
  followed by a NUL so the game's strncmp still matches. The menu shows the values from pictures.
- shows 2805-2812 (0x1cec88), records separated by an empty line: name, goal, venue, capacity,
  crowd, four numbers, roster size, then notes (several lines, maybe in "quotes", up to the next
  empty line). Copied into 0x228-byte records: name 0x80, goal 0x80, venue 0x20 (compared with
  VENUE_KEYS for the venue number, then cut at "("), notes 0x100 (quotes dropped); crowd and
  roster size are skipped. Drawn by 0x1b1410, which turns ASCII digits, letters and + - * / , .
  " ' : ; ( ) into full-width itself; any other single byte is copied as half of a pair (and
  dropped at the end of a string), so other symbols are written full-width.
- team lists 2797-2804 (0x1d1158): "team<TAB>numbers", the name copied into 32 bytes and later
  compared (strcmp) with the team names in the team tables (TEAM_TABLES) - so the names here
  follow those tables as the build has them when this step runs (list it after any team step).
- title holders 2829-2836 (0x1d2b00) are written by tools/teamdata.py; this step only checks
  the title names: 0x1e11b4 searches them (strstr) for TITLE_KEYS (U-30, junior, light heavy,
  middle, welter, heavy) to decide who may hold the title, so the English must contain the same
  keys, as the executable has them after elf.txt.
Every rewrite is checked by running the game's matching on the English: the same setting numbers,
venue numbers, title classes and teams as the Japanese, and the field sizes.

mmdata.txt: blocks `@ <kind>.<n> max=<bytes> in <entries>`, kinds name, goal, venue, crowd, notes
(all shows). No EN lines = the Japanese stays. Roster sizes ("18名") are converted.
"""
import argparse
import functools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import elftext  # noqa: E402
import font  # noqa: E402
import paths  # noqa: E402
import pools  # noqa: E402

PACK = '/DATA/KC2FIRE.000'
ELF = 'SLPM_656.02'
SHEETS = list(range(2403, 2423)) + list(range(2813, 2821)) + list(range(2837, 2845))
SHOWS = list(range(2805, 2813))
TEAMS = list(range(2797, 2805))
TITLES = list(range(2829, 2837))
ENTRIES = SHEETS + SHOWS + TEAMS + TITLES
CRLF = b'\r\n'
SJ = lambda s: s.encode('cp932')  # noqa: E731

# Executable file offsets of the key strings (from the parsers named in the docstring).
PREFIX_KEYS = ((0x2ae780, 20), (0x2ae798, 10), (0x2e6160, 2))     # strncmp(line, key, n) -> 0
SETTING_KEYS = (
    (0x2ae7a8, 0x2ae7b8, 0x2ae7d0, 0x2ae7e8, 0x2ae810, 0x2ae828, 0x2ae840, 0x2e6168),  # rules
    (0x2ae850, 0x2ae860),  # how a match is won
    (0x2e6170, 0x2e6178),  # rounds
    (0x2e6180, 0x2e6188, 0x2e6190, 0x2e6198, 0x2e61a0, 0x2e61a8, 0x2e61b0),  # time limit
    (0x2ae878, 0x2ae888),  # falls
    (0x2e61b8, 0x2e61c0, 0x2e6180, 0x2e6188, 0x2e6190),  # round time
    (0x2e61c8, 0x2e61d0, 0x2e61d8, 0x2e61e0, 0x2e61e8, 0x2e61f0, 0x2e61f8, 0x2e6200, 0x2e6208,
     0x2e6210, 0x2e6218, 0x2e6220, 0x2e6228, 0x2e6230, 0x2e6238, 0x2e61b0),  # rounds
    (0x2e6170, 0x2e6178),  # points
    (0x2e6240, 0x2e6248, 0x2e6250),  # number of points
    (0x2e6258, 0x2e6260, 0x2e6268, 0x2e6270, 0x2e6240),  # down points
    (0x2e6258, 0x2e6260, 0x2e6268, 0x2e6270, 0x2e6240),  # escape points
    (0x2ae898, 0x2ae8b0, 0x2e6178),  # judges
    (0x2e61c8, 0x2e61d0, 0x2e61d8, 0x2e61e0, 0x2e61e8, 0x2e61f0, 0x2e61f8, 0x2e6200),  # CPU level
    (0x2e6278, 0x2e6280, 0x2e6288, 0x2e6290),  # game speed
    (0x2ae8c8, 0x2ae8d8, 0x2ae8e8, 0x2e6298, 0x2e62a0, 0x2e62a8, 0x2e62b0, 0x2e62b8, 0x2e62c0,
     0x2ae8f8, 0x2ae908, 0x2ae918, 0x2e62c8, 0x2ae930, 0x2ae940, 0x2ae950, 0x2e62d0, 0x2e62d8,
     0x2ae960, 0x2ae970, 0x2e62e0, 0x2ae980, 0x2ae990, 0x2ae9a8, 0x2ae9c0, 0x2ae9d0, 0x2e62e8),  # ring
    (0x2ae9e0, 0x2ae9f0, 0x2aea00, 0x2aea10, 0x2aea20, 0x2aea30, 0x2aea48, 0x2aea60, 0x2aea78),  # crowd
    (0x2aea88, 0x2aeaa8, 0x2aeab8, 0x2aead0, 0x2aeae8, 0x2aeaf8, 0x2aeb08, 0x2aeb18, 0x2aeb28,
     0x2aeb38, 0x2aeb48, 0x2aeb58),  # venue
    (0x2e6170, 0x2e6178), (0x2e6170, 0x2e6178), (0x2e6170, 0x2e6178), (0x2e6170, 0x2e6178),
    (0x2e62f0, 0x2e6210, 0x2e6178),  # count-out
    (0x2e6170, 0x2e6178),
    (0x2e62f8, 0x2e6300, 0x2e6178),  # critical rate
    (0x2aeb68, 0x2aeb80, 0x2aeb90, 0x2aeba0, 0x2aebb0, 0x2aebc0, 0x2aebd0, 0x2aebe0, 0x2aebf0,
     0x2aec00),  # referee
    (0x2aec10, 0x2e6308, 0x2aec20, 0x2aec30),  # ring announcer
    (0x2aec40, 0x2e6178),  # caller
    (0x2aec50, 0x2aec60, 0x2e6178),  # colour commentator
    (0x2e6170, 0x2e6178), (0x2e6170, 0x2e6178),
)
VENUE_KEYS = (0x2afa38, 0x2afa50, 0x2afa60, 0x2afa78, 0x2afa90, 0x2afaa0, 0x2afab0, 0x2afac0,
              0x2afad0, 0x2afae0, 0x2afaf0)                       # shows: strcmp, first match
TITLE_KEYS = (0x2b04e8, 0x2b04f8, 0x2b0508, 0x2e6530, 0x2b0518, 0x2e6538)  # strstr in title names
CROWD_KEYS = SETTING_KEYS[15]                                       # shows: crowd (not read)
TEAM_TABLES = (2003, 2020, 2000, 2017)       # u32 count, 12 bytes, count x 0x28: name (0x24) ...
TEAM_FIRST, TEAM_STRIDE, TEAM_NAME = 0x10, 0x28, 0x24
FW_SPACE = SJ('　')

# Show text is drawn by 0x1b1410, which converts these single bytes to full-width itself.
SAFE_1410 = set('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz +-*/,.\'":;()')
SHOW_FIELDS = ('name', 'goal', 'venue', 'capacity', 'crowd', 'n1', 'n2', 'n3', 'size')
LIMITS = {'name': 0x7f, 'goal': 0x7f, 'venue': 0x1f, 'notes': 0xff, 'team': 0x1f, 'crowd': 0x7f}
KINDS = ('name', 'goal', 'venue', 'crowd', 'notes')
SIZE = re.compile(r'^([0-9?]+)名(?:（([0-9]+)名）)?$')


def text_path():
    return paths.TEXT / 'mmdata.txt'


@functools.lru_cache(maxsize=None)
def original(entry):
    p = paths.EXTRACTED / 'DATA' / 'KC2FIRE_000' / f'{entry:05d}.bin'
    if not p.exists():
        sys.exit(f'{paths.show(p)} not found - run tools/extract.py first')
    return p.read_bytes()


def cstr(data, off):
    return bytes(data[off:data.index(b'\0', off)])


# ---------------------------------------------------------------- formats: parse and write back

def parse_sheet(data):
    """[(value, flag)] per line (30 lines a match)."""
    assert data.endswith(CRLF)
    return [tuple(ln.split(b'\t')) for ln in data[:-2].split(CRLF)]


def write_sheet(rows):
    return CRLF.join(b'\t'.join(r) for r in rows) + CRLF


def parse_shows(data):
    """[{field: bytes, 'notes': bytes, 'quoted': bool, 'tail': bytes}] (records split on an empty line)."""
    out = []
    for rec in data.split(CRLF + CRLF):
        if not rec:
            out.append(None)
            continue
        parts = rec.split(CRLF, len(SHOW_FIELDS))
        r = dict(zip(SHOW_FIELDS, parts))
        notes = parts[len(SHOW_FIELDS)]
        r['tail'] = CRLF if notes.endswith(CRLF) else b''
        notes = notes[:len(notes) - len(r['tail'])]
        r['quoted'] = len(notes) >= 2 and notes[:1] == b'"' and notes[-1:] == b'"'
        r['notes'] = notes[1:-1] if r['quoted'] else notes
        out.append(r)
    return out


def write_shows(recs):
    out = []
    for r in recs:
        if r is None:
            out.append(b'')
            continue
        notes = b'"' + r['notes'] + b'"' if r['quoted'] else r['notes']
        out.append(CRLF.join([r[f] for f in SHOW_FIELDS] + [notes + r['tail']]))
    return (CRLF + CRLF).join(out)


def parse_lines(data):
    """Team lists and title holders: [[column, ...]] per line."""
    assert data.endswith(CRLF)
    return [ln.split(b'\t') for ln in data[:-2].split(CRLF)]


def write_lines(rows):
    return CRLF.join(b'\t'.join(r) for r in rows) + CRLF


def title_groups(rows):
    """(title row index, [holder row indexes]) for each title (title, 3 holder lines, ○/× lines)."""
    marks = (SJ('○'), SJ('×'))
    out, i = [], 0
    while i < len(rows):
        out.append((i, [i + 1, i + 2, i + 3]))
        i += 4
        while i < len(rows) and rows[i][0][:2] in marks:
            i += 1
    return out


# ---------------------------------------------------------------- what the other steps write

class Context:
    """The executable's keys and team names as the build writes them."""

    def __init__(self, packs=None, english=True):
        self.elf = original_elf()
        self.glyphs = pools.font_codes(packs) if packs else None
        self.elf_en = self.elf          # the executable as elftext.py's step leaves it
        if english:
            p = paths.TEXT / 'elf.txt'
            if p.exists():
                self.elf_en = bytearray(self.elf)
                for b in blocks.BlockFile(p).blocks:
                    if b.english:
                        off = int(b.id, 16)
                        new = elftext.encode('\n'.join(b.english), self.glyphs or {}, p)
                        n = max(self.elf.index(b'\0', off) - off, len(new))
                        self.elf_en[off:off + n] = new.ljust(n, b'\0')
        self.teams = team_names(packs) if (packs and english) else {}

    def key(self, off, english=True):
        return cstr(self.elf_en if english else self.elf, off)


@functools.lru_cache(maxsize=None)
def original_elf():
    p = paths.EXTRACTED / ELF
    if not p.exists():
        sys.exit(f'{paths.show(p)} not found - run tools/extract.py first')
    return p.read_bytes()


def team_names(packs):
    """{Japanese team name: name now in the build's team tables} for names a step changed."""
    out = {}
    for e in TEAM_TABLES:
        old, new = original(e), packs.get(PACK, e)
        n = int.from_bytes(old[:4], 'little')
        for i in range(n):
            at = TEAM_FIRST + i * TEAM_STRIDE
            a, b = cstr(old[at:at + TEAM_NAME] + b'\0', 0), cstr(new[at:at + TEAM_NAME] + b'\0', 0)
            if a != b:
                if out.get(a, b) != b:
                    sys.exit(f'mmdata: team {a.decode("cp932")!r} has two different names in the team tables '
                             f'({out[a]!r}, {b!r}) - the team lists can only match one')
                out[a] = b
    return out


# ---------------------------------------------------------------- the game's matching, simulated

def strncmp(a, b, n):
    """True when the C strncmp(a, b, n) finds them equal."""
    for i in range(n):
        x, y = a[i] if i < len(a) else 0, b[i] if i < len(b) else 0
        if x != y:
            return False
        if x == 0:
            return True
    return True


def setting_number(value, k, ctx, english):
    """What 0x1b4208 stores for value in setting k (None = no key matched, the byte keeps 0)."""
    for off, n in PREFIX_KEYS:
        if strncmp(value, ctx.key(off, english), n):
            return 'prefix'
    v = value.split(b'\0')[0]
    for i, off in enumerate(SETTING_KEYS[k]):
        if v == ctx.key(off, english):
            return i
    return None


def venue_number(venue, ctx, english):
    for i, off in enumerate(VENUE_KEYS):
        if venue == ctx.key(off, english):
            return i
    return None


def title_class(title, ctx, english):
    return tuple(ctx.key(off, english) in title for off in TITLE_KEYS)


# ---------------------------------------------------------------- encoding

def encode_show(text, glyphs, where):
    """Show text for 0x1b1410: its own ASCII set as single bytes, anything else full-width."""
    out = bytearray()
    for ch in text:
        if ch == '\n':
            out += CRLF
        elif ch in SAFE_1410:
            out.append(ord(ch))
        else:
            out += pools.encode(ch, glyphs, where)
    return bytes(out)


def load_text(path, glyphs):
    """{(kind, Japanese bytes): English bytes} from mmdata.txt."""
    bf = blocks.BlockFile(path)
    out, problems = {}, []
    for b in bf.blocks:
        kind = b.id.split('.')[0]
        if kind not in KINDS:
            problems.append(f'{path.name}:{b.line}: unknown kind {kind!r} (one of {", ".join(KINDS)})')
            continue
        if not b.english:
            continue
        jp = '\n'.join(bf.source(b))
        en = '\n'.join(b.english)
        where = f'{paths.show(path)}:{b.line}'
        if kind != 'notes' and len(b.english) > 1:
            problems.append(f'{where}: {kind} is one line')
        bad = set(en) & set('"%' + ('(' if kind == 'venue' else ''))
        if bad:
            problems.append(f'{where}: no {" ".join(sorted(bad))} here (the game drops " and reads % as a format'
                            + (', and cuts a venue at "("' if kind == 'venue' else '') + ')')
            continue
        enc = encode_show(en, glyphs, where)
        if kind in LIMITS and len(enc) > LIMITS[kind]:
            problems.append(f'{where}: {len(enc)} bytes, room for {LIMITS[kind]}: {en!r}')
        out[kind, SJ(jp).replace(b'\n', CRLF)] = enc
    if problems:
        sys.exit('\n'.join(problems[:20]))
    return out


def convert_size(v):
    m = SIZE.match(v.decode('cp932'))
    if not m:
        return v
    return (m.group(1) + (f' ({m.group(2)})' if m.group(2) else '')).encode('ascii')


# ---------------------------------------------------------------- the step

def rewrite(entry, data, text, ctx, problems):
    """One entry with the English in; problems collects what doesn't hold."""
    if entry in SHEETS:
        rows = parse_sheet(data)
        out = []
        for i, (value, *rest) in enumerate(rows):
            k = i % 30
            want = setting_number(value, k, ctx, False)
            new = value
            for off, n in PREFIX_KEYS:
                jp, en = ctx.key(off, False), ctx.key(off)
                if strncmp(value, jp, n):
                    if en != jp:
                        new = en if len(en) >= n else en + b'\0'
                    break
            else:
                if isinstance(want, int):
                    new = ctx.key(SETTING_KEYS[k][want])
            if setting_number(new, k, ctx, True) != want:
                problems.append(f'{entry} line {i + 1}: {value.decode("cp932")!r} -> {new!r} would read as '
                                f'another setting value - the keys for setting {k} clash in elf.txt')
            out.append((new, *rest))
        return write_sheet(out)
    if entry in SHOWS:
        recs = parse_shows(data)
        for r in recs:
            if r is None:
                continue
            for f in ('name', 'goal'):
                r[f] = text.get((f, r[f]), r[f])
            want = venue_number(r['venue'], ctx, False)
            r['venue'] = ctx.key(VENUE_KEYS[want]) if want is not None else text.get(('venue', r['venue']), r['venue'])
            if venue_number(r['venue'], ctx, True) != want:
                problems.append(f'{entry}: venue {r["venue"]!r} reads as another venue number than the Japanese')
            crowd = next((off for off in CROWD_KEYS if ctx.key(off, False) == r['crowd']), None)
            r['crowd'] = ctx.key(crowd) if crowd else text.get(('crowd', r['crowd']), r['crowd'])
            r['size'] = convert_size(r['size'])
            r['notes'] = text.get(('notes', r['notes']), r['notes'])
            for f in ('name', 'goal', 'venue', 'notes'):
                if len(r[f]) > LIMITS[f]:
                    problems.append(f'{entry}: {f} {r[f]!r}: {len(r[f])} bytes, room for {LIMITS[f]}')
        return write_shows(recs)
    if entry in TEAMS:
        rows = parse_lines(data)
        for row in rows:
            row[0] = ctx.teams.get(row[0], row[0])
            if len(row[0]) > LIMITS['team']:
                problems.append(f'{entry}: team {row[0]!r}: {len(row[0])} bytes, room for {LIMITS["team"]}')
        return write_lines(rows)
    if entry in TITLES:
        # written by tools/teamdata.py; checked here: the title classes the game reads from the names
        rows, orig = parse_lines(data), parse_lines(original(entry))
        for t, _ in title_groups(orig):
            jp, now = orig[t][0], rows[t][0] if t < len(rows) else b''
            if now == jp:
                continue              # not translated (yet)
            if title_class(now, ctx, True) != title_class(jp, ctx, False):
                keys = [ctx.key(off).decode('cp932') for off in TITLE_KEYS]
                problems.append(f'{entry}: title {now!r} must contain the same of {keys} as {jp.decode("cp932")!r} '
                                '(0x1e11b4: the game picks who may hold it by these words) - fix teamdata.csv or elf.txt')
        return data
    raise ValueError(entry)


def step(path, files):
    """build.py text step: Match Maker sheets, shows and team lists in English (titles: checked)."""
    packs = files.packs
    ctx = Context(packs)
    text = load_text(Path(path), ctx.glyphs)
    problems, changed = [], 0
    for e in ENTRIES:
        data = packs.get(PACK, e)
        new = rewrite(e, data, text, ctx, problems)
        if new != data:
            packs.put(PACK, e, new)
            changed += 1
    if problems:
        sys.exit(f'{paths.show(path)}:\n  ' + '\n  '.join(problems[:20]))
    print(f'text: {paths.show(path)}: {changed} of {len(ENTRIES)} Match Maker entries')


# ---------------------------------------------------------------- dump / verify

def strings():
    """[(kind, Japanese str, [entries])] in file order, each (kind, text) once."""
    ctx = Context(english=False)
    venue_jp = {ctx.key(off, False) for off in VENUE_KEYS}
    crowd_jp = {ctx.key(off, False) for off in CROWD_KEYS}
    seen = {}
    for e in SHOWS:
        for r in parse_shows(original(e)):
            if r is None:
                continue
            for kind in ('name', 'goal', 'venue', 'crowd', 'notes'):
                v = r[kind]
                if kind == 'venue' and v in venue_jp or kind == 'crowd' and v in crowd_jp:
                    continue
                seen.setdefault((kind, v), []).append(e)
    return [(k, v.decode('cp932').replace('\r\n', '\n'), sorted(set(es))) for (k, v), es in seen.items()]


def ranges(es):
    out, start = [], None
    for i, e in enumerate(es):
        if start is None:
            start = e
        if i + 1 == len(es) or es[i + 1] != e + 1:
            out.append(str(start) if start == e else f'{start}-{e}')
            start = None
    return ','.join(out)


def dump(force=False):
    out = text_path()
    if out.exists() and not force:
        print(f'{paths.show(out)} exists - kept (--force to dump again and lose its English)')
        return
    lines = ['# Match Maker shows (KC2FIRE.000 2805-2812) - see tools/mmdata.py.',
             '# Shows: name, goal, venue (only venues the executable has no key for; the others follow',
             '# elf.txt), crowd, notes (several lines). Drawn by a routine that takes ASCII letters, digits,',
             '# spaces and + - * / , . \' : ; ( ) - other symbols go in full-width. No " or %.',
             '# max= is the room in bytes.', '']
    count = {}
    for kind, jp, es in strings():
        count[kind] = count.get(kind, 0) + 1
        lines.append(f'@ {kind}.{count[kind]} max={LIMITS.get(kind, 0)} in {ranges(es)}')
        lines += [f'JP {ln}' if ln else 'JP' for ln in jp.split('\n')]
        lines.append('')
    out.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    print(f'{paths.show(out)}: {sum(count.values())} strings ({", ".join(f"{k} {n}" for k, n in count.items())})')


class _Packs:
    def get(self, pack, e):
        return original(e)


def verify():
    ok = True
    for e in ENTRIES:
        data = original(e)
        if e in SHEETS:
            rows = parse_sheet(data)
            same = write_sheet(rows) == data and len(rows) % 30 == 0 and all(len(r) == 2 for r in rows)
        elif e in SHOWS:
            same = write_shows(parse_shows(data)) == data
        else:
            same = write_lines(parse_lines(data)) == data
        if not same:
            print(f'{e}: read -> write DIFFERENT (or not the expected layout)')
            ok = False
    print(f'{len(ENTRIES)} entries: read -> write ' + ('byte-identical' if ok else 'DIFFERENT'))
    # the step with no English (Japanese keys and teams) must change nothing
    ctx = Context(_Packs(), english=False)
    problems, diff = [], []
    for e in ENTRIES:
        if rewrite(e, original(e), {}, ctx, problems) != original(e) and e not in SHOWS:
            diff.append(e)
        if e in SHOWS:      # roster sizes are converted even without English; everything else stays
            recs = parse_shows(original(e))
            for r in recs:
                if r:
                    r['size'] = convert_size(r['size'])
            if rewrite(e, original(e), {}, ctx, problems) != write_shows(recs):
                diff.append(e)
    if diff or problems:
        print(f'step without English changes entries {diff}: ' + '; '.join(problems[:5]))
        ok = False
    else:
        print('step without English: no change')
    # every setting value is a key the game knows
    unknown = {}
    for e in SHEETS:
        for i, (value, flag) in enumerate(parse_sheet(original(e))):
            if setting_number(value, i % 30, ctx, False) is None:
                unknown.setdefault(value.decode('cp932'), []).append(f'{e}:{i + 1}')
    for v, where in unknown.items():
        print(f'value {v!r} matches no key ({", ".join(where[:4])}) - the game keeps 0 for it')
    print(f'{len(SHEETS)} sheets: ' + ('every value matches a key' if not unknown else f'{len(unknown)} unknown values'))
    # with elf.txt and mmdata.txt: every sheet value and venue must still resolve to the same key
    ctx = Context(_Packs())
    text = load_text(text_path(), ctx.glyphs) if text_path().exists() else {}
    problems = []
    for e in SHEETS + SHOWS:
        rewrite(e, original(e), text, ctx, problems)
    for p in problems:
        print(p)
    print('English parse: ' + ('every setting and venue resolves as in Japanese' if not problems else f'{len(problems)} problems'))
    return ok and not problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('dump'); s.add_argument('--force', action='store_true')
    sub.add_parser('verify')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'dump':
        dump(args.force)
        return 0
    return 0 if verify() else 1


if __name__ == '__main__':
    sys.exit(main())
