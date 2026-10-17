#!/usr/bin/env python3
"""Build the Survival Road page, docs/survival-road/index.html: every course and difficulty, the
opponent pools for each round, how a run goes (losses, continues, finals) and the souls it pays.

  survivalmap.py [--out PATH] [--template PATH] [--json PATH]

Reads the original entries (extracted/: KC2FIRE.000 2012/2013 opponent tables, 2019 roster, 2396
shop, 2398-2422 notices, grids and settings sheets, and the executable's tables) and the English
(translation/text/*.txt/*.csv, translation/graphics.csv), then embeds the data in
tools/survivalmap_template.html (shared parts: tools/pagekit.py; Google Fonts is its only
download). --json also writes the data. Rules the code applies are constants below with the
address they come from; docs/TECHNICAL.md "Survival Road" has the whole picture.
"""
import argparse
import csv
import json
import struct
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import mmdata  # noqa: E402
import pagekit  # noqa: E402
import rosterdb  # noqa: E402
import paths  # noqa: E402


def entry(n):
    return (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000' / f'{n:05d}.bin').read_bytes()


_ELF = None


def elf():
    global _ELF
    if _ELF is None:
        _ELF = (paths.EXTRACTED / 'SLPM_656.02').read_bytes()
    return _ELF


def vaddr_off(a):
    """File offset of a data address (second loadable segment, docs: 0x323d80 -> 0x224d80)."""
    return a - 0x323d80 + 0x224d80


def words(a, n):
    return list(struct.unpack_from(f'<{n}i', elf(), vaddr_off(a)))


def cstr_off(off):
    return elf()[off:elf().index(b'\0', off)].decode('cp932')


# ------------------------------------------------------------------ English sources

def elf_english():
    bf = blocks.BlockFile(paths.TEXT / 'elf.txt')
    return {int(b.id, 16): '\n'.join(b.english) for b in bf.blocks if b.english}


def teamdata_english():
    out = {}
    with open(paths.TEXT / 'teamdata.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['english']:
                out[(r['table'], r['field'], r['japanese'])] = r['english']
    return out


def graphics_english(image):
    with open(paths.GRAPHICS_CSV, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['image'] == image:
                jp = [s.strip() for s in r['japanese'].split(' | ')]
                en = [s.strip() for s in r['english'].split(' | ')] if r['english'] else []
                return [(j, (e if e and e != '=' else j)) for j, e in zip(jp, en + [''] * len(jp))]
    return []


class Names:
    """Wrestler id -> English name. Ids index the 410 records of roster 2019 (the roster Survival
    Road loads: 0x1bbb60 loads entries 0x7e3 = 2019 and 0x7e1 = 2017); a record's first variant
    block holds the surname / given name, translated in wrestlers.txt or roster.csv."""

    def __init__(self):
        self.d = entry(2019)
        self.n = struct.unpack_from('<I', self.d, 0)[0]
        self.base = 16 + 64 * self.n
        bf = blocks.BlockFile(paths.TEXT / 'wrestlers.txt')
        self.full = {}
        for b in bf.blocks:
            if b.english:
                self.full.setdefault('\n'.join(bf.source(b)), b.english[0])
        self.parts = {}
        with open(paths.TEXT / 'roster.csv', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r['english']:
                    self.parts.setdefault((r['field'], r['japanese']), r['english'])

    def jp(self, w):
        v = struct.unpack_from('<h', self.d, 16 + 64 * w + 2)[0]
        o = self.base + 4 + 0x8ed * v
        s = self.d[o:o + 15].split(b'\0')[0].decode('cp932')
        g = self.d[o + 15:o + 36].split(b'\0')[0].decode('cp932')
        return s, g

    def name(self, w):
        if w < 0:
            return None
        s, g = self.jp(w)
        for c in (s + '　' + g, s + '・' + g, s + g, g + s, g + '・' + s, g + '　' + s):
            if c in self.full:
                return self.full[c]
        parts = [self.parts.get(('given', g), g) if g else '', self.parts.get(('surname', s), s)]
        return ' '.join(p for p in parts if p)

    def jp_name(self, w):
        s, g = self.jp(w)
        return (s + '　' + g).strip('　')


# ------------------------------------------------------------------ constants from the code

DIFFICULTY_KEYS = [0x2af3f0, 0x2af400, 0x2af410, 0x2af420, 0x2af430]   # file offsets (0x3ae3f0...)
# 0x1bc1f8 jump table 0x3ae290: qualifier rounds (+0x26) and wins needed (+0x28) per difficulty
QUALIFIERS = {1: (3, 3), 2: (4, 3), 3: (4, 4), 4: (5, 5), 5: (5, 5)}
# 0x1bcbb0: finals (mode 2) rounds = wins needed; Easy has no finals (0x1bcad8 ends after round 3)
FINALS = {1: None, 2: 3, 3: 4, 4: 5, 5: 5}
# 0x1c3898 (table 0x3ae490): continues at the start of a run; + title bonus 0x1c3de8 (not Easy)
CONTINUES = {1: 0, 2: 3, 3: 2, 4: 1, 5: 0}
# 0x1bc3c4.. CPU level per difficulty/round: words 0x3ae0c0 (qualifiers) / 0x3ae150 (finals),
# index difficulty*6 + round; 0 = leave the sheet value
CPU_Q, CPU_F = words(0x3ae0c0, 36), words(0x3ae150, 36)
# critical rate per difficulty/round, built on the stack at 0x1bc484 / 0x1bc60c (0 High, 1 Normal, 2 None)
CRIT_KEYS = ['High', 'Normal', 'None']


def crit_table(finals):
    t = [0] * 36
    if not finals:
        for r in (1, 2, 3):
            t[6 + r] = 2
        for r in (1, 2, 3, 4):
            t[12 + r] = 1
    else:
        for r in (1, 2, 3):
            t[12 + r] = 1
    for r in (1, 2, 3, 4):
        t[18 + r] = 1
    for r in (1, 2, 3, 4, 5):
        t[24 + r] = 1
    for r in (1, 2, 3, 4):
        t[30 + r] = 1
    t[35] = 0
    return t


CRIT_Q, CRIT_F = crit_table(False), crit_table(True)
# 0x1be0e0: match rating -> grade
GRADES = [(6, 'S', 100), (5, 'A', 80), (4, 'B', 60), (3, 'C', 40), (2, 'D', 0)]
# 0x1bc930: base souls = words 0x3ae1e0[difficulty*7 + grade]
SOULS_BASE = words(0x3ae1e0, 42)
# 0x1bc97c (jump table 0x3ae2b0 on the title): bonus souls for an A / S match
TITLE_BONUS = {1: (300, 500), 2: (100, 200), 3: (75, 150), 4: (50, 100), 5: (50, 0), 6: (25, 0),
               7: (0, 0), 8: (0, 0)}
TITLE_CONTINUES = {7: 1, 8: 2}            # 0x1c3de8, table 0x3ae4d0 (not on Easy)
SETTING_NAMES = [e for _, e in graphics_english('000_01515')][:30]
COURSE_KEYS = {7: 0x2af460, 8: 0x2af470}  # shop row names that unlock a course (0x1c2f98)
DIFF_LOCK_KEYS = {4: 0x2af4a8, 5: 0x2af4c0}  # shop row names that unlock a difficulty (0x1c3a8c)


# ------------------------------------------------------------------ data readers

def grid(n):
    """2401 / 2402: 8 course blocks x 5 round rows x 5 difficulty columns -> rank classes."""
    rows = [ln.split('\t') for ln in entry(n).decode('cp932').split('\r\n')]
    out = {}
    for c in range(1, 9):
        for r in range(1, 6):
            cells = rows[(c - 1) * 5 + (r - 1)]
            for d in range(1, 6):
                cell = cells[d - 1] if d - 1 < len(cells) else ''
                out[c, r, d] = sorted({'EDCBAS'.index(ch) + 1 for ch in cell if ch in 'EDCBAS'})
    return out


def team_table(n):
    """2012 / 2013 (lpSurvivalTeam): 512 entries: two s32 wrestler ids at 8*i, course at
    0x1000+4i (2 and 3 swapped on load by 0x1bef30), rank class at 0x1800+4i, title limit at 0x2000+4i."""
    d = entry(n)
    out = []
    for i in range(512):
        a, b = struct.unpack_from('<ii', d, 8 * i)
        if a < 0 and b < 0:
            continue
        course, cls, lim = (struct.unpack_from('<i', d, base + 4 * i)[0] for base in (0x1000, 0x1800, 0x2000))
        course = {2: 3, 3: 2}.get(course, course)
        out.append({'i': i, 'ids': [a, b], 'course': course, 'class': cls, 'title_limit': lim})
    return out


def shop_rows():
    rows = []
    for ln in entry(2396).decode('cp932').split('\r\n'):
        if ln.strip():
            rows.append(ln.split('\t'))
    return rows


def display(k, jp, en):
    """Page wording for values whose executable keys stay Japanese (Match Maker keys, elf.txt)."""
    if en is None:
        return 'by difficulty'
    if jp == '3カウント':
        return '3 Count'
    if jp == '無制限':
        return 'No limit'
    if jp.endswith('分') and jp[:-1].isdigit():
        return jp[:-1] + ' min'
    if jp.endswith('点') and jp[:-1].isdigit():
        return jp[:-1] + (' pt' if jp[:-1] == '1' else ' pts')
    return en


class Settings:
    def __init__(self, elf_en):
        self.elf_en = elf_en

    def value(self, k, jp):
        for off, n in mmdata.PREFIX_KEYS:
            if mmdata.strncmp(jp.encode('cp932'), elf()[off:off + n], n):
                return None, 'prefix'
        for i, off in enumerate(mmdata.SETTING_KEYS[k]):
            if cstr_off(off) == jp:
                return self.elf_en.get(off, jp), i
        return jp, None

    def sheet(self, n):
        rows = mmdata.parse_sheet(entry(n))
        out = []
        for m in range(len(rows) // 30):
            rnd = []
            for k in range(30):
                v, flag = (x.decode('cp932') for x in rows[30 * m + k])
                en, idx = self.value(k, v)
                rnd.append({'setting': SETTING_NAMES[k], 'jp': v, 'en': en, 'display': display(k, v, en),
                            'key_index': idx, 'flag': flag})
            out.append(rnd)
        return out


# ------------------------------------------------------------------ build

def build():
    elf_en = elf_english()
    td = teamdata_english()
    names = Names()
    st = Settings(elf_en)
    course_jp = [ln for ln in entry(2400).decode('cp932').split('\r\n') if ln]
    course_long = graphics_english('000_02451')
    titles_img = graphics_english('000_02455')
    grids = {'singles': grid(2401), 'tag': grid(2402)}
    tables = {'singles': team_table(2012), 'tag': team_table(2013)}
    shop = shop_rows()

    def shop_req(name_off):
        key = cstr_off(name_off)
        for r in shop:
            if r[1] == key:
                promo, num, diff = r[5], r[6], r[7]
                diff_n = [cstr_off(o) for o in DIFFICULTY_KEYS].index(diff) + 1
                return {'shop_item': td.get(('shop', 'name', key), unicodedata.normalize('NFKC', key)), 'shop_item_jp': key,
                        'price_souls': int(r[3]),
                        'on_sale_when': ({'course': promo, 'cleared_at_least': diff_n} if promo else
                                         {'courses_cleared': int(num), 'cleared_at_least': diff_n})}
        return None

    # opponents
    opponents, links = {}, rosterdb.mode_links(2004)   # ids index the Survival Road roster copy
    for mode, t in tables.items():
        lst = []
        for e in t:
            a, b = e['ids']
            rec = {'entry': e['i'], 'course': e['course'], 'class': e['class'],
                   'class_letter': 'EDCBAS'[e['class'] - 1], 'title_limit': e['title_limit'] or None}
            if mode == 'singles':
                rec.update(wrestler=names.name(a), wrestler_jp=names.jp_name(a), wrestler_id=a,
                           second=names.name(b), second_jp=names.jp_name(b) if b >= 0 else None,
                           second_id=b if b >= 0 else None, link=links.get(a), second_link=links.get(b))
            else:
                rec.update(team=[names.name(a), names.name(b)], team_jp=[names.jp_name(a), names.jp_name(b)],
                           team_ids=[a, b], team_links=[links.get(a), links.get(b)])
            lst.append(rec)
        opponents[mode] = lst

    difficulties = []
    for d in range(1, 6):
        q_rounds, q_wins = QUALIFIERS[d]
        f = FINALS[d]
        difficulties.append({
            'id': d, 'name': elf_en.get(DIFFICULTY_KEYS[d - 1]), 'name_jp': cstr_off(DIFFICULTY_KEYS[d - 1]),
            'qualifiers': {'rounds': q_rounds, 'wins_needed': q_wins if d > 1 else None,
                           'cpu_level': [CPU_Q[d * 6 + r] or None for r in range(1, q_rounds + 1)],
                           'critical': [CRIT_KEYS[CRIT_Q[d * 6 + r]] for r in range(1, q_rounds + 1)]},
            'finals': None if f is None else {
                'rounds': f, 'wins_needed': f,
                'cpu_level': [CPU_F[d * 6 + r] or None for r in range(1, f + 1)],
                'critical': [CRIT_KEYS[CRIT_F[d * 6 + r]] for r in range(1, f + 1)]},
            'total_matches': q_rounds + (f or 0),
            'continues': CONTINUES[d],
            'souls_by_grade': {g: SOULS_BASE[d * 7 + n] for n, g, _ in GRADES},
            'locked_until': shop_req(DIFF_LOCK_KEYS[d]) if d in DIFF_LOCK_KEYS else None,
        })

    def pool(mode, course, classes, finals=False):
        out = []
        for o in opponents[mode]:
            if finals:
                ok = o['class'] >= 5
            else:
                ok = o['course'] == course and o['class'] in classes
            if ok:
                out.append(o['entry'])
        return out

    courses = []
    for c in range(1, 9):
        jp = course_jp[c - 1]
        long_jp, long_en = course_long[c - 1] if c - 1 < len(course_long) else (jp, jp)
        desc = course_long[8 + c - 1] if 8 + c - 1 < len(course_long) else ('', '')
        course = {'id': c, 'key_jp': jp, 'key': td.get(('shop', 'promotion', jp), jp),
                  'name': long_en.strip('〈〉'), 'name_jp': long_jp, 'description': desc[1],
                  'cut': c == 6, 'locked_until': shop_req(COURSE_KEYS[c]) if c in COURSE_KEYS else None,
                  'modes': {}}
        for mode, sheet_base, offered in (('singles', 0x963, c != 6), ('tag', 0x96c, c not in (6, 7))):
            sheet_no = sheet_base + c
            rounds = []
            for r, settings in enumerate(st.sheet(sheet_no), 1):
                by_d = {}
                for d in range(1, 6):
                    if r > QUALIFIERS[d][0]:
                        continue
                    classes = grids[mode][c, r, d]
                    by_d[d] = {'classes': ''.join('EDCBAS'[x - 1] for x in classes),
                               'cpu_level': CPU_Q[d * 6 + r] or None,
                               'critical': CRIT_KEYS[CRIT_Q[d * 6 + r]],
                               'pool': pool(mode, c, classes)}
                rounds.append({'round': r, 'by_difficulty': by_d, 'settings': settings})
            course['modes'][mode] = {'offered': offered, 'sheet_entry': sheet_no, 'rounds': rounds}
        courses.append(course)

    finals = {}
    for mode, n in (('singles', 2421), ('tag', 2422)):
        rounds = []
        for r, settings in enumerate(st.sheet(n), 1):
            by_d = {d: {'cpu_level': CPU_F[d * 6 + r] or None, 'critical': CRIT_KEYS[CRIT_F[d * 6 + r]]}
                    for d in range(2, 6) if r <= FINALS[d]}
            rounds.append({'round': r, 'by_difficulty': by_d, 'settings': settings})
        finals[mode] = {'sheet_entry': n, 'pool': pool(mode, None, None, finals=True), 'rounds': rounds}

    title_names = [titles_img[i] for i in range(29, 37)]
    titles = []
    rule = {1: 'average grade A with an S among the last 10, or average S',
            2: 'average grade A, no S among the last 10',
            3: 'average grade B with 4+ A among the last 10', 4: 'average grade B with 2-3 A',
            5: 'average grade B with 1 A', 6: 'average grade B with no A',
            7: 'average grade C', 8: 'average grade D'}
    for t in range(1, 9):
        a, s = TITLE_BONUS[t]
        titles.append({'id': t, 'name': title_names[t - 1][1], 'name_jp': title_names[t - 1][0],
                       'rule': rule[t], 'bonus_souls': {'A': a, 'S': s},
                       'extra_continues': TITLE_CONTINUES.get(t, 0),
                       'shop_half_price': t == 1,
                       'special_opponents': f'entries with title_limit >= {t}'})

    notices = {}
    for n in (2398, 2399):
        jp = entry(n).decode('cp932').replace('\r\n', '\n')
        notices[n] = {'jp': jp, 'en': td.get(('notice', str(n), jp))}

    intro = {img: graphics_english(img) for img in ('000_02426', '000_02427', '000_02445')}
    return {
        'source': 'tools/survivalmap.py',
        'setting_names': SETTING_NAMES,
        'grades': [{'grade': n, 'letter': g, 'min_rating': m} for n, g, m in GRADES],
        'titles': titles,
        'difficulties': difficulties,
        'courses': courses,
        'finals': finals,
        'opponents': opponents,
        'souls': {
            'per_match': 'souls_by_grade[difficulty][grade of the match rating] + title bonus (A/S only); '
                         'after every finished match, won or lost (0x1bc930-0x1bcaa8); capped at 9,999',
            'stored': 'Survival data (0x334fe0) +4, u32',
        },
        'save': {
            'working_copy': 'heap block 0x55ac bytes at [gp-0x5728] (0x3e5348); 0x1bea18 copies the lasting fields to 0x334fe0',
            'fields': {'+1': 'type: 1 Singles, 2 Singles with a second, 3 Tag', '+2': 'course 1-8',
                       '+3': 'difficulty 1-5', '+4': 'souls (u32, max 9,999)',
                       '+8': 'title 1-8 (0 = no match yet)', '+0xa': 'matches played (s16, wraps 999 -> 1)',
                       '+0xc': 'best rating', '+0xd..+0x16': 'last 10 match ratings (newest first)',
                       '+0x18..+0x1f': 'cleared difficulty per course 1-8 (0 = never)',
                       '+0x20': 'souls of the last match', '+0x22': 'bonus souls of the last match',
                       '+0x24': 'stage: 1 qualifiers, 2 finals', '+0x25': 'round', '+0x26': 'rounds in this stage',
                       '+0x27': 'wins in this stage', '+0x28': 'wins needed', '+0x29': 'continues left',
                       '+0x2a/+0x2c': 'player wrestler ids (wrestler + second, or the tag pair)',
                       '+0x53a8': 'current opponent entry', '+0x53aa..': '512 used-entry flags (cleared at a new run)',
                       '+0x55ac..': 'Secret Shop row states (0 hidden, 1 on sale, 2 bought)'},
        },
        'notices': notices,
        'screens': {k: [{'jp': j, 'en': e} for j, e in v] for k, v in intro.items()},
        'movie': {'file': 'KC2FIRE_AFS/9002_KachinukiOP.sfd',
                  'when': 'starting a course (docs/HIDDEN_CONTENT.md, verified in game); call site not traced'},
        'flow': {
            'modes': ['Singles', 'Singles with a second', 'Tag'],
            'run': 'qualifiers (course pool, rounds by difficulty) then, except on Easy, the finals '
                   '(class A wrestlers of every course); Easy ends after its 3 qualifiers with notice 2398',
            'loss': 'no immediate game over: GAME OVER when wins + matches left < wins needed '
                    '(0x1bcb08); Easy never checks. GAME OVER offers Continue while continues remain: '
                    'the same match is replayed (same opponent). Notice 2399 when none are left.',
            'clear': 'after the last finals win: ending 0x1bbc70 (staff credits 0x1bb1e0, entries '
                     '3133/3134); the course\'s cleared difficulty (Survival data +0x17+course) is raised',
            'between_matches': 'menu: Next Match / Hall of Souls (Secret Shop) / Save-Quit (picture 2456); '
                               'no health carry-over found (each match set up from its sheet)',
            'repeats': 'a wrestler is met at most once per run (qualifiers and finals); entries with '
                       'the player\'s own wrestlers are skipped',
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, help='default: docs/survival-road/index.html')
    ap.add_argument('--template', type=Path, help='default: tools/survivalmap_template.html')
    ap.add_argument('--json', type=Path, help='also write the data here')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if not (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000').exists():
        sys.exit(f'{paths.show(paths.EXTRACTED)}: no KC2FIRE_000 - run tools/extract.py first')
    d = build()
    if args.json:
        args.json.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    template = args.template or Path(__file__).resolve().parent / 'survivalmap_template.html'
    # the page leaves out the cut Pancrase course: it has no opponents, so there is nothing to map
    # (docs/HIDDEN_CONTENT.md has what is left of it); --json keeps it
    page = dict(d, courses=[c for c in d['courses'] if not c['cut']])
    out, size = pagekit.write('survival-road', template, page, args.out)
    n = sum(len(v) for v in d['opponents'].values())
    print(f'{len(page["courses"])} courses, {n} opponent entries -> {paths.show(out)} ({size // 1024} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
