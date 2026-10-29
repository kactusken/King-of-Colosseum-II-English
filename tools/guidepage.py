#!/usr/bin/env python3
"""Build the player's guide, docs/guide/index.html: how to play, the modes, controls, how matches
work, rules, Edit Mode, the special skills, secrets and a Japanese glossary.

  guidepage.py [--out PATH] [--template PATH] [--check]

The prose is in tools/guide_template.html (shared parts: tools/pagekit.py; Google Fonts is its
only download). This tool adds the data the game holds:
  - the special skills (match, mode and combination skills) with their effects, from the English
    in translation/text/messages.txt (entries 175-499) and the skill-list pictures in
    translation/graphics.csv (000_01673 match skills, 000_01674 combinations);
  - the Japanese glossary (GLOSSARY below), every "on screen" term checked against the English in
    translation/, so a renamed term can't go stale on the page.
The template writes buttons as <kbd class="f sq">□</kbd> (face buttons: sq, crs, cir, tri) and
<kbd>R1</kbd> (shoulders), and the controller diagram's face buttons as <!--BTN sq x y r-->; the
build draws them all with the shared button icons (pagekit.button(), the ones the wrestler database
uses).
--check builds the page in memory and fails if docs/guide/index.html differs or a glossary term
is no longer in the translation (check.py runs it). Needs only translation/, not extracted/.
"""
import argparse
import csv
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pagekit  # noqa: E402
import paths  # noqa: E402

TOOLS = Path(__file__).resolve().parent
# message ranges (translation/text/messages.txt): skill name, then its description lines
MODE_SKILLS = range(175, 225)     # groups ended by a '＃' line
MATCH_SKILLS = range(225, 400)    # the same; the last group has no '＃'
COMBO_SKILLS = range(400, 500)    # fixed groups of four: name, three lines
PICTURES = ('000_01672', '000_01673', '000_01674')   # the names as the skill lists draw them (values and
#                                                  mode skills, match skills, combinations)

