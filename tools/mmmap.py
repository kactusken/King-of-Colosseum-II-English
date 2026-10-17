#!/usr/bin/env python3
"""Build the Match Maker route map, docs/matchmaker-map/index.html: every briefing, check,
verdict, advice answer, game over and ending of each promotion's Match Maker campaign.

  mmmap.py [--out PATH] [--template PATH] [--json PATH]

Reads the original entries (extracted/) for the structure and translation/text/mmtalk.txt,
mmdata.txt, elf.txt and wrestlers.txt for the English, then embeds the data in
tools/mmmap_template.html (shared parts: tools/pagekit.py). The page needs internet access only
for Google Fonts. Rerun it after
changing the Match Maker text. --json also writes the data on its own.

Campaign flow (*from the code*, driver 0x1cd190; docs/TECHNICAL.md "Match Maker campaign flow"):
- slot s (1 New Japan, 2 NOAH, 3 All Japan, 4 ZERO-ONE, 5 WJ, 6 Pancrase - cut) reads entries
  base + s: briefings 2853, verdicts 2861 (goals met) / 2869 (a goal missed), advice 2877 with
  its index 2885, shows 2805. Slot 0's entries copy slot 1's; slot 7 (Free Show) has no dialogue.
- briefing item 0 (show 1 only, before item 1), item k for show k, item 6 after a failed show
  (then GAME OVER), item 7 when the campaign is over, item k+6 after show k's briefing (k = 2-4)
  when show k-1 scored 85 or more (it announces the guest wrestlers 0x1d1868 adds).
- a show passes when attendance >= its goal and the average match rating >= its goal; the
  verdict is item (show-1)*6 + grade of 2861+s (passed) or 2869+s (failed), grades S A B C D E
  for a score of 95/85/70/50/30 or more, score = (attendance / capacity * 100 + rating) / 2.
- the last show is a bonus show: played only if every earlier show scored 85 or more;
  otherwise the ending follows the second-to-last show.
- advice: 2877+s holds a header line then the items of four blocks (prompt, Matchmaking,
  Match Rating, Other; なし lines count); 2885+s lists per topic and show the item numbers,
  taken in turn each time the topic is asked (counters reset when the office is entered).
Item numbers count every item of an entry (header and なし lines too); mmtalk.txt ids count
strings only, so this tool maps one onto the other.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import mmdata  # noqa: E402
import mmtalk  # noqa: E402
import pagekit  # noqa: E402
import rosterdb  # noqa: E402
import paths  # noqa: E402

BRIEFING, MET, MISSED, ADVICE, ADVICE_INDEX, SHOWS = 2853, 2861, 2869, 2877, 2885, 2805
GRADES = [('S', 95), ('A', 85), ('B', 70), ('C', 50), ('D', 30), ('E', 0)]
TOPICS = ['Matchmaking', 'Match Rating', 'Other']
NONE = 'なし'
# slot -> (key, tab label, speakers: president, second speaker or None)
PROMOTIONS = {
    1: ('njpw', 'New Japan', ('Masahiro Chono', 'Tatsumi Fujinami')),
    2: ('noah', 'NOAH', ('Mitsuharu Misawa', 'Masao Inoue')),
    3: ('ajpw', 'All Japan', ('Keiji Mutoh', None)),
    4: ('zero1', 'ZERO-ONE', ('Shinya Hashimoto', None)),
    5: ('wj', 'WJ', ('Katsuji Nagashima', None)),
    6: ('pancrase', 'Pancrase (cut)', ('Masami Ozaki', None)),
}
# guest wrestlers 0x1d1868 adds for show k when show k-1 scored 85 or more (*from the code*)
GUESTS = {1: {2: ['坂口　征二', '山本　小鉄'], 3: ['星野　勘太郎'], 4: ['アックス・ドゥガン']},
          2: {2: ['ラッシャー木村'], 3: ['セイバー'], 4: ['サム・ポップ']},
          3: {2: ['黒師無双'], 3: ['グレート・ムタ'], 4: ['スター・バイソン']},
          4: {2: ['バット・サファリ'], 3: ['長州　力'], 4: ['真田　伸久']},
          5: {2: ['マスク・ド・パンサー'], 3: ['パワー・ウォリアー']},
          6: {3: ['獣神サンダー・ライガー'], 4: ['火野輪　伸人']}}
SECOND_PROMPT = {1, 2}   # the advice prompt is the second speaker's at the bonus show (0x1d4d10)
# the cut Pancrase data is one show off: its announcements are items 8/9 (after shows 2/3's
# briefings) but 0x1d1868 adds Liger at show 3 and Hinowa at show 4
OFF_BY_ONE = {6: 'Cut data: this line names a guest whom the code adds one show later.'}


def items(entry):
    """[(kind, value, string index or None)] as the game's parser sees the entry."""
    out, n = [], 0
    for kind, v in mmtalk.game_items(mmtalk.entry_data(entry)):
        out.append((kind, v, n if kind == 'string' else None))
        n += kind == 'string'
    return out


