"""Minimal VU micro-mode disassembler (pairs: lower word at +0, upper at +4).

usage: python vu_dis.py <micromem.bin> [start_byte] [end_byte]
"""
import struct, sys

D = lambda c: ''.join(ch for ch, b in zip('xyzw', (24, 23, 22, 21)) if c >> b & 1)
FT = lambda c: (c >> 16) & 31
FS = lambda c: (c >> 11) & 31
FD = lambda c: (c >> 6) & 31
BC = 'xyzw'


def s11(c):
    v = c & 0x7ff
    return v - 0x800 if v & 0x400 else v


def upper(c):
    op = c & 0x3f
    d = D(c)
    flags = ''.join(f for f, b in (('[I]', 31), ('[E]', 30), ('[M]', 29), ('[D]', 28), ('[T]', 27)) if c >> b & 1)
    if op < 0x20 and op not in (0x1c, 0x1d, 0x1e, 0x1f):
        names = ['add', 'sub', 'madd', 'msub', 'max', 'mini', 'mul']
        n = names[op >> 2] if op < 0x1c else None
        s = f'{n}{BC[op & 3]}.{d} vf{FD(c)}, vf{FS(c)}, vf{FT(c)}{BC[op & 3]}'
    elif op < 0x30:
        tab = {0x1c: 'mulq', 0x1d: 'maxi', 0x1e: 'muli', 0x1f: 'minii', 0x20: 'addq', 0x21: 'maddq', 0x22: 'addi',
               0x23: 'maddi', 0x24: 'subq', 0x25: 'msubq', 0x26: 'subi', 0x27: 'msubi', 0x28: 'add', 0x29: 'madd',
               0x2a: 'mul', 0x2b: 'max', 0x2c: 'sub', 0x2d: 'msub', 0x2e: 'opmsub', 0x2f: 'mini'}
        s = f'{tab[op]}.{d} vf{FD(c)}, vf{FS(c)}' + (f', vf{FT(c)}' if op >= 0x28 else '')
    elif op >= 0x3c:
        i = ((op & 3) << 5) | FD(c)  # 0x3c..0x3f with fd field
        b = BC[op & 3]
        t = {0: f'adda{b}', 1: f'suba{b}', 2: f'madda{b}', 3: f'msuba{b}', 6: f'mula{b}'}
        k = FD(c) >> 2 if False else FD(c)
        tabs = {0x3c: ['addax', 'subax', 'maddax', 'msubax', 'itof0', 'ftoi0', 'mulax', 'mulaq', 'addaq', 'subaq', 'adda', 'suba'],
                0x3d: ['adday', 'suby', 'madday', 'msubay', 'itof4', 'ftoi4', 'mulay', 'abs', 'maddaq', 'msubaq', 'madda', 'msuba'],
                0x3e: ['addaz', 'subz', 'maddaz', 'msubaz', 'itof12', 'ftoi12', 'mulaz', 'mulai', 'addai', 'subai', 'mula', 'opmula'],
                0x3f: ['addaw', 'subw', 'maddaw', 'msubaw', 'itof15', 'ftoi15', 'mulaw', 'clip', 'maddai', 'msubai', '?', 'nop']}
        n = tabs[op][FD(c)] if FD(c) < 12 else f'?u{op:x}.{FD(c)}'
        s = 'nop' if n == 'nop' else f'{n}.{d} vf{FT(c)}, vf{FS(c)}'
    else:
        s = f'?upper {c:08x}'
    return (s + ' ' + flags).strip()


