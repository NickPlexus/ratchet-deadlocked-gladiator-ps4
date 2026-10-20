"""Translate the joint-blend VU0 micro program into EE code (COP2 macro mode).

The game's routine runs a persistent VU0 micro program and talks to it through vi1/vi2 flags. On the
PS4 emulator this never behaves like real hardware. Here the micro program is turned into ordinary EE
code using the same VU0 registers in macro mode, executed synchronously at every point where the EE
routine would hand work to VU0:

  * vcallms 0         -> run translated code from micro 0x000
  * ctc2 zero, viN    -> release (as before) + run translated code from where it stopped
  * each wait loop    -> "if viN == 0 continue, else remember this point and return"
  * end of program    -> return (halt)

Only k0/k1 are used as scratch (interrupts disabled around the call).
Usage (python): build(base, sites, micro_bytes) -> {addr: word}
"""
import struct
import vu_dis

K0, K1 = 26, 27
VU0MEM_HI = 0x1100           # VU0 data memory mapped at 0x11004000


# ---------------- EE encoders ----------------
def I_(op, rs, rt, imm): return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def R_(rs, rt, rd, sa, fn): return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn
def lui(rt, imm): return I_(0x0F, 0, rt, imm)
def ori(rt, rs, imm): return I_(0x0D, rs, rt, imm)
def addiu(rt, rs, imm): return I_(0x09, rs, rt, imm)
def andi(rt, rs, imm): return I_(0x0C, rs, rt, imm)
def lw(rt, off, base): return I_(0x23, base, rt, off)
def sw(rt, off, base): return I_(0x2B, base, rt, off)
def sll(rd, rt, sa): return R_(0, rt, rd, sa, 0x00)
def sra(rd, rt, sa): return R_(0, rt, rd, sa, 0x03)
def addu(rd, rs, rt): return R_(rs, rt, rd, 0, 0x21)
def jr(rs): return R_(rs, 0, 0, 0, 0x08)
def j(t): return 0x08000000 | ((t & 0x0FFFFFFF) >> 2)
def cfc2(rt, vi, i=0): return 0x48400000 | (rt << 16) | (vi << 11) | i
def ctc2(rt, vi, i=0): return 0x48C00000 | (rt << 16) | (vi << 11) | i
def lqc2(vf, off, base): return I_(0x36, base, vf, off)
def sqc2(vf, off, base): return I_(0x3E, base, vf, off)
NOP, DI, EI = 0, 0x42000039, 0x42000038
REG_I = 21


def hi_lo(a):
    lo = a & 0xFFFF
    hi = (a >> 16) + (1 if lo & 0x8000 else 0)
    return hi & 0xFFFF, lo


class Asm:
    def __init__(self, base):
        self.base, self.words, self.labels, self.fix = base, [], {}, []

    def pc(self): return self.base + 4 * len(self.words)
    def emit(self, *ws): self.words.extend(ws)
    def label(self, name): self.labels[name] = self.pc()

    def branch(self, op, rs, rt, target):           # op: 4 beq, 5 bne, 1 regimm (rt=0 bltz, 1 bgez)
        self.fix.append((len(self.words), 'br', target))
        self.emit(I_(op, rs, rt, 0))

    def jump(self, target):
        self.fix.append((len(self.words), 'j', target))
        self.emit(0x08000000)

    def la(self, reg, target):                      # load label address (fixed later)
        self.fix.append((len(self.words), 'la', target))
        self.emit(lui(reg, 0), ori(reg, reg, 0))

    def resolve(self):
        for i, kind, t in self.fix:
            a = self.labels[t] if isinstance(t, str) else t
            pc = self.base + 4 * i
            if kind == 'br':
                off = (a - (pc + 4)) // 4
                assert -32768 <= off < 32768
                self.words[i] = (self.words[i] & 0xFFFF0000) | (off & 0xFFFF)
            elif kind == 'j':
                self.words[i] = j(a)
            elif kind == 'la':
                self.words[i] = lui(self.words[i] >> 16 & 31, a >> 16)
                self.words[i + 1] = ori(self.words[i + 1] >> 16 & 31, self.words[i + 1] >> 16 & 31, a & 0xFFFF)
        return {self.base + 4 * k: w for k, w in enumerate(self.words)}


