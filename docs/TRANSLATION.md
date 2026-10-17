# Translation

## Where the text is

| File | Holds | Checked by |
|---|---|---|
| `translation/script/*.txt` | *(story/dialogue)* | `tools/lint.py` |
| `translation/text/messages.txt` | system messages, title history, belt names, weight classes (.000 1441) | `tools/lint.py` |
| `translation/text/actions.txt` | Dojo mode categories, lessons, goals, controls (.000 1443) | `tools/lint.py` |
| `translation/text/mmtalk.txt` | Match Maker briefings, verdicts, advice, tips (.000 2853-2884, 2901) | `tools/lint.py`, `tools/mmtalk.py check` |
| `translation/text/teamdata.csv` | Promotions, Elimination teams, title holders, Secret Shop items, notices (.000 2000-2020, 2396-2400, 2829-2836) | `tools/lint.py`, `tools/teamdata.py verify` |
| `translation/text/mmdata.txt` | Match Maker show names, goals, venues, notes (.000 2805-2812; settings/team sheets follow elf.txt / teamdata automatically) | `tools/lint.py`, `tools/mmdata.py verify` |
| `translation/text/dojo.txt` | Dojo mode trainer dialogue (.000 1455) | `tools/lint.py`, `tools/dojo.py verify` |
| `translation/text/matches.txt` | match types, title matches, leagues, tournaments (.000 1445) | `tools/lint.py` |
| `translation/graphics.csv` | images with text | `tools/check.py` |

Reference pages built from the game's data and the English (rebuild them all with
`python3 tools/pagekit.py` after changing the text they show):
- [matchmaker-map](matchmaker-map/index.html): every Match Maker campaign - when each briefing,
  verdict and advice answer plays, with the English and the Japanese (`tools/mmmap.py`);
- [survival-road](survival-road/index.html): courses, difficulties, rounds and opponent pools
  (`tools/survivalmap.py`);
- [secret-shop](secret-shop/index.html): shop items, when they go on sale, what they unlock,
  souls (`tools/shopmap.py`);
- [wrestlers](wrestlers/index.html): every wrestler and costume with stats and moveset
  (`tools/rosterdb.py`).

## File formats

Message blocks: `@ id`, source lines (`JP `), translation lines (`EN `); no `EN` lines = original
kept. A file's header says what it holds and its limits (`# limit lines=3 chars=28` is checked by
lint). Tables: original columns beside English ones (`japanese`/`english`, or `X`/`en_X`). See
`tools/blocks.py` and `tools/textdb.py`.

Control codes: `%d` (a number filled in by the game) - keep each one. New lines are the block's
lines; a final empty line is a trailing new line and must match the original's.

How English is stored: letters, digits and punctuation as full-width Shift-JIS (2 bytes each; the
game measures each glyph, so it still looks like a normal proportional font), spaces and new lines
as 1 byte - except in strings of several lines, where spaces are full-width too: the game's line
splitting for multi-line dialogs breaks on single-byte spaces (*verified in game*, message 551). `'` becomes ’ and `"` alternates “ / ” (the font has no full-width ASCII quotes). △ ○ × □ are
drawn as the PS button icons - use them for buttons ("Direction + △"). Check how a line
will look with `python3 tools/font.py preview out.png "text"`.

## Style guide

- Names: real people, promotions, titles and events use their own official English spellings
  (given name first: Kyohei Wada); the game's parody venues are romanized with English generic
  words (Oedo Kokugikan, Rinkai Colosseum). Terms in `translation/glossary.csv` are used as given.
- Executable strings (`translation/text/elf.txt`) have fixed slots; where a full name doesn't fit
  it is shortened, never respelled: Rinkai, Kawashima / Stadium, Regional, Butokan (All Japan),
  K. Yamamoto, S. Hashimoto, S. Nishinaga, N. Hinowa, Momota. Strings already in English
  (ＮＯ ＤＡＴＡ, ＳＵＰＥＲ ＨＡＲＤ, Ｒ１), number formats and symbols are left as they are.
- Menu items, labels and titles: Title Case, short (they must fit the Japanese slot - see the
  render notes). Help lines and messages: sentence case, plain and direct ("Set the time limit",
  "Choose the referee"); questions end with "?", statements without a full stop unless there are
  several sentences.
- Buttons: ○ / × / △ / □ / L1 / R1 stay as symbols; "○ OK", "× Back".
- Wrestling terms: established English (Rope Break, Ring-out Count, Lumberjack); Japanese
  wrestling words only where they are the established name (Muga, Tenkaichi).
- Numbers as digits; "1st/2nd" for order; "vs." with a full stop.

## Images with text (`translation/graphics.csv`)

All 10,254 pictures of KC2FIRE.000 are catalogued (2026-10-15): 336 have text to translate (299 to
draw + 37 exact duplicates that follow them, `dup_of`), the rest are `keep` (logos, portraits,
art, textures, pictures already in English, the copyright notice - not transcribed). In the
`japanese` column ` | ` separates labels (reading order: top to bottom, left column first) and
` / ` (with spaces) is a line break; a `/` without spaces is a real slash in the picture.
Transcriptions were made from zoomed pictures; half-/full-width forms are best effort.

## Hand edits (`translation/hand/`)

Pictures whose lettering is part of the artwork (banners, stamps, icons, button bars) are edited
by small Pillow scripts in `translation/hand/<image>.py` (shared styles in bannerlib.py,
ui_common.py, caption.py). `.venv/bin/python tools/hand.py [image ...]` runs them and approves
the results (snapped to the palette, frozen in images-approved/). Pictures that only needed
hand-made boxes or splits stay with the automatic renderer (their rows in graphics.csv).

## Glossary

