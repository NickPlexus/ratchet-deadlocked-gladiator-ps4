"""Patch EE memory inside a PCSX2 savestate (.p2s zip) and write it to another slot.

Code is patched only where the word in memory equals the word in the ELF (so we never touch data).
usage (python): from statepatch import patch_state, cop2_all_interlock
"""
import struct, sys, zipfile, os
import zstandard

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))  # ee_dis.py
from ee_dis import load

SS = os.environ.get('DL_SSTATE', os.path.expanduser(r'~/Documents/PCSX2/sstates/SCUS-97465 (C84B9CFE).%02d.p2s'))
BOOT = os.environ.get('DL_BOOT_ELF', 'Unpacked/boot_elf.elf')  # from a Wrench unpack
LVL1 = os.environ.get('DL_LVL1_OVERLAY', 'Unpacked/levels/campaign/1_dreadzone_station/overlay.elf')
OVERLAY_LO = 0x21E180


def code_words(elf, lo=0, hi=0x2000000):
    for va, b in load(elf):
        for i in range(len(b) // 4):
            a = va + i * 4
            if lo <= a < hi:
                yield a, struct.unpack_from('<I', b, i * 4)[0]


def cop2_xfer(w):
    if (w >> 26) != 0x12 or (w >> 25) & 1:
        return None
    return {1: 'qmfc2', 2: 'cfc2', 5: 'qmtc2', 6: 'ctc2'}.get((w >> 21) & 0x1F)


def cop2_all_interlock(kinds=('qmfc2', 'cfc2', 'qmtc2', 'ctc2')):
    """Every non-interlocked COP2 transfer in core + level-1 code -> set I bit."""
    out = []
    for elf, lo, hi in ((BOOT, 0, OVERLAY_LO), (LVL1, OVERLAY_LO, 0x2000000)):
        for a, w in code_words(elf, lo, hi):
            k = cop2_xfer(w)
            if k in kinds and not (w & 1):
                out.append((a, w, w | 1))
    return out


def read_state(path):
    """{name: bytes}; PCSX2 stores members with zstd (zip method 93), which zipfile can't read."""
    out = {}
    with open(path, 'rb') as f:
        for zi in zipfile.ZipFile(path).infolist():
            f.seek(zi.header_offset)
            h = f.read(30)
            n, e = struct.unpack_from('<HH', h, 26)
            f.seek(zi.header_offset + 30 + n + e)
            raw = f.read(zi.compress_size)
            out[zi.filename] = (zstandard.ZstdDecompressor().decompress(raw, max_output_size=zi.file_size)
                                if zi.compress_type == 93 else raw)
    return out


def write_state(path, members):
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    os.replace(tmp, path)


def patch_state(src_slot, dst_slot, patches, label=''):
    st = read_state(SS % src_slot)
    mem = bytearray(st['eeMemory.bin'])
    n = skipped = 0
    for a, orig, new in patches:
        cur = struct.unpack_from('<I', mem, a)[0]
        if cur == orig:
            struct.pack_into('<I', mem, a, new); n += 1
        else:
            skipped += 1
    st['eeMemory.bin'] = bytes(mem)
    write_state(SS % dst_slot, st)
    print(f'{label}: patched {n}, skipped {skipped} (memory != ELF) -> slot {dst_slot}')
    return n


if __name__ == '__main__':
    p = cop2_all_interlock()
    from collections import Counter
    print(Counter(cop2_xfer(o) for _, o, _ in p))
    patch_state(1, 5, p, 'cop2 all-interlock')
