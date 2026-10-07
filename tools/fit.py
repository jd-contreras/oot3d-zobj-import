"""Rigid point-cloud fitting (used to seat hand-held items where Link's own item sits)."""
import numpy as np


def kabsch(src, dst):
    """Rotation r, translation t minimising |r @ src + t - dst| for corresponding points."""
    ca, cb = src.mean(0), dst.mean(0)
    u, _, vt = np.linalg.svd((src - ca).T @ (dst - cb))
    d = np.diag([1, 1, np.sign(np.linalg.det(u @ vt))])
    r = (u @ d @ vt).T
    return r, cb - r @ ca


def _nearest(a, b):
    d = ((a[:, None, :] - b[None]) ** 2).sum(-1)
    i = d.argmin(1)
    return i, np.sqrt(d[np.arange(len(a)), i])


def icp(src, dst, iters=60, src_uv=None, dst_uv=None):
    """Rigid ICP of src onto dst (no correspondence needed). Tries the 4 proper PCA-axis flips as
    starting poses. Near-symmetric items fit equally well flipped, so among poses within 15% of the
    best rms the one whose matched points also agree in UV wins (when UVs are given).
    Returns (r, t, rms)."""
    if src_uv is not None:
        src, k = np.unique(src, axis=0, return_index=True)
        src_uv = np.asarray(src_uv)[k]
        dst, k = np.unique(dst, axis=0, return_index=True)
        dst_uv = np.asarray(dst_uv)[k]
    else:
        src, dst = np.unique(src, axis=0), np.unique(dst, axis=0)
    cs, cd = src.mean(0), dst.mean(0)
    As = np.linalg.svd(src - cs)[2]
    Ad = np.linalg.svd(dst - cd)[2]
    cands = []
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        f = np.diag([sx, sy, sx * sy])
        r = Ad.T @ f @ As
        if np.linalg.det(r) < 0:
            r = Ad.T @ np.diag([sx, sy, -sx * sy]) @ As
        t = cd - r @ cs
        for _ in range(iters):
            moved = src @ r.T + t
            i, _ = _nearest(moved, dst)
            r, t = kabsch(src, dst[i])
        _, dist = _nearest(src @ r.T + t, dst)
        _, back = _nearest(dst, src @ r.T + t)
        rms = np.sqrt((dist ** 2).mean() / 2 + (back ** 2).mean() / 2)
        uv_err = 0.0
        if src_uv is not None:
            i, _ = _nearest(src @ r.T + t, dst)
            uv_err = np.abs(src_uv - dst_uv[i]).sum(1).mean()
        cands.append((rms, uv_err, r, t))
    lo = min(c[0] for c in cands)
    rms, _, r, t = min((c for c in cands if c[0] <= lo * 1.15), key=lambda c: (c[1], c[0]))
    return r, t, rms


def fork_ends(a):
    """(handle, tip, tip) of a Y-shaped item (slingshot): the three extreme ends; the two tips are
    the closest pair."""
    a = np.unique(np.asarray(a, float), axis=0)
    c = a.mean(0)
    A = a[np.argmax(((a - c) ** 2).sum(1))]
    B = a[np.argmax(((a - A) ** 2).sum(1))]
    C = a[np.argmax(np.minimum(((a - A) ** 2).sum(1), ((a - B) ** 2).sum(1)))]
    rad = 0.08 * np.ptp(a, 0).max()
    e = [a[((a - x) ** 2).sum(1) < rad ** 2].mean(0) for x in (A, B, C)]
    d = {(i, j): np.linalg.norm(e[i] - e[j]) for i, j in ((0, 1), (0, 2), (1, 2))}
    i, j = min(d, key=d.get)
    k = 3 - i - j
    return np.array([e[k], e[i], e[j]])


def weighted_similarity(src, dst, w):
    """Scale s, rotation r, translation t minimising sum w |s r src + t - dst|^2."""
    w = np.asarray(w, float)[:, None]
    ca, cb = (src * w).sum(0) / w.sum(), (dst * w).sum(0) / w.sum()
    a, b = src - ca, dst - cb
    u, sv, vt = np.linalg.svd((a * w).T @ b)
    d = np.diag([1, 1, np.sign(np.linalg.det(u @ vt))])
    r = (u @ d @ vt).T
    s = np.trace(np.diag(sv) @ d) / (w * a ** 2).sum()
    return s, r, cb - s * r @ ca


def fit_fork(src_pts, dst_pts, tip_weight=4.0):
    """Similarity putting a slingshot's handle and fork tips on another's (the game pins the string to
    the target's tips). Tip order is chosen by the smaller residual. Returns (s, r, t, tip error)."""
    se, de = fork_ends(src_pts), fork_ends(dst_pts)
    best = None
    for order in ([0, 1, 2], [0, 2, 1]):
        s, r, t = weighted_similarity(se[order], de, [1, tip_weight, tip_weight])
        err = np.linalg.norm(s * se[order] @ r.T + t - de, axis=1)[1:].max()
        if best is None or err < best[3]:
            best = (s, r, t, err)
    return best
