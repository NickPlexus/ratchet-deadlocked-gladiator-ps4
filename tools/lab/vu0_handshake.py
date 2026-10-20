"""Root-cause fix for twisted models: proper EE<->VU0 handshake in the joint-blend routine.

The routine (level overlay, e.g. 0x53C818 in level 1) runs a persistent VU0 micro program (vcallms 0)
and feeds it through vf1..vf8; it releases VU0 with `ctc2 zero, vi1` / `ctc2 zero, vi2`. VU0 reads the
inputs and sets the flag back to 1. The EE never checks that flag: it overwrites vf1..vf8 and reads the
results (vf9..vf12) a fixed number of instructions later, assuming VU0 already got there. If the EE runs
faster than VU0 (PS4 JIT, PCSX2 300%), VU0 gets half of one joint and half of the next.

Fix: after every release, wait until VU0 sets the flag back (cfc2 k0, viN; beq k0, zero).

  site:   ctc2 zero, viN   ->  j cave
  site+4: X                ->  nop
  cave:   ctc2 zero, viN / loop: until viN != 0 or VU0 stopped (vi29 bit 0) or 65536 spins / X / j site+8
"""
import struct

CTC2_ZERO_VI1 = 0x48C00800
CTC2_ZERO_VI2 = 0x48C01000
CAVE_BASE = 0xFE000


def j(target):
    return 0x08000000 | ((target & 0x0FFFFFFF) >> 2)


def is_branch(w):
    op = w >> 26
    return op in (1, 2, 3, 4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17) or (op == 0 and (w & 0x3F) in (8, 9)) \
        or (op == 0x12 and ((w >> 21) & 31) == 8)


def find_sites(read32, lo, hi):
    """Release points: ctc2 zero, vi1/vi2 inside routines that call vcallms 0 and poll nothing."""
    sites = []
    for a in range(lo, hi, 4):
        w = read32(a)
        if w in (CTC2_ZERO_VI1, CTC2_ZERO_VI2):
            sites.append(a)
    return sites


def build(read32, sites, cave_base=CAVE_BASE):
    """Returns [(addr, orig, new)] for sites + caves (caves have orig None)."""
    out = []
    for i, s in enumerate(sites):
        w0, w1 = read32(s), read32(s + 4)
        assert not is_branch(read32(s - 4)), f'{s:#x} in delay slot'
        assert not is_branch(w1), f'{s + 4:#x} is a branch'
        vi = (w0 >> 11) & 31
        c = cave_base + i * 0x40
        cfc2_k0 = 0x48400000 | (26 << 16) | (vi << 11)
        cfc2_k0_vpustat = 0x48400000 | (26 << 16) | (29 << 11)
        cave = [w0,                 # +0  release VU0
                0x3C1B0001,         # +4  lui k1, 1  (spin cap 65536, never hang)
                cfc2_k0, 0,         # +8  loop: k0 = flag
                0x17400008, 0,      # +16 bne k0, zero, done (+52)  VU0 took the inputs
                cfc2_k0_vpustat,    # +24 k0 = VPU-STAT
                0x277BFFFF,         # +28 addiu k1, k1, -1
                0x335A0001,         # +32 andi k0, k0, 1
                0x13400003, 0,      # +36 beq k0, zero, done        VU0 stopped
                0x1F60FFF6, 0,      # +44 bgtz k1, loop (+8)
                w1, j(s + 8), 0]    # +52 done: original next instruction, back
        for k, x in enumerate(cave):
            out.append((c + k * 4, None, x))
        out.append((s, w0, j(c)))
        out.append((s + 4, w1, 0))
    return out


if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from statepatch import read_state, write_state, SS
    src, dst = int(sys.argv[1]), int(sys.argv[2])
    st = read_state(SS % src)
    mem = bytearray(st['eeMemory.bin'])
    r32 = lambda a: struct.unpack_from('<I', mem, a)[0]
    sites = find_sites(r32, 0x53C818, 0x53D5A0)
    print('sites:', ' '.join(f'{s:#x}' for s in sites))
    for a, orig, new in build(r32, sites):
        assert orig is None or r32(a) == orig
        struct.pack_into('<I', mem, a, new)
    st['eeMemory.bin'] = bytes(mem)
    write_state(SS % dst, st)
    print(f'patched slot {src} -> slot {dst}')
