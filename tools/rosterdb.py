#!/usr/bin/env python3
"""Build the wrestler database page, docs/wrestlers/index.html: every wrestler and costume with
profile, skills, parameters, finisher and signatures, full moveset, entrance, unlock and Match
Maker details, plus the Edit Mode samples and the Match Maker title holders.

  rosterdb.py [--out PATH] [--template PATH] [--json PATH]

Reads the original entries (extracted/: KC2FIRE.000 1999 WrestlerData, 2005 Edit templates, 1452
their names, 1450 move slots, 2008 moves, 2010 appearance parts, 2000 promotions, 2001
Elimination teams, 1453 voices, 1441 labels, 2009 Match Maker rosters, 2396 shop, 2829-2836 title
sheets; the executable's label table 0x3a9ff0) and the English (translation/text/*,
translation/graphics.csv), then embeds a trimmed copy in tools/rosterdb_template.html (shared
parts: tools/pagekit.py). --json writes the full model (undecoded fields kept as raw values).

Formats (*from the code*; docs/TECHNICAL.md "Wrestler data"): WrestlerData = u32 wrestlers,
u32 blocks, 8 zero bytes, 64-byte index records (+2 four u16 variant blocks, +0xa variant count,
+0xb promotion, +0xf weight class, +0x10 unlock flag), then 0x8ed-byte packed variant blocks,
unpacked as the game's 0x1149c0 does (unpack() below) into the 0xa6a-byte working struct.
Moves: 285 slots (1450), each value an index in its 2008 group; clutch categories 5-16 take
their group from the Clutch Setting slot (0x163580, group_of()).
"""
import argparse
import csv
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import pagekit  # noqa: E402
import paths  # noqa: E402