def is_none(it):
    return it[0] == 'line' and it[1] == NONE.encode('cp932')


class Talk:
    """mmtalk.txt: every entry.string id -> its block, and the dialogue the page shows."""

    def __init__(self):
        bf = blocks.BlockFile(mmtalk.text_path())
        self.by_id, self.used = {}, {}
        for b in bf.blocks:
            for i in [b.id] + b.meta.split()[1:]:
                self.by_id[i] = b
        self.bf = bf

    def ref(self, entry, item):
        """Dialogue id for item `item` of `entry` (None for a なし line), recorded for the page."""
        it = items(entry)[item]
        if it[2] is None:
            return None
        b = self.by_id[f'{entry}.{it[2]}']
        if b.id not in self.used:
            jp = mmtalk.jp_pages('\n'.join(self.bf.source(b)))
            en = mmtalk.en_pages('\n'.join(b.english)) if b.english else [p for p, _ in jp]
            self.used[b.id] = [{'en': e.strip('\n'), 'jp': j.strip('\n').replace('　', ' ').strip(),
                                'second': any(t in ('（藤波）', '（井上）') for t in tags)}
                               for e, (j, tags) in zip(en, jp) if e.strip() or j.strip()]
        return b.id


def show_text():
    """{(kind, Japanese): English} from mmdata.txt, plus elf.txt for the keyed venues/crowds."""
    out = {}
    elf = blocks.BlockFile(paths.TEXT / 'elf.txt')
    for b in elf.blocks:
        if b.english:
            jp = '\n'.join(elf.source(b))
            for kind in ('venue', 'crowd'):
                out.setdefault((kind, jp), '\n'.join(b.english))
    md = blocks.BlockFile(mmdata.text_path())
    for b in md.blocks:
        if b.english:
            out[b.id.split('.')[0], '\n'.join(md.source(b))] = '\n'.join(b.english)
    return out


def wrestler_names():
    bf = blocks.BlockFile(paths.TEXT / 'wrestlers.txt')
    out = {}
    for b in bf.blocks:
        if b.english:
            out.setdefault('\n'.join(bf.source(b)), b.english[0])
    return out


def ascii_or(text):
    """Full-width Latin shown as ASCII (show names kept in the original letters)."""
    return unicodedata.normalize('NFKC', text).replace('　', ' ')


def shows(slot, english):
    out = []
    for r in mmdata.parse_shows(mmdata.original(SHOWS + slot)):
        if r is None:
            continue
        d = {k: r[k].decode('cp932') for k in ('name', 'goal', 'venue', 'crowd')}
        notes = r['notes'].decode('cp932').replace('\r\n', '\n')
        size = r['size'].decode('cp932')
        m = mmdata.SIZE.match(size)
        out.append({
            'name': ascii_or(english.get(('name', d['name']), d['name'])), 'name_jp': d['name'],
            'goal': english.get(('goal', d['goal']), d['goal']), 'goal_jp': d['goal'],
            'venue': english.get(('venue', d['venue'].split('（')[0]), d['venue']), 'venue_jp': d['venue'],
            'crowd': english.get(('crowd', d['crowd']), d['crowd']),
            'capacity': int(r['capacity']), 'matches': int(r['n1']),
            'attendance_goal': int(r['n2']), 'rating_goal': int(r['n3']),
            'roster': int(m.group(1)) if m and m.group(1).isdigit() else size,
            'notes': [ln.strip() for ln in english.get(('notes', notes), notes).split('\n') if ln.strip()],
        })
    return out