# (group, Japanese, romaji, meaning, on screen in the translation; ' / ' separates several terms,
#  each of which must appear in the English of translation/)
GLOSSARY = [
    ('Modes and menus', 'エキシビションマッチ', 'ekishibishon matchi', 'exhibition match', 'Exhibition Match'),
    ('Modes and menus', 'サバイバルロード', 'sabaibaru rōdo', 'survival road', 'Survival Road'),
    ('Modes and menus', 'マッチメイカー', 'matchi meikā', 'match maker (booker)', 'Match Maker'),
    ('Modes and menus', 'タイトルマッチ', 'taitoru matchi', 'title match', 'Title Match'),
    ('Modes and menus', 'シリーズモード', 'shirīzu mōdo', 'series mode', 'Series Mode'),
    ('Modes and menus', 'プロレス道場', 'puroresu dōjō', 'pro wrestling training hall', 'Pro Wrestling Dojo'),
    ('Modes and menus', '魂の殿堂', 'tamashii no dendō', 'hall of souls (the shop)', 'Hall of Souls'),
    ('Modes and menus', 'はじめから / 続きから', 'hajime kara / tsuzuki kara', 'from the start / continue', 'New Game / Continue'),
    ('Modes and menus', 'リーグ戦 / トーナメント', 'rīgu-sen / tōnamento', 'league / tournament', 'League / Tournament'),
    ('Modes and menus', '自動進行', 'jidō shinkō', 'automatic progress', 'Auto Mode'),
    ('Modes and menus', '順位表', "jun'i-hyō", 'standings table', 'Standings'),
    ('Modes and menus', '歴代王者', 'rekidai ōja', 'successive champions', 'Title History'),
    ('Modes and menus', 'ベルト返上', 'beruto henjō', 'returning the belt', 'Vacate Title'),
    ('Modes and menus', '戦いの歴史', 'tatakai no rekishi', 'history of battles', 'Battle History'),
    ('Modes and menus', 'クイックセーブ', 'kuikku sēbu', 'quick save', 'Quick Save'),
    ('Match types and rules', 'シングルマッチ（セコンド）', 'shinguru matchi (sekando)', 'singles with seconds', 'Single Match (Seconds)'),
    ('Match types and rules', 'イリミネーションマッチ', 'iriminēshon matchi', 'five-on-five elimination', 'Elimination Match'),
    ('Match types and rules', '勝ち抜き戦', 'kachinuki-sen', 'winner stays on', 'Gauntlet Match'),
    ('Match types and rules', '総当たり戦', 'sōatari-sen', 'round robin', 'Round Robin'),
    ('Match types and rules', '先鋒 / 次鋒 / 中堅 / 副将 / 大将', 'senpō / jihō / chūken / fukushō / taishō', 'team order, first to last', '1st / 2nd / 3rd / 4th / Captain'),
    ('Match types and rules', 'セコンド', 'sekando', 'ringside second', 'Second'),
    ('Match types and rules', '試合形式', 'shiai keishiki', 'how the match is decided', 'Match Type'),
    ('Match types and rules', '一本勝負 / 三本勝負', 'ippon shōbu / sanbon shōbu', 'one fall / three falls', 'One Fall / Best of 3 Falls'),
    ('Match types and rules', 'プロレスルール', 'puroresu rūru', 'pro wrestling rules', 'Pro Wrestling Rules'),
    ('Match types and rules', 'バーリトゥードルール', 'bāritūdo rūru', 'vale tudo rules', 'Vale Tudo Rules'),
    ('Match types and rules', '無我ルール', 'muga rūru', 'Muga rules', 'Muga Rules'),
    ('Match types and rules', '判定', 'hantei', "judges' decision", 'Judge'),
    ('Match types and rules', 'マストシステム', 'masuto shisutemu', 'must system (judging)', 'Must System'),
    ('Match types and rules', '場外カウント', 'jōgai kaunto', 'count outside the ring', 'Ring-out Count'),
    ('Match types and rules', '反則カウント', 'hansoku kaunto', 'foul count', 'Foul Count'),
    ('Match types and rules', 'ランバージャック', 'ranbājakku', 'lumberjack', 'Lumberjack'),
    ('Match types and rules', '花道', 'hanamichi', 'entrance aisle', 'Ramp'),
    ('Match types and rules', 'ファン層', 'fan-sō', 'kind of fans', 'Crowd'),
    ('Match types and rules', '観客満足度', 'kankyaku manzokudo', 'audience satisfaction', 'Crowd Satisfaction'),
    ('Match types and rules', '実況 / 解説', 'jikkyō / kaisetsu', 'play-by-play / commentary', 'Caller / Color'),
    ('Match types and rules', 'クリティカル', 'kuritikaru', 'critical', 'Critical'),
    ('In the ring', '体力', 'tairyoku', 'physical strength', 'Stamina'),
    ('In the ring', '精神力', 'seishinryoku', 'mental strength', 'Spirit'),
    ('In the ring', '呼吸', 'kokyū', 'breathing', 'Breath'),
    ('In the ring', '呼吸困難', 'kokyū konnan', 'difficulty breathing', 'Breathless'),
    ('In the ring', '耐久度', 'taikyūdo', 'durability', 'Durability'),
    ('In the ring', 'ピヨリ', 'piyori', 'seeing stars', 'Dazed'),
    ('In the ring', '流血', 'ryūketsu', 'bleeding', 'Bleeding'),
    ('In the ring', '魂 / 魂技', 'tamashii / tamashii-waza', 'soul / soul move', 'Soul / Soul Move'),
    ('In the ring', '必殺技 / 得意技', 'hissatsu-waza / tokui-waza', 'certain-kill move / favourite move', 'Finisher / Signature Move'),
    ('In the ring', 'クラッチ', 'kuratchi', 'clutch: the grapple hold before a move', 'Clutch'),
    ('In the ring', 'タイアップクラッチ', 'taiappu kuratchi', 'collar-and-elbow tie-up', 'Tie-Up Clutch'),
    ('In the ring', 'ジャーマンクラッチ', 'jāman kuratchi', 'rear waistlock', 'German Clutch'),
    ('In the ring', 'クラッチ返し技', 'kuratchi kaeshi-waza', 'counter from a clutch', 'reversal'),
    ('In the ring', 'ハンマースルー', 'hanmā surū', '"hammer throw": the whip', 'Irish Whip'),
    ('In the ring', 'フロントヘッドロック', 'furonto heddorokku', 'front headlock', 'Front Headlock'),
    ('In the ring', '羽交い締め', 'hagaijime', 'full nelson', 'Full Nelson'),
    ('In the ring', 'コーナー逆さ吊り', 'kōnā sakasazuri', 'hung upside down in the corner', 'Tree of Woe'),
    ('In the ring', 'がぶり', 'gaburi', 'front facelock (sprawl)', 'Facelock'),
    ('In the ring', 'マウント / バックマウント', 'maunto / bakku maunto', 'mount / back mount', 'Mount / Back Mount'),
    ('In the ring', 'ホーミングダッシュ / ロープダッシュ', 'hōmingu dasshu / rōpu dasshu', 'homing run / run off the ropes', 'Homing Dash / Rope Dash'),
    ('In the ring', 'ガード / キャッチ', 'gādo / kyatchi', 'guard / catch', 'Guard / Catch'),
    ('In the ring', '引き起こし', 'hikiokoshi', 'pulling up', 'Pick-up'),
    ('In the ring', '狸寝入り', 'tanuki-neiri', "a raccoon dog's sleep: playing possum", 'Play Possum'),
    ('In the ring', 'ロープブレイク / ロープエスケープ', 'rōpu bureiku / rōpu esukēpu', 'rope break / rope escape', 'Rope Break / Rope Escape'),
    ('In the ring', 'アピール', 'apīru', 'appeal to the crowd', 'Taunt'),
    ('In the ring', 'タッチ / カット', 'tatchi / katto', 'tag / breaking up a hold', 'Tag / Cut Attack'),
    ('In the ring', 'ツープラトン', 'tsū puraton', '"two-platoon": a double-team move', 'Double Team'),
    ('In the ring', '凶器 / 鉄柵', 'kyōki / tessaku', 'weapon / iron barrier', 'weapon / barrier'),
    ('In the ring', '場外', 'jōgai', 'outside the ring', 'outside'),
    ('Edit Mode', 'エディット', 'editto', 'edit', 'Edit'),
    ('Edit Mode', '団体エディット / 団体移籍', 'dantai editto / dantai iseki', 'promotion edit / transfer', 'Promotion Edit / Transfers'),
    ('Edit Mode', 'レスラータイプ', 'resurā taipu', 'a version (costume) of a wrestler', 'Wrestler Type'),
    ('Edit Mode', 'レスラーメイク', 'resurā meiku', "the wrestler's look", 'Appearance'),
    ('Edit Mode', '技装備', 'waza sōbi', 'moves equipped', 'Moveset'),
    ('Edit Mode', '隠し装備', 'kakushi sōbi', 'hidden equipment', 'Hidden Moves'),
    ('Edit Mode', 'ＣＯＭロジック', 'komu rojikku', 'CPU logic', 'CPU Logic'),
    ('Edit Mode', '返しタイプ', 'kaeshi taipu', 'reversal type', 'Reversals'),
    ('Edit Mode', '魂ボタン数', 'tamashii botan-sū', 'number of soul buttons', 'Soul Buttons'),
    ('Edit Mode', '試合用 / モード用特殊スキル', 'shiai-yō / mōdo-yō tokushu sukiru', 'special skill for matches / for modes', 'Match Special Skill / Mode Special Skill'),
    ('Edit Mode', 'サンプルロード', 'sanpuru rōdo', 'load a sample', 'Load Sample'),
    ('Edit Mode', '前口上', 'maekōjō', 'introduction speech', 'Intro Speech'),
    ('Edit Mode', '引退', 'intai', 'retired', 'Retired'),
]


