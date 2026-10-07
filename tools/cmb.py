"""OoT3D CMB (version 6) reader. Layouts follow noclip.website src/OcarinaOfTime3D/cmb.ts."""
import struct
from dataclasses import dataclass, field

MAT_SIZE = 0x15C
COMBINER_SIZE = 0x28
TEX_SIZE = 0x24
ATTRS = ('position', 'normal', 'color', 'uv0', 'uv1', 'uv2', 'bone_idx', 'bone_wt')
DTYPE = {0x1400: ('b', 1), 0x1401: ('B', 1), 0x1402: ('h', 2), 0x1403: ('H', 2),
         0x1404: ('i', 4), 0x1405: ('I', 4), 0x1406: ('f', 4)}


@dataclass
class Attrib:
    start: int
    scale: float
    dtype: int
    mode: int  # 0 array, 1 constant
    const: tuple


@dataclass
class Prms:
    skinning: int  # 0 single bone, 1 rigid, 2 smooth
    bone_table: list
    index_type: int
    count: int
    offset: int  # byte offset into index buffer
    unk_prm: bytes = b''


@dataclass
class Sepd:
    flags: int
    center: tuple
    offset: tuple
    attrs: dict
    bone_dim: int
    unk_after_dim: int
    prms: list = field(default_factory=list)


@dataclass
class Texture:
    size: int
    levels: int
    is_etc1: int
    is_cube: int
    w: int
    h: int
    gl_format: int
    data_off: int
    name: str


@dataclass
class CMB:
    raw: bytes
    name: str
    header: dict
    bones_raw: bytes
    materials: list  # raw 0x15C byte blobs
    combiners: list  # raw 0x28 byte blobs
    mats_tail: bytes
    textures: list
    meshes: list  # (sepd, material, raw4)
    mshs_opaque: int
    mshs_ids: int
    sepds: list
    luts_raw: bytes
    vatr: dict  # attr -> (size, offset) into vatr chunk
    vatr_chunk: bytes
    indices: bytes
    tex_data: bytes


def _chunk(d, o, magic):
    assert d[o:o + 4] == magic, (d[o:o + 4], magic, hex(o))
    return struct.unpack_from('<I', d, o + 4)[0]


def read(d):
    assert d[:4] == b'cmb ' and struct.unpack_from('<I', d, 8)[0] == 6
    name = d[0x10:0x20].split(b'\0')[0].decode()
    n_idx, skl, mats, tex, sklm, luts, vatr, idx, texdata = struct.unpack_from('<9I', d, 0x20)
    hdr = dict(n_idx=n_idx, skl=skl, mats=mats, tex=tex, sklm=sklm, luts=luts, vatr=vatr, idx=idx, texdata=texdata)

    skl_size = _chunk(d, skl, b'skl ')
    bones_raw = d[skl:skl + skl_size]

    mats_size = _chunk(d, mats, b'mats')
    nmat = struct.unpack_from('<I', d, mats + 8)[0]
    materials = [d[mats + 0xC + i * MAT_SIZE: mats + 0xC + (i + 1) * MAT_SIZE] for i in range(nmat)]
    comb_off = mats + 0xC + nmat * MAT_SIZE
    max_comb = 0
    for m in materials:
        n = struct.unpack_from('<I', m, 0x120)[0]
        for k in range(n):
            max_comb = max(max_comb, struct.unpack_from('<H', m, 0x124 + 2 * k)[0] + 1)
    combiners = [d[comb_off + i * COMBINER_SIZE: comb_off + (i + 1) * COMBINER_SIZE] for i in range(max_comb)]
    mats_tail = d[comb_off + max_comb * COMBINER_SIZE: mats + mats_size]

    _chunk(d, tex, b'tex ')
    ntex = struct.unpack_from('<I', d, tex + 8)[0]
    textures = []
    for i in range(ntex):
        o = tex + 0xC + i * TEX_SIZE
        size, lv, etc, cube, w, h, fmt, doff = struct.unpack_from('<IHBBHHII', d, o)
        textures.append(Texture(size, lv, etc, cube, w, h, fmt, doff, d[o + 0x14:o + 0x24].split(b'\0')[0].decode()))

    _chunk(d, sklm, b'sklm')
    mshs_off, shp_off = struct.unpack_from('<II', d, sklm + 8)
    mshs = sklm + mshs_off
    _chunk(d, mshs, b'mshs')
    nmesh, opaque, ids = struct.unpack_from('<IHH', d, mshs + 8)
    meshes = []
    for i in range(nmesh):
        o = mshs + 0x10 + 4 * i
        meshes.append((struct.unpack_from('<H', d, o)[0], d[o + 2], d[o + 3]))

    shp = sklm + shp_off
    _chunk(d, shp, b'shp ')
    nshp = struct.unpack_from('<I', d, shp + 8)[0]
    sepds = []
    for i in range(nshp):
        so = shp + struct.unpack_from('<H', d, shp + 0x10 + 2 * i)[0]
        _chunk(d, so, b'sepd')
        cnt, flags = struct.unpack_from('<HH', d, so + 8)
        center = struct.unpack_from('<3f', d, so + 0xC)
        offs = struct.unpack_from('<3f', d, so + 0x18)
        p = so + 0x24
        attrs = {}
        for a in ATTRS:
            start, scale, dt, mode = struct.unpack_from('<IfHH', d, p)
            attrs[a] = Attrib(start, scale, dt, mode, struct.unpack_from('<4f', d, p + 0xC))
            p += 0x1C
        bone_dim, unk = struct.unpack_from('<HH', d, p)
        p += 4
        sepd = Sepd(flags, center, offs, attrs, bone_dim, unk)
        for k in range(cnt):
            po = so + struct.unpack_from('<H', d, p + 2 * k)[0]
            _chunk(d, po, b'prms')
            n_prm, skin, nbt, bt_off, prm_off = struct.unpack_from('<IHHII', d, po + 8)
            assert n_prm == 1
            bt = list(struct.unpack_from('<%dH' % nbt, d, po + bt_off))
            pr = po + prm_off
            _chunk(d, pr, b'prm ')
            itype, = struct.unpack_from('<H', d, pr + 0x10)
            count, off = struct.unpack_from('<HH', d, pr + 0x14)
            sepd.prms.append(Prms(skin, bt, itype, count, off * 2, d[pr + 8:pr + 0x10] + d[pr + 0x12:pr + 0x14]))
        sepds.append(sepd)

    luts_size = _chunk(d, luts, b'luts')
    vatr_size = _chunk(d, vatr, b'vatr')
    vatr_tab = {}
    for i, a in enumerate(ATTRS):
        size, off = struct.unpack_from('<II', d, vatr + 0xC + 8 * i)
        vatr_tab[a] = (size, off)
    return CMB(d, name, hdr, bones_raw, materials, combiners, mats_tail, textures, meshes, opaque, ids,
               sepds, d[luts:luts + luts_size], vatr_tab, d[vatr:vatr + vatr_size],
               d[idx:idx + n_idx * 2], d[texdata:] if texdata else b'')


