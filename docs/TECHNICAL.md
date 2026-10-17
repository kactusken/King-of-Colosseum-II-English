# Technical notes - King of Colosseum II

**Conventions:** numbers in hex with `0x`; addresses are RAM addresses unless marked as file
offsets; `u16`/`u32` little-endian unless marked BE. Findings are marked *verified in game* or
*from the code*.

## Contents
- [Image](#image) · [Disc layout](#disc-layout) · [Executable and memory](#executable-and-memory)
- [Archives and compression](#archives-and-compression) · [Text](#text) · [Images](#images)
- [Open questions](#open-questions)

## Image
`King of Colosseum II (Japan).iso`, 4593778688 bytes, SHA-1 `f519ef2b98c0340c9ccd876e4988507d49787785`.

## Disc layout
| LBA | Size | File | Contents |
|---|---|---|---|
| 284 | 57 | `/SYSTEM.CNF` |  |
| 285 | 3048408 | `/SLPM_656.02` |  |
| 1774 | 393216 | `/MODULES/MODULES.BIN` |  |
| 1966 | 275345 | `/MODULES/IOPRP300.IMG` |  |
| 2101 | 1073741824 | `/DATA/HELLO.FOR` | zero padding |
| 526389 | 1073741824 | `/DATA/GOOD.BYE` | zero padding |
| 1050677 | 52 | `/DATA/KC2FIRE.DIR` |  |
| 1050678 | 1874507776 | `/DATA/KC2FIRE.AFS` |  |
| 1965965 | 244441088 | `/DATA/KC2FIRE.000` |  |
| 2085321 | 239804416 | `/DATA/KC2FIRE.001` |  |
| 2202413 | 48629760 | `/DATA/KC2FIRE.MVS` |  |
| 2226158 | 34603008 | `/DATA/LAST.DAY` | zero padding |

Single-layer DVD, 2,243,056 sectors (DVD-5 holds 2,295,104: about 100 MB of room to grow at the
end). ISO9660 + UDF 1.02 bridge; UDF partition starts at sector 264. The mastering tool stored
every file in one UDF extent, so files over 1 GB have lengths that overflow the 30-bit field
(`tools/disc.py` keeps that layout). `HELLO.FOR`, `GOOD.BYE` and `LAST.DAY` are all zeros: padding
that pushes the data towards the outer edge of the disc. *From the data.*

`SYSTEM.CNF`: `BOOT2 = cdrom0:\SLPM_656.02;1`, `VER = 1.03`, `VMODE = NTSC`.
`KC2FIRE.DIR` (52 bytes) lists `kc2fire.afs`, `kc2fire.mvs`, `kc2fire.000`, `kc2fire.001`.

## Executable and memory
`SLPM_656.02`: ELF, entry `0x00100008`. Segments: `0x00100000-0x00323d28` (file `0x1000`) and
`0x00323d80-0x00426a70` (file `0x224d80`, BSS from `0x003e5acf`). *From the data* (`tools/elf.py info`).

## Archives and compression
Four data files, all read by index (no file names in the game's lookups). Unpacked by
`tools/extract.py` into `extracted/DATA/KC2FIRE_AFS/`, `KC2FIRE_000/`, `KC2FIRE_001/`, `KC2FIRE_MVS/`.
Every reader has a writer, and `tools/check.py` proves each round trip byte-identical. *From the data.*

| File | Format | Entries | Contents |
|---|---|---|---|
| `KC2FIRE.AFS` | CRI AFS | 9,003 | 9,000 ADX audio clips (commentary, calls, music), 3 SFD movies (`KachinukiOP.sfd` ...) |
| `KC2FIRE.000` | the game's pack | 7,519 | 3,282 TIM2 images, 759 sound banks (`IECS`), text/script files, model and other data |
| `KC2FIRE.001` | the game's pack | 16,017 | 4,641 TIM2 images and binary data (wrestler models/textures?) |
| `KC2FIRE.MVS` | the game's pack | 16,660 | all uncompressed; probably motion data (records start `?? ?? 00 02`) - not text |

`KC2FIRE.DIR` (text, CRLF) only lists the four file names; the ELF names them too
(`kc2fire.afs` ...) and opens them through `cdrom0:`.

### KC2FIRE.AFS (`tools/afs.py`)
Standard CRI AFS: `"AFS\0"`, u32 count, count x (u32 offset, u32 size), then the name table's
(offset, size). Entries in index order, each at the next 0x800 boundary, zero between; first entry
at 0x12000. The header padding (0x11970-0x12000) holds 1,567 bytes of leftover buffer contents
(they look like ADX data) - kept verbatim. Name table after the last entry: 0x30 per entry = name
(0x20), six u16 date fields (2003-12-17 ... 2004-05-10), and a u32 that the mastering tool filled
with header word k+1 instead of the size (a known CRI tool quirk; `afs.py` reproduces it). Names
repeat (345 duplicates), so unpacked files are `NNNN_<name>`. Nothing in it is text; only the
three movies could carry burnt-in Japanese.

### KC2FIRE.000 / .001 / .MVS (`tools/pak.py`)
No magic. u32 0x800, u32 count N, N x 16 bytes (u32 offset, u32 stored size, u32 size, u32 flags);
the table is zero-padded to the next 0x800 boundary, which is the base the offsets count from.
Entries are contiguous in index order, 0x80-aligned, zero-padded. *From the data* unless noted.

- **flags low u16 = group size**, not a type: the loader (0x28b178 -> 0x28aff8) reads that many
  consecutive entries with one read from the first entry's offset, allocating the sum of their
  stored sizes (or unpacked sizes, for compressed entries). *From the code.*
- **Every group starts on a sector and spans whole sectors** (23,082 of 23,082); the last entry's
  stored size carries the padding. The game reads groups in whole sectors into a buffer of that
  size: a test build that shrank three stored sizes to 0x80 multiples **crashed at boot** (the crash
  is *verified in game*; this as its cause is *from the code* until the fixed build boots -
  1441/1442 load at start-up with the font). `pak.layout_errors()` checks
  every rebuilt pack and `build.py` refuses to write one that breaks these rules.
- flags bit 16 = compressed; `size` is then the unpacked size. Entry 0 of `.MVS` has flags 0x0c96
  and one other 0x13f4 - kept as is.

Compression is LZSS, decoded by the game at 0x28a338: flag byte, low bit first, 1 = literal,
0 = two bytes `a b` copying `(b >> 4) + 2` bytes (2-17) from ring position `a | (b & 0x0f) << 8`;
4 KB ring, zero-filled, **written from position 1** (output byte i at position (i + 1) & 0xfff).
Position 0 is therefore never written, and **a copy from it is the end marker**: every original
stream ends with one (20,182 of 20,182). In about half the entries the marker comes before `size`
bytes (size = length rounded up to 0x80) and the rest is zero. *From the code*; `pak.py` matches
the routine on every sampled entry. (A first decoder that wrote from position 0 got sizes and
leading literals right but every copy one byte off - only visible in the TIM2 headers of
compressed images. The text and font entries are uncompressed, so nothing tested in game was
affected.)

Repacking keeps unchanged groups byte for byte; a group with a changed entry is rewritten
contiguously, in its old place if it fits, otherwise after the last group.

### String pools (`tools/pools.py`)
Three pairs of entries: a pool of strings and, in the next entry, a u32 offset per string. The
pool holds the strings in table order, NUL-terminated and padded to an even length, empty strings
included (507 of 576 in 1445 are empty). Writing it back the same way gives the original bytes.
Since every string is reached through the table, English can be any length. *From the data.*
Half-width digits occur in 1443 (`ステップ4`), which the renderer would skip - so either those
lines are drawn another way or never shown (*open*).

### Indexed string tables (`tools/tables.py`)
2008 (moves), 2010 (wrestler names, costume parts, themes), 2011 (second move list): u32 A, u32 N,
u32 S, u32 0; A group records (8 bytes, untouched); N item records of R bytes (12 / 32 / 4), each
starting with the u32 offset of its string; then the pool of S bytes - every string NUL-terminated,
in order, including one or two no record points at. Rebuilding the pool and rewriting the offsets
reproduces all three byte for byte. *From the data.* All three entries are stored uncompressed,
like every entry changed so far - pak.compress() is proven by round trips but *not yet in game*.

### Roster data (entries 1999, 2002, 2004, 2016, 2018, 2019)
Six copies of the wrestler roster. The real layout (*from the code*, loader 0x1164d0 -> 0x114920;
details under "Wrestler data" below) is index records + packed variant blocks; tools/records.py
reads it as fixed records of 0x23b4 bytes (four variant blocks), which works because the blocks
are contiguous.
Text fields at the record start: surname 15 bytes (+0x00), given name 21 (+0x0f), nickname 33
(+0x24), special move from +0x45; NUL-padded Shift-JIS. *From the data.* The wrestler select
screen (list, NICK NAME, NAME, SPECIAL MOVES) reads these, not table 2010 (*verified in game*:
names stayed Japanese with 2010 in English). Full-width English is too long for these fields
(surname 7 letters) - so they're written as ASCII, which the renderer patch draws (docs/PATCHES.md;
*verified in game*). **Wrestler-list width** (*verified in game*, 2026-10-16): each list name is drawn into a text
canvas about 128 px wide (field +0x14 of the text object, set by 0x10c248); the draw routine
0x10c938 starts a new line when a glyph would end at or past it, which pushes every later name in
the list down a row. Surnames must stay under 128 px (tools/font.py widths): "Tengu Kais|er" and
"Yanagisaw|a" did this. A name of exactly 128 px wraps too (Ogasawara, *verified in game*): at most 127; tools/lint.py checks it. The shortened names (Yanagi, Kaiser, Ogasa) *verified in game*. Variant blocks: each record holds four (Type 1-4) 0x8ed apart. A foreign
wrestler's NAME is surname + messages block 516 (・ in Japanese, a space in English) + given name.

### Edit-mode templates (entry 2005)
The wrestler types and sample wrestlers Edit loads into a wrestler: 157 blocks of 0x8ed bytes from
0x26d4 (header u32 155, 157), each laid out like one roster variant (surname / given / nickname /
special move); the last block is 4 bytes short, its text fields whole. tools/records.py writes it
with the roster translations (SINGLES). *From the data.*

### Save title (entry 1432)
icon.sys for the memory card: title キングオブコロシアム２ at +0xc0. Kept (user decision).

### Fixed-record text tables (entries 1448, 1450-1454)
Arrays of fixed records filling the whole entry, NUL-padded Shift-JIS fields at fixed offsets
(`tools/records.py`, English as ASCII like the roster, full-width when it holds symbols). *From the data* (field sizes = the longest
string plus padding up to the first number in any record):
- 1448 appearance categories (Stance, Build, costume parts): 32-byte records, name 28 bytes;
- 1450 move slots ("pgEquipData", 0x169818: Homing Dash, Tie-Up □ ...): 36-byte records, name 28,
  then u16 slot, button, category (0-34, labels 000_01682) and 2008 move group. Button codes as the
  Edit Mode move screen draws them (*verified in game*, 2026-10-16): 0-3 □ × ○ △, 6 □×, 7 △○,
  8/9/10/14 D-pad + □ / × / ○ / □×, 16-22 R1 + □ × ○ △ □× △○ □×, 24 R1, 25 R2, 26 R2 + D-pad,
  27-30 right stick up / left / right / down, 999 none; 6, 7, 14 and 22 also show the red 魂 (Soul
  move) icon;
- 1451 CPU logic actions (Keep Distance, Use a Strike ...): 48-byte records, name 32;
- 1452 wrestler types and edit samples: 128-byte records, name 40 + help line 84;
- 1453 voices (shout + wrestler): 48-byte records, name 44;
- 1454 theme music: 48-byte records, name 44.
The CPU Logic edit screen draws 1450/1451 (*verified in game*: Japanese there while everything
else was English; English after this step). Voices are romanized shouts with the wrestler's name.
Other entries with font text not translated yet (from a scan for kana): 2000-2020 team names, 2380, 2396-2400 (unlockables,
Survival Road notes), 2403-2422 (Survival Road course settings) / 2813-2844 (Match Maker show settings), 2805-2811 show goals,
2829-2836 title names, 2853-2884 + 2901 Match Maker dialogue and tips, 3133/3134 staff credits
(kept, user decision), 1455 (Dojo) is done, below.

### Dojo dialogue (entry 1455, `tools/dojo.py`)
1495 records of 0x58 bytes: text (84 bytes, NUL-padded Shift-JIS), u16 marker at +0x54 (1 = line,
0x63 = end of page, 0x270f = end of a section), u16 speaker at +0x56 (0 Yamamoto, 1 Hoshino). A
page is up to three line records and a marker record; the screen (0x17ad90) walks the records by
index, so English keeps every record in place (an empty line record is skipped). Each line is cut
into segments by 0x191290, which steps two bytes at a time looking for 「…」 (drawn yellow,
brackets included) and ○△□× / Ｒ１Ｒ２Ｌ１Ｌ２ (button icons), and the page is appended into one
multi-line text object ("%s\n" through 0x1982b8). English is therefore stored fully full-width,
spaces included: at most 41 characters (82 bytes) and 636 px a line. *From the code*; not yet
verified in game.

### Match Maker dialogue (`tools/mmtalk.py`)
Entries 2853-2860 (briefings), 2861-2876 (verdicts after a show, 6 per show from best to worst),
2877-2884 (advice) and 2901 (loading tips), one per promotion slot (New Japan, New Japan, NOAH,
All Japan, ZERO-ONE, WJ, Pancrase, New Japan). They are Shift-JIS text files parsed at run time
(0x1d5600, 0x1d58c4, 0x1df5a0, 0x1b27ac). Items are "quoted strings" or unquoted lines (headers;
`なし` = no answer, compared by the code). In a string, `↓` ends a page, （笑）（怒）（気） set the
page's expression, （藤波）/（井上） make it the second speaker's, and any other （…） is skipped. A
page is copied into a 0xC0 buffer with no terminator (at most 191 bytes); 16 pages per briefing,
8 per verdict. The draw routine 0x1cdf20 splits lines on CR LF, draws `<…>` in yellow and ○×△□
as button icons. Text goes through 0x1b1410, which converts half-width letters, digits and
`+-*/,.':;()` to full-width itself, so English is stored as ASCII, other punctuation full-width.
Tips use 128-byte buffers. *From the code*; English not yet verified in game.

### Match Maker campaign flow (*from the code*, 2026-10-16; `tools/mmmap.py`)
New Japan is slot 1 (guest table 0x3aef10 is indexed slot-1; the Free Show check 0x1ce830 tests
slots 1-5); each entry kind is read as base + slot, so slot 0's copies are unused. Driver 0x1cd190;
state at [gp-0x56d0]: +0 slot, +1 show (1-based), +3 result (0 passed, 1 failed, 2 campaign over),
+4 started by Continue. Show records at [gp-0x5678] (0x228 bytes): +0x220 capacity, +0x222
attendance goal, +0x224 bouts, +0x226 rating goal. Five shows for New Japan, NOAH, All Japan and
ZERO-ONE, four for WJ and Pancrase (*from the data*).
- Office 0x1d4f70 (jump table 0x3ae8b0): Start Show (only with every bout set, 0x1d1000), Match
  Cards, Show Info, Wrestler Info, Title Info, Past Shows (from show 2), Rankings, Quit; Advice
  is handled inside the office.
- After a show (0x1cd6b0): failed if attendance < goal or the (int) average match rating < goal.
  The verdict screen 0x1df1c8 always follows. Failed: briefing item 6, GAME OVER (0x1b2568, shared
  with Survival Road), company select. Passed the last show: item 7, the clear sequence 0x1bb1e0,
  cleared flag 0x3669d4[slot] (all of slots 1-5: the Free Show notice 0x1e7778). Otherwise the
  next show; the last show is a bonus show, played only if every earlier show scored 85 or more,
  else the campaign ends after the one before. No replays, no other branches.
- Score (0x1d0e20) = (attendance / capacity x 100 + rating) / 2; grade (0x1df978) S >= 95,
  A >= 85, B >= 70, C >= 50, D >= 30, else E. Verdict (0x1df324): item (show-1)x6 + grade of
  2861+slot when both goals were met, 2869+slot when one was missed.
- Briefings 2853+slot (0x1d5f34, 0x1d6fd0), item numbers counting every item: 0 before show 1's
  briefing, k for show k, 6 after a failed show, 7 at the end, k+6 after show k's briefing (k =
  2-4) when show k-1 scored 85+ (0x1d4b50; skipped if the item is なし). 0x1d1868 adds that
  show's guest wrestlers under the same condition. Pancrase's announcements are one show early
  (items 8/9 name Liger and Hinowa, whom the code adds at shows 3/4).
- Advice 2877+slot with the index 2885+slot (parsers 0x1d58c4, 0x1d5d60; use 0x1d6720): four
  blocks (prompt, Matchmaking, Match Rating, Other), each a header line then items, なし counting.
  The index has per topic one line per show listing item numbers in the topic block; each ask
  takes the next number, wrapping, and the counters reset when the office is entered (0x1d52d0).
  The prompt is block 0 item 1, or item 2 (the second speaker) at New Japan's and NOAH's show 5
  (0x1d4d10). 2885-2892 have no text to translate.
- Free Show (slot 7): venue, cards, show; no office, briefing or verdict, so 2860/2868/2876/2884
  are unused.
Not traced: the attendance formula, the clear sequence's content, the Continue byte 0x352aad +
slot x 0x2604, the Free Show's result screens.

### Wrestler data (*from the code*, 2026-10-16; `tools/rosterdb.py`)
- **WrestlerData** 1999 (= 2016): u32 255 wrestlers, u32 541 blocks, 8 zero bytes, 255 index
  records of 64 bytes, then 541 packed variant blocks of 0x8ed bytes. 2002/2018 (Match Maker, 0x1cccf8:
  310 / 598) and 2004/2019 (Survival Road, 0x1bbb60: 410 / 698) add the 155 Edit templates and
  100 empty Edit slots; their real wrestlers' blocks are byte-identical to 1999 (*from the data*).
  Records 0-154 are wrestlers (147 Spike Tomoki, 151-154 the Trainees); 155-254 are empty.
- **Index record**: +0 id, +2 four u16 block numbers (Type 1-4), +0xa variant count, +0xb promotion
  (2000), +0xc order in the promotion, +0xf weight class (0 Junior, 1 Openweight, 2 Heavy, 3 Super
  Heavy; shown through 0x3a9fe0 as messages 60-63), +0x10 unlock flag.
- **Variant block**: unpacked by 0x1149c0 (repacked by 0x115188) into a 0xa6a-byte struct:
  +8 surname 15, +0x17 given name 21, +0x2c nickname 33, +0x4d special move 49 bytes; +0x7e name
  separator (full-width space / none / ・ / ＝), +0x7f given name first (0x116940); profile
  (0x154820, drawn by 0x153b98): +0x80 nationality (messages 135+), +0x81 build (64+), +0x84 height
  cm, +0x82 weight kg, +0x85-0x87 birthday (year-1900, 0x79 unknown), +0x88-0x8a fight style and the
  two reversal types (messages 69 + table 0x3a9ff0), +0x90/+0x92 voices (1453 id at +0x2c), +0x8b
  colour (109+), +0x8c popularity (132+2-v); skills (0x15ee10): +0x94 soul buttons, +0x95 critical
  type, +0x96-0x9b recovery / breathing / spirit (and bleeding), +0x9c-0x9f neck / arm / waist / leg
  durability (0 strong, 1 average, 2 weak, 3 injured - Chono's neck, *from the data*), +0xa0 move
  speed, +0xa1 turnbuckles, +0xa3-0xa5 match skills, +0xa6 mode skill; +0xa8 eleven offense and
  +0xb3 eleven defense values 1-10 (labels 000_01677); +0xc0-0x12e appearance, 25 items keyed by
  table 2010 (+4 key per group; load 0x15a530); +0x130 285 move slots (u16: index in the slot's
  2008 group, 0x163670; clutch categories 5-16 take the group from the Clutch Setting, 0x163580);
  packed +0x2c3 five u16 slot+1 for finisher and signatures 1-4; +0x36e 1,786 seven-bit CPU logic
  weights (not mapped). Not decoded: +0x8d (model/face id), +0x8e, +0x8f, +0xa2, the colour bytes.
  Label directions for recovery/breathing/spirit, move speed and turnbuckles are inferred.
- **2009** ("PilonData", 0x119028): the Match Maker rosters, 7 groups (campaign slots 1-7) of
  8-byte records: +0 wrestler, +2 promotion, +3 unit/logo, +4 class, +5 a 0-100 value the show code
  reads (0x1cf438; probably popularity), +6 bits that look like "on the roster for show k+1".
- **Match Maker titles** 2829+slot: 9 lines a title (name, three holder lines, five ○/× show
  flags, parser 0x1d2b00); rand() % 3 (0x1d2f4c) picks the holder line when a campaign starts.
- **2001** Elimination teams: members are five u16 wrestler ids at +0x24.

### Survival Road (*from the code*, 2026-10-16; `tools/survivalmap.py`)
- Run state: a 0x55ac-byte heap copy at [gp-0x5728] (driver 0x1bbf28; 0x1bea18 saves the lasting
  fields to 0x334fe0): +1 type (1 singles, 2 singles with a second, 3 tag), +2 course 1-8,
  +3 difficulty 1-5, +4 souls, +8 title 1-8, +0xd the last 10 ratings, +0x18 best cleared
  difficulty per course, +0x24 stage, +0x25 round, +0x27 wins, +0x28 wins needed, +0x29 continues,
  +0x53aa 512 "already met" flags, +0x55ac shop row states.
- Loaded per run (0x1beb00, 0x1beec8): 2400 course list, grid 2401 (singles) / 2402 (tag),
  qualifier sheets 2404-2411 / 2413-2420 (0x963 / 0x96c + course; 2403 and 2412 are unused copies),
  finals sheets 2421 / 2422, opponent tables 2012 / 2013 ("lpSurvivalTeam", 512 slots: two s32
  wrestler ids - singles wrestler + second, tag partners -, course at +0x1000, class 2-5 at
  +0x1800, title limit at +0x2000; courses 2 and 3 are swapped on load, 0x1bef30).
- Courses (0x1c2ed0): 1-5 open, 6 Pancrase always skipped (0x1c2f94), 7 Fighters (singles only,
  0x1c2f80) and 8 Superstars shown only once their shop items are bought (found by name).
- Difficulty: qualifier rounds / wins needed and finals 0x1bc1c4 (jump table 0x3ae290), 0x1bcbb0;
  continues 0x1c3898 (+1 / +2 for titles 7 / 8, not on Easy, 0x1c3de8); CPU levels 0x3ae0c0 /
  0x3ae150; critical rate 0x1bc484 / 0x1bc60c; SUPER HARD and MASTER shown only when bought (0x1c3a8c).
- Opponent draw (0x1bc260, 0x1befd8): from entries not yet met and without the player's wrestlers;
  qualifiers: the run's course, a class the grid cell (course, round, difficulty) allows; finals:
  class A from any course; a title limit v keeps an entry out unless the title is 1..v. rand() %
  count, then every entry with that wrestler is marked met. No fixed bosses.
- After a match (0x1bc930-0x1bcaa8): souls = table 0x3ae1e0[difficulty][grade] + title bonus
  (0x3ae2b0), won or lost, capped at 9,999; grade 0x1be0e0 (S 100, A 80+, B 60+, C 40+, D);
  title 0x1be168 from the last 10. GAME OVER (0x1b2568) when wins + matches left < wins needed
  (0x1bcb08); Easy ends after 3 with notice 2398; a continue replays the same match. Clearing
  the finals: ending 0x1bbc70, credits 0x1bb1e0, best cleared difficulty raised (0x1bcc4c).
- Not traced: the match-rating formula, the sheets' ○/× flags, what Save & Quit keeps.

### Secret Shop and unlocks (*from the code*, 2026-10-16; `tools/shopmap.py`)
docs/HIDDEN_CONTENT.md "How unlocking works" has the flags and the shop's state. Further:
- 2396 columns (parser 0x1bf340): flag id, name, category (prefix of 2397), price, description,
  course (prefix of 2400), number of courses, difficulty (0x3ae3f0), preview picture (2475+n).
- On sale (0x1bfaf8, on entering the shop): a row with a course needs that course cleared at the
  row's difficulty or harder; without one, that many courses. A course counts after its finals
  (0x1bcc4c); every row asks Normal or harder, so Easy never counts.
- Rows found by name, not flag: the two courses (0x3ae460 / 0x3ae470), SUPER HARD / MASTER
  (0x3ae4a8 / 0x3ae4c0) and the Edit Points +50 rows (0x3ae5f0, strcmp in 0x1c9390). Their
  English must equal elf.txt's; tools/teamdata.py checks it (the Edit points key was "Edit P+50"
  against "Edit Points +50" in the shop until 2026-10-16, so those rows did nothing).
- Unlock flags are written only by 0x100c40 (unlock-all), 0x116690 / 0x11a5d0 (start-up), 0x17a850
  (Dojo), 0x18a640 (password) and the shop. Match Maker sets none (the Free Show is 0x1ce830).

### Team data and text sheets (`tools/teamdata.py`)
2000/2017 and 2003/2020 (promotions, 40-byte records, name 36) and 2001 (Elimination teams,
48-byte records, name 31) are u32 count + 12 zero bytes + fixed records. 2396/2397/2400 (Secret
Shop items, categories, promotion/course list), 2829-2836 (title holders per promotion) and
2398/2399 (notices) are Shift-JIS tab/CRLF text files that the game parses on load. Many cells
are keys the code compares as strings: the shop's category/promotion/difficulty (prefix strncmp
against 2397, 2400 and the executable's difficulty names at 0x3ae3f0), title holders (strstr in
the wrestlers' full names, 0x1d2a80 - so a holder is an English name fragment that finds the same
wrestlers), Match Maker promotion names (strcmp against 0x3aec48). Their English must match the
other side; teamdata.py verify and the build step check this. *From the code.* Not translated:
2032 (variant -> wrestler source table), 2049/2050 (motion/move-slot enum names, dev only), 2380
(no load found). The Match Maker sheet parser 0x1b4208 compares cells with the executable's
10分...60分 / 5点... / 普通, which therefore stay Japanese in elf.txt.

### Match Maker data (`tools/mmdata.py`)
2403-2422 (Survival Road's per-course settings - the same sheet format: loaded by the Survival
Road code 0x1beb00 as 0x963 + course for singles and 0x96c + course for tag, after 2400 and the
grids 2401/2402; *from the code*, 2026-10-16), 2813-2820 and 2837-2844 (show settings sheets),
2805-2812 (shows), 2797-2804 (team
lists) and 2829-2836 (title holders) are Shift-JIS text files (CRLF, tab-separated) that the game
parses when Match Maker loads and frees afterwards (*from the code*: loaders 0x1beb48, 0x1ceaf0,
0x1d113c, 0x1d2a4c; parsers 0x1b4208, 0x1cec88, 0x1d1158, 0x1d2b00). Sheet values are never
drawn: they are compared with key strings in the executable (three `strncmp` prefixes, then a
per-setting `strcmp` list, jump table 0x3adc70), so each value is written as the key reads after
elf.txt (a shorter prefix key is followed by a NUL). Show venues are compared with
0x2afa38-0x2afaf0 and cut at "("; show name/goal/notes are copied into 0x80/0x80/0x100-byte slots
and drawn by 0x1b1410, which converts ASCII letters, digits and `+-*/,.":;'()` itself (other
symbols must be full-width; an unknown last byte is dropped). Team lists are `strcmp`ed with the
team tables; title names are searched for Ｕ－３０/Junior/Light Heavy/Middle/Welter/Heavy
(0x1e11b4) to pick eligible holders. The step simulates every comparison on the English and stops
on any difference. **Rule for elf.txt:** its strings in 0x2ae780-0x2afaf0 and 0x2e6160-0x2e6538
are also keys - change them only together with a build (mmdata.py derives the sheets from them).

### Entries 2014/2015, 2029-2031
2014 is the name-entry screen's kana->kanji conversion dictionary: u32 data size, 128 u32
offsets, then ~110,000 NUL-terminated (reading, candidate, class digit) Shift-JIS triples; 2015 is
the single-kanji list (rows of 16 kanji, CRLF). Both are loaded by 0x10b668
("JapaneseList"/"TanJapaneseList") and used only by the name-entry module (0x188918-0x18a628) -
player input, out of scope, must stay unchanged. *From the code.* 2029 (move/action TSV, 3,591
rows x 19 columns: id, motion code, name, parameters), 2030 (one `<clip id>＿<transcript>` line per
KC2FIRE.AFS clip, in AFS order - the script of all commentary/announcer audio) and 2031 (the C
header `#define K06_ADX (0)` ... for the same 9,003 AFS files) are developer source files: no
loader call or data table refers to them. *From the code.* Not translated.

### Original behaviour that looks like a bug
- Options > Sound Option > Music Test: the title (theme names, table 2010 entries 3101-3341) shows
  only its first few letters, a different number each frame, so it flickers. The untouched
  Japanese disc does exactly the same in PCSX2 2.8.2 (*verified in game*, 2026-10-16), and the
  title bytes are identical there, so the translation leaves it alone. The software renderer shows
  the same (*verified in game*), so it is the game's own behaviour, not the emulator's GPU.

### How the build writes text
`build.py` text steps change entries through `files.packs` (decompressed on demand); each changed
pack is rebuilt once with `pak.pack()`: a changed entry stays in its slot if it fits, otherwise it
goes after the last entry. If the pack then outgrows its place on the disc (KC2FIRE.000 has none -
.001 follows it), `disc.py` cuts the room off the end of the zero-padding file `GOOD.BYE` and moves
the pack there (tested on a scratch image; ISO9660 and UDF stay consistent). The game finds the
data files through the file system (no LBAs in the ELF) - *relocation verified in game* (the build that grew .000 by 518 KB boots and loads normally).

## Images
All in `KC2FIRE.000`, one TIM2 per entry (sometimes several pictures): 10,254 pictures, exported
by `tools/gfx.py` to `review/images-original/` (ids `000_NNNNN[_pK]`) and shown on
`review/contact-sheets/`. `.001` (wrestler and ring textures) is not exported - out of scope.
`gfx.py verify` writes every PNG back and gets the original bytes (in `check.py`); the build
imports English PNGs through the same path (tested offline). *From the data.*

| Entries | What |
|---|---|
| ~1456-2300 | UI: title plates (many already English: EXHIBITION MATCH, SELECT ORDER...), dialog boxes drawn as images (1702 save prompt, 1710 retire warning), **text atlases** - one picture holding every label of a screen (1474 shared words incl. 決定/戻る; 1515/1516 the CONFIGURATION labels and values) |
| ~2695-... | wrestler portraits, ring/promotion art - keep |
| ~4250-7000 | multi-picture entries: crowds, 3D textures - keep |

**TIM2 variants.** Image type 10 = 8bpp and 9 = 4bpp, both **swizzled**: the pixels are stored as
the GS holds them after uploading the picture as PSMT8/PSMT4 and reading the memory back as
PSMCT32 rows (w/2 x h/2, resp. w/2 x h/4). `tim2.swizzle_map()` models GS memory with the standard
block/column tables (checked against the well-known PSMT8 formula; 4bpp checked visually and by
write-back). 8bpp CLUTs are in CSM1 order; 4bpp pictures have 32 CLUT entries (type 0x43) with
the 16 colours in entries 0-7 and 16-23. One 8x8 4bpp picture (000_07034) is smaller than a GS
block and isn't decoded. Only 57 pictures are unswizzled (type 5).

**Atlases.** The game draws labels as rectangles cut from an atlas (the `boxes` column in
graphics.csv holds each label's rectangle). *Verified in game* (2026-10-15, test build with 70
rendered pictures - mode-select help, Exhibition Match list and help, CONFIGURATION labels, name
plates): English drawn into the pictures shows correctly; left-aligned list labels may use the
width of their column (Gauntlet Match / Round Robin drawn wider than their Japanese showed in
full), and a list must keep the original's left edge - centring each label in its Japanese-sized
box misaligned the Exhibition list. `render.py` takes alignment from the original (labels sharing
a left edge within 8 px = left-aligned list). Shared-words atlas 000_01474 in English *verified in
game*: ○ OK / × Back hints, START Done, Red/Blue Corner (inset 5 px - English starts flush where
kanji had side bearing); no visible edge where labels were cleared. Second pass (251 pictures: Series, Title Match,
Elimination, Edit Wrestler, Survival Road, Match Maker, banners) *verified in game* with no issues.
Third pass (41 hand edits: banners, stamps, button bars, number-gap messages) *verified in game*:
the game's digits land in the gaps left for them (Wrestler Type _, Of _ bouts, Rd. _, attendance).

Other image formats seen: `PiW` (the font code tables), `PS2D` (1432).

## Prior art (2026-10-15)
- No disc translation patch exists that we could find. A fan site offers an English **texture
  replacement pack for PCSX2** (menus, rings, wrestlers): it doesn't touch the disc, but shows
  how players already translate the menus.
- GameFAQs has 2004 guides (a move list and guide that doubles as the community translation, a
  general FAQ, a Dojo mode FAQ, a Match Maker guide) - the source for established English names.
  Common names: Exhibition Match, Survival Road, Match Maker, Title Match, Series Mode, Edit Mode,
  Dojo, Secret Shop, Survival Points, Edit Points; match types Single, Tag Team, Handicap, Triple
  Threat, Battle Royal, 5-on-5 Elimination.
- An English release of the same developer's Fire Pro Wrestling Returns exists; useful for
  individual move names, but its translators shortened names to fit, so not a ready-made mapping.
- No format documentation or tools for KC2FIRE.000/.001/.MVS, the text or the font; no TCRF page.
  AFS is documented (AFSLib, AFS Packer) and matches what's above.

## Open questions
- Which screens use the dojo font, and which have the proportional flag clear (byte 0x21 of the
  text object; `$t2` at 0x10c76c).
- Entry `type` values in the packs (1 = data, 2 = sound bank `IECS`, 4 = models? ...).
- Do the three SFD movies have burnt-in Japanese?
- Does the game read a pack block's `stored` bytes or decode until `size`? (matters when growing)
