#!/usr/bin/env python3
"""Code patches: everything unlocked (group `all`) and the developers' camera viewer (`debugview`).

  unlockpatch.py show        the hook sites and the assembled code

Group `all` (build.py --unlocks all; the All Unlocked releases; docs/PATCHES.md):
- The game has a routine that unlocks everything, 0x100c40, reached only from a name-entry
  password (docs/HIDDEN_CONTENT.md): every Secret Shop unlock flag (ids 60-278 of the flag array
  0x3ef1e8) and the wrestler flags derived from them, all rings, every shop item bought, the
  Survival Road record maxed (9,999 souls, half price, rank 5, Edit points 400). It all lives in
  the system save, so a memory card load would overwrite it. Two hooks call it:
    0x121f18  boot, after the game's start-up init 0x11a5d0 (for a new game without a save);
    0x19c3e0  after a system-data load (0x118620 unpacks the save blocks; its only caller),
              keeping the loader's return value.
  Each site's `jal` points at a wrapper (0x31e470-0x31e4bf) that calls the original function and
  then `extra` (0x31e430), which jumps to 0x100c40 when done. `extra` sets the unlock flags
  nothing in the game sets (EXTRA_FLAGS: 25 wrestler 147, 24 Trainee #1-#4, 4 the Retired group,
  2 Mystery 1-3 and the cut Pancrase moves and Edit parts) and clears the option-value states
  that hide the cut options and the Dojo-reward referee (SHOWN_OPTIONS). Both sit in the
  unreferenced library routine that also holds the text patch's cave (tools/textpatch.py),
  after it.
- 0x157780 (MYSTERY_HEADER): the Edit face screen lists header 5, Mystery.
- parts_step(): a data step on entry 2010 - the flag-2 Edit parts with an empty body-type mask
  fit every type.
Decisions: user, 2026-10-16. All *verified in game*.

Group `debugview` (developer, build.py DEV_GROUPS: only when named): debug_patches().
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mips_asm  # noqa: E402
import textpatch  # noqa: E402

FILE = textpatch.FILE
EXTRA = 0x31e430          # flag routine; the text cave ends before it (checked)
CAVE = 0x31e470           # wrappers
CAVE_END = textpatch.CAVE + textpatch.CAVE_SIZE   # 0x31e4c0, end of the unreferenced routine

UNLOCK_ALL = 0x100c40     # the game's unlock-all routine (only caller: the password, 0x18a788)
INIT = 0x11a5d0           # start-up init (memsets the game state, default flags)
UNPACK = 0x118620         # system-data load: unpacks the save blocks
BOOT_SITE = 0x121f18      # jal INIT / nop
LOAD_SITE = 0x19c3e0      # jal UNPACK / move a0,s2  (the delay slot stays)
FLAGS = 0x3ef1e8          # unlock flag array (ids 0-279)
EXTRA_FLAGS = (25, 24, 4, 2)
OPTION_STATES = 0x3e9a5e  # option value states (0 shown, 1 locked, 3 never shown; defaults 0x101230)
# option values to show: referee 9 Kotetsu Yamamoto (the Dojo reward); the cut ones, which the game
# never shows (state 3, *verified in game*): ring 13 Pancrase, ring 16 WAR, referee 8 Soichi Hiroto,
# rule 2 Pancrase Rules, crowd 5 Pancrase Fans. Rule 8 (also 3) is an empty slot and stays hidden.
SHOWN_OPTIONS = (0x92, 0x56, 0x59, 0x91, 0x02, 0x69)

# original words at the hook sites and in the unreferenced routine (checked by the build)
ORIGINAL = {BOOT_SITE: 0x0c046974, LOAD_SITE: 0x0c046188}
ROUTINE_ORIGINAL = bytes.fromhex(        # 0x31e430-0x31e4bf
    '040062ac040144267b2c0c0c2d30200202000010040051ae040040ae4200053c402bb026402da4240000a0af'
    '070005242d3000002d380002000208242d480002'
    '08000a248c650c0c2d580000040043040400038efeff023c03000010ffff4234402b828e0000c3ae'
    '8000bfdf7000b6df6000b5df5000b4df4000b3df3000b2df2000b1df1000b0df0800e0039000bd27')

EXTRA_SOURCE = """
extra:
    lui $t0, %hi(FLAGS)
    addiu $t0, $t0, %lo(FLAGS)
    addiu $t1, $zero, 1
{stores}
{options}
    j UNLOCK_ALL
    nop
"""
WRAPPER_SOURCE = """
boot:
    addiu $sp, $sp, -16
    sw $ra, 0($sp)
    jal INIT
    nop
    jal EXTRA
    nop
    lw $ra, 0($sp)
    jr $ra
    addiu $sp, $sp, 16
load:
    addiu $sp, $sp, -16
    sw $ra, 0($sp)
    jal UNPACK
    nop
    sw $v0, 4($sp)
    jal EXTRA
    nop
    lw $v0, 4($sp)
    lw $ra, 0($sp)
    jr $ra
    addiu $sp, $sp, 16
