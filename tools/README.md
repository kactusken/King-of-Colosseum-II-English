# Tools

Everything is Python 3 and runs from the project folder or anywhere else; every tool has `--help`
(or prints its usage). Folder locations come from [paths.py](paths.py) and can be moved with the
folder options. `build.py`, `make_patches.py` and everything they import use only the standard
library; the tools marked *Pillow* or *capstone* need `.venv` (`pip install -r requirements.txt`).

Set up from the translation kit (version 433e414). Tools marked *game* are stubs to fill in.

## Used by the build

| Tool | What it does |
|---|---|
| [../build.py](../build.py) | builds the translated image (text steps, code patches, images, write-back) |
| [paths.py](paths.py) | every folder location and the folder options |
| [image.py](image.py) | the output image: fresh copy or fast restore from a journal; checksums |
| [disc.py](disc.py) | reads and writes files in the disc image (PS2) |
| [codepatch.py](codepatch.py) | applies code patch tables, checking the original bytes first |
| [catalog.py](catalog.py) | the image catalogue: which file the build uses, fingerprints, stale renders |
| [gfx.py](gfx.py) | the TIM2 pictures in KC2FIRE.000: export (review/images-original), import, write-back verify |
| [pngio.py](pngio.py) | PNG reading and indexed PNG writing without dependencies |
| [blocks.py](blocks.py), [textdb.py](textdb.py) | message block files; every translatable string as one list |
| [elf.py](elf.py) | the PS2 executable: segments, address ↔ file offset (for code patches) |
| [afs.py](afs.py) | CRI AFS (`KC2FIRE.AFS`): unpack, repack, byte-identical verify |
| [font.py](font.py) | the fonts: CMP1 glyphs (byte pair encoding), code table, the game's width rule, sheets, English previews |
| [pools.py](pools.py) | string pools in KC2FIRE.000 (messages, Dojo lessons, match names): dump to translation/text/, build step |
| [tables.py](tables.py) | indexed string tables in KC2FIRE.000 (moves, wrestlers, move list): dump, build step |
| [elftext.py](elftext.py) | text in the executable, replaced in place (ASCII single-line, full-width multi-line): dump, build step |
| [records.py](records.py) | fixed-record text tables from the kit, configured for this game: the rosters and Edit templates (roster.csv), CPU logic, wrestler types, appearance, voices, theme music (fields.csv): dump, verify, measure, build step |
| [dojo.py](dojo.py) | Dojo mode trainer dialogue (.000 1455, fixed 0x58-byte line records, full-width): dump, build step |
| [mmtalk.py](mmtalk.py) | Match Maker briefings, verdicts, advice, tips (.000 2853-2884, 2901: text files parsed at run time): dump, check, build step |
| [mmdata.py](mmdata.py) | Match Maker shows, setting sheets, team lists (.000 2403-2422, 2797-2844; tab/CRLF sheets whose values are executable keys): dump, verify, build step |
| [teamdata.py](teamdata.py) | promotion/team tables, title holders, Secret Shop list, notices (.000 2000-2020, 2396-2400, 2829-2836; records and tab/CRLF sheets whose cells are keys): dump, verify, build step |
| [textpatch.py](textpatch.py) | code patch: the renderer draws single-byte ASCII; [test_textpatch.py](test_textpatch.py) simulates it |
| [unlockpatch.py](unlockpatch.py) | code patches: group `all` (the game's own unlock-all routine at boot and after a save load, plus the content the game never unlocks: flags, cut options, Mystery faces, Edit part body types) and the developer group `debugview` (the camera test viewer) |
| [pak.py](pak.py) | the game's packs (`KC2FIRE.000/.001/.MVS`): table, LZSS, unpack, repack, verify |
| [tim2.py](tim2.py) | PS2 TIM2 images: reading, PNG export, writing pixels back; swizzled 4/8bpp (GS memory model) |
| [mips_asm.py](mips_asm.py) | a small MIPS assembler for hooks (R3000 encodings, valid on the R5900) |

## Checking

| Tool | What it does |
|---|---|
| [check.py](check.py) | runs every check (`--quick` for the pre-commit hook, `--control` for a lossless-build proof) |
| [stepcheck.py](stepcheck.py) | run one build text step against `extracted/` (no image, nothing written) and list what it changed - for testing a step while the image is busy |
| [lint.py](lint.py) | text: leftover source text, control codes, line/char/byte limits, glossary |
| [status.py](status.py) | how far along the text and images are |

## Translating

| Tool | What it does |
|---|---|
| [fill_text.py](fill_text.py) | fills repeated strings from a source → English table |
| [render.py](render.py) | *Pillow*: automatic English renders, only redrawing what changed |
| [edit.py](edit.py) | *Pillow*: hand-edit workflow - start, check, approve, reset, sheets |
| [compare.py](compare.py) | *Pillow*: original \| English sheets |
| [contact.py](contact.py) | *Pillow*: every original image on labelled sheets |

## Research

| Tool | What it does |
|---|---|
| [extract.py](extract.py) | unpacks the disc into `extracted/` and exports the images (*game*: `unpack()`) |
| [sjisscan.py](sjisscan.py) | finds Shift-JIS text in binary files |
| [mipsdis.py](mipsdis.py) | *capstone*: disassembler with reference and call search (ELF or raw@base:64) |
| [bss_scan.py](bss_scan.py) | estimates how far past its end a code module's memory use reaches |
| [pagekit.py](pagekit.py) | the reference pages in docs/: shared stylesheet ([pages_common.css](pages_common.css)), theme switch, nav, the controller button icons, writing a page from its template; run it to rebuild every page |
| [guidepage.py](guidepage.py) | builds the player's guide, `docs/guide/index.html` ([template](guide_template.html)): skills from the translation, a glossary checked against it; `--check` (in check.py --quick) |
| [mmmap.py](mmmap.py) | builds the Match Maker route map, `docs/matchmaker-map/index.html` (page template [mmmap_template.html](mmmap_template.html)): every briefing, check, verdict and advice answer per promotion, from the original entries and the English text |
| [survivalmap.py](survivalmap.py) | builds `docs/survival-road/index.html` ([template](survivalmap_template.html)): every course, difficulty, round and opponent pool, losses and continues, souls |
| [shopmap.py](shopmap.py) | builds `docs/secret-shop/index.html` ([template](shopmap_template.html)): every shop item, its price, when it goes on sale and what it unlocks; souls and titles; other unlocks |
| [rosterdb.py](rosterdb.py) | builds `docs/wrestlers/index.html` ([template](rosterdb_template.html)): every wrestler, costume and Edit sample with profile, skills, parameters and moveset (decodes WrestlerData like the game's 0x1149c0); `--json` writes the full model |
