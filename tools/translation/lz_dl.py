"""Insomniac PS2 "WAD" LZ compressor with a tighter parse than Wrench's.

Packet format (see Wrench src/engine/compression.cpp, decompress_packet):
  0x00-0x0f  literal: flag 1..15 -> flag+3 bytes; flag 0 -> next byte + 18 bytes.
             A literal packet may not be followed by another literal packet.
  0x10-0x1f  far match: len = flag&7 (0 -> next byte + 7), then +2; b0, b1;
             offset = 0x4000 + (flag&8)*0x800 + b1*0x40 + (b0>>2).  b0&3 = trailing literals.
             0x11 00 00 is a "dummy" packet that only carries trailing literals;
             0x12 00 00 is the pad packet that skips to the next 0x1000 boundary.
  0x20-0x3f  match: len = (flag&0x1f)+2 (0 -> next byte + 0x1f + 2); b1, b2;
             offset = b2*0x40 + (b1>>2) + 1.  b1&3 = trailing literals.
  0x40-0xff  little match: len = (flag>>5)+1, offset = b1*8 + ((flag>>2)&7) + 1.  flag&3 = trailing literals.
The compressed stream is consumed in 0x2000-byte chunks: no packet may straddle one, so a pad
packet + 0xEE filler is inserted before a packet that would.
"""
import struct

MAX_LIT = 273
WINDOW = 32704          # same safe far range as Wrench (a == 0)
MAX_LEN = 264           # far big match limit; plain big match goes to 288 but keep one limit
CHAIN_DEPTH = 256


def _match_cost(length, off):
    if length <= 8 and off <= 2048:
        return 2
    if off <= 16384:
        return 3 if length <= 33 else 4
    return 3 if length <= 9 else 4


def _encode_match(length, off):
    if length <= 8 and off <= 2048:
        a, b = (off - 1) % 8, (off - 1) // 8
        return bytearray([((length - 1) << 5) | (a << 2), b])
    if off <= 16384:
        a, b = (off - 1) % 0x40, (off - 1) // 0x40
        if length > 33:
            return bytearray([0x20, length - 33, a << 2, b])
        return bytearray([0x20 | (length - 2), a << 2, b])
    d = off - 0x4000
    b, c = d % 0x40, d // 0x40
    if length > 9:
        return bytearray([0x10, length - 9, b << 2, c])
    return bytearray([0x10 | (length - 2), b << 2, c])


class _Finder:
    def __init__(self, data):
        self.d = data
        self.n = len(data)
        self.head = {}
        self.prev = [-1] * self.n
        self.ins = 0

    def insert_upto(self, pos):
        d = self.d
        while self.ins < pos and self.ins + 2 < self.n:
            k = d[self.ins:self.ins + 3]
            self.prev[self.ins] = self.head.get(k, -1)
            self.head[k] = self.ins
            self.ins += 1

    def best(self, i):
        """Best (gain, length, offset) match at i, preferring cheap encodings."""
        d, n = self.d, self.n
        if i + 3 > n:
            return None
        self.insert_upto(i)
        cand = self.head.get(d[i:i + 3], -1)
        maxlen = min(MAX_LEN, n - i)
        best = None
        depth = 0
        while cand >= 0 and i - cand <= WINDOW and depth < CHAIN_DEPTH:
            depth += 1
            off = i - cand
            # extend
            l = 3
            if best is None or d[cand + (best[1] if best[1] < maxlen else 0)] == d[i + (best[1] if best[1] < maxlen else 0)]:
                while l < maxlen and d[cand + l] == d[i + l]:
                    step = min(16, maxlen - l)
                    if d[cand + l:cand + l + step] == d[i + l:i + l + step]:
                        l += step
                    else:
                        while l < maxlen and d[cand + l] == d[i + l]:
                            l += 1
                        break
                gain = l - _match_cost(l, off)
                if best is None or gain > best[0]:
                    best = (gain, l, off)
                    if l == maxlen:
                        break
            cand = self.prev[cand]
        if best and best[0] <= 0:
            return None
        return best


