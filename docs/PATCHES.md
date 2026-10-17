# Patches

What the build changes besides text and images, one section per patch: what the original code
does, what changed, why it works, the tool that makes it, limits to respect, and whether it was
*verified in game*.

## ASCII text (always on with the translation)

**What the original does.** The text renderer only draws two-byte Shift-JIS: the draw loop
(0x10c938) fetches a glyph only for a lead byte (0x81-0x9f, 0xe0-0xfc); any other single byte
draws nothing and takes no width, except space (0x20, 4 units) and new line (0x0a). So English had
to be stored full-width, two bytes a letter - too long for fixed fields such as the roster names
(a 7-letter surname limit).

**What changed** (`tools/textpatch.py`, applied by build.py `text_code_patches()`):
- 0x10c65c, in the text formatter every drawn string is copied through: `j fmt` + `nop`. The cave
  routine writes a printable ASCII byte (0x21-0x7e) as its full-width two-byte code (the table
  below) and other single bytes unchanged, then returns to the loop (0x10c6bc). The draw loop
  downstream sees ordinary Shift-JIS.
- 0x10cc20 (glyph lookup) and 0x10ccf0 (glyph width): `j lu` / `j w`, keeping each routine's
  second instruction in the delay slot. The cave maps a code whose high byte is printable ASCII to
  its full-width code, then runs the replaced first instruction and returns. This covers the ~10
  callers that measure a raw string (0x10cf90) for centring before formatting.
- Cave: 0x31e2b8, an unreferenced 520-byte library routine (no call, jump, data pointer or built
  address anywhere in the ELF); 372 bytes used - three routines and a 94-entry table (ASCII
  0x21-0x7e -> the codes tools/font.py uses: ' -> ’, " -> ”, - -> －, ~ -> ～, the rest U+FF01-FF5E).
  Only t4-t7 are used (the width routine keeps t0-t3 live).

**Checks.** The build verifies the original instructions at the three sites and the cave's SHA-1.
`tools/test_textpatch.py` runs the cave in an EE-accurate interpreter for all 255 byte values
(check.py, quick).

**Limits.** Multi-line dialogs still need full-width text: their line splitting breaks on
single-byte characters (see docs/TECHNICAL.md); pools.py encodes multi-line strings full-width.
A single-byte `"` always draws the closing quote. *Verified in game* (2026-10-15): the game boots
and draws all text as before; the roster names, stored as ASCII, show on the wrestler select screen.

## Yellow quotes in the Dojo (always on with the translation)
The Dojo dialogue (and the lesson panel drawn through the same splitter, 0x191290 / 0x1a2538)
draws a run that starts with the first entry of the token table at 0x3abdb0 and ends with the
first entry of the table at 0x3abe00 in yellow - 「…」 in Japanese, brackets included. The English
puts move names in “…” (what `"` encodes to), so those two entries become “ (0x8167) and ”
(0x8168): build.py TEXT_DATA_PATCHES, data only, original bytes checked. The other entries
(○ △ □ ×, Ｒ１ Ｒ２ Ｌ１ Ｌ２) are the button-icon tokens and must stay as they are. *From the code*;
not yet seen in game. User, 2026-10-15: try it and judge in game.
The splitter steps through each line two bytes at a time, so a token after an odd number of
single-byte characters is missed (*verified in game*: the goal "Rope Rebound", one space inside
the quotes, left the yellow run open into the advice lines; a △ after an odd count drew as a plain
glyph). pools.encode therefore keeps “ ” ○ △ □ × Ｒ１ Ｒ２ Ｌ１ Ｌ２ on even offsets from the line
start by widening one space before them (GRID_TOKENS). The Dojo dialogue (tools/dojo.py) is fully
full-width and always on the grid.

## Everything unlocked (group `all`, `--unlocks all`; the All Unlocked release variants)
**What the original does.** The game has a routine that unlocks everything, 0x100c40, reached only
through a name-entry password (docs/HIDDEN_CONTENT.md "Password"). It sets the Secret Shop unlock
flags 60-278 and the wrestler flags derived from them, turns every ring on, marks every shop item
bought and maxes the Survival Road record (9,999 souls, half price, Edit points 400). All of this
is system-save data, so a memory card load replaces it. Content the game itself never unlocks
(docs/HIDDEN_CONTENT.md) it leaves alone.

**What changed** (`tools/unlockpatch.py`; user, 2026-10-16):
- Hooks: 0x121f18 (boot, after the start-up init 0x11a5d0 - a new game without a save) and
  0x19c3e0 (after a system-data load: 0x118620 unpacks the save blocks; its only caller) `jal` a
  wrapper (0x31e470-0x31e4bf) that calls the original function, keeping the loader's return value,
  and then the flag routine `extra` (0x31e430, 64 bytes), which jumps to 0x100c40 when done.
- `extra` sets the unlock flags nothing in the game sets: 25 (wrestler 147), 24 (Trainee #1-#4),
  4 (the Retired group they are listed in) and 2 (Mystery 1-3 and the cut Pancrase moves and
  Edit parts); and clears the option-value states that hide the cut options (Pancrase Rules, the
  Pancrase and WAR rings, Pancrase Fans, referee Soichi Hiroto) and the Dojo reward, referee
  Kotetsu Yamamoto.
- 0x157780 `beq s1, 5` -> `nop`: the Edit face screen lists header 5, Mystery.
- A data step (`unlockpatch.parts_step`, entry 2010) gives the 191 flag-2 Edit parts whose
  body-type mask is 0 every type (0x0fff), so the part lists offer them.
- Both code areas are in the unreferenced library routine that also holds the text patch's cave,
  after it; unlockpatch.py stops if the text cave ever grows into them. The translation draws the
  names of the cut options into their empty label slots (graphics.csv, 000_01516-01518).

*Verified in game* (2026-10-16): hidden wrestlers and colour versions selectable (Kotetsu Yamamoto
under New Japan), every Secret Shop item bought, all rings; wrestler 147 (Freelance), the Trainees
(Retired) and Mystery 1-3 (via Edit) selectable and playable; the Mystery faces, referee faces,
Pancrase costume parts and the hidden clutch moves in Edit; the cut options and Kotetsu as referee
work in matches; loading a save keeps everything unlocked.

**Limits.** Souls and the other Survival records are reset to the routine's values at every
load. The Japan (All Unlocked) variant has no translation step, so the cut options' names stay
blank there (the original label pictures have none).

## Camera test viewer (group `debugview`; not in releases)
**What the original does.** The developers' camera test screen 0x286108 is still in the executable
but nothing calls it (docs/HIDDEN_CONTENT.md).
**What changed** (`tools/unlockpatch.py debug_patches`): the title menu's jump table entry 8
(0x3a8ff0, the last menu item) points at a 6-instruction stub written over the unreferenced
printer 0x1978f0: `jal 0x286108`, then the case's own work (a0 = [gp-0x5eb0], s0 = 0x2f, v0 = 5)
and a jump back to 0x125650. The viewer returns on SELECT and the menu item opens as usual.
*Verified in game* (2026-10-16). A developer group (build.py DEV_GROUPS): only built when named,
`--unlocks all,debugview`; never in `all`, the default build or the releases.
