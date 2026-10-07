"""Write an OoT3D CMB using an existing one as the template.

Kept template meshes are copied verbatim (their sepd chunks, vertex slices and indices stay where
they were relative to each attribute slice). New meshes are smooth-skinned like Link's body:
world-space bind-pose positions, two bone slots per vertex.
"""
import struct
from dataclasses import dataclass, field

import numpy as np

import cmb as cmbr
import cmbskel

ALIGN_TEX = 0x80  # start of the texture data block
ALIGN_EACH_TEX = 1  # Link's textures are packed back to back
MAX_BONES_PER_PRMS = 8
MAT_SIZE_ADD = 0x15C
COMBINER_SIZE = 0x28
# Write one-bone meshes as SingleBone (bone-local) like Link's. Off: every mesh is smooth-skinned
# and one-entry bone tables get a zero-weight partner (the path proven in-game for body/hair).
SINGLE_BONE_MODE = False


@dataclass
class NewMesh:
    group: int
    material: int
    tris: list  # each: 3 x (pos(xyz world), nrm(xyz unit), uv(u,v), bone)
    translucent: bool = False


@dataclass
class NewTexture:
    name: str
    w: int
    h: int
    gl_format: int
    data: bytes


def _pad(b, a):
    return b + b'\0' * (-len(b) % a)


def _chunk(magic, body):
    return magic + struct.pack('<I', 8 + len(body)) + body


