"""Custom N64 player animations (an ML64 link_animetion .zdata) -> OoT3D .csab animations.

Only the animations a bank changes from vanilla are converted (fingerprints in anim_tables.VANILLA).
Each OoT3D bone driven by an N64 limb takes that limb's world rotation times a fitted constant
correction (anim_tables.CALIB); bones without an N64 limb (clavicles, bow string, model root) keep
OoT3D's own motion for that animation. Root translation follows anim_tables.ROOT.
"""
import struct, hashlib
import numpy as np

import csab, animview, n64anim, anim_tables

ZDATA_SIZE = 0x265C30
ROT16 = 0x8000 / np.pi
AXES = csab.AXES  # tx ty tz rx ry rz sx sy sz


def is_anim_bank(data):
    return len(data) == ZDATA_SIZE


def changed(zdata):
    """N64 names of the animations a link_animetion bank changes from vanilla."""
    out = []
    for name, fc, off in anim_tables.ANIMS:
        h = hashlib.sha1(zdata[off:off + n64anim.FRAME_SIZE * fc]).hexdigest()[:16]
        if h != anim_tables.VANILLA[name]:
            out.append(name)
    return out


def _resample(rots, trans, count):
    """N64 frames resampled to `count` frames (OoT3D sometimes retimed an animation)."""
    n = len(rots)
    if n == count:
        return rots, trans
    t = np.linspace(0, n - 1, count)
    i0 = np.floor(t).astype(int)
    i1 = np.minimum(i0 + 1, n - 1)
    a = (t - i0)[:, None, None]
    d = (rots[i1] - rots[i0] + np.pi) % (2 * np.pi) - np.pi  # shortest way round
    return rots[i0] + d * a, trans[i0] + (trans[i1] - trans[i0]) * a[:, :, 0]


def _track_size(d, o, rot16):
    typ, n = struct.unpack_from('<II', d, o)
    key = (8 if rot16 else 16) if typ == 2 else (4 if rot16 else 8)
    return 0x10 + n * key


def _anod_blobs(d):
    """Original anods: {bone: (raw bytes, rot16, {axis: raw track bytes})}."""
    anodc, bonec = struct.unpack_from('<II', d, 0x30)
    t = (0x38 + 2 * bonec + 3) & ~3
    out = {}
    for i in range(anodc):
        o = 0x18 + struct.unpack_from('<I', d, t + 4 * i)[0]
        bone, rot16 = struct.unpack_from('<HH', d, o + 4)
        offs = struct.unpack_from('<9H', d, o + 8)
        tracks = {}
        for a, off in zip(AXES, offs):
            if off:
                r16 = bool(rot16) and a[0] == 'r'
                tracks[a] = d[o + off:o + off + _track_size(d, o + off, r16)]
        end = max([o + off + len(tracks[a]) for a, off in zip(AXES, offs) if off] + [o + 0x1C])
        out[bone] = (d[o:end], rot16, tracks)
    return out


def _anod(bone, rot16, tracks):
    """anod chunk: header + tracks (raw bytes, already in the anod's rotation format)."""
    body, offs = b'', []
    for a in AXES:
        if a in tracks:
            offs.append(0x1C + len(body))
            body += tracks[a] + b'\0' * (-len(tracks[a]) % 4)
        else:
            offs.append(0)
    return b'anod' + struct.pack('<HH9HH', bone, rot16, *offs, 0) + body


# OoT3D only animates through hermite tracks (its linear tracks are single-key constants, and
# multi-key linear rotations are read as zero). Tangent units, measured on the game's own curves
# against central differences: int16 rotations 2 x (binary-angle units per frame), float
# translations (units per frame) / 40.
ROT_TANGENT, TRANS_TANGENT = 2.0, 1 / 40


def _hermite(values, rot16):
    """One key per frame. values: rotations as continuous int16 binary angles, or translations."""
    v = np.asarray(values, float)
    n = len(v)
    slope = np.gradient(v) if n > 1 else np.zeros(1)
    head = struct.pack('<IIII', 2, n, 0, max(n - 1, 0))
    if rot16:
        tan = np.clip(np.round(slope * ROT_TANGENT), -32768, 32767)
        wrapped = ((np.round(v) + 0x8000) % 0x10000) - 0x8000
        return head + b''.join(struct.pack('<Hhhh', i, int(a), int(t), int(t)) for i, (a, t) in enumerate(zip(wrapped, tan)))
    tan = slope * TRANS_TANGENT
    return head + b''.join(struct.pack('<Ifff', i, float(a), float(t), float(t)) for i, (a, t) in enumerate(zip(v, tan)))