def compress(data, muffin=b'WRENCH010'):
    data = bytes(data)
    n = len(data)
    f = _Finder(data)
    packets = []          # list of bytearrays; trailing literals merged into the previous match packet
    last_kind = 'start'   # 'start' | 'lit' | 'match' (match slot free) | 'match_full'
    lits = bytearray()

    def flush_literals():
        nonlocal last_kind, lits
        while lits:
            if len(lits) <= 3 and last_kind == 'match':
                p = packets[-1]
                p[len(p) - 2] |= len(lits)
                p += lits
                last_kind = 'match_full'
                lits = bytearray()
            elif len(lits) <= 3 or last_kind == 'lit':
                # dummy packet carrying up to 3 literals (also separates two literal packets)
                k = min(3, len(lits))
                packets.append(bytearray([0x11, k, 0]) + lits[:k])
                lits = lits[k:]
                last_kind = 'match_full'
            else:
                k = min(MAX_LIT, len(lits))
                pkt = bytearray([k - 3]) if k <= 18 else bytearray([0, k - 18])
                packets.append(pkt + lits[:k])
                lits = lits[k:]
                last_kind = 'lit'

    i = 0
    while i < n:
        m = f.best(i)
        if m:
            # lazy evaluation: prefer a clearly better match one or two bytes later
            m1 = f.best(i + 1) if i + 1 < n else None
            if m1 and m1[0] > m[0] + 1:
                lits.append(data[i]); i += 1
                continue
            flush_literals()
            gain, length, off = m
            packets.append(_encode_match(length, off))
            last_kind = 'match'
            i += length
        else:
            lits.append(data[i]); i += 1
    flush_literals()

    # pad to keep packets inside 0x2000-byte chunks (mirrors Wrench append_buffer)
    out = bytearray(b'WAD' + b'\0\0\0\0' + muffin[:9].ljust(9, b'\0'))
    for p in packets:
        pos = len(out) - 0x10
        if (pos % 0x2000) + len(p) > 0x2000 - 3:
            out += b'\x12\x00\x00'
            while (len(out) - 0x10) % 0x2000 != 0:
                out.append(0xEE)
        out += p
    struct.pack_into('<i', out, 3, len(out))
    return bytes(out)


def decompress(buf):
    """Reference decoder (port of Wrench's) used to self-check compress()."""
    size = struct.unpack_from('<i', buf, 3)[0]
    end = size
    p = 0x10
    begin = 0x10
    dst = bytearray()
    while p < end:
        flag = buf[p]; p += 1
        if flag < 0x10:
            ln = flag + 3 if flag else buf[p] + 18
            if not flag:
                p += 1
            dst += buf[p:p + ln]; p += ln
            continue
        if flag < 0x20:
            ml = flag & 7
            if ml == 0:
                ml = buf[p] + 7; p += 1
            b0, b1 = buf[p], buf[p + 1]; p += 2
            back = (flag & 8) * 0x800 + b1 * 0x40 + (b0 >> 2)
            if back:
                ml += 2
                src = len(dst) - back - 0x4000
            elif ml != 1:
                while (p - begin) % 0x1000:
                    p += 1
                continue
            else:
                src = None
        elif flag < 0x40:
            ml = flag & 0x1f
            if ml == 0:
                ml = buf[p] + 0x1f; p += 1
            ml += 2
            b1, b2 = buf[p], buf[p + 1]; p += 2
            src = len(dst) - b2 * 0x40 - (b1 >> 2) - 1
        else:
            b1 = buf[p]; p += 1
            src = len(dst) - b1 * 8 - ((flag >> 2) & 7) - 1
            ml = (flag >> 5) + 1
        if ml != 1:
            for k in range(ml):
                dst.append(dst[src + k])
        lit = buf[p - 2] & 3
        dst += buf[p:p + lit]; p += lit
    return bytes(dst)


if __name__ == '__main__':
    import sys, time
    src = open(sys.argv[1], 'rb').read()
    t = time.time()
    c = compress(src)
    assert decompress(c) == src, 'self-check failed'
    open(sys.argv[2], 'wb').write(c)
    print(f'{len(src)} -> {len(c)} bytes in {time.time() - t:.1f}s')
