"""Minimal OoT3D CSAB reader (layout from noclip.website csab.ts)."""
import struct

AXES = ('tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz')


def _track(d, o, rot16):
    typ, n, t0, t1 = struct.unpack_from('<IIII', d, o)
    p, frames = o + 0x10, []
    for _ in range(n):
        if typ == 2 and rot16:  # hermite, int16
            t, v, ti, to = struct.unpack_from('<Hhhh', d, p); p += 8
        elif typ == 2:  # hermite
            t, v, ti, to = struct.unpack_from('<Ifff', d, p); p += 16
        elif rot16:  # linear, int16 rotation
            t, v = struct.unpack_from('<Hh', d, p); p += 4
        else:  # linear
            t, v = struct.unpack_from('<If', d, p); p += 8
        frames.append((t, v))
    return typ, frames


def read(d):
    assert d[:4] == b'csab'
    duration = struct.unpack_from('<I', d, 0x28)[0] + 1
    anodc, bonec = struct.unpack_from('<II', d, 0x30)
    t = (0x38 + 2 * bonec + 3) & ~3
    nodes = {}
    for i in range(anodc):
        o = 0x18 + struct.unpack_from('<I', d, t + 4 * i)[0]
        bone, rot16 = struct.unpack_from('<HH', d, o + 4)
        offs = struct.unpack_from('<9H', d, o + 8)
        nodes[bone] = {a: _track(d, o + off, rot16 and a[0] == 'r') for a, off in zip(AXES, offs) if off}
    return duration, nodes


def patch_translations(d, old, new, delta, eps=0.5):
    """Rewrite translation keys so they follow a refitted skeleton.

    Keys equal to the old bind translation become the new one; other keys are shifted by the
    bone's translation delta. Returns new bytes (same size)."""
    out = bytearray(d)
    anodc, bonec = struct.unpack_from('<II', d, 0x30)
    t = (0x38 + 2 * bonec + 3) & ~3
    for i in range(anodc):
        o = 0x18 + struct.unpack_from('<I', d, t + 4 * i)[0]
        bone = struct.unpack_from('<H', d, o + 4)[0]
        if bone not in delta:
            continue
        for k, off in enumerate(struct.unpack_from('<3H', d, o + 8)):
            if not off:
                continue
            p = o + off
            typ, n = struct.unpack_from('<II', d, p)
            stride = 16 if typ == 2 else 8
            for j in range(n):
                vo = p + 0x10 + j * stride + 4
                v = struct.unpack_from('<f', d, vo)[0]
                nv = new[bone][k] if abs(v - old[bone][k]) < eps else v + delta[bone][k]
                struct.pack_into('<f', out, vo, nv)
    return bytes(out)