def mat_textures(m):
    """Texture indices bound to the 3 slots of a raw material."""
    return [struct.unpack_from('<h', m, 0x10 + 0x18 * j)[0] for j in range(3)]


def read_attrib(c, sepd, attr, n_comp):
    """Decode a sepd vertex attribute array into a list of tuples (all vertices of the vatr slice)."""
    a = sepd.attrs[attr]
    if a.mode == 1:
        return None
    fmt, sz = DTYPE[a.dtype]
    size, off = c.vatr[attr]
    base = off + a.start
    stride = sz * n_comp
    n = (size - a.start) // stride
    buf = c.vatr_chunk
    out = []
    for i in range(n):
        out.append(tuple(v * a.scale for v in struct.unpack_from('<%d%s' % (n_comp, fmt), buf, base + i * stride)))
    return out


def _attr_reader(c, sepd, attr, n_comp):
    a = sepd.attrs[attr]
    if a.mode == 1:
        const = a.const[:n_comp]
        return lambda i: const
    fmt, sz = DTYPE[a.dtype]
    base = c.vatr[attr][1] + a.start
    stride = sz * n_comp
    buf = c.vatr_chunk
    f = '<%d%s' % (n_comp, fmt)
    return lambda i: tuple(v * a.scale for v in struct.unpack_from(f, buf, base + i * stride))


def triangles(c, sepd):
    """Yield (prms, [3 x vertex dict]) for each triangle. Vertex dict: pos, nrm, uv, bones, weights."""
    pos = _attr_reader(c, sepd, 'position', 3)
    nrm = _attr_reader(c, sepd, 'normal', 3)
    uv = _attr_reader(c, sepd, 'uv0', 2)
    bi = _attr_reader(c, sepd, 'bone_idx', sepd.bone_dim)
    bw = _attr_reader(c, sepd, 'bone_wt', sepd.bone_dim)
    for p in sepd.prms:
        fmt, sz = DTYPE[p.index_type]
        idx = struct.unpack_from('<%d%s' % (p.count, fmt), c.indices, p.offset)
        for t in range(0, p.count - 2, 3):
            vs = []
            for i in idx[t:t + 3]:
                bones = [p.bone_table[int(round(b))] for b in bi(i)] if sepd.attrs['bone_idx'].mode == 0 else [p.bone_table[0]]
                wts = bw(i) if p.skinning == 2 else (1.0,)
                vs.append(dict(pos=pos(i), nrm=nrm(i), uv=uv(i), bones=bones, weights=wts))
            yield p, vs