# ---------------- micro program analysis ----------------
def s11(c):
    v = c & 0x7FF
    return v - 0x800 if v & 0x400 else v


def lower_kind(lo):
    op7 = lo >> 25
    if op7 == 0x40:
        return 'macro'
    return {0x00: 'lq', 0x01: 'sq', 0x08: 'iaddiu', 0x09: 'isubiu', 0x20: 'b', 0x28: 'ibeq', 0x29: 'ibne',
            0x2C: 'ibltz', 0x2D: 'ibgtz', 0x2E: 'iblez', 0x2F: 'ibgez'}.get(op7, f'?{op7:#x}')


def upper_rw(up):
    """(reads, writes) of an upper instruction as sets of names (vfN, ACC, Q, I)."""
    if up & 0x3F == 0x3F and ((up >> 6) & 31) == 11:      # nop
        return set(), set()
    op = up & 0x3F
    ft, fs, fd = (up >> 16) & 31, (up >> 11) & 31, (up >> 6) & 31
    r, w = {f'vf{fs}'}, set()
    if op >= 0x3C:                                      # 3-op table: ACC dest or itof/ftoi/clip/abs
        idx = fd
        name = vu_dis.upper(up).split()[0].split('.')[0]
        if name.startswith(('itof', 'ftoi', 'abs')):
            return {f'vf{fs}'}, {f'vf{ft}'}
        r.add(f'vf{ft}') if not name.endswith(('q', 'i')) else None
        if name.endswith('q'): r.add('Q')
        if name.endswith('i'): r.add('I')
        if name.startswith(('madd', 'msub')): r.add('ACC')
        w.add('ACC')
        return r, w
    name = vu_dis.upper(up).split()[0].split('.')[0]
    if not name.endswith(('q', 'i')): r.add(f'vf{ft}')
    if name.endswith('q'): r.add('Q')
    if name.endswith('i'): r.add('I')
    if name.startswith(('madd', 'msub')): r.add('ACC')
    w.add(f'vf{fd}')
    return r, w


def lower_rw(lo, kind):
    it, is_ = (lo >> 16) & 31, (lo >> 11) & 31
    if kind == 'lq': return {f'vi{is_}', 'MEM'}, {f'vf{it}'}
    if kind == 'sq': return {f'vf{is_}', f'vi{it}'}, {'MEM'}
    if kind in ('iaddiu', 'isubiu'): return {f'vi{is_}'}, {f'vi{it}'}
    if kind in ('b',): return set(), set()
    if kind in ('ibeq', 'ibne'): return {f'vi{it}', f'vi{is_}'}, set()
    if kind.startswith('ib'): return {f'vi{is_}'}, set()
    # macro-able lower ops used here: move, mtir, iand, div, rsqrt, nop
    d = vu_dis.lower(lo, 0)
    n = d.split()[0].split('.')[0]
    if n == 'nop': return set(), set()
    if n == 'move': return {f'vf{is_}'}, {f'vf{it}'}
    if n == 'mtir': return {f'vf{is_}'}, {f'vi{it}'}
    if n == 'iand': return {f'vi{is_}', f'vi{it}'}, {f'vi{(lo >> 6) & 31}'}
    if n in ('div', 'rsqrt'): return {f'vf{is_}', f'vf{it}'}, {'Q'}
    raise ValueError(d)


def find_waits(mc):
    out = {}
    for A in range(0, 0x880, 8):
        lo = struct.unpack_from('<I', mc, A)[0]
        if lo >> 25 == 0x28 and (lo >> 11) & 31 == 0:
            vi = (lo >> 16) & 31
            R = A + 8 + s11(lo) * 8
            lo2, lob = struct.unpack_from('<I', mc, A + 0x10)[0], struct.unpack_from('<I', mc, A + 0x20)[0]
            if lo2 >> 25 == 0x28 and (lo2 >> 16) & 31 == vi and lob >> 25 == 0x20 and vi in (1, 2):
                out[A] = (vi, R)
    return out