def _build_sepd(mesh, vatr_starts, out_arrays, idx_buf, bind_world):
    """Append vertex data for `mesh` to the arrays and return the sepd chunk bytes.

    A mesh on one bone is written like Link's: SingleBone skinning with bone-local positions
    (the game treats any one-entry bone table that way). Otherwise smooth skinning with
    world-space bind positions; one-entry tables get a zero-weight second bone."""
    bones_used = {v[3] for t in mesh.tris for v in t}
    single = SINGLE_BONE_MODE and len(bones_used) == 1
    if single:
        b = next(iter(bones_used))
        inv = np.linalg.inv(bind_world[b])
        mesh = NewMesh(mesh.group, mesh.material, [
            [(tuple(inv[:3, :3] @ np.array(p) + inv[:3, 3]), tuple(bind_world[b][:3, :3].T @ np.array(n)), uv, bone)
             for p, n, uv, bone in t] for t in mesh.tris], mesh.translucent)
    # split triangles into primitive sets whose bone tables fit
    sets, cur, cur_bones = [], [], []
    for t in mesh.tris:
        bs = {v[3] for v in t}
        if len(set(cur_bones) | bs) > MAX_BONES_PER_PRMS:
            sets.append((cur, cur_bones)); cur, cur_bones = [], []
        cur.append(t)
        cur_bones += [b for b in sorted(bs) if b not in cur_bones]
    if cur:
        sets.append((cur, cur_bones))
    if not single:
        for _, table in sets:
            if len(table) == 1:
                table.append(0 if table[0] != 0 else 1)  # zero-weight partner keeps the table smooth

    verts, vmap = [], {}
    prms_specs = []
    for tris, table in sets:
        local = {b: i for i, b in enumerate(table)}
        idx = []
        for t in tris:
            for pos, nrm, uv, bone in t:
                key = (tuple(round(c, 4) for c in pos), tuple(round(c, 3) for c in nrm),
                       tuple(round(c, 5) for c in uv), local[bone], id(table))
                if key not in vmap:
                    vmap[key] = len(verts)
                    verts.append((pos, nrm, uv, local[bone]))
                idx.append(vmap[key])
        prms_specs.append((table, idx))
    assert len(verts) < 0x10000

    # UVs as int16 * scale, like every Link mesh (the game reads texcoords as shorts)
    uv_max = max(max(abs(c) for c in v[2]) for v in verts)
    uv_scale = max(uv_max, 1e-6) / 32767
    starts = {}
    arrays = [('position', '<3f', lambda v: v[0]),
              ('normal', '<3b', lambda v: tuple(max(-127, min(127, round(c * 127))) for c in v[1])),
              ('uv0', '<2h', lambda v: tuple(int(round(c / uv_scale)) for c in v[2]))]
    if not single:
        arrays += [('bone_idx', '<2B', lambda v: (v[3], v[3])), ('bone_wt', '<2B', lambda v: (100, 0))]
    for name, fmt, getter in arrays:
        arr = out_arrays[name]
        while len(arr) % 4:
            arr.append(0)
        starts[name] = vatr_starts[name] + len(arr)
        for v in verts:
            arr += struct.pack(fmt, *getter(v))

    xs = [v[0] for v in verts]
    center = tuple((min(p[i] for p in xs) + max(p[i] for p in xs)) / 2 for i in range(3))

    def attr(name, scale, dtype):
        return struct.pack('<IfHH4f', starts.get(name, 0), scale, dtype, 0, 0, 0, 0, 0)

    body = struct.pack('<HH3f3f', len(prms_specs), 0x0B if single else 0xCB, *center, 0, 0, 0)
    body += attr('position', 1.0, 0x1406)
    body += attr('normal', 1 / 127, 0x1400)
    body += attr('color', 1.0, 0x1406)
    body += attr('uv0', uv_scale, 0x1402)
    body += attr('uv1', 1.0, 0x1406)
    body += attr('uv2', 1.0, 0x1406)
    if single:
        body += attr('bone_idx', 1.0, 0x1406)
        body += attr('bone_wt', 1.0, 0x1406)
        body += struct.pack('<HH', 1, 0)
    else:
        body += attr('bone_idx', 1.0, 0x1401)
        body += attr('bone_wt', 0.01, 0x1401)
        body += struct.pack('<HH', 2, 0)
    head_len = 8 + len(body) + 2 * len(prms_specs)
    head_len += -head_len % 4

    prms_blobs, offs = [], []
    o = head_len
    for table, idx in prms_specs:
        while len(idx_buf) % 2:
            idx_buf.append(0)
        idx_off = len(idx_buf) // 2
        assert idx_off < 0x10000, 'index buffer too large for prm offset field'
        idx_buf += struct.pack('<%dH' % len(idx), *idx)
        bt = _pad(struct.pack('<%dH' % len(table), *table), 4)
        prm = _chunk(b'prm ', struct.pack('<II', 1, 0) + struct.pack('<HHHH', 0x1403, 0, len(idx), idx_off))
        prms_hdr_len = 0x18
        prms = _chunk(b'prms', struct.pack('<IHHII', 1, 0 if single else 2, len(table), prms_hdr_len, prms_hdr_len + len(bt)) + bt + prm)
        offs.append(o)
        prms_blobs.append(prms)
        o += len(prms)
    head = body + struct.pack('<%dH' % len(offs), *offs)
    sepd = b'sepd' + struct.pack('<I', o) + head
    sepd = _pad(sepd, 4)
    assert len(sepd) == head_len
    return sepd + b''.join(prms_blobs)


ATTR_COMP = {'position': 3, 'normal': 3, 'color': 4, 'uv0': 2, 'uv1': 2, 'uv2': 2}


