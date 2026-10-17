#!/usr/bin/env python3
"""Code patches from a table, each checked against the original bytes before it is written.

    # (group, file, address, original, new, description or None)
    CODE_PATCHES = [
        # Mode select shows 8 modes, 10 if byte 0x80048580 is set - which no normal gameplay sets
        # (docs/PATCHES.md "Hidden modes"). Skipping the check always shows all 10.
        ('unlocks', 'PROG.BIN', 0x8005ecbc, 0x10400003, 0x00000000, 'Survival unlocked'),  # beqz -> nop
    ]

`original` and `new` are 32-bit little-endian words (int) or bytes of equal length (e.g. from
tools/mips_asm.py). A mismatch stops the build: "unexpected code at 0x...". Groups are picked with
build.py --unlocks; a None description keeps the output short for multi-site patches.

apply(files, patches, groups, to_offset): files is build.py's Files (get/put by name);
to_offset(file, address) turns an address into a file offset (overlay base, ELF segments, ...).
"""
import struct


def as_bytes(v):
    return struct.pack('<I', v) if isinstance(v, int) else bytes(v)


def apply(files, patches, groups, to_offset, quiet=False):
    applied = 0
    for group, name, addr, old, new, what in patches:
        if group not in groups:
            continue
        old, new = as_bytes(old), as_bytes(new)
        if len(old) != len(new):
            raise SystemExit(f'patch at {addr:#x} in {name}: original and new differ in length')
        data = files.get(name)
        off = to_offset(name, addr)
        if bytes(data[off:off + len(old)]) != old:
            raise SystemExit(f'{name}: unexpected code at {addr:#x} (offset {off:#x}): found '
                             f'{bytes(data[off:off + len(old)]).hex()}, expected {old.hex()} - wrong image, or the '
                             f'file was changed by an earlier step')
        data[off:off + len(new)] = new
        files.put(name, data)
        applied += 1
        if what and not quiet:
            print(f'patch: {what}')
    return applied
