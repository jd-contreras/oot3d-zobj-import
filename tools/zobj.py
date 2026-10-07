"""Read an OoT player zobj (ML64 / zzplayas layout): skeleton, display lists, textures.

Vertices are returned in the space of the limb that owns them. Vertices loaded while a
segment 0x0D matrix is active belong to that matrix's limb (N64 "smooth skinning" seams).
"""
import struct
from dataclasses import dataclass, field

N_LIMBS = 21


@dataclass
class Limb:
    pos: tuple
    child: int
    sibling: int
    dl: int
    parent: int = -1


@dataclass
class Tex:
    addr: int
    fmt: int  # 0 RGBA 1 YUV 2 CI 3 IA 4 I
    siz: int  # 0 4b 1 8b 2 16b 3 32b
    w: int
    h: int
    tlut: int  # palette address or 0
    seg: int  # segment of addr (6 = this file, 8/9 = eyes/mouth)
    cms: int = 0  # clamp/mirror flags S
    cmt: int = 0


@dataclass
class Tri:
    v: list  # 3 x (limb, pos(x,y,z), uv(s,t), rgba)
    tex: object  # Tex or None
    prim: tuple
    env: tuple
    lit: bool
    combine: tuple = (0, 0)  # raw G_SETCOMBINE words
    env_set: bool = False  # env colour set by the model itself (else the game supplies it)
    geom: int = 0x00220405  # F3DEX2 geometry mode (G_CULL_BACK 0x400, G_CULL_FRONT 0x200)
    other_l: int = 0  # othermode low word (render mode; ZMODE in bits 10-11)
    other_h: int = 0  # othermode high word (cycle type in bits 20-21)

    @property
    def texgen(self):
        return bool(self.geom & 0x40000)  # G_TEXTURE_GEN: spherical environment mapping

    @property
    def two_cycle(self):
        return (self.other_h >> 20) & 3 == 1

    @property
    def cull(self):
        """0 none, 1 back, 2 front."""
        return 1 if self.geom & 0x400 else 2 if self.geom & 0x200 else 0

    @property
    def decal(self):
        return (self.other_l >> 10) & 3 == 3  # ZMODE_DEC

    @property
    def tunic(self):
        """Combiner reads ENVIRONMENT colour the model never sets: the game's tunic colour."""
        return not self.env_set and uses_env(*self.combine)


    @property
    def alpha_from_texture(self):
        """True when the combiner's alpha output reads TEXEL0 alpha (cutout / blended material)."""
        w0, w1 = self.combine
        slots = [(w0 >> 12) & 7, (w1 >> 12) & 7, (w0 >> 9) & 7, (w1 >> 9) & 7,
                 (w1 >> 21) & 7, (w1 >> 3) & 7, (w1 >> 18) & 7, w1 & 7]
        return 1 in slots


def uses_env(w0, w1):
    cyc = [((w0 >> 20) & 0xF, (w1 >> 28) & 0xF, (w0 >> 15) & 0x1F, (w1 >> 15) & 7),
           ((w0 >> 5) & 0xF, (w1 >> 24) & 0xF, w0 & 0x1F, (w1 >> 6) & 7)]
    return any(5 in c for c in cyc)


@dataclass
class Model:
    data: bytes
    limbs: list
    tris: list = field(default_factory=list)
    mtx_limb: list = field(default_factory=list)
    dropped: int = 0  # triangles referencing vertices we could not load


def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


def find_skeleton(d):
    if d[0x5000:0x500B] == b'MODLOADER64':
        p = 0x5380  # ML64 player manifest: flex skeleton header lives here
        lt, cnt = struct.unpack_from('>IB', d, p)
        if cnt == N_LIMBS:
            return p
    for o in range(0, len(d) - 12, 4):
        lt, cnt = struct.unpack_from('>IB', d, o)
        if lt >> 24 == 6 and cnt == N_LIMBS and d[o + 5:o + 8] == b'\0\0\0' and (lt & 0xFFFFFF) < len(d):
            return o
    raise ValueError('no 21-limb skeleton found')


def read(src):
    """src: file path or the zobj bytes."""
    d = src if isinstance(src, (bytes, bytearray)) else open(src, 'rb').read()
    sk = find_skeleton(d)
    lt = struct.unpack_from('>I', d, sk)[0] & 0xFFFFFF
    limbs = []
    for i in range(N_LIMBS):
        p = struct.unpack_from('>I', d, lt + 4 * i)[0] & 0xFFFFFF
        x, y, z, c, s, dl = struct.unpack_from('>hhhBBI', d, p)
        limbs.append(Limb((x, y, z), c, s, dl))

    def set_parent(i, parent):
        while i != 255:
            limbs[i].parent = parent
            if limbs[i].child != 255:
                set_parent(limbs[i].child, i)
            i = limbs[i].sibling
    set_parent(0, -1)

    m = Model(d, limbs)
    # segment 0x0D matrix n = n-th limb that draws (depth-first == index order)
    m.mtx_limb = [i for i, l in enumerate(limbs) if l.dl]
    for i, l in enumerate(limbs):
        if l.dl:
            _run_dl(m, l.dl, i, m.mtx_limb)
    return m


