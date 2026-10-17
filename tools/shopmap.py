#!/usr/bin/env python3
"""Build the Secret Shop & Unlocks page, docs/secret-shop/index.html: every shop item with its
price, when it goes on sale and what it unlocks, how souls are earned, and every other unlock.

  shopmap.py [--out PATH] [--template PATH] [--json PATH]

Reads the original entries (extracted/: KC2FIRE.000 2396 items, 2397 categories, 2400 courses,
1999 roster, 1452 Edit samples, 2010 Edit parts) and the English (translation/text/teamdata.csv,
fields.csv, wrestlers.txt, roster.csv, elf.txt), then embeds the data in
tools/shopmap_template.html (shared parts: tools/pagekit.py; Google Fonts is its only download). --json also writes the data.
Rerun it after changing those texts.

Rules (*from the code*; docs/TECHNICAL.md "Secret Shop and unlocks"): shop screen 0x1c96c0 from
the Survival Road menu; one state byte per row at 0x334fe0+0x55ac+row (0 hidden, 1 for sale,
2 bought). 0x1bfaf8 puts a row on sale when its course was cleared at its difficulty or harder,
or (no course) when that many courses were. Buying costs souls (half price with the King of
Kings title). Leaving the shop copies linked rows, sets flag[id] = bought, the ring options and
Edit points, and the derived wrestler/colour flags (LINKED, RING_OF, DERIVED below). Rows the
game finds by name (NAME_KEYS) must have the same English as the executable's key - the page
build stops otherwise (tools/teamdata.py verify checks the same).
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
import pagekit  # noqa: E402
import paths  # noqa: E402

# --- rules from the code -------------------------------------------------------------------------
DIFFICULTIES = {1: 'イージー', 2: 'ノーマル', 3: 'ハード', 4: 'Sハード', 5: 'マスター'}   # 0x3ae3f0
# shop row id -> rows bought with it (0x1ca974-0x1cab50: state copied at shop exit)
LINKED = {60: [61], 68: [69], 82: [83, 84, 85, 86, 87, 88, 89], 90: [91], 92: [93], 95: [96], 188: [189]}
# unlock flag (shop row id) -> derived wrestler/variant flags (0x1caca4-0x1cb030, same in 0x100c80)
DERIVED = [(60, 6), (64, 7), (65, 8), (66, 9), (67, 10), (68, 11), (70, 12), (71, 13), (72, 14), (77, 15),
           (78, 16), (79, 17), (82, 18), (90, 19), (95, 20), (97, 21), (102, 22), (99, 45), (100, 46),
           (62, 26), (62, 27), (63, 28), (63, 29), (73, 30), (73, 31), (74, 32), (75, 33), (75, 34),
           (76, 35), (76, 36), (80, 37), (81, 38), (92, 39), (94, 40), (94, 41), (98, 42), (98, 43), (101, 44)]
# ring rows -> Ring option item (option category 0xe, 0x101498; jump table 0x3ae640)
RING_OF = {265: 9, 266: 10, 268: 17, 269: 18, 270: 19, 271: 20, 272: 21, 273: 22, 274: 23, 275: 24,
           276: 25, 277: 26, 279: 15}
# preview picture overrides written after parsing (0x1bf9a8-0x1bfa94): table row -> wrestler column
PORTRAIT_OVERRIDE = {3: 0x136, 4: 0x137, 14: 0x138, 15: 0x139, 16: 0x13a, 17: 0x13b, 21: 0x13c,
                     22: 0x13d, 33: 0x13e, 35: 0x13f, 39: 0x140, 42: 0x141}
# rows the game finds by NAME (strcmp against executable strings), with what they do
NAME_KEYS = {'エディットＰ＋５０': (0x3ae5f0, 'edit_points', 'Edit points +50 (0x1c9390)'),
             'ＳＵＰＥＲ ＨＡＲＤ': (0x3ae4a8, 'difficulty', 'Super Hard difficulty in Survival Road (0x1c3a18)'),
             'ＭＡＳＴＥＲ': (0x3ae4c0, 'difficulty', 'Master difficulty in Survival Road (0x1c3a18)'),
             '格闘家コース': (0x3ae460, 'course', 'Fighter course in Survival Road, singles (0x1c2ed0)'),
             'Ｓスターズコース': (0x3ae470, 'course', 'S-Stars course in Survival Road (0x1c2ed0)')}
# souls per Survival Road match: table 0x3ae1e0 [difficulty][grade]; grade = 0x1be0e0(rating)
SOULS = {1: [5, 10, 20, 50, 100], 2: [10, 30, 50, 100, 200], 3: [20, 60, 100, 150, 300],
         4: [40, 120, 200, 300, 600], 5: [80, 240, 400, 600, 1200]}
GRADES = ['rating < 40', '40-59', '60-79', '80-99', '100']
# extra souls by current title (Survival data +8) for a match graded 80-99 / 100 (0x1bc978, table 0x3ae2b0)
TITLE_BONUS = {1: (300, 500), 2: (100, 200), 3: (75, 150), 4: (50, 100), 5: (50, 0), 6: (25, 0)}
TITLES = [  # Survival data +8, set by 0x1be168 after every match; names: atlas 000_02442 (graphics.csv)
    (1, 'キング・オブ・キングス', 'King of Kings', 'average of the last 10 ratings 80+ and at least one 100 (or average 100); shop prices halved'),
    (2, '魂の伝道師', 'Soul Evangelist', 'average 80-99, no 100 among the last 10'),
    (3, 'Ｍｒ．プロレス', 'Mr. Pro Wrestling', 'average 60-79, four or more 80-99 ratings'),
    (4, 'エンターテイナー', 'Entertainer', 'average 60-79, two or three 80-99 ratings'),
    (5, '未完の大器', 'Rough Diamond', 'average 60-79, one 80-99 rating'),
    (6, '悩める中堅', 'Struggling Midcarder', 'average 60-79, no 80-99 rating'),
    (7, 'グリーンボーイ', 'Green Boy', 'average 40-59'),
    (8, '学生プロレス並', 'Backyard Wrestler', 'average below 40')]


def data_dir():
    return paths.EXTRACTED / 'DATA' / 'KC2FIRE_000'


def sheet(n):
    """Rows of a tab/CRLF Shift-JIS text entry."""
    t = (data_dir() / f'{n:05d}.bin').read_bytes().decode('cp932')
    return [ln.split('\t') for ln in t.replace('\r', '').split('\n') if ln.strip()]


def teamdata_en():
    out = {}
    with open(paths.TEXT / 'teamdata.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            out[(r['table'], r['field'], r['japanese'])] = r['english']
    return out


def en_of(td, field, jp):
    e = td.get(('shop', field, jp), '')
    return e or unicodedata.normalize('NFKC', jp)  # no English = kept (already English letters, full-width)


def elf_en():
    bf = blocks.BlockFile(paths.TEXT / 'elf.txt')
    out = {}
    for b in bf.blocks:
        src, en = bf.source(b), b.english
        if src:
            out[int(b.id, 16)] = (src[0], en[0] if en else src[0])
    return out


def elf_string(addr):
    o = addr - 0x323d80 + 0x224d80
    d = (paths.EXTRACTED / 'SLPM_656.02').read_bytes()
    return d[o:d.index(b'\0', o)].decode('cp932')


def wrestler_parts():
    """[(jp, en)] per item of table 2010, with each item's u16 unlock flag (+0x1a)."""
    d = (data_dir() / '02010.bin').read_bytes()
    a, n, s, _ = struct.unpack_from('<4I', d, 0)
    base = 16 + 8 * a
    r = (len(d) - s - base) // n
    pool = len(d) - s
    offs = {}
    pos, idx = 0, 0
    for st in d[pool:-1].split(b'\0'):
        offs[pos] = idx
        pos += len(st) + 1
        idx += 1
    bf = blocks.BlockFile(paths.TEXT / 'wrestlers.txt')
    en = {int(b.id): (b.english[0] if b.english else bf.source(b)[0]) for b in bf.blocks}
    jp = {int(b.id): bf.source(b)[0] for b in bf.blocks}
    items = []
    for i in range(n):
        rec = d[base + r * i:base + r * (i + 1)]
        o = struct.unpack_from('<I', rec, 0)[0]
        k = offs[o]
        items.append((i, jp.get(k, ''), en.get(k, ''), struct.unpack_from('<H', rec, 0x1a)[0]))  # '' = empty string
    return items


