# Images with text

Every image with text has a row in `translation/graphics.csv` (columns: see `tools/catalog.py`).
The build uses, in this order: a hand edit in `translation/images-handmade/`, an approved image in
`translation/images-approved/`, an automatic render in `translation/images-rendered/`, else the
original. All three hold indexed PNGs in the game's palette.

## Automatic renders

Plain labels (one background + one text colour, optionally an outline) are drawn by
`.venv/bin/python tools/render.py` from the row's `english` (`' / '` forces a line break; `font`,
`align`, `boxes` hints). It only redraws rows that changed since they were drawn. Look at the
result with `tools/compare.py`, then `tools/edit.py approve <image>` freezes it.

## Hand edits

1. Find the image: `.venv/bin/python tools/edit.py list <words>`, or `review/compare/`, or
   `review/contact-sheets/`.
2. `.venv/bin/python tools/edit.py start <image>` → edit `translation/images-handmade/<image>.png`
   (same size; the original palette is best, RGB works too and is snapped on approve; transparent
   stays transparent). `<image>_original.png` next to it is for reference.
   - Aseprite: opens indexed; save as PNG.
   - GIMP: keep Image › Mode › Indexed; File › Export As › PNG over the same file.
   - Photoshop: Image › Mode › Indexed Color with the existing palette.
3. `.venv/bin/python tools/edit.py check <image>` → `OK`, or `!` lines saying what to fix;
   `<image>_check.png` shows the original above yours.
4. `python3 build.py` and look at it in the emulator.
5. `.venv/bin/python tools/edit.py approve <image>` → moved to `images-approved/`, marked done.

Undo: `edit.py reset <image>`. Several images: names, commas, ranges (`0013_020-0013_052`) or
patterns (`0013_*`).

## Many similar images as one sheet

`edit.py sheet start <name> <images>` writes `translation/images-handmade/sheets/<name>.png`:
original | English pairs at real size. Edit the right-hand images (magenta = transparent), then
`sheet check`, `sheet split` or `sheet approve`.

## How the game cuts label sprites (verified in game, 2026-10-15)
- List menus (graphics.csv category `menu`, and LIST_ATLASES in tools/render.py): each label is a
  sprite cut on the list's row grid (e.g. every 24 rows; the middle of the gap only where no grid
  line falls in it), and the texture filter shows a sprite's last row on the next sprite's top
  edge. *Verified in game*: a probe build (white marks, one per row, on Match Maker company select)
  showed rows 88-95 in ZERO-ONE and 95-105 in WJ; the J of "All Japan" showed at row 71, the last
  row before the grid line 72. So the English, outline included, stays inside its sprite and off
  its last row (SPRITE_GAP); a descender that would cross is lifted, and only a label whose
  letters can't fit at all is drawn smaller.
- Some atlases (FIXED_ATLASES: 01474 button legends, 02473 Hall of Souls) cut each sprite to the
  label's own width: "Delete" showed as "Delet". There the English is never widened past the
  original label (squeezed or drawn smaller instead). Other atlases showed widened labels whole.
- Hand edits (translation/hand/) follow the same rules by hand.
- Atlases in render.py UNIFORM_ATLASES draw all labels of a size group at the size the tightest
  one needed (the second pass list menus get), so a label that fits doesn't stand out bigger than
  its neighbours. Add a picture there when one label looks bigger than the rest of its list.
- Small pixel-font lists (000_02381 / 02382) are hand scripts drawing the game's own system font
  at half size (translation/hand/stat_list.py); the condensed TrueType face is unreadable there.