# ML64 / OOTO player manifest: LUT entries (8 bytes each) from 0x5090, in this order
LUT_NAMES = [
    'WAIST', 'RTHIGH', 'RSHIN', 'RFOOT', 'LTHIGH', 'LSHIN', 'LFOOT', 'HEAD', 'HAT', 'COLLAR',
    'LSHOULDER', 'LFOREARM', 'RSHOULDER', 'RFOREARM', 'TORSO', 'LHAND', 'LFIST', 'LHAND_BOTTLE',
    'RHAND', 'RFIST', 'SWORD_SHEATH', 'SWORD_HILT', 'SWORD_BLADE', 'LONGSWORD_HILT',
    'LONGSWORD_BLADE', 'LONGSWORD_BROKEN', 'SHIELD_HYLIAN', 'SHIELD_MIRROR', 'HAMMER', 'BOTTLE',
    'BOW', 'OCARINA_TIME', 'HOOKSHOT', 'UPGRADE_LFOREARM', 'UPGRADE_LHAND', 'UPGRADE_LFIST',
    'UPGRADE_RFOREARM', 'UPGRADE_RHAND', 'UPGRADE_RFIST', 'BOOT_LIRON', 'BOOT_RIRON',
    'BOOT_LHOVER', 'BOOT_RHOVER', 'FPS_LFOREARM', 'FPS_LHAND', 'FPS_RFOREARM', 'FPS_RHAND',
    'FPS_HOOKSHOT', 'HOOKSHOT_CHAIN', 'HOOKSHOT_HOOK', 'HOOKSHOT_AIM', 'BOW_STRING', 'BLADEBREAK',
]
LUT_BASE = 0x5090
# Child manifest (hylian-modding/Z64-CustomPlayerModels zobj_checker/child_map.ts): from 0x50D0
CHILD_LUT_NAMES = [
    'SHIELD_DEKU', 'WAIST', 'RTHIGH', 'RSHIN', 'RFOOT', 'LTHIGH', 'LSHIN', 'LFOOT', 'HEAD', 'HAT',
    'COLLAR', 'LSHOULDER', 'LFOREARM', 'RSHOULDER', 'RFOREARM', 'TORSO', 'LHAND', 'LFIST',
    'LHAND_BOTTLE', 'RHAND', 'RFIST', 'SWORD_SHEATH', 'SWORD_HILT', 'SWORD_BLADE', 'SLINGSHOT',
    'OCARINA_FAIRY', 'OCARINA_TIME', 'DEKU_STICK', 'BOOMERANG', 'SHIELD_HYLIAN_BACK', 'BOTTLE',
    'MASTER_SWORD', 'GORON_BRACELET', 'FPS_RIGHT_ARM', 'SLINGSHOT_STRING', 'MASK_BUNNY',
    'MASK_GERUDO', 'MASK_GORON', 'MASK_KEATON', 'MASK_SPOOKY', 'MASK_TRUTH', 'MASK_ZORA', 'MASK_SKULL',
]
CHILD_LUT_BASE = 0x50D0


def is_child(m):
    """ML64 header byte 0x500B: 0 = adult, 1 = child."""
    return m.data[0x500B] == 1


def lut(m):
    """Map LUT name -> display list segment address (ML64 layout)."""
    out = {}
    names, base = (CHILD_LUT_NAMES, CHILD_LUT_BASE) if is_child(m) else (LUT_NAMES, LUT_BASE)
    for i, name in enumerate(names):
        w0, w1 = struct.unpack_from('>II', m.data, base + 8 * i)
        if w0 >> 24 == 0xDE and w1 >> 24 == 6:
            out[name] = w1
    return out


def dl_tris(m, addr, limb):
    """Triangles of one display list drawn in `limb`'s space (not added to m.tris)."""
    saved, m.tris = m.tris, []
    try:
        _run_dl(m, addr, limb, m.mtx_limb)
        return m.tris
    finally:
        m.tris = saved