# ---------------- translation ----------------
def emit_vu_addr(a, vi, imm):
    """k1 = 0x11004000-relative base for VU0 mem qword (vi + imm); returns the lqc2/sqc2 offset."""
    if vi == 0:
        a.emit(lui(K1, VU0MEM_HI))
        return 0x4000 + ((imm & 0xFF) << 4)
    a.emit(cfc2(K1, vi), addiu(K1, K1, imm), andi(K1, K1, 0xFF), sll(K1, K1, 4), lui(K0, VU0MEM_HI), addu(K1, K1, K0))
    return 0x4000


def emit_lower(a, lo, kind):
    it, is_ = (lo >> 16) & 31, (lo >> 11) & 31
    dest = (lo >> 21) & 0xF
    if kind == 'macro':
        if lo == 0x8000033C:
            return
        a.emit(0x4A000000 | (lo & 0x01FFFFFF))
    elif kind == 'lq':
        assert dest == 0xF, 'partial lq'
        off = emit_vu_addr(a, is_, s11(lo))
        a.emit(lqc2(it, off, K1))
    elif kind == 'sq':
        assert dest == 0xF, 'partial sq'
        off = emit_vu_addr(a, it, s11(lo))
        a.emit(sqc2(is_, off, K1))
    elif kind in ('iaddiu', 'isubiu'):
        imm = ((lo >> 10) & 0x7800) | (lo & 0x7FF)
        if kind == 'isubiu': imm = -imm
        if is_ == 0:
            a.emit(addiu(K1, 0, imm))
        else:
            a.emit(cfc2(K1, is_), addiu(K1, K1, imm))
        a.emit(ctc2(K1, it))
    else:
        raise ValueError(kind)


def emit_upper(a, up):
    if (up & 0x3F) == 0x3F and ((up >> 6) & 31) == 11:
        return
    a.emit(0x4A000000 | (up & 0x01FFFFFF))


def emit_pair(a, mc, pc):
    lo, up = struct.unpack_from('<II', mc, pc)
    if up >> 31 & 1:                                   # I bit: lower is the immediate for I
        a.emit(lui(K1, lo >> 16), ori(K1, K1, lo & 0xFFFF), ctc2(K1, REG_I))
        emit_upper(a, up)
        return
    kind = lower_kind(lo)
    assert not kind.startswith('?'), (hex(pc), kind)
    ur, uw = upper_rw(up)
    lr, lwr = lower_rw(lo, kind) if kind not in ('b',) and not kind.startswith('ib') else (set(), set())
    if uw & lr and lwr & ur:
        raise ValueError(f'pair swap conflict at {pc:#x}')
    if uw & lr:          # lower must see the old value -> lower first
        emit_lower(a, lo, kind); emit_upper(a, up)
    else:
        emit_upper(a, up); emit_lower(a, lo, kind)


