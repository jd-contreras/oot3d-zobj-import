"""Decode 3DS (PICA200) textures to RGBA. Ported from noclip.website Common/CTR/pica_texture.ts."""
import struct

ETC1, ETC1A4 = 0x675A, 0x675B
RGBA8, RGB8, RGBA5551, RGB565, RGBA4444 = 0x14016752, 0x14016754, 0x80346752, 0x83636754, 0x80336752
LA8, LA4, L8, L4, A8, A4 = 0x14016758, 0x67606758, 0x14016757, 0x67616757, 0x14016756, 0x67616756

_TABLE = [[2, 8, -2, -8], [5, 17, -5, -17], [9, 29, -9, -29], [13, 42, -13, -42],
          [18, 60, -18, -60], [24, 80, -24, -80], [33, 106, -33, -106], [47, 183, -47, -183]]


def _e4(n): return (n << 4) | n
def _e5(n): return (n << 3) | (n >> 2)
def _e6(n): return (n << 2) | (n >> 4)
def _clamp(v): return 0 if v < 0 else 255 if v > 255 else v


def _morton(i):
    return ((i >> 2) & 4) | ((i >> 1) & 2) | (i & 1)


def _tiled(w, h, data, bpp, fn):
    px = [(0, 0, 0, 0)] * (w * h)
    o = 0
    for yy in range(0, h, 8):
        for xx in range(0, w, 8):
            for i in range(64):
                x, y = _morton(i), _morton(i >> 1)
                px[(yy + y) * w + xx + x] = fn(data, o)
                o += bpp
    return px


def _etc1_block(px, w, x0, y0, w1, w2, alpha):
    diff, flip = w1 & 2, w1 & 1
    t1, t2 = _TABLE[(w1 >> 5) & 7], _TABLE[(w1 >> 2) & 7]
    if diff:
        def s3(n): return n - 8 if n & 4 else n
        r1, g1, b1 = (w1 >> 27) & 31, (w1 >> 19) & 31, (w1 >> 11) & 31
        c1 = (_e5(r1), _e5(g1), _e5(b1))
        c2 = (_e5((r1 + s3((w1 >> 24) & 7)) & 31), _e5((g1 + s3((w1 >> 16) & 7)) & 31), _e5((b1 + s3((w1 >> 8) & 7)) & 31))
    else:
        c1 = (_e4((w1 >> 28) & 15), _e4((w1 >> 20) & 15), _e4((w1 >> 12) & 15))
        c2 = (_e4((w1 >> 24) & 15), _e4((w1 >> 16) & 15), _e4((w1 >> 8) & 15))
    for i in range(16):
        look = (((w2 >> (16 + i)) & 1) << 1) | ((w2 >> i) & 1)
        y, x = i & 3, i >> 2
        second = (y & 2) if flip else (x & 2)
        base, tab = (c2, t2) if second else (c1, t1)
        px[(y0 + y) * w + x0 + x] = tuple(_clamp(c + tab[look]) for c in base) + (alpha[y][x],)


def _etc1(w, h, data, has_alpha):
    px = [(0, 0, 0, 255)] * (w * h)
    o = 0
    for yy in range(0, h, 8):
        for xx in range(0, w, 8):
            for y in (0, 4):
                for x in (0, 4):
                    alpha = [[255] * 4 for _ in range(4)]
                    if has_alpha:
                        a = struct.unpack_from('<Q', data, o)[0]
                        o += 8
                        for ax in range(4):
                            for ay in range(4):
                                alpha[ay][ax] = _e4(a & 15)
                                a >>= 4
                    w2, w1 = struct.unpack_from('<II', data, o)
                    o += 8
                    _etc1_block(px, w, xx + x, yy + y, w1, w2, alpha)
    return px


