"""Compare two PCSX2 savestate memory dumps: find 4x4 float matrices that are sane in A and broken in B."""
import sys, struct, math
import numpy as np


def load(path):
    return np.frombuffer(open(path, 'rb').read(), dtype='<f4')


def sane_rows(m):
    """m: (N,4,4). A bone/world matrix: 3 basis rows with length 0.05..20, finite, row3 finite and
    |t| < 1e5, column w of rows 0..2 ~ 0."""
    fin = np.isfinite(m).all(axis=(1, 2))
    basis = np.linalg.norm(m[:, :3, :3], axis=2)
    ok_len = ((basis > 0.05) & (basis < 20)).all(axis=1)
    ok_t = (np.abs(m[:, 3, :3]) < 1e5).all(axis=1)
    ok_w = (np.abs(m[:, :3, 3]) < 1e-3).all(axis=1)
    return fin & ok_len & ok_t & ok_w


def main(a_path, b_path, base=0):
    A, B = load(a_path), load(b_path)
    n = len(A) // 16
    ma, mb = A[:n * 16].reshape(n, 4, 4), B[:n * 16].reshape(n, 4, 4)
    with np.errstate(all='ignore'):
        sa, sb = sane_rows(ma.astype(np.float64)), sane_rows(mb.astype(np.float64))
    good_bad = np.nonzero(sa & ~sb)[0]
    print(f'sane in A: {sa.sum()}  sane in B: {sb.sum()}  sane-in-A-but-not-B: {len(good_bad)}')
    # cluster addresses
    runs = []
    for i in good_bad:
        a = base + i * 64
        if runs and a - runs[-1][1] <= 0x400:
            runs[-1][1] = a; runs[-1][2] += 1
        else:
            runs.append([a, a, 1])
    runs.sort(key=lambda r: -r[2])
    for r in runs[:25]:
        print(f'  {r[0]:08X}-{r[1]:08X}  {r[2]} matrices')
    return runs


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3], 16) if len(sys.argv) > 3 else 0)