def advice(slot, talk):
    """(prompt ids, {show: {topic: [ids in the order the game gives them]}})."""
    blocks_, cur = [], None
    for i, it in enumerate(items(ADVICE + slot)):
        if it[0] == 'line' and not is_none(it):
            cur = []
            blocks_.append(cur)
        else:
            cur.append(i)
    prompt = [talk.ref(ADVICE + slot, i) for i in blocks_[0][:2]]
    rows, cur = [], None
    for ln in mmtalk.entry_data(ADVICE_INDEX + slot).decode('cp932').split('\r\n'):
        if not ln:
            continue
        if ln[0].isdigit():
            cur.append([int(x) for x in ln.split(',') if x and int(x)])
        else:
            cur = []
            rows.append(cur)
    per_show = {}
    for t, name in enumerate(TOPICS):
        for k, row in enumerate(rows[t]):
            ids = [talk.ref(ADVICE + slot, blocks_[t + 1][x - 1]) for x in row]
            per_show.setdefault(k + 1, {})[name] = [i for i in ids if i]
    return prompt, per_show


def promotion(slot, talk, english, names, links):
    key, label, speakers = PROMOTIONS[slot]
    b = BRIEFING + slot
    bi = items(b)
    sh = shows(slot, english)
    n = len(sh)
    prompt, adv = advice(slot, talk)
    for k, s in enumerate(sh, 1):
        s['n'] = k
        s['bonus'] = k == n
        s['briefing'] = talk.ref(b, k)
        s['intro'] = talk.ref(b, 0) if k == 1 else None
        f = k + 6
        if 2 <= k <= 4 and f < len(bi) and not is_none(bi[f]):
            s['followup'] = {'line': talk.ref(b, f), 'after': k - 1,
                             'guests': [names.get(g, g) for g in GUESTS.get(slot, {}).get(k, [])],
                             'guest_links': [links.get(re.sub('[\u3000 ・]', '', g)) for g in GUESTS.get(slot, {}).get(k, [])],
                             'note': OFF_BY_ONE.get(slot)}
        s['advice'] = adv.get(k, {})
        s['advice_prompt'] = prompt[1] if slot in SECOND_PROMPT and k == n and prompt[1] else prompt[0]
        s['met'] = [talk.ref(MET + slot, (k - 1) * 6 + g) for g in range(6)]
        s['missed'] = [talk.ref(MISSED + slot, (k - 1) * 6 + g) for g in range(6)]
    return {'slot': slot, 'key': key, 'label': label, 'speakers': speakers, 'shows': sh,
            'gameover': talk.ref(b, 6), 'ending': talk.ref(b, 7),
            'cut': slot == 6}


def build():
    talk = Talk()
    english, names, links = show_text(), wrestler_names(), rosterdb.name_links()
    promos = [promotion(s, talk, english, names, links) for s in PROMOTIONS]
    return {'promotions': promos, 'grades': GRADES, 'dialogue': talk.used}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, help='default: docs/matchmaker-map/index.html')
    ap.add_argument('--template', type=Path, help='default: tools/mmmap_template.html')
    ap.add_argument('--json', type=Path, help='also write the data here')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if not (paths.EXTRACTED / 'DATA' / 'KC2FIRE_000').exists():
        sys.exit(f'{paths.show(paths.EXTRACTED)}: no KC2FIRE_000 - run tools/extract.py first')
    template = args.template or Path(__file__).resolve().parent / 'mmmap_template.html'
    d = build()
    if args.json:
        args.json.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    out, size = pagekit.write('matchmaker-map', template, d, args.out)
    n = sum(len(p['shows']) for p in d['promotions'])
    print(f'{len(d["promotions"])} promotions, {n} shows, {len(d["dialogue"])} dialogue strings'
          f' -> {paths.show(out)} ({size // 1024} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
