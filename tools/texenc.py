"""Encode RGBA pixels into 3DS (PICA200) tiled texture formats."""
import struct

RGBA8 = 0x14016752


def _morton(i):
    # inverse of noclip's morton7: tile pixel index -> (x, y) inside an 8x8 tile
    x = (i & 1) | ((i >> 1) & 2) | ((i >> 2) & 4)
    y = ((i >> 1) & 1) | ((i >> 2) & 2) | ((i >> 3) & 4)
    return x, y


_ORDER = [_morton(i) for i in range(64)]


def pad_to_tiles(px, w, h):
    """Repeat a texture so both sides are at least 8 (UVs are normalised, so wrapping still matches)."""
    nw, nh = max(w, 8), max(h, 8)
    if (nw, nh) == (w, h):
        return px, w, h
    out = [px[(y % h) * w + (x % w)] for y in range(nh) for x in range(nw)]
    return out, nw, nh


def encode_rgba8(px, w, h):
    """px: list of (r,g,b,a), top row first. Data row 0 is the top row (sampled at v = 1)."""
    assert w % 8 == 0 and h % 8 == 0
    out = bytearray()
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for x, y in _ORDER:
                r, g, b, a = px[(ty + y) * w + tx + x]
                out += struct.pack('<I', (r << 24) | (g << 16) | (b << 8) | a)
    return bytes(out)


def decode_rgba8(data, w, h):
    px = [None] * (w * h)
    k = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for x, y in _ORDER:
                v = struct.unpack_from('<I', data, k)[0]
                k += 4
                px[(ty + y) * w + tx + x] = (v >> 24, (v >> 16) & 255, (v >> 8) & 255, v & 255)
    return px
