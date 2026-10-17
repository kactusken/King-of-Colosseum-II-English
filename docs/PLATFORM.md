# Platform notes: PlayStation 2 (PS2)

Starting notes for PS2 projects; much of this is still to be confirmed on a real project. Mark what
you verify and add what you learn (here and in the kit's copy).

## Disc
- Images are `.iso` with 2048-byte sectors (DVD, sometimes CD). No EDC/ECC to regenerate.
- Most DVDs carry **ISO9660 + UDF** over the same files. The console and PCSX2 read ISO9660; keep
  UDF consistent anyway (`tools/disc.py` updates both; `disc.py check <iso>` compares them).
- Mastering tools often store files over 1 GB as a single UDF extent whose length overflows into
  the type bits. `disc.py` keeps that layout when it rewrites such a file.
- Big zero-filled padding files (names like `DUMMY`, or joke names) push data to the outer edge of
  the disc for speed. `extract.py` skips them; they are not free space as far as the file system is
  concerned.
- Games often find data through their own tables (LBA tables in the ELF, archive indexes such as
  CRI AFS), not through the file system - check before relocating or growing a file.
- A DVD image is 4+ GB: builds restore only what the last build changed (`tools/image.py`), and
  browser patchers may not cope with patches against it; point players to Delta Patcher / xdelta3.

## Code
- CPU: Emotion Engine, MIPS R5900 (MIPS III + 128-bit multimedia "MMI" instructions). Branch delay
  slots apply; loads are interlocked (no load delay slot). Registers are 64/128-bit.
- The executable (`SLPM_xxx.xx`, `SLUS_xxx.xx`, named in `SYSTEM.CNF`) is an ELF: use
  `tools/elf.py` to turn RAM addresses into file offsets. Overlays and IOP modules (`.IRX`) may
  also be present.
- `tools/mipsdis.py` decodes the 64-bit integer instructions; capstone doesn't know MMI, so those
  words show as `.word` or wrong mnemonics.
- Debugging: PCSX2 has a built-in debugger (memory, breakpoints, disassembly). *Check whether your
  PCSX2 version offers a GDB/remote interface before writing a client.*

## Text
- Shift-JIS is common (`tools/sjisscan.py`); fonts are usually textures, so check whether ASCII /
  half-width glyphs exist before planning a variable-width font.

## Images
- TIM2 (`.tm2`, "TIM2" magic) is the common texture format: 4/8bpp with 16/32-bit CLUTs, alpha
  0x80 = opaque, 8bpp CLUTs usually in CSM1 order (`tools/tim2.py` handles it). Games may also use
  raw GS textures with separate palettes, often swizzled - look before assuming TIM2.
- TIM2 writers vary: King of Colosseum II uses image types 0x0a / 0x09 for **swizzled** 8bpp / 4bpp
  (GS memory order: write as PSMT8/PSMT4, read back as PSMCT32 rows - `tim2.swizzle_map()`), and
  4bpp CLUTs of 32 entries with the colours in 0-7 and 16-23. Scrambled-looking text in a decode
  is the sign. Tally the header bytes across all files before trusting a parser.
- Check a decompressor on the *content* of compressed entries (e.g. TIM2 headers past the first
  bytes), not just sizes: an off-by-one window start passes size checks and leading literals.