def decode(fmt, w, h, data):
    if fmt == ETC1:
        return _etc1(w, h, data, False)
    if fmt == ETC1A4:
        return _etc1(w, h, data, True)
    if fmt == RGBA8:
        return _tiled(w, h, data, 4, lambda d, o: (d[o + 3], d[o + 2], d[o + 1], d[o]))
    if fmt == RGB8:
        return _tiled(w, h, data, 3, lambda d, o: (d[o + 2], d[o + 1], d[o], 255))
    if fmt == RGB565:
        def f(d, o):
            p = struct.unpack_from('<H', d, o)[0]
            return (_e5(p >> 11), _e6((p >> 5) & 63), _e5(p & 31), 255)
        return _tiled(w, h, data, 2, f)
    if fmt == RGBA5551:
        def f(d, o):
            p = struct.unpack_from('<H', d, o)[0]
            return (_e5(p >> 11), _e5((p >> 6) & 31), _e5((p >> 1) & 31), 255 if p & 1 else 0)
        return _tiled(w, h, data, 2, f)
    if fmt == RGBA4444:
        def f(d, o):
            p = struct.unpack_from('<H', d, o)[0]
            return (_e4(p >> 12), _e4((p >> 8) & 15), _e4((p >> 4) & 15), _e4(p & 15))
        return _tiled(w, h, data, 2, f)
    if fmt == LA8:
        return _tiled(w, h, data, 2, lambda d, o: (d[o + 1], d[o + 1], d[o + 1], d[o]))
    if fmt == L8:
        return _tiled(w, h, data, 1, lambda d, o: (d[o], d[o], d[o], 255))
    if fmt == A8:
        return _tiled(w, h, data, 1, lambda d, o: (255, 255, 255, d[o]))
    if fmt in (LA4,):
        return _tiled(w, h, data, 1, lambda d, o: (_e4(d[o] >> 4),) * 3 + (_e4(d[o] & 15),))
    if fmt in (L4, A4):
        px = [(0, 0, 0, 255)] * (w * h)
        for yy in range(0, h, 8):
            for xx in range(0, w, 8):
                base = ((yy // 8) * (w // 8) + xx // 8) * 32
                for i in range(64):
                    v = d4 = (data[base + i // 2] >> (4 * (i & 1))) & 15
                    x, y = _morton(i), _morton(i >> 1)
                    px[(yy + y) * w + xx + x] = (_e4(v),) * 3 + (255,) if fmt == L4 else (255, 255, 255, _e4(v))
        return px
    raise ValueError('unknown texture format %x' % fmt)


# ---------------------------------------------------------------- encoders

def _q4(v): return max(0, min(15, (v * 15 + 127) // 255))
def _q5(v): return max(0, min(31, (v * 31 + 127) // 255))


def _best_subblock(pixels, base):
    """Pick the intensity table and per-pixel modifiers for one 2x4 subblock."""
    best = None
    for ti, tab in enumerate(_TABLE):
        err, sel = 0, []
        for p in pixels:
            be, bs = None, 0
            for s, m in enumerate(tab):
                e = sum((p[k] - _clamp(base[k] + m)) ** 2 for k in range(3))
                if be is None or e < be:
                    be, bs = e, s
            err += be
            sel.append(bs)
        if best is None or err < best[0]:
            best = (err, ti, sel)
    return best


def _encode_block(px, w, x0, y0):
    """Return (w1, w2) for a 4x4 block, trying both flips, individual and differential modes."""
    def sub(flip, second):
        out = []
        for i in range(16):
            y, x = i & 3, i >> 2
            if ((y & 2) if flip else (x & 2)) == (2 if second else 0):
                out.append((i, px[(y0 + y) * w + x0 + x]))
        return out

    best = None
    for flip in (0, 1):
        s1, s2 = sub(flip, False), sub(flip, True)
        avg = [tuple(sum(p[k] for _, p in s) / len(s) for k in range(3)) for s in (s1, s2)]
        cands = []
        # individual mode: 4-bit bases
        q = [tuple(_q4(int(round(c))) for c in a) for a in avg]
        cands.append((0, q, [tuple(_e4(c) for c in qq) for qq in q]))
        # differential mode: 5-bit base + 3-bit signed delta
        q1 = tuple(_q5(int(round(c))) for c in avg[0])
        q2 = tuple(_q5(int(round(c))) for c in avg[1])
        if all(-4 <= b - a <= 3 for a, b in zip(q1, q2)):
            cands.append((1, (q1, q2), [tuple(_e5(c) for c in q1), tuple(_e5(c) for c in q2)]))
        for diff, qs, bases in cands:
            e1, t1, sel1 = _best_subblock([p for _, p in s1], bases[0])
            e2, t2, sel2 = _best_subblock([p for _, p in s2], bases[1])
            if best is None or e1 + e2 < best[0]:
                best = (e1 + e2, flip, diff, qs, t1, t2, [i for i, _ in s1], sel1, [i for i, _ in s2], sel2)
    _, flip, diff, qs, t1, t2, i1, sel1, i2, sel2 = best
    if diff:
        (r1, g1, b1), (r2, g2, b2) = qs
        w1 = (r1 << 27) | (((r2 - r1) & 7) << 24) | (g1 << 19) | (((g2 - g1) & 7) << 16) | (b1 << 11) | (((b2 - b1) & 7) << 8)
    else:
        (r1, g1, b1), (r2, g2, b2) = qs
        w1 = (r1 << 28) | (r2 << 24) | (g1 << 20) | (g2 << 16) | (b1 << 12) | (b2 << 8)
    w1 |= (t1 << 5) | (t2 << 2) | (2 if diff else 0) | flip
    # table index s -> (msb, lsb): tables are ordered [+small, +large, -small, -large] = lookups 0,1,2,3
    w2 = 0
    for idxs, sels in ((i1, sel1), (i2, sel2)):
        for i, s in zip(idxs, sels):
            w2 |= ((s >> 1) & 1) << (16 + i) | (s & 1) << i
    return w1, w2


def encode_etc1(px, w, h):
    """px: (r,g,b,a) list, top row first, same row order as decode()."""
    out = bytearray()
    for yy in range(0, h, 8):
        for xx in range(0, w, 8):
            for y in (0, 4):
                for x in (0, 4):
                    w1, w2 = _encode_block(px, w, xx + x, yy + y)
                    out += struct.pack('<II', w2, w1)
    return bytes(out)


def encode_rgb565(px, w, h):
    out = bytearray()
    for yy in range(0, h, 8):
        for xx in range(0, w, 8):
            for i in range(64):
                x, y = _morton(i), _morton(i >> 1)
                r, g, b, a = px[(yy + y) * w + xx + x]
                out += struct.pack('<H', ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255))
    return bytes(out)


def encode(fmt, px, w, h):
    if fmt == ETC1:
        return encode_etc1(px, w, h)
    if fmt == RGB565:
        return encode_rgb565(px, w, h)
    raise ValueError('no encoder for %x' % fmt)