def _run_dl(m, addr, limb, mtx_limb):
    d = m.data
    vbuf = [None] * 64
    stack = []
    cur_limb = [limb]
    mtx_stack = []
    st = dict(timg=0, timg_fmt=0, timg_siz=0, tlut=0, tiles={}, prim=(255,) * 4, env=(255,) * 4,
              lit=True, tex_on=False, combine=(0, 0), env_set=False, geom=0x00220405, other_l=0, other_h=0x00100000)
    pc = addr

    def seg(a):
        return a >> 24, a & 0xFFFFFF

    while True:
        s, off = seg(pc)
        if s != 6 or off + 8 > len(d):
            return
        w0, w1 = struct.unpack_from('>II', d, off)
        op = w0 >> 24
        pc += 8
        if op == 0x01:  # G_VTX
            n = (w0 >> 12) & 0xFF
            end = (w0 >> 1) & 0x7F
            vs, vo = seg(w1)
            for k in range(n):
                if vs != 6:
                    continue
                x, y, z, _, sv, tv, r, g, b, a = struct.unpack_from('>hhhHhhBBBB', d, vo + 16 * k)
                vbuf[end - n + k] = (cur_limb[0], (x, y, z), (sv, tv), (r, g, b, a))
        elif op in (0x05, 0x06):  # G_TRI1 / G_TRI2
            idx = [((w0 >> 16) & 0xFF) // 2, ((w0 >> 8) & 0xFF) // 2, (w0 & 0xFF) // 2]
            tris = [idx]
            if op == 0x06:
                tris.append([((w1 >> 16) & 0xFF) // 2, ((w1 >> 8) & 0xFF) // 2, (w1 & 0xFF) // 2])
            tex = _cur_tex(st) if st['tex_on'] else None
            for t in tris:
                vv = [vbuf[i] for i in t]
                if None not in vv:
                    m.tris.append(Tri(vv, tex, st['prim'], st['env'], st['lit'], st['combine'], st['env_set'], st['geom'], st['other_l'], st['other_h']))
                else:
                    m.dropped += 1
        elif op == 0xDA:  # G_MTX
            ms, mo = seg(w1)
            if ms == 0x0D:
                mtx_stack.append(cur_limb[0])
                cur_limb[0] = mtx_limb[mo // 0x40]
        elif op == 0xD8:  # G_POPMTX
            if mtx_stack:
                cur_limb[0] = mtx_stack.pop()
            else:
                cur_limb[0] = limb
        elif op == 0xDE:  # G_DL
            if (w0 >> 16) & 0xFF == 0:
                stack.append(pc)
            pc = w1
        elif op == 0xDF:  # G_ENDDL
            if not stack:
                return
            pc = stack.pop()
        elif op == 0xD7:  # G_TEXTURE
            st['tex_on'] = bool(w0 & 0x02)
        elif op == 0xE3:  # G_SETOTHERMODE_H
            ln = (w0 & 0xFF) + 1
            sh = 32 - ((w0 >> 8) & 0xFF) - ln
            mask = ((1 << ln) - 1) << sh
            st['other_h'] = (st['other_h'] & ~mask) | (w1 & mask)
        elif op == 0xE2:  # G_SETOTHERMODE_L
            ln = (w0 & 0xFF) + 1
            sh = 32 - ((w0 >> 8) & 0xFF) - ln
            mask = ((1 << ln) - 1) << sh
            st['other_l'] = (st['other_l'] & ~mask) | (w1 & mask)
        elif op == 0xD9:  # G_GEOMETRYMODE
            st['geom'] = (st['geom'] & (w0 & 0xFFFFFF)) | w1
            clear = ~(w0 & 0xFFFFFF) & 0xFFFFFF
            mode = 0x00020000  # G_LIGHTING
            if clear & mode:
                st['lit'] = False
            if w1 & mode:
                st['lit'] = True
        elif op == 0xFD:  # G_SETTIMG
            st['timg'] = w1
            st['timg_fmt'] = (w0 >> 21) & 7
            st['timg_siz'] = (w0 >> 19) & 3
        elif op == 0xF0:  # G_LOADTLUT
            st['tlut'] = st['timg']
        elif op == 0xF3:  # G_LOADBLOCK
            st['loaded'] = st['timg']
        elif op == 0xF4:  # G_LOADTILE
            st['loaded'] = st['timg']
        elif op == 0xF5:  # G_SETTILE
            tile = (w1 >> 24) & 7
            t = st['tiles'].setdefault(tile, {})
            t.update(fmt=(w0 >> 21) & 7, siz=(w0 >> 19) & 3, cmt=(w1 >> 18) & 3, cms=(w1 >> 8) & 3)
        elif op == 0xF2:  # G_SETTILESIZE
            tile = (w1 >> 24) & 7
            t = st['tiles'].setdefault(tile, {})
            t['w'] = (((w1 >> 12) & 0xFFF) - ((w0 >> 12) & 0xFFF)) // 4 + 1
            t['h'] = ((w1 & 0xFFF) - (w0 & 0xFFF)) // 4 + 1
        elif op == 0xFA:  # G_SETPRIMCOLOR
            st['prim'] = tuple(w1.to_bytes(4, 'big'))
        elif op == 0xFC:  # G_SETCOMBINE
            st['combine'] = (w0, w1)
        elif op == 0xFB:  # G_SETENVCOLOR
            st['env_set'] = True
            st['env'] = tuple(w1.to_bytes(4, 'big'))


def _cur_tex(st):
    t = st['tiles'].get(0)
    if not t or 'w' not in t or 'loaded' not in st:
        return None
    a = st['loaded']
    return Tex(a & 0xFFFFFF, t['fmt'], t['siz'], t['w'], t['h'],
               (st['tlut'] & 0xFFFFFF) if t['fmt'] == 2 else 0, a >> 24, t.get('cms', 0), t.get('cmt', 0))


def decode_texture(m, tex, eyes=None):
    """Return a list of RGBA tuples (w*h). `eyes` supplies data for segments 8/9."""
    d = m.data
    if tex.seg != 6:
        if not eyes or tex.seg not in eyes:
            return [(255, 255, 255, 255)] * (tex.w * tex.h)
        base = eyes[tex.seg]
    else:
        base = tex.addr
    w, h, out = tex.w, tex.h, []
    n = w * h

    def rgba16(v):
        return ((v >> 11) * 255 // 31, ((v >> 6) & 31) * 255 // 31, ((v >> 1) & 31) * 255 // 31, 255 if v & 1 else 0)

    if tex.fmt == 0 and tex.siz == 2:
        for i in range(n):
            out.append(rgba16(struct.unpack_from('>H', d, base + 2 * i)[0]))
    elif tex.fmt == 0 and tex.siz == 3:
        for i in range(n):
            out.append(tuple(d[base + 4 * i:base + 4 * i + 4]))
    elif tex.fmt == 2:
        pal = [rgba16(struct.unpack_from('>H', d, tex.tlut + 2 * i)[0]) for i in range(256 if tex.siz == 1 else 16)]
        for i in range(n):
            if tex.siz == 1:
                out.append(pal[d[base + i]])
            else:
                b = d[base + i // 2]
                out.append(pal[(b >> 4) if i % 2 == 0 else (b & 15)])
    elif tex.fmt == 3:
        for i in range(n):
            if tex.siz == 0:
                b = d[base + i // 2]
                v = (b >> 4) if i % 2 == 0 else (b & 15)
                g = (v >> 1) * 255 // 7
                out.append((g, g, g, 255 if v & 1 else 0))
            elif tex.siz == 1:
                b = d[base + i]
                g, a = (b >> 4) * 17, (b & 15) * 17
                out.append((g, g, g, a))
            else:
                g, a = d[base + 2 * i], d[base + 2 * i + 1]
                out.append((g, g, g, a))
    elif tex.fmt == 4:
        for i in range(n):
            if tex.siz == 0:
                b = d[base + i // 2]
                g = ((b >> 4) if i % 2 == 0 else (b & 15)) * 17
            else:
                g = d[base + i]
            out.append((g, g, g, g))
    else:
        out = [(255, 0, 255, 255)] * n
    return out


def combine_rgb(tri, texel, env=None):
    """Evaluate the N64 colour combiner per texel with shade = 1 (the 3DS lights it).

    texel: (N, 3) floats 0-1. env: override for ENVIRONMENT (tunic / gauntlet colour), else the
    model's own env colour (or white if it never sets one). Returns (N, 3) floats 0-1."""
    import numpy as np
    w0, w1 = tri.combine
    prim = np.array(tri.prim[:3], float) / 255
    e = np.array((env if env is not None else (tri.env if tri.env_set else (255, 255, 255)))[:3], float) / 255
    one, zero = np.ones(3), np.zeros(3)
    prim_a = tri.prim[3] / 255
    env_a = (tri.env[3] if tri.env_set else 255) / 255

    def inp(kind, v, comb):
        common = {0: comb, 1: texel, 2: texel, 3: prim, 4: one, 5: e}
        if v in common:
            return common[v]
        if kind == 'a':
            return one if v == 6 else zero
        if kind == 'c':
            return {7: one, 8: one, 9: one, 10: prim_a * one, 11: one, 12: env_a * one}.get(v, zero)
        if kind == 'd':
            return one if v == 6 else zero
        return zero

    def cycle(a, b, c, d, comb):
        return (inp('a', a, comb) - inp('b', b, comb)) * inp('c', c, comb) + inp('d', d, comb)

    c1 = ((w0 >> 20) & 0xF, (w1 >> 28) & 0xF, (w0 >> 15) & 0x1F, (w1 >> 15) & 7)
    c2 = ((w0 >> 5) & 0xF, (w1 >> 24) & 0xF, w0 & 0x1F, (w1 >> 6) & 7)
    out = cycle(*c1, comb=texel)
    if tri.two_cycle:
        out = cycle(*c2, comb=out)
    return np.clip(out, 0, 1)
