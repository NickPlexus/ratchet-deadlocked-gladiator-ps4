"""Patch edited text straight into a copy of the original ISO (no Wrench repack).

Wrench's full repack rebuilds every LEVELn.WAD, and the repacked levels do not load.
This patcher keeps the original disc layout and only rewrites:
  * the language table: 1 copy in the boot WAD + 2 copies in every level WAD (95 in total),
    each stored LZ-compressed; we decompress, swap the table, recompress, and write the block
    back into its own slot;
  * cutscene subtitles: stored uncompressed as <ru>\\0<en>\\0 pairs; the new Russian may use
    the space of both strings (the English copy is only shown with the French language).

usage: python iso_patch.py <original iso> <text dir with strings.tsv/subtitles.tsv> <output iso>
"""
import csv, hashlib, json, os, shutil, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.dirname(HERE)
ROOT = os.path.dirname(TR)
sys.path.insert(0, HERE)
from dl_rus import encode  # noqa: E402
from text_tool import read_table, write_table, load_tsv  # noqa: E402
import find_text_blocks  # noqa: E402
import lz_dl  # noqa: E402

WRENCH = os.path.join(ROOT, 'Tools', 'wrench', 'wrench_v0.6_windows', 'wrenchbuild.exe')
ORIG_TABLE = os.path.join(TR, 'backup_rus1', 'english.bin')
BLOCKS_JSON = os.path.join(TR, 'text_blocks_rus1.json')
SUBS_JSON = os.path.join(TR, 'subtitle_slots_rus1.json')
ORIG_TEXT = os.path.join(TR, 'text_rus1')


def log(*a):
    print(*a, flush=True)


def build_table(text_dir):
    entries = read_table(ORIG_TABLE)
    for row in load_tsv(os.path.join(text_dir, 'strings.tsv')):
        i = int(row['idx'])
        entries[i] = (entries[i][0], encode(row['ru']))
    tmp = os.path.join(tempfile.mkdtemp(), 't.bin')
    write_table(tmp, entries)
    return open(tmp, 'rb').read()


def wrench(*args):
    r = subprocess.run([WRENCH, *args], capture_output=True, text=True)
    return r


def slot_size(iso, blk):
    """Bytes available for a compressed block. Boot WAD entries are listed in a ToC right before them."""
    off = blk['offset']
    if off % 0x800 == 0x80:
        iso.seek(off - 0x80)
        toc = struct.unpack('<4I', iso.read(16))
        if toc[0] == 0x80:
            return toc[2] - 0x80
    return blk['csize']


def find_subtitle_slots(iso_path):
    """Locate every Russian subtitle string (and the English one after it) in the ISO."""
    subs = load_tsv(os.path.join(ORIG_TEXT, 'subtitles.tsv'))
    subs.sort(key=lambda r: (int(r['mpeg']), int(r['sub'])))
    want = {}   # exact "<ru>\0<en>\0" pair -> subtitle keys in disc order
    for r in subs:
        b = encode(r['ru']) + b'\0' + encode(r['en']) + b'\0'
        want.setdefault(b, []).append(r['mpeg'] + '/' + r['sub'])
    import re
    f = open(iso_path, 'rb')
    size = os.path.getsize(iso_path)
    probe = re.compile(b'|'.join(re.escape(k[:24]) for k in want))
    occ = {k: set() for k in want}
    CH = 64 << 20
    for start in range(0, size, CH):
        f.seek(start)
        buf = f.read(CH + 8192)
        if not probe.search(buf):
            continue
        for k in want:
            j = buf.find(k)
            while j >= 0:
                occ[k].add(start + j)
                j = buf.find(k, j + 1)
    slots = {}   # key -> list of places (some cutscenes exist twice on the disc)
    for k, keys in want.items():
        places = sorted(occ[k])
        n = len(keys)
        if not places or len(places) % n:
            continue        # ambiguous or missing: leave these lines alone
        copies = len(places) // n
        for idx, key in enumerate(keys):
            for p in places[idx::n] if copies == 1 else [places[c * n + idx] for c in range(copies)]:
                f.seek(p + len(k))
                pad = f.read(3)
                extra = len(pad) - len(pad.lstrip(b'\0'))   # alignment zeros after the English string
                # new Russian may use its own bytes + the English copy + alignment; last byte stays NUL
                slots.setdefault(key, []).append({'offset': p, 'ru_len': k.index(b'\0'), 'room': len(k) - 1 + extra})
    return slots


