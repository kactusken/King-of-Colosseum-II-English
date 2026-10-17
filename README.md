# King of Colosseum II — English Translation

An English translation patch for **King of Colosseum II**, the PlayStation 2 pro wrestling game
released only in Japan.

It covers all of the game's text: the menus and options, the roster and wrestler data, move names,
the Dojo tutorial, Match Maker, Survival Road, the Secret Shop, Edit Mode, results, and the menu
graphics. That comes to 16,997 text entries and 292 pictures. English is drawn with the game's own
proportional font, so it reads like normal text and fits the original windows.

> **Status: first public beta.** Everything is translated, but not every mode has been played
> through in English yet. The Dojo dialogue and lessons and the Match Maker briefings and verdicts
> in particular haven't been checked on screen. You may find text that runs out of its box, a name
> that doesn't fit, or a line that reads oddly. Please report anything like that
> ([how to report](#reporting-problems)). [CHANGELOG.md](CHANGELOG.md) lists what's in each
> release.

## Downloads

Get the latest zip from the [Releases](../../releases) page. It contains three patches. Pick one:

| Patch | What you get |
|---|---|
| **King of Colosseum II (English)** | The translation, with the game otherwise unchanged. Wrestlers, rings and shop items unlock as you play, as in the original. |
| **King of Colosseum II (English) (All Unlocked)** | The translation with everything unlocked from the start: every wrestler and costume, every ring, every Secret Shop item. It also unlocks content the game itself never gives you: hidden wrestlers and the cut Pancrase parts, rings and options. |
| **King of Colosseum II (Japan) (All Unlocked)** | The original Japanese game with the same unlocks. |

## How to patch

You need your own copy of the original Japanese disc as an `.iso` image. Disc images are not
provided here.

- Game: *King of Colosseum II* (Japan), serial **SLPM-65602**.
- The `.iso` must match: 4,593,778,688 bytes, CRC32 `fad699da`,
  SHA-1 `f519ef2b98c0340c9ccd876e4988507d49787785`.

Then:

1. Apply the `.xdelta` patch to the `.iso` with an xdelta tool:
   - Delta Patcher is a desktop app for Windows, macOS and Linux.
   - On the command line:
     `xdelta3 -d -s "King of Colosseum II (Japan).iso" "patch.xdelta" "patched.iso"`
   - Browser patchers such as Rom Patcher JS may not cope with a 4.5 GB DVD image.
2. Open the patched `.iso` in your emulator. The patch has been tested in
   [PCSX2](https://pcsx2.net/).

## Notes for players

- **Names.** Real wrestlers, promotions, titles and venues use their own official English
  spellings (given name first). The game's made-up venues get English names (Oedo Kokugikan,
  Rinkai Colosseum).
- **What's still in Japanese.** The title logo, promotion and belt logos, costumes and ring art
  stay as they are, because they're artwork. So do the three movies, the spoken commentary, the
  kana/kanji grids on the name-entry screen (English names use the A-Z grid), the staff credits
  and the save's title on the memory card.
- **Saves.** The patch doesn't change the save format, so memory cards from the Japanese game
  should work. With an "All Unlocked" patch, loading an old save keeps everything unlocked, but
  Survival Road's souls and records are reset to the unlocked values at every load.
- **Hidden content.** The game holds an unlock-everything password, a developers' camera test
  viewer, a cut Pancrase promotion and more. See
  [docs/HIDDEN_CONTENT.md](docs/HIDDEN_CONTENT.md).

## Reporting problems

Open an [issue](../../issues) with:

- a screenshot,
- which patch you used,
- where you were: the mode and menu, or in Dojo or Match Maker, which lesson or show.

Text that is cut off, overlaps, or still shows Japanese is especially helpful. Reports from the
Dojo and Match Maker are the most useful of all, even if everything looked fine.

## For ROM hackers and contributors

Everything needed to rebuild the patches from the original disc is in this repository: the
translated text, the patching code (Python 3, no dependencies for the build) and documentation of
the game's formats.

| Document | What's in it |
|---|---|
| [docs/BUILDING.md](docs/BUILDING.md) | Setting up, building, making patches, and the checking tools |
| [docs/TRANSLATION.md](docs/TRANSLATION.md) | Text file formats, scope, style guide, glossary, and naming decisions |
| [docs/EDITING.md](docs/EDITING.md) | Editing the in-game text graphics |
| [docs/PATCHES.md](docs/PATCHES.md) | How each code patch works: ASCII text, Dojo quotes, unlocks, the camera test viewer |
| [docs/TECHNICAL.md](docs/TECHNICAL.md) | The game's disc layout, archives, compression, fonts, data formats, and memory map |
| [docs/PLATFORM.md](docs/PLATFORM.md) | PS2 pitfalls for this kind of work |
| [docs/HIDDEN_CONTENT.md](docs/HIDDEN_CONTENT.md) | Unlockables, debug features, and unused and cut content |
| [tools/README.md](tools/README.md) | Every tool, what it's for and how to run it |
| [Match Maker Map](https://kactusken.github.io/King-of-Colosseum-II-English/matchmaker-map/) | Every Match Maker campaign: when each briefing, verdict and advice answer plays |
| [Survival Road Map](https://kactusken.github.io/King-of-Colosseum-II-English/survival-road/) | Courses, difficulties, rounds and opponent pools |
| [Secret Shop](https://kactusken.github.io/King-of-Colosseum-II-English/secret-shop/) | Shop items, when they go on sale, and what they unlock |
| [Wrestler Database](https://kactusken.github.io/King-of-Colosseum-II-English/wrestlers/) | Every wrestler and costume with stats and moveset |

Quick start:

```sh
python3 tools/extract.py                 # unpack the disc in rom/ into extracted/
python3 build.py                         # -> build/King of Colosseum II (English).iso
python3 make_patches.py --version v0.1   # -> release/*.xdelta and a zip (needs xdelta3)
```

## Legal

This is a non-commercial fan translation. It contains no copyrighted game data that would let
anyone play without owning the game. The patches only work on your own copy of the disc. King of
Colosseum II and its contents belong to their respective owners. The Japanese text in this
repository is included for translation and reference.

The code in this repository is released under the [MIT License](LICENSE).
