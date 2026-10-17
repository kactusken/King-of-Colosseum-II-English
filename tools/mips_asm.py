#!/usr/bin/env python3
"""Tiny MIPS assembler for small hooks (R3000 encodings; also valid on the PS2's R5900).

Supports the instructions used by the patches in this project, labels,
%hi(sym)/%lo(sym) (with carry), numeric literals and symbol arithmetic
such as `%lo(TABLE+2)`. No delay-slot scheduling: write the slot yourself.

    code = assemble(source, base=0x8005a8fc, symbols={"DRAW": 0x80062e54})
"""
import re
import struct

REG = {n: i for i, n in enumerate(
    ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
     't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
     's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
     't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra'])}

R3 = {'addu': 33, 'subu': 35, 'and': 36, 'or': 37, 'xor': 38, 'slt': 42, 'sltu': 43}
SHIFT = {'sll': 0, 'srl': 2, 'sra': 3}
SHIFTV = {'sllv': 4, 'srlv': 6, 'srav': 7}  # sllv rd, rt, rs
IMM = {'addiu': 9, 'slti': 10, 'sltiu': 11, 'andi': 12, 'ori': 13, 'xori': 14}
MEM = {'lb': 32, 'lh': 33, 'lw': 35, 'lbu': 36, 'lhu': 37, 'sb': 40, 'sh': 41, 'sw': 43}
BR2 = {'beq': 4, 'bne': 5}
BR1 = {'blez': 6, 'bgtz': 7}


class AsmError(Exception):
    pass


def reg(tok):
    tok = tok.strip().lstrip('$')
    if tok not in REG:
        raise AsmError(f'bad register {tok!r}')
    return REG[tok]


def evaluate(expr, symbols):
    expr = expr.strip()
    m = re.fullmatch(r'%(hi|lo)\((.+)\)', expr)
    if m:
        v = evaluate(m.group(2), symbols) & 0xFFFFFFFF
        if m.group(1) == 'hi':
            return ((v + 0x8000) >> 16) & 0xFFFF
        lo = v & 0xFFFF
        return lo - 0x10000 if lo & 0x8000 else lo
    tokens = re.findall(r'[+-]|[^+-]+', expr.replace(' ', ''))
    total, sign = 0, 1
    for t in tokens:
        if t == '+':
            sign = 1
        elif t == '-':
            sign = -1
        else:
            if re.fullmatch(r'0x[0-9a-fA-F]+|\d+', t):
                val = int(t, 0)
            elif t in symbols:
                val = symbols[t]
            else:
                raise AsmError(f'unknown symbol {t!r}')
            total += sign * val
            sign = 1
    return total


def parse_mem(op):
    m = re.fullmatch(r'(.*)\((\$?\w+)\)', op.strip())
    if not m:
        raise AsmError(f'bad memory operand {op!r}')
    return (m.group(1) or '0'), reg(m.group(2))


def lines_of(source):
    for raw in source.splitlines():
        line = raw.split(';')[0].split('#')[0].strip()
        if line:
            yield line


def assemble(source, base, symbols=None):
    symbols = dict(symbols or {})
    # pass 1: labels / sizes
    pc = base
    items = []
    for line in lines_of(source):
        while ':' in line.split()[0]:
            label, _, rest = line.partition(':')
            symbols[label.strip()] = pc
            line = rest.strip()
            if not line:
                break
        if not line:
            continue
        mnem, _, ops = line.partition(' ')
        ops = [o.strip() for o in ops.split(',')] if ops.strip() else []
        if mnem == '.byte':
            items.append((pc, mnem, ops))
            pc += len(ops)
            continue
        if mnem == '.half':
            items.append((pc, mnem, ops))
            pc += 2 * len(ops)
            continue
        if mnem == '.word':
            items.append((pc, mnem, ops))
            pc += 4 * len(ops)
            continue
        if mnem == '.align':
            pad = (-pc) % (1 << int(ops[0]))
            items.append((pc, '.byte', ['0'] * pad))
            pc += pad
            continue
        if mnem == 'li' and not re.fullmatch(r'-?(0x[0-9a-fA-F]{1,4}|\d+)', ops[1]):
            raise AsmError('li supports 16-bit literals only; use lui/addiu')
        items.append((pc, mnem, ops))
        pc += 4
    # pass 2: encode
    out = bytearray()
    for pc, mnem, ops in items:
        if mnem == '.byte':
            out += bytes(evaluate(o, symbols) & 0xFF for o in ops)
            continue
        if mnem == '.half':
            for o in ops:
                out += struct.pack('<H', evaluate(o, symbols) & 0xFFFF)
            continue
        if mnem == '.word':
            for o in ops:
                out += struct.pack('<I', evaluate(o, symbols) & 0xFFFFFFFF)
            continue
        if pc % 4:
            raise AsmError(f'unaligned instruction at {pc:#x}')
        out += struct.pack('<I', encode(mnem, ops, pc, symbols))
    return bytes(out), symbols