def _write(orig, anods):
    """A csab like `orig` (header fields kept) with the given {bone: anod bytes}."""
    bonec = struct.unpack_from('<I', orig, 0x34)[0]
    order = sorted(anods)
    table = [-1] * bonec
    for i, b in enumerate(order):
        table[b] = i
    head = bytearray(orig[:0x38])
    struct.pack_into('<I', head, 0x30, len(order))
    body = bytes(head) + struct.pack('<%dh' % bonec, *table)
    body += b'\0' * (-len(body) % 4)
    offs_at = len(body)
    body += b'\0' * (4 * len(order))
    offs = []
    for b in order:
        offs.append(len(body) - 0x18)
        body += anods[b] + b'\0' * (-len(anods[b]) % 4)
    body = bytearray(body)
    struct.pack_into('<%dI' % len(order), body, offs_at, *offs)
    struct.pack_into('<I', body, 0x04, len(body))
    return bytes(body)


def convert_csab(orig, zdata, n64_name, bones, age):
    """New csab bytes for one OoT3D animation from the bank's N64 animation."""
    fc, off = next((fc, off) for n, fc, off in anim_tables.ANIMS if n == n64_name)
    dur, nodes = csab.read(orig)
    trans, rots, _ = n64anim.frames(zdata, off, fc)
    rots, trans = _resample(rots, trans, dur)
    calib = {int(b): (l, np.array(c).reshape(3, 3)) for b, (l, c) in anim_tables.CALIB[age].items()}
    root = anim_tables.ROOT[age]
    parents = [b['parent'] for b in bones]
    euler = {b: np.zeros((dur, 3)) for b in calib}
    for f in range(dur):
        w64 = n64anim.limb_world(rots[f], anim_tables_parents())
        orig_local = [m[:3, :3] for m in _locals(bones, nodes, f)]
        world = []
        for b, p in enumerate(parents):
            pw = world[p] if p >= 0 else np.eye(3)
            if b in calib:
                l, c = calib[b]
                wb = w64[l] @ c
                euler[b][f] = n64anim.euler(pw.T @ wb)
            else:
                wb = pw @ orig_local[b]
            world.append(wb)
    blobs = _anod_blobs(orig)
    anods = {b: raw for b, (raw, _, _) in blobs.items()}
    for b in calib:
        tracks = {a: t for a, t in (blobs[b][2].items() if b in blobs else ()) if a[0] != 'r'}
        ang = np.unwrap(euler[b], axis=0)
        for k, a in enumerate(('rx', 'ry', 'rz')):
            tracks[a] = _hermite(ang[:, k] * ROT16, True)
        if b == 1:  # root translation from the N64 root
            for k, a in enumerate(('tx', 'ty', 'tz')):
                scale, offset = root[k]
                tracks[a] = _hermite(trans[:, k] * scale + offset, False)
        anods[b] = _anod(b, 1, tracks)
    return _write(orig, anods)


def anim_tables_parents():
    return [-1, 0, 1, 2, 3, 4, 2, 6, 7, 0, 9, 10, 9, 9, 13, 14, 9, 16, 17, 9, 9]


def _locals(bones, nodes, f):
    """OoT3D local rotation matrices of every bone at frame f (bind pose where not animated)."""
    out = []
    for i, b in enumerate(bones):
        r = list(b['rot'])
        n = nodes.get(i, {})
        for k, ax in enumerate('xyz'):
            if 'r' + ax in n:
                r[k] = animview.sample(n['r' + ax], f, True)
        m = np.eye(4)
        m[:3, :3] = n64anim.rot(*r)
        out.append(m)
    return out


def convert_all(files, zdata, bones, age, names=None, log=print):
    """{csab path: new bytes} for every changed animation found in this zar (all variants)."""
    names = changed(zdata) if names is None else names
    paths = n64anim.csab_paths(files)
    out = {}
    for name in names:
        targets = n64anim.oot3d_paths(name, paths)
        if not targets:
            log(f'  animation {name}: no OoT3D counterpart, skipped')
            continue
        for p in targets:
            out[p] = convert_csab(files[p], zdata, name, bones, age)
        log(f'  animation {name} -> ' + ', '.join(targets))
    return out