def read_blocks(path):
    """{number: (Japanese lines, English lines)} of a JP/EN text file."""
    out, cur = {}, None
    for line in path.read_text(encoding='utf-8').splitlines():
        m = re.match(r'@ (\d+)', line)
        if m:
            cur = out.setdefault(int(m.group(1)), ([], []))
        elif cur is not None and line[:3] in ('JP ', 'EN '):
            cur[0 if line.startswith('JP') else 1].append(line[3:])
    return out


def picture_names():
    """Japanese -> English of the skill-list pictures."""
    names = {}
    with open(paths.GRAPHICS_CSV, encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            if r['image'] in PICTURES:
                jp = [s.strip() for s in r['japanese'].split('|')]
                en = [s.strip() for s in r['english'].split('|')]
                if len(jp) != len(en):
                    sys.exit(f"graphics.csv {r['image']}: {len(jp)} Japanese names but {len(en)} English - fix the row")
                names.update(zip(jp, en))
    return names


def skills():
    msg = read_blocks(paths.TEXT / 'messages.txt')
    pics = picture_names()

    def group(rng, fixed=None):
        """Split a message range into skills: a new one starts after a '＃' line, at a line that is
        a skill name in the pictures (some '＃' lines are missing), or every `fixed` lines."""
        out = []
        for n in rng:
            jp, en = msg.get(n, ([], []))
            jp, en = ''.join(jp).strip(), ' '.join(en).strip()
            if jp == '＃':
                out.append([])
            elif not out or (jp in pics) or (fixed and len(out[-1]) == fixed):
                out.append([(jp, en)])
            else:
                out[-1].append((jp, en))
        rows = []
        for g in filter(None, out):
            (jp, en), lines = g[0], [e for _, e in g[1:] if e]
            if jp:
                rows.append({'jp': jp, 'name': pics.get(jp, en), 'text': ' '.join(lines)})
        return rows

    return {'match': group(MATCH_SKILLS), 'mode': group(MODE_SKILLS), 'combo': group(COMBO_SKILLS, 4)}


def english_corpus():
    """Every English string the patch shows, as one lower-case text (for the glossary check)."""
    parts = []
    for p in sorted((paths.TEXT).iterdir()):
        t = p.read_text(encoding='utf-8')
        parts += [l[3:] for l in t.splitlines() if l.startswith('EN ')] if p.suffix == '.txt' else [t]
    for p in [paths.GRAPHICS_CSV] + sorted((paths.TRANSLATION / 'hand').glob('*.py')):
        parts.append(p.read_text(encoding='utf-8'))
    return '\n'.join(parts).lower()


def glossary():
    corpus = english_corpus()
    rows, missing = [], []
    for grp, jp, romaji, meaning, en in GLOSSARY:
        for term in en.split(' / '):
            if term.lower() not in corpus:
                missing.append(f'{jp}: "{term}"')
        rows.append({'group': grp, 'jp': jp, 'romaji': romaji, 'meaning': meaning, 'en': en})
    return rows, missing


FACE = {'sq': 'sq', 'crs': 'x', 'cir': 'o', 'tri': 'tri'}


def buttons(html):
    """The template's button markup -> the shared button icons (see the docstring)."""
    html = re.sub(r'<kbd class="f (sq|crs|cir|tri)">[^<]*</kbd>', lambda m: pagekit.button(FACE[m.group(1)]), html)
    html = re.sub(r'<kbd>([LR][12])</kbd>', lambda m: pagekit.button(m.group(1)), html)

    def diagram(m):   # an icon inside the controller SVG: the disc scaled to radius r at (x, y)
        kind, x, y, r = m.group(1), *map(float, m.groups()[1:])
        k = r / 10
        return (f'<g transform="translate({x - r:g} {y - r:g}) scale({k:g})"><circle cx="10" cy="10" r="9.2" '
                f'style="fill:var(--b-disc);stroke:var(--b-ring)" stroke-width="0.8"/>{pagekit.GLYPH[kind]}</g>')
    return re.sub(r'<!--BTN (sq|x|o|tri) ([\d.]+) ([\d.]+) ([\d.]+)-->', diagram, html)


def model():
    rows, missing = glossary()
    return {'skills': skills(), 'glossary': rows}, missing


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, help='default: docs/guide/index.html')
    ap.add_argument('--template', type=Path, help='default: tools/guide_template.html')
    ap.add_argument('--check', action='store_true', help='fail if the page is out of date or a glossary term went stale')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    d, missing = model()
    if missing:
        sys.exit('glossary terms no longer in the translation (update GLOSSARY in tools/guidepage.py):\n  '
                 + '\n  '.join(missing))
    template = args.template or TOOLS / 'guide_template.html'
    target = args.out or paths.DOCS / 'guide' / 'index.html'
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = pagekit.write('guide', template, d, Path(tmp) / 'index.html', buttons)
            fresh = out.read_bytes()
        if not target.exists() or target.read_bytes() != fresh:
            sys.exit(f'{paths.show(target)} is out of date - run python3 tools/guidepage.py')
        print(f'{paths.show(target)} is up to date')
        return 0
    out, size = pagekit.write('guide', template, d, target, buttons)
    s = d['skills']
    print(f"{len(s['match'])} match, {len(s['mode'])} mode, {len(s['combo'])} combination skills, "
          f"{len(d['glossary'])} glossary rows -> {paths.show(out)} ({size // 1024} KB)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
