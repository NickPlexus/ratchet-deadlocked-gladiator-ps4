"""Find every compressed block in the ISO that holds the language table (boot + one per level)."""
import json, os, struct, subprocess, sys, tempfile

def scan(iso, wrench, table, out_json):
    head = table[:64]
    hits = []
    f = open(iso, 'rb')
    CH = 64 << 20
    pos = 0
    tail = b''
    tmp = tempfile.mkdtemp()
    while True:
        buf = f.read(CH)
        if not buf:
            break
        data = tail + buf
        base = pos - len(tail)
        i = data.find(b'WAD')
        while i >= 0:
            if i + 7 <= len(data):
                size = struct.unpack_from('<I', data, i + 3)[0]
                if 0x1000 < size < 0x400000:
                    hits.append((base + i, size))
            i = data.find(b'WAD', i + 1)
        tail = data[-8:]
        pos += len(buf)
    print('WAD candidates:', len(hits), flush=True)
    found = []
    seen = set()
    for off, size in hits:
        if off in seen:
            continue
        seen.add(off)
        out = os.path.join(tmp, 'u.bin')
        if os.path.exists(out):
            os.remove(out)
        subprocess.run([wrench, 'decompress', iso, '-o', out, '-x', hex(off)], capture_output=True)
        if not os.path.exists(out):
            continue
        b = open(out, 'rb').read()
        h = b.find(head)
        if h >= 0 and b[h:h + len(table)] == table:
            f.seek(off + size)
            after = f.read(0x40000)
            free = len(after) - len(after.lstrip(b'\0'))
            found.append({'offset': off, 'csize': size, 'usize': len(b), 'table_at': h, 'free_after': free})
            print(hex(off), hex(size), 'table@', hex(h), 'zeros after', hex(free), flush=True)
    json.dump(found, open(out_json, 'w'), indent=1)
    return found

if __name__ == '__main__':
    iso, wrench, table, out = sys.argv[1:5]
    scan(iso, wrench, open(table, 'rb').read(), out)