def entry(n):
    return (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000' / f'{n:05d}.bin').read_bytes()


def sj(b):
    return b.split(b'\0')[0].decode('cp932', 'replace')


def cp(b):
    return b.split(b'\0')[0].decode('cp932', 'replace')


# ---------------------------------------------------------------- WrestlerData
class WD:
    def __init__(self, n=1999):
        d = self.d = entry(n)
        self.nw, self.nv = struct.unpack_from('<II', d, 0)
        self.vbase = 16 + 64 * self.nw

    def index(self, i):
        return self.d[16 + 64 * i:16 + 64 * i + 64]

    def block(self, v):
        o = self.vbase + 0x8ed * v
        return self.d[o:o + 0x8ed]

    def variants(self, i):
        """variant numbers of wrestler i: u16 at +2+2k (k=0..3), the game's slot k"""
        r = self.index(i)
        return [struct.unpack_from('<H', r, 2 + 2 * k)[0] for k in range(4)]


def unpack(p):
    """0x1149c0: packed block p (0x8ed bytes) -> dict of out-struct offsets -> values"""
    p = p + b'\0' * 8
    o = {}
    o[0x0] = p[0] | p[1] << 8
    o[0x2] = p[2] & 3
    o[0x4] = p[2] >> 2
    o[0x3] = p[3]
    o['text'] = p[4:0x7a]           # -> out+8..0x7e
    b = lambda i: p[i]
    o[0x7e] = b(0x7a) & 3
    o[0x7f] = (b(0x7a) >> 2) & 1
    o[0x80] = ((b(0x7a) >> 3) | (b(0x7b) << 5)) & 0x3f
    o[0x81] = (b(0x7b) >> 1) & 7
    o[0x84] = ((b(0x7b) >> 4) | (b(0x7c) << 4)) & 0xff
    o[0x82] = ((b(0x7c) >> 4) | (b(0x7d) << 4)) & 0x1ff
    o[0x85] = ((b(0x7d) >> 5) | (b(0x7e) << 3)) & 0xff
    o[0x86] = ((b(0x7e) >> 5) | (b(0x7f) << 3)) & 0xf
    o[0x87] = (b(0x7f) >> 1) & 0x1f
    o[0x88] = ((b(0x7f) >> 6) | (b(0x80) << 2)) & 0x1f
    o[0x89] = (b(0x80) >> 3) & 0x1f
    o[0x8a] = b(0x81) & 0x3f
    o[0x90] = ((b(0x81) >> 6) | (b(0x82) << 2) | (b(0x83) << 10)) & 0xffff
    o[0x92] = ((b(0x83) >> 6) | (b(0x84) << 2) | (b(0x85) << 10)) & 0xffff
    o[0x8b] = ((b(0x85) >> 6) | (b(0x86) << 2)) & 0xff
    o[0x8c] = b(0x86) >> 6
    o[0x8d] = b(0x87)
    o[0x8e] = b(0x88)
    o[0x8f] = b(0x89)
    o[0x94] = b(0x8a) & 7
    o[0x95] = (b(0x8a) >> 3) & 0xf
    o[0x96] = ((b(0x8a) >> 7) | (b(0x8b) << 1)) & 3
    o[0x97] = (b(0x8b) >> 1) & 3
    o[0x98] = (b(0x8b) >> 3) & 3
    o[0x99] = (b(0x8b) >> 5) & 3
    o[0x9a] = ((b(0x8b) >> 7) | (b(0x8c) << 1)) & 3
    o[0x9b] = (b(0x8c) >> 1) & 3
    o[0x9c] = (b(0x8c) >> 3) & 3
    o[0x9d] = (b(0x8c) >> 5) & 3
    o[0x9e] = ((b(0x8c) >> 7) | (b(0x8d) << 1)) & 3
    o[0x9f] = (b(0x8d) >> 1) & 3
    o[0xa0] = (b(0x8d) >> 3) & 3
    o[0xa1] = (b(0x8d) >> 5) & 3
    o[0xa2] = ((b(0x8d) >> 7) | (b(0x8e) << 1)) & 3
    o[0xa3] = b(0x8e)
    o[0xa4] = b(0x8f)
    o[0xa5] = b(0x90)
    o[0xa6] = b(0x91)
    o['a8'] = p[0x92:0xa8]          # 0x16 bytes -> out+0xa8..0xbe
    o['c0'] = p[0xa8:0x116]         # 0x6e bytes -> out+0xc0..0x12e
    lo = p[0x116:0x116 + 0x11d]
    hi = p[0x116 + 0x11d:0x116 + 0x1ad]
    mv = []
    for i in range(0x11d):
        mv.append(lo[i] | ((hi[i // 2] >> (4 * (i & 1))) & 0xf) << 8)
    q = 0x116 + 0x1ad   # 0x2c3
    marks = [struct.unpack_from('<H', p, q + 2 * k)[0] for k in range(5)]
    for k, bit in enumerate((0x1000, 0x2000, 0x6000, 0xc000, 0xe000)):
        if marks[k] - 1 >= 0:
            mv[marks[k] - 1] |= bit
    o['moves'] = mv               # out+0x130, 0x11d u16
    o['marks'] = marks
    q += 10                       # 0x2cd
    bits = int.from_bytes(p[q:q + 0x620], 'little')
    o['logic'] = [(bits >> (7 * i)) & 0x7f for i in range(0x6fa)]   # out+0x36e, 0x6fa bytes
    return o


def unpack(p):
    """0x1149c0: packed block p (0x8ed bytes) -> dict of out-struct offsets -> values"""
    p = p + b'\0' * 8
    o = {}
    o[0x0] = p[0] | p[1] << 8
    o[0x2] = p[2] & 3
    o[0x4] = p[2] >> 2
    o[0x3] = p[3]
    o['text'] = p[4:0x7a]           # -> out+8..0x7e
    b = lambda i: p[i]
    o[0x7e] = b(0x7a) & 3
    o[0x7f] = (b(0x7a) >> 2) & 1
    o[0x80] = ((b(0x7a) >> 3) | (b(0x7b) << 5)) & 0x3f
    o[0x81] = (b(0x7b) >> 1) & 7
    o[0x84] = ((b(0x7b) >> 4) | (b(0x7c) << 4)) & 0xff
    o[0x82] = ((b(0x7c) >> 4) | (b(0x7d) << 4)) & 0x1ff
    o[0x85] = ((b(0x7d) >> 5) | (b(0x7e) << 3)) & 0xff
    o[0x86] = ((b(0x7e) >> 5) | (b(0x7f) << 3)) & 0xf
    o[0x87] = (b(0x7f) >> 1) & 0x1f
    o[0x88] = ((b(0x7f) >> 6) | (b(0x80) << 2)) & 0x1f
    o[0x89] = (b(0x80) >> 3) & 0x1f
    o[0x8a] = b(0x81) & 0x3f
    o[0x90] = ((b(0x81) >> 6) | (b(0x82) << 2) | (b(0x83) << 10)) & 0xffff
    o[0x92] = ((b(0x83) >> 6) | (b(0x84) << 2) | (b(0x85) << 10)) & 0xffff
    o[0x8b] = ((b(0x85) >> 6) | (b(0x86) << 2)) & 0xff
    o[0x8c] = b(0x86) >> 6
    o[0x8d] = b(0x87)
    o[0x8e] = b(0x88)
    o[0x8f] = b(0x89)
    o[0x94] = b(0x8a) & 7
    o[0x95] = (b(0x8a) >> 3) & 0xf
    o[0x96] = ((b(0x8a) >> 7) | (b(0x8b) << 1)) & 3
    o[0x97] = (b(0x8b) >> 1) & 3
    o[0x98] = (b(0x8b) >> 3) & 3
    o[0x99] = (b(0x8b) >> 5) & 3
    o[0x9a] = ((b(0x8b) >> 7) | (b(0x8c) << 1)) & 3
    o[0x9b] = (b(0x8c) >> 1) & 3
    o[0x9c] = (b(0x8c) >> 3) & 3
    o[0x9d] = (b(0x8c) >> 5) & 3
    o[0x9e] = ((b(0x8c) >> 7) | (b(0x8d) << 1)) & 3
    o[0x9f] = (b(0x8d) >> 1) & 3
    o[0xa0] = (b(0x8d) >> 3) & 3
    o[0xa1] = (b(0x8d) >> 5) & 3
    o[0xa2] = ((b(0x8d) >> 7) | (b(0x8e) << 1)) & 3
    o[0xa3] = b(0x8e)
    o[0xa4] = b(0x8f)
    o[0xa5] = b(0x90)
    o[0xa6] = b(0x91)
    o['a8'] = p[0x92:0xa8]          # 0x16 bytes -> out+0xa8..0xbe
    o['c0'] = p[0xa8:0x116]         # 0x6e bytes -> out+0xc0..0x12e
    lo = p[0x116:0x116 + 0x11d]
    hi = p[0x116 + 0x11d:0x116 + 0x1ad]
    mv = []
    for i in range(0x11d):
        mv.append(lo[i] | ((hi[i // 2] >> (4 * (i & 1))) & 0xf) << 8)
    q = 0x116 + 0x1ad   # 0x2c3
    marks = [struct.unpack_from('<H', p, q + 2 * k)[0] for k in range(5)]
    for k, bit in enumerate((0x1000, 0x2000, 0x6000, 0xc000, 0xe000)):
        if marks[k] - 1 >= 0:
            mv[marks[k] - 1] |= bit
    o['moves'] = mv               # out+0x130, 0x11d u16
    o['marks'] = marks
    q += 10                       # 0x2cd
    bits = int.from_bytes(p[q:q + 0x620], 'little')
    o['logic'] = [(bits >> (7 * i)) & 0x7f for i in range(0x6fa)]   # out+0x36e, 0x6fa bytes
    return o


# ---------------------------------------------------------------- indexed string tables (2008/2010)
def text_file(name):
    t = (paths.TEXT / f'{name}.txt').read_text(encoding='utf-8')
    out = {}
    for b in re.split(r'\n(?=@ )', t):
        m = re.match(r'@ (\d+)', b)
        if not m:
            continue
        jp = '\n'.join(l[3:] for l in b.splitlines() if l.startswith('JP'))
        en = '\n'.join(l[3:] for l in b.splitlines() if l.startswith('EN'))
        out[int(m.group(1))] = (jp, en)
    return out


def table(n, name):
    d = entry(n)
    A, N, S, _ = struct.unpack_from('<4I', d, 0)
    R = (len(d) - S - 16 - 8 * A) // N
    groups = [struct.unpack_from('<II', d, 16 + 8 * k) for k in range(A)]
    rb = 16 + 8 * A
    pool = rb + N * R
    # pool string offsets in order
    offs = []
    o = 0
    P = d[pool:pool + S]
    while o < S:
        e = P.index(b'\0', o)
        offs.append(o)
        o = e + 1
        while o < S and o % 2 and P[o] == 0:   # padding? keep simple
            break
    idx = {v: k for k, v in enumerate(offs)}
    txt = text_file(name)
    recs = []
    for i in range(N):
        r = d[rb + i * R: rb + (i + 1) * R]
        so = struct.unpack_from('<I', r, 0)[0]
        jp = P[so:P.index(b'\0', so)].decode('cp932', 'replace')
        pi = idx.get(so)
        en = txt.get(pi, ('', ''))[1] if pi is not None else ''
        recs.append(dict(i=i, pool=pi, jp=jp, en=en, raw=r))
    return groups, recs


# ---------------------------------------------------------------- move slots


def group_of(k, moves):
    """the 2008 group a slot's value indexes (0x163670 -> 0x163580)"""
    name, slot, btn, cat, gid = SLOTS[k]
    if 5 <= cat <= 16:
        j = cat - 5
        cs = BY_CAT[4][j]               # Clutch Settings slot j
        v = moves[cs] & 0x3ff
        if cat < 11:
            if v == 1:
                return 0x36 if gid != 4 else 0x4a
            if 0x11 <= v < 0x15:
                return 0x46
            if 0x15 <= v < 0x1b:
                return 0x47
            if v < 0x1b:
                return v + 0x35
            return v + 0x35 - 8
        else:
            if 9 <= v < 12:
                return 0x54
            return v + 0x4b
    return gid


def move_of(k, moves):
    g = group_of(k, moves)
    v = moves[k] & 0x3ff
    if not (0 <= g < len(GROUPS)):
        return None, g, v
    cnt = GROUPS[g][0] >> 16
    if v >= cnt:
        return None, g, v
    return GROUPS[g][1] + v, g, v


# ---------------------------------------------------------------- English lookups
def csv_rows(name):
    path = paths.GRAPHICS_CSV if name == '../graphics.csv' else paths.TEXT / name
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))




def en(field, jp):
    return ROSTER_EN.get((field, jp)) or None


def msg(i):
    jp, e = MSG.get(i, ('', ''))
    return {'jp': jp, 'en': e or None}


def atlas(img):
    r = GFX[img]
    J = r['japanese'].split(' | ')
    E = r['english'].split(' | ')
    return [{'jp': j, 'en': E[i] if i < len(E) else None} for i, j in enumerate(J)]


def team(table_, field, jp):
    return TEAM_EN.get((table_, field, jp))


# ---------------------------------------------------------------- label lists (with sources)


def lab(x):
    return x['en'] or x['jp']


# ---------------------------------------------------------------- promotions, voices, parts, shop




def part(item, key):
    cnt = PG[item][0] >> 16
    st = PG[item][1]
    for x in PR[st:st + cnt]:
        if struct.unpack_from('<H', x['raw'], 4)[0] == key:
            return {'id': key, 'jp': x['jp'], 'en': x['en'] or None, 'table_2010': x['i']}
    return {'id': key, 'jp': None, 'en': None}


def appearance(c0):
    vals = {}
    for nm, t, off in APPEAR:
        rel = off - 0xc0
        vals[nm] = c0[rel] if t == 'B' else struct.unpack_from('<H', c0, rel)[0]
    out = {}
    for it, (nm, t, off) in enumerate(APPEAR):
        v = vals[nm]
        if it >= 21:                         # 0x15a6dc: stored as index-1, 0xffff = none
            key = (v + 1) & 0xffff
        elif it == 17:                       # gear type: +1000 / +0x9c by entrance gear (0x15a698, 0x15a7a4)
            key = v + (1000 if vals['entrance_gear'] >= 3 else 0x9c if vals['entrance_gear'] == 1 else 0)
        else:
            key = v
        out[nm] = part(it, key)
    used = {off - 0xc0 + k for _, t, off in APPEAR for k in range(1 if t == 'B' else 2)}
    out['raw_other_c0'] = {hex(0xc0 + i): c0[i] for i in range(len(c0)) if i not in used and c0[i]}
    return out




# ---------------------------------------------------------------- one variant
def decode_variant(block, logic=False):
    o = unpack(block)
    t = o['text']
    sur, giv, nick, move = sj(t[:15]), sj(t[15:36]), sj(t[36:69]), sj(t[69:])
    sep = {0: '　', 1: '', 2: '・', 3: '＝'}.get(o[0x7e], '?')     # 0x116940
    jp_full = (giv + sep + sur) if o[0x7f] else (sur + sep + giv)
    e_s, e_g = en('surname', sur) if sur else '', en('given', giv) if giv else ''
    esep = '' if not (e_s and e_g) else ' '
    en_game = ((e_g or '') + esep + (e_s or '')) if o[0x7f] else ((e_s or '') + esep + (e_g or ''))
    # Japanese-style names (separator = full-width space) read surname first in the game's order;
    # the Western order is the reverse of the game's order. Others (・ / none / ＝) are kept.
    parts = [x for x in ([e_g, e_s] if o[0x7f] else [e_s, e_g]) if x]
    en_west = ' '.join(reversed(parts) if o[0x7e] == 0 else parts)
    year = o[0x85]
    bday = None if year in (0x79, 0xff) else {'year': 1900 + year, 'month': o[0x86], 'day': o[0x87]}
    skills_raw = [o[k] for k in range(0x96, 0xa3)]
    names7 = ['recovery', 'recovery_bleeding', 'breathing', 'breathing_bleeding', 'spirit', 'spirit_bleeding']
    skills = {'soul_buttons': o[0x94], 'critical': {'raw': o[0x95], 'label': lab(CRITICAL[o[0x95]]) if o[0x95] < 7 else None}}
    for i, nm in enumerate(names7):
        raw = skills_raw[i]
        trip = LOW_AVG_HIGH[nm.split('_')[0]]
        disp = 2 - raw
        skills[nm] = {'raw': raw, 'label': lab(A1672[trip[disp]]) if 0 <= disp <= 2 else None}
    for i, nm in enumerate(['neck', 'arm', 'waist', 'leg']):
        raw = skills_raw[6 + i]
        disp = {1: 1, 0: 2, 2: 0, 3: 3}[raw]
        skills[nm + '_durability'] = {'raw': raw, 'label': lab(DURABILITY[disp])}
    skills['move_speed'] = {'raw': o[0xa0], 'label': lab(SPEED[o[0xa0]]) if o[0xa0] < 3 else None}
    skills['post_climbing'] = {'raw': o[0xa1], 'label': lab(CLIMB[o[0xa1]])}
    skills['mode_special_skill'] = {'raw': o[0xa6], 'label': lab(MODE_SKILL[o[0xa6]]) if o[0xa6] < 11 else None}
    skills['match_special_skills'] = [{'raw': o[k], 'label': lab(A1673[o[k]]) if o[k] < len(A1673) else None}
                                      for k in (0xa3, 0xa4, 0xa5) if o[k]]
    params = {'offense': {lab(A1677[i]): o['a8'][i] for i in range(11)},
              'defense': {lab(A1677[11 + i]): o['a8'][11 + i] for i in range(11)}}
    mv = o['moves']
    slot_moves = []
    for k in range(len(SLOTS)):
        m, g, v = move_of(k, mv)
        slot_moves.append(m if m is not None else -1)
    specials = []
    for j, mk in enumerate(o['marks']):
        if mk:
            m = slot_moves[mk - 1]
            specials.append({'kind': ['finisher', 'signature1', 'signature2', 'signature3', 'signature4'][j],
                             'slot': mk - 1, 'move': m, 'move_en': MOVES[m]['en'] if m >= 0 else None,
                             'move_jp': MOVES[m]['jp'] if m >= 0 else None})
    style = lambda raw: msg(69 + STYLE_RAW_TO_DISPLAY[raw]) if raw < 40 else None
    v = {
        'variant_block': None, 'type': o[0x2] + 1, 'unlock_flag': o[0x3],
        'surname': {'jp': sur, 'en': e_s or None}, 'given': {'jp': giv, 'en': e_g or None},
        'full_name': {'jp': jp_full, 'en_game_order': en_game.strip() or None, 'en_western': en_west or None},
        'nickname': {'jp': nick, 'en': en('nickname', nick)}, 'special_move_text': {'jp': move, 'en': en('move', move)},
        'name_format': {'separator': o[0x7e], 'given_first': o[0x7f]},
        'nationality': dict(raw=o[0x80], **msg(135 + o[0x80])),
        'build': dict(raw=o[0x81], **msg(64 + o[0x81])),
        'height_cm': o[0x84], 'weight_kg': o[0x82], 'birthday': bday,
        'fight_style': dict(raw=o[0x88], **(style(o[0x88]) or {})),
        'reversal_type_odds': dict(raw=o[0x89], **(style(o[0x89]) or {})),
        'reversal_type_moves': dict(raw=o[0x8a], **(style(o[0x8a]) or {})),
        'voice1': dict(raw=o[0x90], **VOICES.get(o[0x90], {})), 'voice2': dict(raw=o[0x92], **VOICES.get(o[0x92], {})),
        'favorite_color': dict(raw=o[0x8b], **msg(109 + o[0x8b])),
        'popularity': dict(raw=o[0x8c], **msg(132 + 2 - o[0x8c])),
        'skills': skills, 'parameters': params,
        'specials': specials, 'moveset': slot_moves,
        'appearance': appearance(o['c0']),
        'raw': {'model_id_0x8d': o[0x8d], 'unknown_0x8e': o[0x8e], 'unknown_0x8f': o[0x8f],
                'unknown_0xa2': o[0xa2], 'variant_0x4': o[0x4]},
    }
    if logic:
        v['raw']['cpu_logic'] = o['logic']
    return v


# ---------------------------------------------------------------- Match Maker (2009) and titles
def mm_table():
    d = entry(2009)
    A = struct.unpack_from('<I', d, 0)[0]
    groups = [struct.unpack_from('<HHI', d, 16 + 8 * k) for k in range(A)]
    base = 16 + 8 * A
    out = {}
    slot_names = ['New Japan', 'NOAH', 'All Japan', 'ZERO-ONE', 'WJ', 'Pancrase', 'Free Show']
    for k, (gid, cnt, st) in enumerate(groups):
        for i in range(cnt):
            r = d[base + 8 * (st + i): base + 8 * (st + i) + 8]
            wid = struct.unpack_from('<H', r, 0)[0]
            out.setdefault(wid, []).append({
                'campaign_slot': k + 1, 'campaign': slot_names[k] if k < len(slot_names) else None,
                'promotion': r[2], 'unit': r[3], 'class_raw': r[4], 'value_0x5': r[5],
                'flags_0x6': r[6], 'raw_0x7': r[7]})
    return out


def titles(roster, templates):
    out = []
    for slot in range(1, 8):
        n = 2829 + slot
        lines = [l.split('\t') for l in entry(n).rstrip(b'\0').decode('cp932').split('\r\n')]
        lines = [l for l in lines if any(c.strip() for c in l)]
        for b in range(0, len(lines) - 8, 9):
            blk = lines[b:b + 9]
            name = blk[0][0]
            cands = []
            for row in blk[1:4]:
                holders = []
                for key in [c for c in row if c.strip()]:
                    hits = [w['id'] for w in roster if key in w['_jp_full_all']]
                    thits = [w['id'] for w in templates if key in w['_jp_full_all']]
                    holders.append({'key_jp': key, 'key_en': team('titles', 'holder', key), 'matches': hits,
                                    'template_matches': thits})
                cands.append(holders)
            out.append({'entry': n, 'campaign_slot': slot, 'name': {'jp': name, 'en': team('titles', 'name', name)},
                        'holder_candidates': cands, 'allowed_on_show': [r[0] == '○' for r in blk[4:9]]})
    return out


def elimination_teams():
    d = entry(2001)
    out = []
    for i in range(struct.unpack_from('<I', d, 0)[0]):
        r = d[16 + 48 * i:64 + 48 * i]
        jp = cp(r[:31])
        if not jp:
            continue
        u = struct.unpack_from('<8H', r, 32)
        out.append({'id': i, 'jp': jp, 'en': team('teams', 'name', jp), 'members': list(u[2:7]),
                    'raw': {'byte_0x1f': r[31], 'u16_0x20': u[0], 'u16_0x22': u[1]}})
    return out


# ---------------------------------------------------------------- roster
def wrestler(w, i, logic, kind):
    r = w.index(i)
    nvar = r[0xa]
    vs = [struct.unpack_from('<H', r, 2 + 2 * k)[0] for k in range(nvar)]
    variants = []
    for vn in vs:
        o = w.vbase + 0x8ed * vn
        blk = w.d[o:o + 0x8ed]
        if len(blk) < 0x8ed:
            blk = blk + b'\0' * (0x8ed - len(blk))
        v = decode_variant(blk, logic)
        v['variant_block'] = vn
        variants.append(v)
    v0 = variants[0]
    cls = r[0xf]
    return {
        'id': i, 'kind': kind,
        'name': v0['full_name'], 'surname': v0['surname'], 'given': v0['given'],
        'promotion': dict(id=r[0xb], **{k: PROMOS[r[0xb]][k] for k in ('jp', 'en')}) if r[0xb] < len(PROMOS) else {'id': r[0xb]},
        'order_in_promotion': r[0xc],
        'weight_class': dict(raw=cls, **msg(60 + CLASS_RAW_TO_DISPLAY[cls])) if cls < 4 else {'raw': cls},
        'unlock_flag': r[0x10],
        'variant_count': nvar, 'variants': variants,
        'raw_index': {'u8_0xd': r[0xd], 'u8_0xe': r[0xe], 'rest': r[0x11:].hex() if any(r[0x11:]) else ''},
        '_jp_full_all': ' '.join(v['full_name']['jp'] for v in variants),
    }


def load():
    """Read the tables every decoder below uses (call once, after paths.configure)."""
    global A1672, A1673, A1677, A1682, APPEAR, BY_CAT, CLASS_RAW_TO_DISPLAY, CLIMB, CRITICAL, DURABILITY, E, FIELDS_EN, GFX, GROUPS, LOW_AVG_HIGH, MODE_SKILL, MOVES, MSG, P, PG, PR, PROMOS, ROSTER_EN, SHOP, SLOTS, SPEED, STYLE_RAW_TO_DISPLAY, TEAM_EN, V, VOICES
    E = entry(1450)
    SLOTS = []   # (name, slot, button, category, group)
    for k in range(len(E) // 36):
        r = E[36 * k:36 * k + 36]
        SLOTS.append((r[:28].split(b'\0')[0].decode('cp932'),) + struct.unpack_from('<4h', r, 28))
    BY_CAT = {}
    for k, s in enumerate(SLOTS):
        BY_CAT.setdefault(s[3], []).append(k)     # in table order (0x169878 builds the same)
    GROUPS, MOVES = table(2008, 'moves')
    ROSTER_EN = {(r['field'], r['japanese']): r['english'] for r in csv_rows('roster.csv')}
    FIELDS_EN = {(r['table'], r['japanese']): r['english'] for r in csv_rows('fields.csv')}
    TEAM_EN = {(r['table'], r['field'], r['japanese']): r['english'] for r in csv_rows('teamdata.csv')
               if r['table'] and r['field']}
    MSG = text_file('messages')                     # 1441: id -> (jp, en)
    GFX = {r['image']: r for r in csv_rows('../graphics.csv')}
    A1672 = atlas('000_01672')       # skill values
    A1673 = atlas('000_01673')       # match special skills
    A1677 = atlas('000_01677')       # parameter names
    A1682 = atlas('000_01682')       # move-slot categories
    CLASS_RAW_TO_DISPLAY = [0, 3, 1, 2]                      # 0x3a9fe0 (0x1542f8)
    STYLE_RAW_TO_DISPLAY = list(struct.unpack_from('<40i', (paths.EXTRACTED / 'SLPM_656.02').read_bytes(),
                                                   0x3a9ff0 - 0x323d80 + 0x224d80))   # 0x3a9ff0
    CRITICAL = A1672[0:7]                                     # None, Finisher, Suplex ... (raw = index)
    LOW_AVG_HIGH = {'recovery': (13, 15, 14), 'breathing': (9, 15, 10), 'spirit': (11, 15, 12)}
    DURABILITY = [A1672[11], A1672[15], A1672[12], A1672[20]]  # display 0 weak 1 avg 2 strong 3 injured
    SPEED = [A1672[7], A1672[15], A1672[8]]
    CLIMB = A1672[16:20]
    MODE_SKILL = A1672[23:34]
    P = entry(2000)
    PROMOS = []
    for i in range(struct.unpack_from('<I', P, 0)[0]):
        r = P[16 + 40 * i:56 + 40 * i]
        jp = cp(r[:36])
        PROMOS.append({'id': i, 'jp': jp, 'en': team('promotions', 'name', jp), 'logo': r[0x25],
                       'order': r[0x26], 'unlock_flag': r[0x27]})
    V = entry(1453)
    VOICES = {}
    for k in range(len(V) // 48):
        r = V[48 * k:48 * k + 48]
        jp = cp(r[:44])
        VOICES[struct.unpack_from('<H', r, 0x2c)[0]] = {'jp': jp, 'en': FIELDS_EN.get(('voices', jp))}
    PG, PR = table(2010, 'wrestlers')              # appearance parts: group = edit item
    APPEAR = [('face', 'H', 0xc6), ('stance', 'B', 0xc0), ('body_type', 'B', 0xc1), ('body_size', 'B', 0xc2),
              ('special_gear', 'B', 0xc3), ('sunglasses', 'B', 0xd0), ('chest', 'H', 0xd6), ('r_elbow', 'H', 0xdc),
              ('l_elbow', 'H', 0xe2), ('r_hand', 'H', 0xe8), ('l_hand', 'H', 0xee), ('waist', 'H', 0xf4),
              ('r_knee', 'H', 0xfa), ('l_knee', 'H', 0x100), ('feet', 'H', 0x106), ('entrance_face', 'H', 0x10c),
              ('entrance_gear', 'H', 0x112), ('entrance_gear_type', 'H', 0x114), ('entrance_sunglasses', 'B', 0x11a),
              ('belt', 'B', 0x128), ('options', 'B', 0x129), ('intro_speech', 'H', 0x120), ('theme', 'H', 0x122),
              ('entrance_call', 'H', 0x124), ('name_call', 'H', 0x126)]   # 0x15a530 item order
    SHOP = {}
    for line in entry(2396).rstrip(b'\0').decode('cp932').split('\r\n'):
        c = line.split('\t')
        if len(c) >= 9 and c[0].isdigit():
            SHOP[int(c[0])] = {'row': int(c[0]), 'jp': c[1], 'en': team('shop', 'name', c[1]),
                               'category': c[2] or None, 'price': int(c[3]) if c[3].isdigit() else None,
                               'promotion': c[5] or None, 'requirement': c[6] or None,
                               'difficulty': c[7] or None, 'wrestler_number': int(c[8]) if c[8].lstrip('-').isdigit() else None}


def model(logic=False):
    load()
    w = WD(1999)
    roster = [wrestler(w, i, logic, 'roster') for i in range(155)]
    # flags never set by the game (docs/HIDDEN_CONTENT.md): 2, 24, 25; 3 = edit slots; 4 = Retired group
    never = {24: 'never set (Trainees)', 25: 'never set (wrestler 147)'}
    startup = {0, 1, 185, 186}
    for x in roster:
        f = x['unlock_flag']
        x['unlock'] = {'flag': f, 'default_unlocked': f == 0 or f in startup,
                       'note': never.get(f), 'shop': None}
        rows = [s for s in SHOP.values() if s['wrestler_number'] == x['id'] and s['category'] == '隠しレスラー']
        x['unlock']['shop_rows'] = rows
        for v in x['variants']:
            v['default_unlocked'] = v['unlock_flag'] == 0
    mm = mm_table()
    for x in roster:
        x['match_maker'] = mm.get(x['id'], [])
    # Edit templates: 2005 (index records like 1999) + 1452 names/flags
    T = WD(2005)
    tn = entry(1452)
    templates = []
    for i in range(T.nw):
        t = wrestler(T, i, logic, 'edit_template')
        rec = tn[128 * i:128 * i + 128]
        jp = cp(rec[:40])
        t['template'] = {'name': {'jp': jp, 'en': FIELDS_EN.get(('wrestler_types', jp))},
                         'help': {'jp': cp(rec[40:124]), 'en': FIELDS_EN.get(('wrestler_types', cp(rec[40:124])))},
                         'unlock_flag_1452': struct.unpack_from('<H', rec, 0x7c)[0],
                         'category_1452': struct.unpack_from('<H', rec, 0x7e)[0]}
        f = t['unlock_flag']
        t['unlock'] = {'flag': f, 'default_unlocked': f == 0, 'shop': SHOP.get(f)}
        templates.append(t)
    tl = titles(roster, templates)
    for x in roster + templates:
        del x['_jp_full_all']
    out = {
        'source': 'tools/rosterdb.py',
        'lists': {
            'promotions': PROMOS,
            'move_slots': [{'slot': k, 'name_jp': s[0], 'name_en': FIELDS_EN.get(('logic_situations', s[0])),
                            'button': s[2], 'category': s[3],
                            'category_label': lab(A1682[s[3]]) if s[3] < len(A1682) else None, 'group': s[4]}
                           for k, s in enumerate(SLOTS)],
            'moves': [{'id': m['i'], 'jp': m['jp'], 'en': m['en'] or None, 'unlock_flag': m['raw'][0xb]}
                      for m in MOVES],
            'elimination_teams': elimination_teams(),
        },
        'wrestlers': roster,
        'edit_templates': templates,
        'match_maker_titles': tl,
    }
    return out


# ---------------------------------------------------------------- links from the other pages
ROSTER = 155   # WrestlerData records 0-154 are wrestlers; the mode copies add the Edit samples after


def mode_links(entry):
    """{record: page link} for a mode's roster copy (2002/2004: wrestlers, then the 155 Edit
    samples in another order): 'roster/<id>' or 'templates/<id>'. Samples are matched by their
    variant block (all but the first 4 bytes, the record number) - every one matches exactly once."""
    w, t = WD(entry), WD(2005)
    blocks_ = {}
    for j in range(t.nw):
        blocks_.setdefault(t.block(t.variants(j)[0])[4:], []).append(j)
    out = {i: f'roster/{i}' for i in range(ROSTER)}
    for i in range(ROSTER, w.nw):
        vs = w.variants(i)
        hit = blocks_.get(w.block(vs[0])[4:]) if vs[0] < w.nv else None
        if hit and len(hit) == 1:
            out[i] = f'templates/{hit[0]}'
    return out


def name_links():
    """{Japanese full name without spaces or ・, in either name order: page link} for every
    wrestler's costumes ('roster/<id>') and then every Edit sample ('templates/<id>')."""
    out = {}
    for entry, kind, count in ((1999, 'roster', ROSTER), (2005, 'templates', None)):
        w = WD(entry)
        for i in range(count or w.nw):
            for vn in w.variants(i)[:w.index(i)[0xa]]:
                if vn >= w.nv:
                    continue
                t = unpack(w.block(vn))['text']
                sur, giv = sj(t[:15]), sj(t[15:36])
                for key in (sur + giv, giv + sur):
                    out.setdefault(re.sub('[\u3000 ・]', '', key), f'{kind}/{i}')
    return out


def page_data(full):
    """The page's copy: labels in English (Japanese where none), moves as ids into one list."""
    L = lambda x: (x or {}).get('en') or (x or {}).get('jp')
    shop = {}
    for line in entry(2396).rstrip(b'\0').decode('cp932').split('\r\n'):
        c = line.split('\t')
        if len(c) >= 9 and c[0].lstrip('-').isdigit() and c[3].isdigit():
            shop[int(c[0])] = {'name': team('shop', 'name', c[1]) or c[1], 'price': int(c[3])}

    names = {}
    bf = blocks.BlockFile(paths.TEXT / 'wrestlers.txt')
    for b in bf.blocks:
        if b.english:
            names.setdefault(re.sub('[\u3000 ]', '', bf.source(b)[0]), b.english[0])

    def display_name(v):
        """The translated full name (wrestlers.txt, table 2010) where there is one; else surname
        and given name from the roster, family name last only for kanji names (Kenta Kobashi,
        but Spike Tomoki, Mr. OTANI, Trainee #2)."""
        n = v['full_name']
        hit = names.get(re.sub('[\u3000 ]', '', n['jp']))
        if hit:
            return hit
        kanji = lambda t: t and all('\u4e00' <= ch <= '\u9fff' for ch in t)
        return n['en_western'] if kanji(v['surname']['jp']) and kanji(v['given']['jp']) else (n['en_game_order'] or n['jp'])

    def variant(v):
        a = v['appearance']
        return {
            'type': v['type'], 'locked': not v.get('default_unlocked', v['unlock_flag'] == 0), 'flag': v['unlock_flag'],
            'name': display_name(v), 'name_jp': v['full_name']['jp'],
            'nick': v['nickname']['en'] or v['nickname']['jp'], 'nick_jp': v['nickname']['jp'],
            'move_text': v['special_move_text']['en'] or v['special_move_text']['jp'],
            'nation': L(v['nationality']), 'build': L(v['build']), 'height': v['height_cm'], 'weight': v['weight_kg'],
            'birthday': v['birthday'], 'style': L(v['fight_style']),
            'rev_odds': L(v['reversal_type_odds']), 'rev_moves': L(v['reversal_type_moves']),
            'popularity': L(v['popularity']), 'color': L(v['favorite_color']),
            'voices': [L(v['voice1']), L(v['voice2'])],
            'skills': {k: (x['label'] if isinstance(x, dict) else x) for k, x in v['skills'].items() if k != 'match_special_skills'},
            'match_skills': [x['label'] for x in v['skills']['match_special_skills'] if x['label']],
            'offense': v['parameters']['offense'], 'defense': v['parameters']['defense'],
            'specials': [[x['kind'], x['slot'], x['move']] for x in v['specials']],
            'moves': v['moveset'],
            'theme': L(a['theme']), 'entrance': [L(a[k]) for k in ('intro_speech', 'entrance_call', 'name_call')],
            'face': L(a['face']), 'stance': L(a['stance']), 'body': L(a['body_type']),
        }

    def wrestler(w):
        u = w.get('unlock', {})
        rows = [shop[r['row']] for r in u.get('shop_rows', []) if r['row'] in shop]
        return {'id': w['id'], 'name': display_name(w['variants'][0]), 'name_jp': w['name']['jp'],
                'promotion': L(w['promotion']), 'cls': L(w['weight_class']),
                'locked': not u.get('default_unlocked', True), 'never': u.get('note') is not None,
                'shop': rows, 'mm': [m['campaign'] for m in w.get('match_maker', [])],
                'variants': [variant(v) for v in w['variants']]}
    templates = [{'id': t['id'], 'name': t['template']['name']['en'] or t['template']['name']['jp'],
                  'name_jp': t['template']['name']['jp'],
                  'help': t['template']['help']['en'] or t['template']['help']['jp'],
                  'category': ['Wrestler type', 'Pro sample', 'Fighter sample'][t['template']['category_1452']]
                  if t['template']['category_1452'] < 3 else str(t['template']['category_1452']),
                  'locked': not t['unlock']['default_unlocked'],
                  'shop': shop.get(t['unlock']['flag']) if t['unlock']['flag'] else None,
                  'variants': [variant(v) for v in t['variants'][:1]]} for t in full['edit_templates']]
    lists = full['lists']
    return {
        'wrestlers': [wrestler(w) for w in full['wrestlers']],
        'templates': templates,
        'moves': [m['en'] or m['jp'] for m in lists['moves']],
        'slots': [[s['name_en'] or s['name_jp'], s['category_label'], s['button'], s['category']] for s in lists['move_slots']],
        'clutch_slots': BY_CAT[4],
        'titles': [{'campaign': ['', 'New Japan', 'NOAH', 'All Japan', 'ZERO-ONE', 'WJ', 'Pancrase', 'Free Show'][t['campaign_slot']],
                    'name': t['name']['en'] or t['name']['jp'],
                    'holders': [[h['key_en'] or h['key_jp'] for h in c] for c in t['holder_candidates']],
                    'shows': t['allowed_on_show']} for t in full['match_maker_titles']],
        'teams': [{'name': x['en'] or x['jp'], 'members': x['members']} for x in lists['elimination_teams']],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, help='default: docs/wrestlers/index.html')
    ap.add_argument('--template', type=Path, help='default: tools/rosterdb_template.html')
    ap.add_argument('--json', type=Path, help='also write the full model here')
    ap.add_argument('--logic', action='store_true', help='with --json: include the raw CPU-logic values')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if not (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000').exists():
        sys.exit(f'{paths.show(paths.EXTRACTED)}: no KC2FIRE_000 - run tools/extract.py first')
    full = model(args.logic)
    if args.json:
        args.json.write_text(json.dumps(full, ensure_ascii=False, indent=1), encoding='utf-8')
    d = page_data(full)
    template = args.template or Path(__file__).resolve().parent / 'rosterdb_template.html'
    out, size = pagekit.write('wrestlers', template, d, args.out)
    print(f"{len(d['wrestlers'])} wrestlers, {sum(len(w['variants']) for w in d['wrestlers'])} costumes, "
          f"{len(d['templates'])} Edit samples -> {paths.show(out)} ({size // 1024} KB)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