def _relayout(blob, src, arrays, idx_buf, bpv=None):
    """Copy one sepd's vertex/index data to the end of the shared buffers and patch its offsets.
    bpv: if given, filled with bytes per vertex of each array attribute this sepd uses."""
    b = bytearray(blob)
    src_arrays, src_idx = src
    count, flags = struct.unpack_from('<HH', b, 8)
    bone_dim = struct.unpack_from('<H', b, 0x24 + 8 * 0x1C)[0]
    prms_offs = struct.unpack_from('<%dH' % count, b, 0x24 + 8 * 0x1C + 4)
    nverts = 0
    prm_info = []
    for po in prms_offs:
        pr = po + struct.unpack_from('<I', b, po + 0x14)[0]
        itype, = struct.unpack_from('<H', b, pr + 0x10)
        n, off = struct.unpack_from('<HH', b, pr + 0x14)
        isz = 1 if itype == 0x1401 else 2
        data = src_idx[off * 2:off * 2 + n * isz]
        idxs = struct.unpack('<%d%s' % (n, 'B' if isz == 1 else 'H'), data)
        nverts = max(nverts, max(idxs) + 1)
        prm_info.append((pr, data))
    for k, a in enumerate(cmbr.ATTRS):
        e = 0x24 + 0x1C * k
        start, scale, dtype, mode = struct.unpack_from('<IfHH', b, e)
        if mode != 0 or not (flags >> k) & 1:
            continue
        comp = ATTR_COMP.get(a, bone_dim)
        size = nverts * comp * cmbr.DTYPE[dtype][1]
        chunk = src_arrays[a][start:start + size]
        assert len(chunk) == size, (a, start, size, len(src_arrays[a]))
        if bpv is not None:
            bpv[a] = comp * cmbr.DTYPE[dtype][1]
        struct.pack_into('<I', b, e, len(arrays[a]))
        arrays[a] += chunk
    for pr, data in prm_info:
        if len(idx_buf) % 2:
            idx_buf.append(0)
        assert len(idx_buf) // 2 < 0x10000, 'index buffer too large for prm offset field'
        struct.pack_into('<H', b, pr + 0x16, len(idx_buf) // 2)
        idx_buf += data
    return bytes(b)


class _PinOverflow(Exception):
    pass


def write(t, bone_trans, keep_meshes, materials, textures, new_meshes, name=None, combiners=None, pin_sepds=()):
    """t: template cmbr.CMB. keep_meshes: template mesh indices to keep (their sepds are reused).
    materials: full list of raw material blobs. textures: list of (cmbr.Texture, bytes) or NewTexture.
    pin_sepds: kept sepds whose vertex data must stay at Link's original offsets (the game writes
    into them directly, e.g. the bow / slingshot string)."""
    # ---- skl
    skl = bytearray(t.bones_raw)
    n = struct.unpack_from('<I', skl, 8)[0]
    stride = (len(skl) - 16) // n
    for i, tr in enumerate(bone_trans):
        struct.pack_into('<3f', skl, 16 + stride * i + 0x1C, *tr)
    skl = bytes(skl)
    _, bind_world = cmbskel.read_skeleton(skl)

    # ---- mats
    mats = _chunk(b'mats', struct.pack('<I', len(materials)) + b''.join(materials) + b''.join(combiners or t.combiners) + t.mats_tail)
    # Link's mats size field does not equal the chunk length; keep his value (+ added materials)
    orig_mats_size = struct.unpack_from('<I', t.raw, t.header['mats'] + 4)[0]
    mats = mats[:4] + struct.pack('<I', orig_mats_size + MAT_SIZE_ADD * (len(materials) - len(t.materials))
                                      + COMBINER_SIZE * (len(combiners or t.combiners) - len(t.combiners))) + mats[8:]

    # ---- tex + texture data
    entries, tdata = [], bytearray()
    for tx in textures:
        if isinstance(tx, NewTexture):
            meta = (len(tx.data), 1, 0, 0, tx.w, tx.h, tx.gl_format, tx.name)
            data = tx.data
        else:
            old, data = tx
            meta = (old.size, old.levels, old.is_etc1, old.is_cube, old.w, old.h, old.gl_format, old.name)
        tdata += b'\0' * (-len(tdata) % ALIGN_EACH_TEX)
        off = len(tdata)
        tdata += data
        size, lv, etc, cube, w, h, fmt, nm = meta
        entries.append(struct.pack('<IHBBHHII16s', size, lv, etc, cube, w, h, fmt, off, nm.encode()[:16]))
    tex = _chunk(b'tex ', struct.pack('<I', len(entries)) + b''.join(entries))

    # ---- shapes / meshes
    # Keep Link's sepds at their original indices (and his mesh entries byte-for-byte); new sepds
    # take over the slots of removed meshes first, then are appended.
    shp_off = t.header['sklm'] + struct.unpack_from('<I', t.raw, t.header['sklm'] + 12)[0]

    def orig_sepd(i):
        so = shp_off + struct.unpack_from('<H', t.raw, shp_off + 0x10 + 2 * i)[0]
        return t.raw[so:so + struct.unpack_from('<I', t.raw, so + 4)[0]]

    link_src = ({a: t.vatr_chunk[off:off + size] for a, (size, off) in t.vatr.items()}, t.indices)
    kept_sepds = {t.meshes[mi][0] for mi in keep_meshes}

    def layout(pins_first):
        """Place new meshes in sepd slots and rebuild the vertex / index buffers."""
        sepds = [(orig_sepd(i), link_src) for i in range(len(t.sepds))]
        free = [i for i in range(len(t.sepds)) if i not in kept_sepds]
        keep_set = set(keep_meshes)
        opaque, trans = [], []
        for mi, (s_, m, gid) in enumerate(t.meshes):
            if mi in keep_set:
                (trans if mi >= t.mshs_opaque else opaque).append((s_, m, gid))
        new_entries = []
        for nm in new_meshes:
            if not nm.tris:
                continue
            arrs = {a: bytearray() for a in cmbr.ATTRS}
            idx = bytearray()
            blob = _build_sepd(nm, {a: 0 for a in cmbr.ATTRS}, arrs, idx, bind_world)
            new_entries.append((nm, (blob, ({a: bytes(v) for a, v in arrs.items()}, bytes(idx)))))
        def used(entry):
            """{array: bytes} a sepd adds to the shared vertex arrays."""
            arrays = {a: bytearray() for a in cmbr.ATTRS}
            _relayout(entry[0], entry[1], arrays, bytearray())
            return {a: len(v) for a, v in arrays.items()}

        slot_of = {}
        if pins_first:
            # The free slots before the first pinned sepd take only as many new meshes as fit under
            # its original array offsets; the others get a tiny unreferenced
            # placeholder, and the remaining new meshes go after the pinned sepds.
            first_pin = min(pin_sepds)
            sp = t.sepds[first_pin]
            budget = {a: sp.attrs[a].start for a in cmbr.ATTRS
                      if sp.attrs[a].mode == 0 and (sp.flags >> cmbr.ATTRS.index(a)) & 1}
            for i in kept_sepds:
                if i < first_pin:
                    for a, n in used(sepds[i]).items():
                        if a in budget:
                            budget[a] -= n
            arrs = {a: bytearray() for a in cmbr.ATTRS}
            idx = bytearray()
            filler_mesh = NewMesh(0, 0, [[((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0), 0)] * 3])
            filler_blob = _build_sepd(filler_mesh, {a: 0 for a in cmbr.ATTRS}, arrs, idx, bind_world)
            filler = (filler_blob, ({a: bytes(v) for a, v in arrs.items()}, bytes(idx)))
            filler_use = used(filler)
            sizes = [used(e) for _, e in new_entries]
            # smallest first: as many slots as possible hold a real mesh rather than a placeholder
            order = sorted(range(len(new_entries)), key=lambda k: sizes[k]['position'])
            slots = [i for i in free if i < first_pin]
            for pos_in_list, i in enumerate(slots):
                # keep room for a placeholder in every free slot still to come
                reserve = {a: filler_use.get(a, 0) * (len(slots) - pos_in_list - 1) for a in budget}
                pick = next((k for k in order
                             if all(sizes[k].get(a, 0) <= budget[a] - reserve[a] for a in budget)), None)
                use = sizes[pick] if pick is not None else filler_use
                if pick is not None:
                    order.remove(pick)
                    slot_of[pick] = i
                else:
                    sepds[i] = filler
                for a in budget:
                    budget[a] -= use.get(a, 0)
            free = [i for i in free if i > max(pin_sepds)]
        new_opaque = []
        for k, (nm, entry) in enumerate(new_entries):
            if k in slot_of:
                si = slot_of[k]
            elif free:
                si = free.pop(0)
            else:
                si = len(sepds)
                sepds.append(None)
            sepds[si] = entry
            (trans if nm.translucent else new_opaque).append((si, nm.material, nm.group))
        opaque += new_opaque
        mesh_entries = [struct.pack('<HBB', si, m, gid) for si, m, gid in opaque + trans]
        opaque_meshes = opaque

        # Link's vertex data is contiguous in sepd order with no gaps (the game relies on it), and so
        # is the index buffer: rebuild both in sepd order and patch every start / index offset.
        arrays = {a: bytearray() for a in cmbr.ATTRS}
        idx_buf = bytearray()
        sepd_blobs, prev_bpv = [], {}
        for si, (blob, src) in enumerate(sepds):
            if si in pin_sepds:
                # pad the previous sepd with unreferenced vertices up to Link's original starts
                want = {a: t.sepds[si].attrs[a].start for a in cmbr.ATTRS
                        if t.sepds[si].attrs[a].mode == 0 and (t.sepds[si].flags >> cmbr.ATTRS.index(a)) & 1}
                gaps = {a: want[a] - len(arrays[a]) for a in want}
                if any(g < 0 for g in gaps.values()):
                    raise _PinOverflow(si)
                k = gaps['position'] // 12
                for a in cmbr.ATTRS:
                    if a in want:
                        arrays[a] += b'\0' * gaps[a]
                    elif a in prev_bpv:
                        arrays[a] += b'\0' * (k * prev_bpv[a])
            prev_bpv = {}
            sepd_blobs.append(_relayout(blob, src, arrays, idx_buf, prev_bpv))
            if si in pin_sepds:
                got = struct.unpack_from('<I', sepd_blobs[-1], 0x24)[0]
                assert got == t.sepds[si].attrs['position'].start, (si, got)
        return sepds, opaque, trans, sepd_blobs, arrays, idx_buf, mesh_entries

    try:
        sepds, opaque, trans, sepd_blobs, arrays, idx_buf, mesh_entries = layout(False)
    except _PinOverflow:  # new meshes outgrew the space before a pinned sepd
        sepds, opaque, trans, sepd_blobs, arrays, idx_buf, mesh_entries = layout(True)
    opaque_meshes = opaque

    mshs = _chunk(b'mshs', struct.pack('<IHH', len(mesh_entries), len(opaque_meshes), t.mshs_ids) + b''.join(mesh_entries))
    shp_head = 0x10 + 2 * len(sepd_blobs)
    shp_head += -shp_head % 4
    offs, o = [], shp_head
    for b in sepd_blobs:
        offs.append(o)
        o += len(b)
    assert o < 0x10000, 'shp chunk too large (sepd offsets are 16-bit)'
    shp = b'shp ' + struct.pack('<III', o, len(sepd_blobs), 0)
    shp = _pad(shp + struct.pack('<%dH' % len(offs), *offs), 4) + b''.join(sepd_blobs)
    sklm = b'sklm' + struct.pack('<III', 0x10 + len(mshs) + len(shp), 0x10, 0x10 + len(mshs)) + mshs + shp

    # ---- vatr
    vhead = 0xC + 8 * len(cmbr.ATTRS)
    body, table, o = bytearray(), [], vhead
    for a in cmbr.ATTRS:
        arr = _pad(bytes(arrays[a]), 4)  # Link pads each array's end to 4 bytes (and counts it)
        table.append(struct.pack('<II', len(arr), o))
        body += arr
        o += len(arr)
    max_index = len(arrays['position']) // 12  # template stores its position count here
    vatr = b'vatr' + struct.pack('<II', vhead + len(body), max_index) + b''.join(table) + body

    luts = t.luts_raw
    idx_bytes = _pad(bytes(idx_buf), 4)

    # ---- assemble
    hdr_len = 0x44
    parts = [skl, mats, tex, sklm, luts, vatr]
    offsets, o = [], hdr_len
    for p in parts:
        offsets.append(o)
        o += len(p)
    idx_off = o
    o += len(idx_bytes)
    o += -o % ALIGN_TEX
    texdata_off = o
    total = texdata_off + len(tdata)
    nm = (name or t.name).encode()[:16]
    header = b'cmb ' + struct.pack('<III16sI', total, 6, 0, nm, len(idx_bytes) // 2)  # Link counts the padding
    header += struct.pack('<8I', *offsets, idx_off, texdata_off)
    out = header + b''.join(parts) + idx_bytes
    out += b'\0' * (texdata_off - len(out)) + bytes(tdata)
    assert len(out) == total
    return out