"""


def assemble(flags=EXTRA_FLAGS):
    """(flag routine, wrappers, labels) storing `flags`."""
    slots = flags
    extra, syms = mips_asm.assemble(EXTRA_SOURCE.format(
        stores='\n'.join(f'    sb $t1, {n}($t0)' for n in slots),
        options='\n'.join(f'    sb $zero, {OPTION_STATES + n - FLAGS}($t0)' for n in SHOWN_OPTIONS)), EXTRA, {'FLAGS': FLAGS, 'UNLOCK_ALL': UNLOCK_ALL})
    if EXTRA + len(extra) > CAVE:
        raise SystemExit(f'unlockpatch: the flag routine needs {len(extra)} bytes, only {CAVE - EXTRA}')
    wrappers, wsyms = mips_asm.assemble(WRAPPER_SOURCE, CAVE, {'INIT': INIT, 'UNPACK': UNPACK, 'EXTRA': EXTRA})
    if CAVE + len(wrappers) > CAVE_END:
        raise SystemExit(f'unlockpatch: the wrappers need {len(wrappers)} bytes, only {CAVE_END - CAVE}')
    text_end = textpatch.CAVE + len(textpatch.build()[0])
    if text_end > EXTRA:
        raise SystemExit(f'unlockpatch: the text cave now ends at 0x{text_end:x}, past 0x{EXTRA:x} - move EXTRA')
    return extra, wrappers, {**syms, **wsyms}


def jal(target):
    return (3 << 26) | ((target >> 2) & 0x3ffffff)


def original(addr, size):
    return ROUTINE_ORIGINAL[addr - EXTRA:addr - EXTRA + size]


MYSTERY_HEADER = 0x157780   # Edit face headers (0x157738): `beq s1, 5` - header 5 (Mystery) never shown


def patches(group='all'):
    """CODE_PATCHES entries (group, file, address, original, new, description)."""
    extra, wrappers, syms = assemble(EXTRA_FLAGS)
    f = '/' + FILE
    return [(group, f, MYSTERY_HEADER, 0x1222001f, 0x00000000, None),   # show the Mystery face header
            (group, f, EXTRA, original(EXTRA, len(extra)), extra, None),
            (group, f, CAVE, original(CAVE, len(wrappers)), wrappers, None),
            (group, f, BOOT_SITE, ORIGINAL[BOOT_SITE], jal(syms['boot']), None),
            (group, f, LOAD_SITE, ORIGINAL[LOAD_SITE], jal(syms['load']),
             "Everything unlocked: the game's unlock-all routine (and wrestler 147, the Trainees, Mystery 1-3) at boot and after a load")]


# Edit parts (KC2FIRE.000 entry 2010, tools/tables.py): 32-byte items in 25 groups; u16 +0x1a =
# unlock flag, u16 +8 = the body types the part fits (bit per type; 0x156e28 lists a part only if
# the edited wrestler's type bit is set). The parts behind flag 2 mostly have mask 0, so even with
# the flag they never show: give them every type (faces, costume parts, gowns; *verified in game*).
PARTS_ENTRY = 2010
PART_GROUPS = (0, 15, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17)
ALL_TYPES = 0x0fff


def parts_step(files):
    """build.py step (with group all): the flag-2 Edit parts with no body type get every type."""
    pack = '/DATA/KC2FIRE.000'
    d = bytearray(files.packs.get(pack, PARTS_ENTRY))
    groups, n, _, _ = struct.unpack_from('<4I', d, 0)
    base = 16 + 8 * groups
    changed = 0
    for g in PART_GROUPS:
        _, count, start, _ = struct.unpack_from('<4H', d, 16 + 8 * g)
        for i in range(start, start + count):
            at = base + 32 * i
            if struct.unpack_from('<H', d, at + 0x1a)[0] == 2 and struct.unpack_from('<H', d, at + 8)[0] == 0:
                struct.pack_into('<H', d, at + 8, ALL_TYPES)
                changed += 1
    files.packs.put(pack, PARTS_ENTRY, d)
    print(f'patch: {changed} hidden Edit parts fit every body type')


# Group `debugview` (developer; never in `all` or releases): the developers' camera test viewer
# 0x286108 (no caller; menu TYPE / CHASE / WRESTLER / TAG / ROT, placeholder wrestlers, its own
# loop; SELECT leaves - docs/HIDDEN_CONTENT.md)
# runs when the last title-menu item is chosen, which then opens as usual. The title menu's case 8
# (jump table 0x3a8fd0) is pointed at a stub in the unreferenced printer 0x1978f0.
DEBUG_VIEWER = 0x286108
DEBUG_STUB = 0x1978f0
DEBUG_STUB_ORIGINAL = bytes.fromhex('f0ffbd270000b0ff3e00103c385010260800bfff4465040c2d200002')
TITLE_CASE8 = 0x3a8ff0    # jump table 0x3a8fd0 entry 8 -> 0x125648 (v0 = 5, s0 = 0x2f, then 0x125650)
DEBUG_SOURCE = """
stub:
    jal VIEWER
    nop
    lw $a0, -0x5eb0($gp)
    addiu $s0, $zero, 0x2f
    j BACK
    addiu $v0, $zero, 5
"""


def debug_patches(group='debugview'):
    blob, syms = mips_asm.assemble(DEBUG_SOURCE, DEBUG_STUB, {'VIEWER': DEBUG_VIEWER, 'BACK': 0x125650})
    f = '/' + FILE
    return [(group, f, DEBUG_STUB, DEBUG_STUB_ORIGINAL[:len(blob)], blob, None),
            (group, f, TITLE_CASE8, 0x125648, DEBUG_STUB,
             "Debug: the developers' camera test viewer runs before the last title-menu item")]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ['show']:
        print(__doc__)
        return 2
    extra, wrappers, syms = assemble(EXTRA_FLAGS)
    print(f'flag routine 0x{EXTRA:x}: {len(extra)}/{CAVE - EXTRA} bytes; wrappers 0x{CAVE:x}: '
          f'{len(wrappers)}/{CAVE_END - CAVE} bytes')
    for group, name, addr, old, new, what in patches():
        print(f'  {group:6} 0x{addr:x}: {codehex(old)} -> {codehex(new)}')
    return 0


def codehex(v):
    return (struct.pack('<I', v) if isinstance(v, int) else bytes(v)).hex()


if __name__ == '__main__':
    sys.exit(main())
