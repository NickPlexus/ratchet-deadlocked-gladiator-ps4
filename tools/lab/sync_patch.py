"""Synchronous EE<->VU0 scheme for the joint-blend routine (no concurrency, works on any emulator).

VU0 microprogram image (RAM 0x100090, uploaded by the game): each wait loop
    A:      ibeq viN, vi0, R        (kept: an old-style release still works)
    A+8:    move vf18, vf17         (delay slot, kept)
    A+0x10: ibeq viN, vi0, R / A+0x20: b A+0x10   (the spin)
becomes  A+0x10: nop[E] | iaddiu vi15, vi0, R/8   -> VU0 stops, remembers where to resume.
Trampoline at 0x100 (old `b` of the first loop): jr vi15. End of program sets vi15 = 0x0F0 (a stop).
EE routine: every `ctc2 zero, viN` (release) -> vcallms 0x100; all COP2 transfers after the first
vcallms get the I bit, so the EE waits for VU0 to stop before touching its registers.
"""
import struct

MC_BASE = 0x100090
TRAMP = 0x100
HALT = 0x0F0
VCALLMS_TRAMP = 0x4A000038 | ((TRAMP // 8) << 6)
LOWER_NOP = 0x8000033C
UPPER_NOP_E = 0x400002FF
REL_START, REL_END = -0xB8, 0x998          # routine range relative to the first release site


def iaddiu_vi15(imm):
    return (0x08 << 25) | (15 << 16) | (imm & 0x7FF)


def m2i(x):
    """VU0 micro address -> offset in the RAM image (a VIF MPG header sits at image+0x800)."""
    return x if x < 0x800 else x + 8


def micro_from_image(img):
    return img[:0x800] + img[0x808:]


def find_waits(mc):
    """[(A, vi, R)] for the spin pattern in the microprogram (byte offsets)."""
    lo = lambda p: struct.unpack_from('<I', mc, p)[0]
    out = []
    for A in range(0, 0x860, 8):
        w = lo(A)
        if w >> 25 == 0x28 and (w >> 11) & 31 == 0:          # ibeq viN, vi0, R
            vi = (w >> 16) & 31
            off = w & 0x7FF
            R = A + 8 + ((off - 0x800) if off & 0x400 else off) * 8
            w2, wb = lo(A + 0x10), lo(A + 0x20)
            if w2 >> 25 == 0x28 and (w2 >> 16) & 31 == vi and wb >> 25 == 0x20 and vi in (1, 2):
                out.append((A, vi, R))
    return out


def micro_patches(img):
    """[(byte offset in image, orig, new)]"""
    mc = micro_from_image(img)
    up = lambda p: struct.unpack_from('<I', mc, p)[0]
    waits = find_waits(mc)
    assert len(waits) == 8, waits
    P = []
    for A, vi, R in waits:
        P.append((A + 0x10, up(A + 0x10), iaddiu_vi15(R // 8)))      # lower
        P.append((A + 0x14, up(A + 0x14), UPPER_NOP_E))               # upper: stop
    first = waits[0][0]
    assert first + 0x20 == TRAMP, hex(first)
    P.append((TRAMP, up(TRAMP), (0x24 << 25) | (15 << 11)))           # jr vi15
    assert up(0x87C) & 0x40000000, 'program end E bit expected at 0x878'
    P.append((0x878, up(0x878), iaddiu_vi15(HALT // 8)))
    return [(m2i(o), w, n) for o, w, n in P]


def ee_patches(read32, site0):
    out = []
    for a in range(site0 + REL_START, site0 + REL_END, 4):
        w = read32(a)
        if w in (0x48C00800, 0x48C01000):
            out.append((a, w, VCALLMS_TRAMP))
        elif (w >> 26) == 0x12 and not (w >> 25) & 1 and ((w >> 21) & 31) in (1, 2, 5, 6) and not w & 1 \
                and a > site0 + REL_START:
            out.append((a, w, w | 1))
    return out


if __name__ == '__main__':
    import sys
    from statepatch import read_state, write_state, SS
    src, dst = int(sys.argv[1]), int(sys.argv[2])
    st = read_state(SS % src)
    mem = bytearray(st['eeMemory.bin'])
    mc = bytes(mem[MC_BASE:MC_BASE + 0x8C8])
    r32 = lambda a: struct.unpack_from('<I', mem, a)[0]
    mp = micro_patches(mc)
    ep = ee_patches(r32, 0x53CC08)
    for off, o, n in mp:
        assert r32(MC_BASE + off) == o
        struct.pack_into('<I', mem, MC_BASE + off, n)
    for a, o, n in ep:
        struct.pack_into('<I', mem, a, n)
    print(f'micro: {len(mp)} words, EE: {sum(1 for p in ep if p[2] == VCALLMS_TRAMP)} releases + '
          f'{sum(1 for p in ep if p[2] != VCALLMS_TRAMP)} interlocks')
    # the microprogram already resident in VU0 micro memory (state taken mid-frame) is re-uploaded by the game
    st['eeMemory.bin'] = bytes(mem)
    write_state(SS % dst, st)
