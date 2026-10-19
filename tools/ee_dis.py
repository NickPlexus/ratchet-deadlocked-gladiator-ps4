"""Tiny R5900 (PS2 EE) disassembler for the opcodes we care about. Falls back to raw words."""
import struct, sys

R = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3', 't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
     's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']
I = {0x08: 'addi', 0x09: 'addiu', 0x0a: 'slti', 0x0b: 'sltiu', 0x0c: 'andi', 0x0d: 'ori', 0x0e: 'xori',
     0x18: 'daddi', 0x19: 'daddiu', 0x20: 'lb', 0x21: 'lh', 0x23: 'lw', 0x24: 'lbu', 0x25: 'lhu', 0x27: 'lwu',
     0x28: 'sb', 0x29: 'sh', 0x2b: 'sw', 0x37: 'ld', 0x3f: 'sd', 0x1e: 'lq', 0x1f: 'sq', 0x31: 'lwc1',
     0x39: 'swc1', 0x36: 'lqc2', 0x3e: 'sqc2'}
SP = {0x00: 'sll', 0x02: 'srl', 0x03: 'sra', 0x08: 'jr', 0x09: 'jalr', 0x21: 'addu', 0x23: 'subu',
      0x24: 'and', 0x25: 'or', 0x2d: 'daddu', 0x2f: 'dsubu', 0x2a: 'slt', 0x2b: 'sltu', 0x0a: 'movz', 0x0b: 'movn'}


def dis(w, pc):
    op = w >> 26; rs = (w >> 21) & 31; rt = (w >> 16) & 31; rd = (w >> 11) & 31
    imm = w & 0xffff; simm = imm - 0x10000 if imm & 0x8000 else imm
    if w == 0:
        return 'nop'
    if op == 0:
        f = w & 0x3f
        n = SP.get(f, f'special.{f:#x}')
        if f in (0, 2, 3):
            return f'{n} {R[rd]}, {R[rt]}, {(w >> 6) & 31}'
        if f == 8:
            return f'jr {R[rs]}'
        return f'{n} {R[rd]}, {R[rs]}, {R[rt]}'
    if op in (2, 3):
        return f"{'j' if op == 2 else 'jal'} {((pc + 4) & 0xf0000000) | ((w & 0x3ffffff) << 2):#x}"
    if op in (4, 5, 0x14, 0x15):
        n = {4: 'beq', 5: 'bne', 0x14: 'beql', 0x15: 'bnel'}[op]
        return f'{n} {R[rs]}, {R[rt]}, {pc + 4 + simm * 4:#x}'
    if op == 1:
        return f'regimm.{rt} {R[rs]}, {pc + 4 + simm * 4:#x}'
    if op in (6, 7):
        return f"{'blez' if op == 6 else 'bgtz'} {R[rs]}, {pc + 4 + simm * 4:#x}"
    if op == 0x0f:
        return f'lui {R[rt]}, {imm:#x}'
    if op in I:
        n = I[op]
        if op in (0x08, 0x09, 0x0a, 0x0b, 0x18, 0x19):
            return f'{n} {R[rt]}, {R[rs]}, {simm}'
        if op in (0x0c, 0x0d, 0x0e):
            return f'{n} {R[rt]}, {R[rs]}, {imm:#x}'
        return f'{n} {R[rt] if op not in (0x31, 0x39, 0x36, 0x3e) else "$f%d" % rt}, {simm}({R[rs]})'
    if op == 0x1c:
        return f'mmi.{w & 0x3f:#x} rd={R[rd]} rs={R[rs]} rt={R[rt]}'
    if op == 0x12:
        return f'cop2 {w:#010x}'
    return f'.word {w:#010x}'


def load(p):
    d = open(p, 'rb').read()
    ph = struct.unpack_from('<I', d, 0x1c)[0]; n = struct.unpack_from('<H', d, 0x2c)[0]
    return [(va, d[off:off + fs]) for t, off, va, pa, fs, ms, fl, al in
            (struct.unpack_from('<8I', d, ph + i * 32) for i in range(n))]


def dump(p, start, end):
    for va, b in load(p):
        if va <= start < va + len(b):
            for a in range(start, end, 4):
                w = struct.unpack_from('<I', b, a - va)[0]
                print(f'{a:#010x}  {w:08x}  {dis(w, a)}')


if __name__ == '__main__':
    dump(sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16))