def main(orig_iso, text_dir, out_iso):
    if not os.path.exists(BLOCKS_JSON):
        log('Ищу копии таблицы текста на диске (один раз, ~5 минут)…')
        find_text_blocks.scan(orig_iso, WRENCH, open(ORIG_TABLE, 'rb').read(), BLOCKS_JSON)
    blocks = json.load(open(BLOCKS_JSON))
    orig_table = open(ORIG_TABLE, 'rb').read()
    new_table = build_table(text_dir)
    if len(new_table) > len(orig_table):
        sys.exit(f'Таблица стала больше исходной на {len(new_table) - len(orig_table)} байт — сократите текст.')
    new_padded = new_table + b'\0' * (len(orig_table) - len(new_table))

    log('Копирую ISO…')
    shutil.copyfile(orig_iso, out_iso)
    src = open(orig_iso, 'rb')
    dst = open(out_iso, 'r+b')
    tmp = tempfile.mkdtemp()
    cache = {}
    changed_table = new_padded != orig_table
    for n, blk in enumerate(blocks if changed_table else [], 1):
        u = os.path.join(tmp, 'u.bin')
        c = os.path.join(tmp, 'c.bin')
        wrench('decompress', orig_iso, '-o', u, '-x', hex(blk['offset']))
        data = bytearray(open(u, 'rb').read())
        at = blk['table_at']
        if bytes(data[at:at + len(orig_table)]) != orig_table:
            sys.exit(f'Блок {hex(blk["offset"])}: таблица не совпадает с ожидаемой — это не тот ISO?')
        data[at:at + len(orig_table)] = new_padded
        h = hashlib.sha1(data).hexdigest()
        if h not in cache:
            open(u, 'wb').write(data)
            if os.path.exists(c):
                os.remove(c)
            wrench('compress', u, '-o', c)
            cache[h] = open(c, 'rb').read()
        comp = cache[h]
        room = slot_size(src, blk)
        if len(comp) > room:
            # Wrench's greedy parser is not tight enough here; use our own encoder (self-checked).
            comp = lz_dl.compress(bytes(data))
            if lz_dl.decompress(comp) != bytes(data):
                sys.exit('Внутренняя ошибка компрессора')
            cache[h] = comp
        if len(comp) > room:
            sys.exit(f'Блок {hex(blk["offset"])}: после сжатия {len(comp)} байт, а места {room}. Сократите текст.')
        dst.seek(blk['offset'])
        dst.write(comp + b'\0' * max(0, blk['csize'] - len(comp)))
        log(f'  таблица {n}/{len(blocks)}: {hex(blk["offset"])} {blk["csize"]} -> {len(comp)} (место {room})')

    # subtitles
    subs_new = {r['mpeg'] + '/' + r['sub']: r['ru'] for r in load_tsv(os.path.join(text_dir, 'subtitles.tsv'))}
    subs_old = {r['mpeg'] + '/' + r['sub']: r['ru'] for r in load_tsv(os.path.join(ORIG_TEXT, 'subtitles.tsv'))}
    todo = {k: v for k, v in subs_new.items() if subs_old.get(k) != v}
    if todo:
        if not os.path.exists(SUBS_JSON):
            log('Ищу субтитры на диске (один раз)…')
            json.dump(find_subtitle_slots(orig_iso), open(SUBS_JSON, 'w'), indent=1)
        slots = json.load(open(SUBS_JSON))
        problems = []
        for k, text in todo.items():
            places = slots.get(k)
            b = encode(text)
            if not places:
                problems.append(f'ролик {k}: место строки на диске не найдено')
                continue
            room = min(s['room'] for s in places)
            if len(b) > room:
                problems.append(f'ролик {k}: {len(b)} байт, помещается {room}')
                continue
            for s in places:
                dst.seek(s['offset'])
                dst.write(b + b'\0' * (s['room'] + 1 - len(b)))
        log(f'Субтитров изменено: {len(todo) - len(problems)}')
        for p in problems:
            log('  ! ' + p)
    dst.close()
    log('Готово:', out_iso)


if __name__ == '__main__':
    main(*sys.argv[1:4])