def templates():
    """[(index, jp, en, flag)] of entry 1452 (wrestler types and Edit samples, 128-byte records)."""
    names = {}
    with open(paths.TEXT / 'fields.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['table'] == 'wrestler_types' and r['field'] == 'name':
                names[r['japanese']] = r['english']
    d = (data_dir() / '01452.bin').read_bytes()
    out = []
    for i in range(len(d) // 128):
        rec = d[128 * i:128 * i + 128]
        jp = rec[:40].split(b'\0')[0].decode('cp932')
        out.append((i, jp, names.get(jp) or jp, struct.unpack_from('<H', rec, 0x7c)[0]))
    return out


def roster():
    """wrestlers {flag: [(index, jp)]}, variants {flag: [(index, jp)]} from entry 1999."""
    d = (data_dir() / '01999.bin').read_bytes()
    n, nv = struct.unpack_from('<II', d, 0)
    vbase = 16 + 64 * n

    def vname(v):
        o = vbase + 0x8ed * v
        s = d[o + 4:o + 19].split(b'\0')[0].decode('cp932')
        g = d[o + 19:o + 40].split(b'\0')[0].decode('cp932')
        return (s + ' ' + g).strip()
    ws, vs, slot = {}, {}, {}
    for i in range(n):
        rec = d[16 + 64 * i:16 + 64 * (i + 1)]
        for k, v in enumerate(struct.unpack_from('<4h', rec, 2)):
            if v >= 0 and not (v == 0 and i):
                slot[v] = (i, k + 1)
        first = struct.unpack_from('<h', rec, 2)[0]
        ws.setdefault(rec[0x10], []).append((i, vname(first) if first >= 0 else ''))
    for v in range(nv):
        vs.setdefault(d[vbase + 0x8ed * v + 3], []).append((v, vname(v), slot.get(v, (None, None))))
    return ws, vs


def roster_en():
    """Japanese name part -> English (roster.csv surname/given)."""
    m = {}
    with open(paths.TEXT / 'roster.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['field'] in ('surname', 'given') and r['english']:
                m[(r['field'], r['japanese'])] = r['english']
    return m


def name_en(jp, rm):
    s, _, g = jp.partition(' ')
    se, ge = rm.get(('surname', s), s), rm.get(('given', g), g) if g else ''
    return f'{ge} {se}'.strip()  # given name first, as the English roster reads


def model():
    td, elf = teamdata_en(), elf_en()
    diff_en = {k: next((e for o, (j, e) in elf.items() if 0x2af3f0 <= o < 0x2af440 and j == v), v)
               for k, v in DIFFICULTIES.items()}
    cats = [{'id': i + 1, 'jp': r[0], 'en': en_of(td, 'category', r[0]),
             'help_jp': r[1], 'help_en': en_of(td, 'category_help', r[1])} for i, r in enumerate(sheet(2397))]
    course_rows = [r[0] for r in sheet(2400)]
    courses = [{'id': i + 1, 'jp': c, 'en': en_of(td, 'promotion', c),
                'playable': i + 1 != 6,
                'note': {6: 'cut: always skipped by the course list (0x1c2f94)',
                         7: 'hidden until the Fighter Course item is bought; singles only',
                         8: 'hidden until the S-Stars Course item is bought'}.get(i + 1, '')}
               for i, c in enumerate(course_rows)]
    parts, temps = wrestler_parts(), templates()
    ws, vs = roster()
    rm = roster_en()
    by_jp_name = {}
    rows = sheet(2396)
    items = []
    for r_i, cells in enumerate(rows, 1):
        cells += [''] * (9 - len(cells))
        rid = int(cells[0])
        jp = cells[1]
        cat = next((c for c in cats if cells[2] and cells[2].startswith(c['jp'])), None)
        price = int(cells[3]) if cells[3] else None
        course = next((i + 1 for i, c in enumerate(course_rows) if cells[5] and cells[5].startswith(c)), 0)
        number = int(cells[6]) if cells[6] else 0
        diff = next((k for k, v in DIFFICULTIES.items() if cells[7] and cells[7].startswith(v)), 0)
        wcol = PORTRAIT_OVERRIDE.get(r_i, int(cells[8]) if cells[8] not in ('',) else -1)
        sold = cat is not None and price is not None
        parent = next((p for p, ch in LINKED.items() if rid in ch), None)
        if not sold:
            req = None
        elif course:
            req = {'type': 'course', 'course': course, 'course_en': courses[course - 1]['en'],
                   'difficulty': diff, 'difficulty_en': diff_en[diff],
                   'text': f"Clear the {courses[course - 1]['en']} course on {diff_en[diff]} or harder"}
        else:
            req = {'type': 'courses', 'count': number, 'difficulty': diff, 'difficulty_en': diff_en[diff],
                   'text': f"Clear {number} course{'s' if number != 1 else ''} on {diff_en[diff]} or harder"}
        unlocks = []
        if rid >= 0:
            for f, w in DERIVED:
                if f != rid:
                    continue
                for wi, wn in ws.get(w, []):
                    unlocks.append({'kind': 'wrestler', 'target': wi, 'flag': w, 'name': name_en(wn, rm), 'name_jp': wn})
                for vi, vn, (owner, k) in vs.get(w, []):
                    if not ws.get(w):
                        unlocks.append({'kind': 'variant', 'target': vi, 'flag': w, 'wrestler': owner, 'type': k,
                                        'name': f'{name_en(vn, rm)} (Type {k})', 'name_jp': vn})
            for ti, tjp, ten, f in temps:
                if f == rid:
                    unlocks.append({'kind': 'edit_template', 'target': ti, 'name': ten, 'name_jp': tjp})
            for pi, pjp, pen, f in parts:
                if f == rid:
                    unlocks.append({'kind': 'edit_part', 'target': pi, 'list': 'A' if pi < 2284 else 'B',
                                    'name': pen, 'name_jp': pjp})
            if rid in RING_OF:
                unlocks.append({'kind': 'ring', 'target': RING_OF[rid], 'name': en_of(td, 'name', jp), 'name_jp': jp})
            for child in LINKED.get(rid, []):
                cj = next(c[1] for c in rows if c[0] == str(child))
                unlocks.append({'kind': 'linked_item', 'target': child, 'name': en_of(td, 'name', cj), 'name_jp': cj})
        if jp in NAME_KEYS:
            addr, kind, what = NAME_KEYS[jp]
            target = {'ＳＵＰＥＲ ＨＡＲＤ': 4, 'ＭＡＳＴＥＲ': 5, '格闘家コース': 7, 'Ｓスターズコース': 8}.get(jp, 50)
            unlocks.append({'kind': kind, 'target': target, 'name': what, 'key_address': hex(addr),
                            'key_en': next((e for o, (j, e) in elf.items() if o == addr - 0x323d80 + 0x224d80), elf_string(addr))})
        item = {'row': r_i, 'id': rid, 'flag': rid if rid >= 0 else None,
                'name_jp': jp, 'name_en': en_of(td, 'name', jp),
                'category': cat['id'] if cat else None, 'category_en': cat['en'] if cat else None,
                'description_jp': cells[4], 'description_en': en_of(td, 'description', cells[4]) if cells[4] else '',
                'price': price, 'price_half': (price // 2) if price is not None else None, 'currency': 'souls' if sold else None,
                'requirement': req, 'sold': sold, 'bought_with': parent,
                'portrait': 2475 + wcol if wcol >= 0 else (2472 if sold else None),
                'unlocks': unlocks}
        if not sold and parent is None and rid >= 0:
            item['note'] = ('set at start-up, always available (0x11a5d0)' if rid in (185, 186) else
                            'Dojo reward (0x17ac80), skipped by the shop exit loop' if rid == 71 else
                            'never for sale: only the unlock-all routine 0x100c40 sets this flag')
        items.append(item)
        by_jp_name.setdefault(jp, []).append(item)
    # key check: names the code compares must equal the English shop name
    key_problems = []
    for jp, (addr, kind, what) in NAME_KEYS.items():
        shop_en = td.get(('shop', 'name', jp)) or jp  # the bytes the build writes (no English = original)
        o = addr - 0x323d80 + 0x224d80
        exe_en = elf.get(o, (jp, jp))[1]
        if shop_en != exe_en:
            key_problems.append({'japanese': jp, 'shop_english': shop_en, 'executable_english': exe_en,
                                 'executable_address': hex(addr), 'effect': what})
    doc = {
        'meta': {'source': 'KC2FIRE.000 entries 2396 (items), 2397 (categories), 2400 (courses); '
                           'flags cross-referenced with 1999, 1452, 2010; rules from the executable',
                 'shop_screen': '0x1c96c0 (Survival Road menu -> Secret Shop; called from 0x1bcce0 / 0x1bcdb0)',
                 'state': 'one byte per row at 0x334fe0+0x55ac+row: 0 hidden, 1 for sale, 2 bought (system save)',
                 'english_key_problems': key_problems},
        'currency': {
            'name': 'souls', 'name_jp': '魂', 'cap': 9999, 'where': 'Survival data +4 (0x334fe4)',
            'earned_in': 'Survival Road only: after every match souls += per-match souls + title bonus (0x1bc950-0x1bcaa8)',
            'per_match': {diff_en[d]: dict(zip(GRADES, v)) for d, v in SOULS.items()},
            'title_bonus': {t[2]: {'80-99': TITLE_BONUS[t[0]][0], '100': TITLE_BONUS[t[0]][1]} for t in TITLES if t[0] in TITLE_BONUS},
            'titles': [{'id': i, 'jp': j, 'en': e, 'condition': c} for i, j, e, c in TITLES],
            'half_price': 'title 1 (King of Kings): every price halved, rounded down (0x1c9bf4)',
            'edit_points': 'not a currency: 200 + 50 per bought Edit Points +50 item, max 400 (0x1c9390 -> 0x3e9a5c)'},
        'difficulties': [{'id': k, 'jp': v, 'en': diff_en[k],
                          'unlock': {4: 'buy SUPER HARD', 5: 'buy MASTER'}.get(k, 'always')} for k, v in DIFFICULTIES.items()],
        'courses': courses,
        'categories': cats,
        'items': items,
        'other_sources': [
            {'verified': False, 'source': 'Dojo: clear course 10 ("Use all you\'ve learned to beat Kotetsu!")', 'address': '0x17ac80',
             'unlocks': [{'kind': 'wrestler', 'target': 45, 'flag': 13, 'name': 'Kotetsu Yamamoto'},
                         {'kind': 'flag', 'target': 71, 'name': 'Kotetsu Yamamoto Edit face'},
                         {'kind': 'referee', 'target': 9, 'name': 'Kotetsu Yamamoto (referee option)'}]},
            {'source': 'Match Maker: clear New Japan, NOAH, All Japan, ZERO-ONE and WJ', 'address': '0x1ce830',
             'unlocks': [{'kind': 'mode', 'target': 7, 'name': 'Free Show (Match Maker slot 7)'}]},
            {'source': 'Name-entry password 小橋蝶野武藤橋本三沢 (Edit Mode -> given name)', 'address': '0x18a640',
             'unlocks': [{'kind': 'all', 'target': '0x100c40', 'name': 'everything: all shop items bought, 9,999 souls, '
                          'King of Kings, every course cleared on Master, all Dojo lessons, Kotetsu Yamamoto'}]},
            {'source': 'Always (start-up)', 'address': '0x116690, 0x11a5d0',
             'unlocks': [{'kind': 'flag', 'target': 0, 'name': 'flag 0 (always)'}, {'kind': 'flag', 'target': 1, 'name': 'flag 1'},
                         {'kind': 'edit_template', 'target': 94, 'name': 'Brendan Daimos'},
                         {'kind': 'edit_template', 'target': 95, 'name': 'Brendan Crank'}]}],
        'never_unlocked': [
            {'flag': 2, 'what': 'Mystery 1-3 promotions, 17 Pancrase moves, 284 Pancrase Edit parts (docs/HIDDEN_CONTENT.md)'},
            {'flag': 4, 'what': '"Retired" wrestler group'},
            {'flag': 24, 'what': 'Trainee #1-#4'},
            {'flag': 25, 'what': 'wrestler 147 (Spike Tomoki)'},
            {'flag': 35, 'what': 'set along with Kikuchi Super Gen. colours, but nothing uses it'},
            {'flag': None, 'what': 'shop rows never put on sale (tick "rows never for sale" under Shop items)'},
            {'flag': None, 'what': 'option values with state 3: Pancrase Rules, rings Pancrase and WAR, Pancrase Fans, referee Soichi Hiroto'},
            {'flag': None, 'what': 'Survival Road course 6 (Pancrase) and Match Maker slot 6 (Pancrase)'}],
    }
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, help='default: docs/secret-shop/index.html')
    ap.add_argument('--template', type=Path, help='default: tools/shopmap_template.html')
    ap.add_argument('--json', type=Path, help='also write the data here')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if not data_dir().exists():
        sys.exit(f'{paths.show(paths.EXTRACTED)}: no KC2FIRE_000 - run tools/extract.py first')
    d = model()
    probs = d['meta']['english_key_problems']
    if probs:
        sys.exit('\n'.join(f"shop item {p['japanese']}: shop says {p['shop_english']!r}, the executable "
                           f"{p['executable_english']!r} - make them the same (teamdata.csv / elf.txt)" for p in probs))
    template = args.template or Path(__file__).resolve().parent / 'shopmap_template.html'
    if args.json:
        args.json.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    out, size = pagekit.write('secret-shop', template, d, args.out)
    items = d['items']
    print(f"{len(items)} shop rows, {sum(1 for i in items if i['sold'])} for sale -> {paths.show(out)} ({size // 1024} KB)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