`translation/glossary.csv` (`japanese, english, notes`): lint warns when a source line contains a
term and the English doesn't use its translation (several accepted forms: `A | B`). Prefer
established community names (existing English guides) over new coinages.

## Scope (decided 2026-10-15)

The goal is a game a native English speaker can play easily, not an English re-skin: menus and
text windows get English, the original art stays as designed.

**Translated:** everything shown as text on screen - menus, options, help and descriptions, move
names, wrestler data and nicknames, results, Dojo mode dialogue, interviews - and images that are
menu labels or text windows.

**Stays as it is:**
- All game art that isn't a menu or text window: the title logo, promotion and belt logos,
  costumes, ring art.
- The three movies (SFD): no subtitles, no re-encoding.
- Audio, including the spoken commentary.
- The kana/kanji name-entry keyboards; English names use the existing full-width A-Z keyboard.
  Exception: the keyboard's character-set buttons 英数字 / 記号 read ABC / !?# (picture 01779).
- The staff credits (KC2FIRE.000 entries 3133/3134).
- The memory card save title (icon.sys, KC2FIRE.000 entry 1432: キングオブコロシアム２).

## Decisions

| Decision | Who / why |
|---|---|
| Scope as above | user, 2026-10-15: playable for English speakers without altering the original art |
| Real wrestler, promotion and venue names: each one's own official English spelling (Jushin Thunder Liger, Pro Wrestling NOAH); the game's parody venues get English renderings | user, 2026-10-15 |
| Debug screens in images (000_02033-02040: match-state readout, commentary categories) stay Japanese until the hidden-content pass after the translation | user, 2026-10-15 |
| Image lettering: Barlow Condensed (SIL OFL, in tools/fonts/) - Bold for menu labels, ExtraBold Italic for the slanted name plates; one text size per picture and the same size wherever the Japanese was the same size, squeezed (to 75 %) before shrinking | user, 2026-10-15: consistent label size across screens |
| Venue names stay faithful to the game, including the dome venue named after the publisher (romanized as in the game, not neutralised) | user, 2026-10-15 |
| 済 stamps read DONE; move-slot icons 必/得1-4/声1-2 read F / S1-S4 / V1-V2; new names on the show plates use Barlow Condensed (not the plates' serif); where a number gap leaves no room, "No. [N]" / "Rd. [N]" (no code patch) | user, 2026-10-15 |
| Kept as drawn: the bronze 予選 / 決勝！ titles on the intro screens (painted over art), the 18 px 魂 icon; counters 人/回 dropped so numbers stand alone | defaults, accepted by the user 2026-10-15 |
| Staff credits stay Japanese | user, 2026-10-15 |
| Memory card save title (icon.sys, entry 1432) stays Japanese | user, 2026-10-16 |
| Name entry: the character-set buttons 英数字 -> "ABC", 記号 -> "!?#"; the rest of the keyboard stays as drawn | user, 2026-10-16 |
| Full names stay in the game's order (Japanese wrestlers surname first: "Chono Masahiro"); no code patch | user, 2026-10-15 |
| サル・ザ・マン is "Saru the Man" (an alias of the wrestler later known as Crazy Monkey; サル kept as Saru, not "Sal" or "Monkey") | user, 2026-10-15 |
| Next to lettering the game already drew in English, the new labels copy that lettering: pause menu 02074 in its own 9-pixel monospaced letters (missing ones drawn to match; names initialled to fit 13 cells: Y. Tsuji / K. Yamazaki / M. Momota), mode menu 02423 in heavy capitals (Barlow Condensed Black) like SINGLE / TAG; units in the digit strip 01516 in the game font: 分 -> min, 点 -> PT | user, 2026-10-15 ("sounds good"); details by Claude |
| Promotion-list menus (images 01535, 03001, 03010): ZERO-ONE and WJ redrawn in the menu font like the others, WJ spelled out as "World Japan"; labels of a list share one size | user, 2026-10-15 |
| Vulgarity and crude jokes are translated as strong as the Japanese, not censored or softened (Chono's ファックオフ = "Fuck off!") | user, 2026-10-15: match the game's intention |
| Move names: established English wrestling terms, checked against the 2004 GameFAQs move guide and Fire Pro usage; literal only where nothing established exists | user, 2026-10-15 |
| Roster surnames must fit the wrestler-list name canvas (wider ones wrap and shift the list): 柳澤 = "Yanagi", テングカイザー = "Kaiser", ハイスパート (Edit template) = "HighSpurt", 小笠原 = "Ogasa" | user, 2026-10-16 |
| Releases: English (no unlocks); English (All Unlocked) and Japan (All Unlocked) with `--unlocks all`, which includes the content the game never unlocks (Spike Tomoki, Trainees, Mystery 1-3, the cut Pancrase parts and options, WAR ring) | user, 2026-10-16 |
| The joke wrestler keeps his in-game name (スパイク = Spike); the release README and variant descriptions never mention it | user, 2026-10-16 |
| Picture naming made consistent: 人気 Popularity, 階級 Weight Class, 所持魂数 / 獲得魂 Souls Held / Souls Earned, 隠し装備 Hidden Moves, カット攻撃 Cut Attack, 上書き先のレスラー the replaced wrestler, 必殺 Finisher, ファン層 Crowd (最大動員数 Max. Attendance), セコンド Seconds, 腕力 Strength; squeezed banners shortened: Jr. Heavyweight Champion Carnival, GHC Jr. Heavyweight Tournament, WJ Strongest Tournament (lists keep the full names); King of Pancrase belts as KOP ... in pictures | user, 2026-10-16 |

## What stays untranslated

See *Scope* above: logos, costumes and other non-menu art, the movies, audio, and the name-entry
keyboards. Mark such images `keep` in `graphics.csv`.
