#!/usr/bin/env python3
"""PS2 executable (ELF, 32-bit little-endian MIPS): segments and address <-> file offset.

  elf.py info <elf>                 entry point and loadable segments
  elf.py offset <elf> <addr>...     file offset of each RAM address (hex)
  elf.py addr <elf> <offset>...     RAM address of each file offset (hex)

Use Elf(data).offset(addr) in build.py's to_offset() for patches to the main executable
(SLPM_xxx.xx / SLUS_xxx.xx). Overlays loaded at runtime are raw binaries: offset = addr - base.
"""
import struct
import sys

PT_LOAD = 1


class Elf:
    def __init__(self, data):
        if data[:4] != b'\x7fELF' or data[4] != 1 or data[5] != 1:
            raise ValueError('not a 32-bit little-endian ELF')
        self.entry, phoff = struct.unpack_from('<II', data, 24)
        phentsize, phnum = struct.unpack_from('<HH', data, 42)
        self.segments = []  # (vaddr, file offset, file size, memory size)
        for i in range(phnum):
            p_type, p_off, p_vaddr, _, p_filesz, p_memsz = struct.unpack_from('<IIIIII', data, phoff + i * phentsize)
            if p_type == PT_LOAD:
                self.segments.append((p_vaddr, p_off, p_filesz, p_memsz))

    def offset(self, addr):
        for vaddr, off, filesz, _ in self.segments:
            if vaddr <= addr < vaddr + filesz:
                return off + addr - vaddr
        raise ValueError(f'{addr:#x} is not in a loaded part of the file (BSS or outside every segment)')

    def addr(self, offset):
        for vaddr, off, filesz, _ in self.segments:
            if off <= offset < off + filesz:
                return vaddr + offset - off
        raise ValueError(f'file offset {offset:#x} is not in a loadable segment')

    def end(self):
        """First address after every segment in memory (where BSS ends)."""
        return max(v + m for v, _, _, m in self.segments)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    e = Elf(open(argv[1], 'rb').read())
    if argv[0] == 'info':
        print(f'entry {e.entry:#010x}')
        for v, o, fs, ms in e.segments:
            print(f'  {v:#010x}-{v + ms:#010x}  file {o:#08x} +{fs:#x}' + (f'  (bss +{ms - fs:#x})' if ms > fs else ''))
    elif argv[0] == 'offset':
        for a in argv[2:]:
            print(f'{int(a, 16):#010x} -> {e.offset(int(a, 16)):#x}')
    elif argv[0] == 'addr':
        for o in argv[2:]:
            print(f'{int(o, 16):#x} -> {e.addr(int(o, 16)):#010x}')
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
