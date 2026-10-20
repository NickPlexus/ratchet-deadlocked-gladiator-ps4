"""Export / import the Deadlocked Russian text for editing.

  python text_tool.py export <unpacked_dir> <out_dir>
      -> strings.tsv   (main language table: globals/misc/boot/english.bin)
      -> subtitles.tsv (cutscene subtitles: globals/mpeg/*/*.asset, text_e)
  python text_tool.py import <unpacked_dir> <edited_dir>
      -> rewrites english.bin and the subtitle text_e fields in place

TSV columns: key, ru (editable), reference columns (fr/es/de/it or en).
Only the "ru" column is read back on import.
"""
import csv, glob, os, re, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_rus import decode, encode, escape  # noqa: E402

BOOT = os.path.join('globals', 'misc', 'boot')
# On the US disc the non-English tables hold the original English text (lower case).
REF_LANGS = ['french']


def read_table(path):
    d = open(path, 'rb').read()
    first = struct.unpack_from('<I', d, 0)[0]
    entries = []  # (header bytes, string bytes or None)
    for i in range(0, first, 16):
        hdr = d[i:i + 16]
        off = struct.unpack_from('<I', hdr, 0)[0]
        s = d[off:d.index(b'\0', off)] if 0 < off < len(d) else None
        entries.append((hdr, s))
    return entries


def write_table(path, entries, align=1):
    # Header entries keep everything but the offset; strings are laid out after the header.
    n = len(entries)
    body = bytearray()
    hdrs = bytearray()
    base = n * 16
    for hdr, s in entries:
        h = bytearray(hdr)
        if s is not None:
            struct.pack_into('<I', h, 0, base + len(body))
            body += s + b'\0'
            while len(body) % align:
                body += b'\0'
        hdrs += h
    open(path, 'wb').write(bytes(hdrs + body))


def ids(entries):
    return [struct.unpack_from('<H', h, 4)[0] for h, _ in entries]


SUB_RE = re.compile(r'(Subtitle (\d+) \{.*?\r?\n\t\t\})', re.S)
FIELD_RE = lambda f: re.compile(r'(\t\t\t%s: ")((?:[^"\\]|\\.)*)(")' % f)


def unq(s):
    return re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), s).replace('\\"', '"').replace('\\\\', '\\')


def q(s):
    out = []
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif 0x20 <= ord(ch) < 0x7f:
            out.append(ch)
        else:
            out.append('\\x%02x' % ord(ch))
    return ''.join(out)


def subtitle_files(root):
    return sorted(glob.glob(os.path.join(root, 'globals', 'mpeg', '*', '*.asset')),
                  key=lambda p: int(os.path.basename(os.path.dirname(p))))


def export(root, out):
    os.makedirs(out, exist_ok=True)
    eng = read_table(os.path.join(root, BOOT, 'english.bin'))
    refs = {}
    for lang in REF_LANGS:
        t = read_table(os.path.join(root, BOOT, lang + '.bin'))
        refs[lang] = {i: s for i, (h, s) in zip(ids(t), t)}
    with open(os.path.join(out, 'strings.tsv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
        w.writerow(['idx', 'id', 'ru', 'en'])
        for idx, ((h, s), sid) in enumerate(zip(eng, ids(eng))):
            if s is None:
                continue
            w.writerow([idx, '%04x' % sid, decode(s)] +
                       [escape(refs[l].get(sid) or b'') for l in REF_LANGS])
    with open(os.path.join(out, 'subtitles.tsv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['mpeg', 'sub', 'start', 'ru', 'en'])
        for p in subtitle_files(root):
            txt = open(p, encoding='latin-1', newline='').read()
            m_id = os.path.basename(os.path.dirname(p))
            for block, n in SUB_RE.findall(txt):
                e = FIELD_RE('text_e').search(block)
                fr = FIELD_RE('text_f').search(block)
                st = re.search(r'start_time: ([\d.]+)', block)
                if not e:
                    continue
                w.writerow([m_id, n, st.group(1) if st else '',
                            decode(unq(e.group(2)).encode('latin-1')),
                            escape(unq(fr.group(2)).encode('latin-1')) if fr else ''])
    print('exported to', out)


def load_tsv(path):
    with open(path, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def do_import(root, src):
    path = os.path.join(root, BOOT, 'english.bin')
    eng = read_table(path)
    changed = 0
    for row in load_tsv(os.path.join(src, 'strings.tsv')):
        i = int(row['idx'])
        new = encode(row['ru'])
        if eng[i][1] != new:
            eng[i] = (eng[i][0], new)
            changed += 1
    write_table(path, eng)
    print('strings changed:', changed)

    subs = {}
    for row in load_tsv(os.path.join(src, 'subtitles.tsv')):
        subs[(row['mpeg'], row['sub'])] = encode(row['ru']).decode('latin-1')
    sc = 0
    for p in subtitle_files(root):
        m_id = os.path.basename(os.path.dirname(p))
        txt = open(p, encoding='latin-1', newline='').read()

        def fix(m):
            nonlocal sc
            block, n = m.group(1), m.group(2)
            new = subs.get((m_id, n))
            if new is None:
                return block
            r = FIELD_RE('text_e')
            old = r.search(block)
            if old and unq(old.group(2)) != new:
                sc += 1
                return r.sub(lambda mm: mm.group(1) + q(new) + mm.group(3), block, count=1)
            return block
        out = SUB_RE.sub(fix, txt)
        if out != txt:
            open(p, 'w', encoding='latin-1', newline='').write(out)
    print('subtitles changed:', sc)


if __name__ == '__main__':
    cmd, a, b = sys.argv[1:4]
    export(a, b) if cmd == 'export' else do_import(a, b)