def build(base, mc, end=0x880):
    """Translated program. Labels: 'L%03x' for micro addresses, 'F_entry', 'F_ret', data words RES and RET."""
    waits = find_waits(mc)
    a = Asm(base)
    # data
    a.label('RES'); a.emit(0)
    a.label('RET'); a.emit(0)
    # entry: resume where we stopped
    a.label('F_entry')
    a.la(K0, 'RES'); a.emit(lw(K0, 0, K0), NOP, jr(K0), NOP)
    # return: back to the per-site continuation, interrupts on again
    a.label('F_ret')
    a.la(K0, 'RET'); a.emit(lw(K0, 0, K0), NOP, jr(K0), EI)

    skip = set()
    for A, (vi, R) in waits.items():
        skip.update(range(A + 0x10, A + 0x30, 8))
    pc = 0
    while pc < end:
        a.label(f'L{pc:03x}')
        if pc in skip:
            pc += 8
            continue
        lo, up = struct.unpack_from('<II', mc, pc)
        if pc in waits:
            vi, R = waits[pc]
            emit_upper(a, up)                          # upper of the ibeq pair
            emit_pair(a, mc, pc + 8)                   # delay slot pair
            a.label(f'W{pc:03x}')                       # re-check point after a return
            a.emit(cfc2(K1, vi), NOP)
            a.branch(4, K1, 0, f'L{R:03x}'); a.emit(NOP)
            # not released yet: remember this point, return to the EE routine
            a.la(K0, f'W{pc:03x}'); a.la(K1, 'RES'); a.emit(sw(K0, 0, K1))
            a.jump('F_ret'); a.emit(NOP)
            pc += 0x10
            continue
        kind = lower_kind(lo) if not (up >> 31 & 1) else 'imm'
        if up >> 30 & 1:                               # E bit: this pair + next, then halt
            emit_pair(a, mc, pc); emit_pair(a, mc, pc + 8)
            a.la(K0, 'HALT'); a.la(K1, 'RES'); a.emit(sw(K0, 0, K1))
            a.jump('F_ret'); a.emit(NOP)
            pc += 0x10
            continue
        if kind in ('b', 'ibeq', 'ibne', 'ibltz', 'ibgez', 'ibgtz', 'iblez'):
            tgt = pc + 8 + s11(lo) * 8
            it, is_ = (lo >> 16) & 31, (lo >> 11) & 31
            # make sure the delay slot does not change the branch's registers
            dlo, dup = struct.unpack_from('<II', mc, pc + 8)
            dk = lower_kind(dlo)
            dw = set()
            if dk not in ('b',) and not dk.startswith('ib') and not (dup >> 31 & 1):
                dw = lower_rw(dlo, dk)[1]
            assert not ({f'vi{it}', f'vi{is_}'} & dw), f'delay slot writes branch reg at {pc:#x}'
            plo, pup = struct.unpack_from('<II', mc, pc - 8) if pc else (0x8000033C, 0x2FF)
            pk = lower_kind(plo)
            pw = set() if (pup >> 31 & 1) or pk == 'b' or pk.startswith('ib') else lower_rw(plo, pk)[1]
            assert not ({f'vi{it}', f'vi{is_}'} & pw) or kind == 'b', f'VI backup hazard at {pc:#x}'
            emit_upper(a, up)
            emit_pair(a, mc, pc + 8)
            if kind == 'b':
                a.jump(f'L{tgt:03x}'); a.emit(NOP)
            else:
                a.emit(cfc2(K1, is_), NOP, sll(K1, K1, 16), sra(K1, K1, 16))
                if kind in ('ibeq', 'ibne'):
                    a.emit(cfc2(K0, it), NOP, sll(K0, K0, 16), sra(K0, K0, 16))
                    a.branch(4 if kind == 'ibeq' else 5, K1, K0, f'L{tgt:03x}')
                elif kind == 'ibltz': a.branch(1, K1, 0, f'L{tgt:03x}')
                elif kind == 'ibgez': a.branch(1, K1, 1, f'L{tgt:03x}')
                elif kind == 'ibgtz': a.branch(7, K1, 0, f'L{tgt:03x}')
                elif kind == 'iblez': a.branch(6, K1, 0, f'L{tgt:03x}')
                a.emit(NOP)
            pc += 0x10
            continue
        emit_pair(a, mc, pc)
        pc += 8
    a.label(f'L{end:03x}')
    a.label('HALT')
    a.jump('F_ret'); a.emit(NOP)
    return a


def build_all(base, mc, sites, read32):
    """sites: list of EE addresses with `ctc2 zero, viN` or `vcallms 0`. Returns {addr: word} incl. site patches."""
    a = build(base, mc)
    words = {}
    stubs = Asm(a.pc())
    for s in sites:
        w0, w1 = read32(s), read32(s + 4)
        stubs.label(f'S{s:x}')
        stubs.emit(DI)
        stubs.la(K0, f'C{s:x}')
        stubs.la(K1, a.labels['RET']); stubs.emit(sw(K0, 0, K1))
        if w0 == 0x4A000038:                           # vcallms 0: start at micro 0
            stubs.la(K0, a.labels['L000']); stubs.la(K1, a.labels['RES']); stubs.emit(sw(K0, 0, K1))
        else:
            assert w0 in (0x48C00800, 0x48C01000), hex(w0)
            stubs.emit(w0)                             # the release itself (vi flag = 0)
        stubs.jump(a.labels['F_entry']); stubs.emit(NOP)
        stubs.label(f'C{s:x}')
        stubs.emit(w1)
        stubs.jump(s + 8); stubs.emit(NOP)
    words.update(a.resolve())
    sw_ = stubs.resolve()
    words.update(sw_)
    for s in sites:
        words[s] = j(stubs.labels[f'S{s:x}'])
        words[s + 4] = NOP
    return words, a, stubs
