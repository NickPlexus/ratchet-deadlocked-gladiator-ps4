"""Check that a compressed WAD block respects the 0x2000-byte chunk rule (no packet straddles a chunk)."""
import json, struct, sys


def packets(buf):
    """Yield (stream_pos, packet_size, flag) for a compressed block (stream starts after the 0x10 header)."""
    size = struct.unpack_from('<i', buf, 3)[0]
    p = 0x10
    while p < size:
        start = p
        flag = buf[p]; p += 1
        if flag < 0x10:
            ln = flag + 3 if flag else buf[p] + 18
            if not flag:
                p += 1
            p += ln
            yield start - 0x10, p - start, flag
            continue
        if flag < 0x20:
            if (flag & 7) == 0:
                p += 1
            b0, b1 = buf[p], buf[p + 1]; p += 2
            if (flag & 8) * 0x800 + b1 * 0x40 + (b0 >> 2) == 0 and (flag & 7) != 1:
                yield start - 0x10, p - start, flag     # pad packet
                while (p - 0x10) % 0x1000:
                    p += 1
                continue
        elif flag < 0x40:
            if (flag & 0x1f) == 0:
                p += 1
            p += 2
        else:
            p += 1
        p += buf[p - 2] & 3
        yield start - 0x10, p - start, flag


def check(buf):
    bad = []
    for pos, sz, flag in packets(buf):
        if flag == 0x12:
            continue
        if (pos % 0x2000) + sz > 0x2000:
            bad.append((pos, sz))
    return bad


if __name__ == '__main__':
    iso = open(sys.argv[1], 'rb')
    blocks = json.load(open(sys.argv[2]))
    total = 0
    for b in blocks:
        iso.seek(b['offset'])
        buf = iso.read(b['csize'] + 16)
        bad = check(buf)
        total += len(bad)
        if bad:
            print(hex(b['offset']), 'straddling packets:', len(bad), [hex(x) for x, _ in bad[:5]])
    print('blocks', len(blocks), 'straddling packets total', total)