def encode(m, ops, pc, sy):
    def imm16(e):
        v = evaluate(e, sy)
        if not -0x8000 <= v <= 0xFFFF:
            raise AsmError(f'immediate out of range: {e} = {v:#x}')
        return v & 0xFFFF

    def branch(target):
        off = (evaluate(target, sy) - (pc + 4)) >> 2
        if not -0x8000 <= off < 0x8000:
            raise AsmError('branch out of range')
        return off & 0xFFFF

    if m == 'nop':
        return 0
    if m == 'move':
        return (reg(ops[1]) << 21) | (reg(ops[0]) << 11) | 33
    if m == 'li':
        return (9 << 26) | (reg(ops[0]) << 16) | imm16(ops[1])
    if m in R3:
        return (reg(ops[1]) << 21) | (reg(ops[2]) << 16) | (reg(ops[0]) << 11) | R3[m]
    if m in SHIFT:
        return (reg(ops[1]) << 16) | (reg(ops[0]) << 11) | ((evaluate(ops[2], sy) & 31) << 6) | SHIFT[m]
    if m in SHIFTV:
        return (reg(ops[2]) << 21) | (reg(ops[1]) << 16) | (reg(ops[0]) << 11) | SHIFTV[m]
    if m in IMM:
        return (IMM[m] << 26) | (reg(ops[1]) << 21) | (reg(ops[0]) << 16) | imm16(ops[2])
    if m == 'lui':
        return (15 << 26) | (reg(ops[0]) << 16) | imm16(ops[1])
    if m in MEM:
        off, base = parse_mem(ops[1])
        return (MEM[m] << 26) | (base << 21) | (reg(ops[0]) << 16) | imm16(off)
    if m in BR2:
        return (BR2[m] << 26) | (reg(ops[0]) << 21) | (reg(ops[1]) << 16) | branch(ops[2])
    if m in BR1:
        return (BR1[m] << 26) | (reg(ops[0]) << 21) | branch(ops[1])
    if m == 'beqz':
        return (4 << 26) | (reg(ops[0]) << 21) | branch(ops[1])
    if m == 'bnez':
        return (5 << 26) | (reg(ops[0]) << 21) | branch(ops[1])
    if m == 'b':
        return (4 << 26) | branch(ops[0])
    if m in ('j', 'jal'):
        t = evaluate(ops[0], sy)
        if (t ^ pc) & 0xF0000000:
            raise AsmError('jump target in a different 256MB region')
        return ((2 if m == 'j' else 3) << 26) | ((t >> 2) & 0x3FFFFFF)
    if m == 'bal':  # bgezal zero, target
        return (1 << 26) | (17 << 16) | branch(ops[0])
    if m == 'divu':
        return (reg(ops[0]) << 21) | (reg(ops[1]) << 16) | 0x1B
    if m == 'mflo':
        return (reg(ops[0]) << 11) | 0x12
    if m == 'jr':
        return (reg(ops[0]) << 21) | 8
    if m == 'jalr':
        return (reg(ops[0]) << 21) | (31 << 11) | 9
    raise AsmError(f'unknown instruction {m!r}')