def lower(c, pc):
    op7 = c >> 25
    it, is_, d = FT(c), FS(c), D(c)
    if op7 == 0x40:
        f = c & 0x3f
        if f == 0x30: return f'iadd vi{FD(c)}, vi{is_}, vi{it}'
        if f == 0x31: return f'isub vi{FD(c)}, vi{is_}, vi{it}'
        if f == 0x32:
            im = FD(c) - 32 if FD(c) & 16 else FD(c)
            return f'iaddi vi{it}, vi{is_}, {im}'
        if f == 0x34: return f'iand vi{FD(c)}, vi{is_}, vi{it}'
        if f == 0x35: return f'ior vi{FD(c)}, vi{is_}, vi{it}'
        if f >= 0x3c:
            k = ((f & 3) << 5) | ((c >> 6) & 31)
            T = {0x0c: f'move.{d} vf{it}, vf{is_}', 0x0d: f'lqi.{d} vf{it}, (vi{is_}++)', 0x0e: f'div Q, vf{is_}.{BC[(c>>21)&3]}, vf{it}.{BC[(c>>23)&3]}',
                 0x0f: f'mtir vi{it}, vf{is_}.{BC[(c>>21)&3]}', 0x10: 'rnext', 0x19: f'mfp.{d} vf{it}, P', 0x1a: f'xtop vi{it}', 0x1b: f'xgkick vi{is_}',
                 0x2c: f'mr32.{d} vf{it}, vf{is_}', 0x2d: f'sqi.{d} vf{is_}, (vi{it}++)', 0x2e: f'sqrt Q, vf{it}.{BC[(c>>23)&3]}', 0x2f: f'mfir.{d} vf{it}, vi{is_}',
                 0x30: f'rget.{d} vf{it}, R', 0x3a: f'xitop vi{it}',
                 0x4d: f'lqd.{d} vf{it}, (--vi{is_})', 0x4e: f'rsqrt Q, vf{is_}.{BC[(c>>21)&3]}, vf{it}.{BC[(c>>23)&3]}', 0x4f: f'ilwr.{d} vi{it}, (vi{is_})',
                 0x50: f'rinit R, vf{is_}', 0x6d: f'sqd.{d} vf{is_}, (--vi{it})', 0x6e: 'waitq', 0x6f: f'iswr.{d} vi{it}, (vi{is_})', 0x70: f'rxor R, vf{is_}',
                 0x7e: 'waitp', 0x1c: f'esadd P, vf{is_}', 0x1e: f'esqrt P, vf{is_}', 0x3e: f'ersqrt P, vf{is_}', 0x5c: f'eleng P, vf{is_}', 0x5d: f'esum P, vf{is_}',
                 0x5e: f'ercpr P, vf{is_}', 0x7c: f'erleng P, vf{is_}', 0x3f: f'eatan P, vf{is_}', 0x1f: f'esin P, vf{is_}', 0x5f: f'eexp P, vf{is_}'}
            if k == 0x6f - 0x40 + 0x40 and False:
                pass
            return T.get(k, f'?lowerT3 {k:#x}') if not (k == 0x0b or c == 0x8000033c) else 'nop'
        return f'?lowerop {f:#x}'
    tgt = pc + 8 + s11(c) * 8
    T = {0x00: f'lq.{d} vf{it}, {s11(c)}(vi{is_})', 0x01: f'sq.{d} vf{is_}, {s11(c)}(vi{it})',
         0x04: f'ilw.{d} vi{it}, {s11(c)}(vi{is_})', 0x05: f'isw.{d} vi{it}, {s11(c)}(vi{is_})',
         0x08: f'iaddiu vi{it}, vi{is_}, {((c >> 10) & 0x7800) | (c & 0x7ff)}',
         0x09: f'isubiu vi{it}, vi{is_}, {((c >> 10) & 0x7800) | (c & 0x7ff)}',
         0x10: f'fceq vi1, {c & 0xffffff:#x}', 0x11: f'fcset {c & 0xffffff:#x}', 0x12: f'fcand vi1, {c & 0xffffff:#x}', 0x13: f'fcor vi1, {c & 0xffffff:#x}',
         0x14: f'fseq vi{it}, {((c >> 10) & 0x800) | (c & 0x7ff):#x}', 0x15: f'fsset {((c >> 10) & 0x800) | (c & 0x7ff):#x}',
         0x16: f'fsand vi{it}, {((c >> 10) & 0x800) | (c & 0x7ff):#x}', 0x17: f'fsor vi{it}, {((c >> 10) & 0x800) | (c & 0x7ff):#x}',
         0x18: f'fmeq vi{it}, vi{is_}', 0x1a: f'fmand vi{it}, vi{is_}', 0x1b: f'fmor vi{it}, vi{is_}', 0x1c: f'fcget vi{it}',
         0x20: f'b {tgt:#x}', 0x21: f'bal vi{it}, {tgt:#x}', 0x24: f'jr vi{is_}', 0x25: f'jalr vi{it}, vi{is_}',
         0x28: f'ibeq vi{it}, vi{is_}, {tgt:#x}', 0x29: f'ibne vi{it}, vi{is_}, {tgt:#x}',
         0x2c: f'ibltz vi{is_}, {tgt:#x}', 0x2d: f'ibgtz vi{is_}, {tgt:#x}', 0x2e: f'iblez vi{is_}, {tgt:#x}', 0x2f: f'ibgez vi{is_}, {tgt:#x}'}
    return T.get(op7, f'?lower {c:08x}')


def dis(mem, start=0, end=None):
    end = end or len(mem)
    for pc in range(start, end, 8):
        lo, up = struct.unpack_from('<II', mem, pc)
        u = upper(up)
        l = f'loi {lo:#010x}' if up >> 31 & 1 else lower(lo, pc)
        print(f'{pc:04x}: {u:<34} | {l}')


if __name__ == '__main__':
    m = open(sys.argv[1], 'rb').read()
    dis(m, int(sys.argv[2], 16) if len(sys.argv) > 2 else 0, int(sys.argv[3], 16) if len(sys.argv) > 3 else None)
