"""Build an OoT3D Link replacement from an ML64 player zobj (adult or child, read from its header).

    python tools/build.py <adult.zobj> <romfs>/actor/zelda_link_boy_new.zar <out_dir>
    python tools/build.py <child.zobj> <romfs>/actor/zelda_link_child_new.zar <out_dir>

Scope: body, head, hands, fists, gauntlets and boots come from the zobj. Held items and the
first-person arms stay OoT3D's own models.

The tunic / eye / mouth texture swaps (link_body / link_eye / link_mouth .cmab) are written into
Link's original texture slots with Link's original sizes and formats, because the game copies the
animation textures into those slots.
"""
import sys, os, struct, dataclasses
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import zobj, cmb, cmbskel, pose, cmbwrite, cmabwrite, texenc, csab, zar, pica, fit
from tunics import TUNICS

CMB_NAME = 'boy/model/link_v2.cmb'
BODY_LIMBS = [1, 3, 4, 5, 6, 7, 8, 12, 13, 14, 16, 17, 20]
HEAD_LIMBS = [10, 11]

# Link mesh group -> zobj display lists (LUT name or 'limb', limb it is drawn in, optional zobj
# address of an N64 Mtx applied to it). Body groups: always the model's.
GROUPS = {
    45: [('limb', l) for l in BODY_LIMBS],
    46: [('limb', l) for l in HEAD_LIMBS],
    47: [],
    13: [('LHAND', 15)], 14: [('LFIST', 15)], 24: [('LHAND_BOTTLE', 15)],
    20: [('RHAND', 18)], 21: [('RFIST', 18)],
    # first-person arms (bow / hookshot aiming)
    26: [('FPS_LFOREARM', 14)], 27: [('FPS_LHAND', 15)], 28: [('limb', 16), ('FPS_RFOREARM', 17)],
}
# Equipment groups: group -> [(equipment key, zobj display lists, Link's materials for that part)].
# Key None = the hand holding the item (always the model's). An item that is not ported (not
# selected, or missing from the model) keeps Link's own meshes of those materials.
# ML64 back matrices: 0x5010 sheathed hilt, 0x5050 shield on the back.
SWORD_BACK, SHIELD_BACK = 0x5010, 0x5050


def rts_mtx(rz, tx, ty, tz):
    """N64 row-vector matrix: rotation about Z (degrees), then translation (guRTSF with rx = ry = 0)."""
    c, s_ = np.cos(np.radians(rz)), np.sin(np.radians(rz))
    M = np.eye(4)
    M[:2, :2] = [[c, s_], [-s_, c]]
    M[3, :3] = (tx, ty, tz)
    return M


# Z64Online's back matrices (UniversalAliasTable). A model can hide its back items with a zero-scale
# matrix; equipment-pack items still show on the back, placed with these defaults.
BACK_MTX_DEFAULT = {SWORD_BACK: rts_mtx(0, -715, -310, 78), SHIELD_BACK: rts_mtx(180, 935, 94, 29)}
MS_SHEATH = ('master_sword', [('SWORD_SHEATH', 19)], {6})
MS_SHEATHED = ('master_sword', [('SWORD_SHEATH', 19), ('SWORD_HILT', 19, SWORD_BACK)], {6, 27, 28})
HYLIAN_BACK = ('hylian_shield', [('SHIELD_HYLIAN', 19, SHIELD_BACK)], {34})
MIRROR_BACK = ('mirror_shield', [('SHIELD_MIRROR', 19, SHIELD_BACK)], {31, 32})
BIGGORON = {7, 8, 9, 10, 11, 12}
ITEMS = {
    0: [MS_SHEATHED, HYLIAN_BACK], 1: [MS_SHEATH, HYLIAN_BACK],
    2: [MS_SHEATHED, MIRROR_BACK], 3: [MS_SHEATH, MIRROR_BACK],
    31: [MS_SHEATHED], 42: [MS_SHEATH],
    # OoT3D's Biggoron scabbard on the back has no N64 equivalent: always Link's
    7: [MIRROR_BACK, ('biggoron_back', [], {30})], 8: [MIRROR_BACK, ('biggoron_back', [], {30} | BIGGORON)],
    10: [HYLIAN_BACK, ('biggoron_back', [], {30})], 11: [HYLIAN_BACK, ('biggoron_back', [], {30} | BIGGORON)],
    16: [(None, [('LFIST', 15)], {22}), ('master_sword', [('SWORD_HILT', 15), ('SWORD_BLADE', 15)], {27, 28, 29})],
    37: [(None, [('LFIST', 15)], {22}), ('biggoron', [('LONGSWORD_HILT', 15), ('LONGSWORD_BLADE', 15)], BIGGORON)],
    38: [(None, [('LFIST', 15)], {22}), ('biggoron', [('LONGSWORD_HILT', 15), ('LONGSWORD_BROKEN', 15)], BIGGORON)],
    32: [(None, [('LFIST', 15)], {22}), ('hammer', [('HAMMER', 15)], {20, 21})],
    23: [(None, [('RFIST', 18)], {22}), ('hylian_shield', [('SHIELD_HYLIAN', 18)], {34})],
    39: [(None, [('RFIST', 18)], {22}), ('mirror_shield', [('SHIELD_MIRROR', 18)], {31, 32})],
    29: [(None, [('RFIST', 18)], {22}), ('bow', [('BOW', 18)], {5})],
    30: [(None, [('FPS_RHAND', 18)], {22}), ('bow', [('BOW', 18)], {5})],
    33: [(None, [('RFIST', 18)], {22}), ('hookshot', [('HOOKSHOT', 18)], {26})],
    34: [(None, [('FPS_RHAND', 18)], {22}), ('hookshot', [('FPS_HOOKSHOT', 18)], {25, 26})],
    40: [(None, [('RHAND', 18)], {22}), ('ocarina', [('OCARINA_TIME', 18)], {33})],
    41: [(None, [('RHAND', 18)], {22}), ('ocarina', [('OCARINA_TIME', 18)], {33})],
    25: [('bottle', [('BOTTLE', 15)], {2, 3})],
    4: [('gauntlets', [('UPGRADE_LFOREARM', 14)], {14, 15})],
    5: [('gauntlets', [('UPGRADE_LHAND', 15)], {14, 15})],
    6: [('gauntlets', [('UPGRADE_LFIST', 15)], {14, 15})],
    17: [('gauntlets', [('UPGRADE_RFOREARM', 17)], {14, 15})],
    18: [('gauntlets', [('UPGRADE_RHAND', 18)], {14, 15})],
    19: [('gauntlets', [('UPGRADE_RFIST', 18)], {14, 15})],
    15: [('hover_boots', [('BOOT_LHOVER', 8)], {23})], 22: [('hover_boots', [('BOOT_RHOVER', 5)], {23})],
    35: [('iron_boots', [('BOOT_LIRON', 8)], {24})], 36: [('iron_boots', [('BOOT_RIRON', 5)], {24})],
}
EQUIPMENT_LABELS = {  # selectable equipment, in display order
    'master_sword': 'Master Sword (sheath, hilt, blade)', 'biggoron': 'Biggoron Sword / Giant\'s Knife',
    'hylian_shield': 'Hylian Shield', 'mirror_shield': 'Mirror Shield', 'hammer': 'Megaton Hammer',
    'bow': 'Bow', 'hookshot': 'Hookshot / Longshot', 'ocarina': 'Ocarina', 'bottle': 'Bottle',
    'gauntlets': 'Gauntlets', 'hover_boots': 'Hover Boots', 'iron_boots': 'Iron Boots',
}
LINK_BOW_MAT = 5  # Link's bow material (p_tex05)
BOW_GROUPS = {29: 'RFIST', 30: 'FPS_RHAND'}  # bow + the hand holding it
# Items seated where Link's own sits in the right hand (bone 20), when ported:
# group -> (equipment key, item, Link's material, hand). Link's two ocarina grips: g41 = g40 turned 179 deg.
SEATED = {40: ('ocarina', 'OCARINA_TIME', 33, 'RHAND'), 41: ('ocarina', 'OCARINA_TIME', 33, 'RHAND')}
# Link meshes the game deforms by writing straight into their vertex data at fixed offsets (bow
# string): their vertices must stay at Link's original offsets.
PINNED_GROUPS = {43, 44}
# A different-shaped item (e.g. N64 vs 3D fairy ocarina) fits Link's only loosely, at an arbitrary
# turn: seat it only when the fit clearly beats the model's authored placement (rms < this x before)
# with a small turn.
SEAT_MIN_GAIN = 0.6
SEAT_GOOD_FIT, SEAT_SMALL_TURN = 0.4, 30  # any turn is trusted only for a fit this good
FORK_ITEMS = {'SLINGSHOT'}  # fitted by handle + fork tips instead (the game draws the string)
FAR_FRAGMENT = 1500  # drop stray bits of a list this far from its limb (e.g. a speck in FPS_LHAND)
TEMPLATE_OPAQUE, TEMPLATE_CUTOUT = 0, 18
MAT_TUNIC, MAT_EYE, MAT_MOUTH = 1, 16, 17
MAT_GAUNTLET = 14  # Link's gauntlet metal: constant colour 4 is set by the game (silver / gold)
MAT_BOTTLE_GLASS, MAT_BOTTLE_CONTENTS = 2, 3  # Link's bottle: glass / contents (constant colour set by the game)
TEX_TUNIC, TEX_EYE, TEX_MOUTH = 1, 15, 16
ZAR_NAME = 'zelda_link_boy_new.zar'
TUNIC_ANIM = True  # tunic colour animated by link_body.cmab (adult only; child Link has no tunic swap)
BODY_CMAB = 'boy/misc/link_body.cmab'
EYE_CMAB, EYE_NAMES = 'boy/misc/link_eye.cmab', ['link_e%02d' % i for i in range(8)]
MOUTH_CMAB, MOUTH_NAMES = 'boy/misc/link_mouth.cmab', ['link_m%02d' % i for i in range(4)]
WRAP = {0: 0x2901, 1: 0x8370, 2: 0x812F, 3: 0x812F}  # N64 cms/cmt -> GL wrap
CLAMP = 0x812F
GAUNTLET_COLOR = (255, 255, 255, 255)  # N64 silver gauntlets (gold: 254, 207, 15)
# Diagnostic switch: True puts eyes, mouth and tunic on ordinary new materials (no texture swaps)
STATIC_FACE_AND_TUNIC = False


def decode(m, tex, tint=None, base=None):
    px = zobj.decode_texture(m, tex, eyes=({tex.seg: base} if base is not None else {8: 0x0, 9: 0x4000}))
    if tint:
        px = [(r * tint[0] // 255, g * tint[1] // 255, b * tint[2] // 255, a) for r, g, b, a in px]
    return px


MAT_SIZE = 0x15C
# OoT3D Randomizer "Custom Tunic Colors" is NOT supported: it swaps in a texture painted for Link's
# tunic UVs, which no zobj shares. Off: the tunic is the model's own (vanilla tunic swap works).
# The dummy materials that absorb the randomizer's fixed-offset patches stay on regardless.
RANDO_CUSTOM_TUNIC = False
# OoT3D Randomizer CustomModel_EditLinkToCustomTunic (code/src/custom_models.c): file offset -> byte
RANDO_TUNIC_EDITS = {
    0x6C4: 0x04, 0x6CC: 0x0B, 0x6CD: 0x00, 0x6CE: 0x11, 0x6CF: 0x00,  # mat 1 combiner list
    0x3588: 0x04, 0x3589: 0x01, 0x3594: 0x76, 0x359C: 0x03,             # combiner 2
    0x35B0: 0x00, 0x35B1: 0x21, 0x35BE: 0xC0, 0x35BF: 0x84, 0x35C4: 0x00,  # combiner 3
    0x36FC: 0x78, 0x36FE: 0x77, 0x36FF: 0x85,                           # combiner 11
}
RANDO_OTHER_WRITES = [0x44E1, 0x44EC, 0x4C52]  # tunic texture entry (size, format), adult deku stick

ADULT = {k: v for k, v in globals().items() if k.isupper()}

# Child Link (zelda_link_child_new.zar). Same 25-bone skeleton as adult; no first-person bow /
# hookshot, gauntlets or boots. Groups identified from renders of childlink_v2.cmb.
CHILD = dict(
    CMB_NAME='child/model/childlink_v2.cmb', ZAR_NAME='zelda_link_child_new.zar',
    GROUPS={
        24: [('limb', l) for l in BODY_LIMBS], 26: [('limb', l) for l in HEAD_LIMBS], 25: [],
        0: [('LHAND', 15)], 1: [('LFIST', 15)], 7: [('LHAND_BOTTLE', 15)],
        3: [('RHAND', 18)], 4: [('RFIST', 18)],
    },
    # Child Link materials: hand 16, Kokiri sword sheath 24 / hilt 20 / blade 0, Hylian shield 17,
    # Deku shield 9, Master Sword 18 19 21, boomerang 5 6 7, bottle 3 4, ocarinas 10 / 22,
    # slingshot 23, first-person sleeve 25, Goron bracelet 26. Groups 22 (slingshot string) and
    # 23 (Deku stick) are placed by game code, so Link's own stay.
    ITEMS={
        9: [('kokiri_sword', [('SWORD_SHEATH', 19), ('SWORD_HILT', 19, 0x5010)], {24, 20}),
            ('hylian_shield', [('SHIELD_HYLIAN_BACK', 19)], {17})],
        10: [('kokiri_sword', [('SWORD_SHEATH', 19)], {24}), ('hylian_shield', [('SHIELD_HYLIAN_BACK', 19)], {17})],
        11: [('kokiri_sword', [('SWORD_SHEATH', 19), ('SWORD_HILT', 19, 0x5010)], {24, 20}),
             ('deku_shield', [('SHIELD_DEKU', 19, 0x5050)], {9})],
        12: [('kokiri_sword', [('SWORD_SHEATH', 19)], {24}), ('deku_shield', [('SHIELD_DEKU', 19, 0x5050)], {9})],
        13: [('deku_shield', [('SHIELD_DEKU', 19, 0x5050)], {9})],
        14: [('kokiri_sword', [('SWORD_SHEATH', 19), ('SWORD_HILT', 19, 0x5010)], {24, 20})],
        21: [('kokiri_sword', [('SWORD_SHEATH', 19)], {24})],
        2: [(None, [('LFIST', 15)], {16}), ('kokiri_sword', [('SWORD_HILT', 15), ('SWORD_BLADE', 15)], {20, 0})],
        16: [(None, [('LHAND', 15)], {16}), ('master_sword', [('MASTER_SWORD', 15)], {18, 19, 21})],
        6: [(None, [('LFIST', 15)], {16}), ('boomerang', [('BOOMERANG', 15)], {5, 6, 7})],
        5: [(None, [('RFIST', 18)], {16}), ('deku_shield', [('SHIELD_DEKU', 18)], {9})],
        8: [('bottle', [('BOTTLE', 15)], {3, 4})],
        17: [(None, [('RHAND', 18)], {16}), ('ocarina', [('OCARINA_FAIRY', 18)], {10})],
        18: [(None, [('RHAND', 18)], {16}), ('ocarina', [('OCARINA_TIME', 18)], {22})],
        19: [(None, [('RFIST', 18)], {16}), ('slingshot', [('SLINGSHOT', 18)], {23})],
        20: [(None, [('FPS_RIGHT_ARM', 18)], {16, 25}), ('slingshot', [('SLINGSHOT', 18)], {23})],
        15: [('goron_bracelet', [('GORON_BRACELET', 14)], {26})],
    },
    EQUIPMENT_LABELS={
        'kokiri_sword': 'Kokiri Sword (sheath, hilt, blade)', 'master_sword': 'Master Sword (pedestal)',
        'deku_shield': 'Deku Shield', 'hylian_shield': 'Hylian Shield', 'boomerang': 'Boomerang',
        'slingshot': 'Slingshot', 'ocarina': 'Ocarinas', 'bottle': 'Bottle', 'goron_bracelet': 'Goron Bracelet',
    },
    BOW_GROUPS={}, PINNED_GROUPS={22, 23},  # slingshot string, Deku stick
    BACK_MTX_DEFAULT={0x5010: rts_mtx(0, -440, -211, 0), 0x5050: rts_mtx(180, 545, 0, 80)},
    SEATED={17: ('ocarina', 'OCARINA_FAIRY', 10, 'RHAND'), 18: ('ocarina', 'OCARINA_TIME', 22, 'RHAND'),
            19: ('slingshot', 'SLINGSHOT', 23, 'RFIST'), 20: ('slingshot', 'SLINGSHOT', 23, 'FPS_RIGHT_ARM')},
    TEMPLATE_OPAQUE=2, TEMPLATE_CUTOUT=13,
    MAT_TUNIC=None, MAT_EYE=14, MAT_MOUTH=15, TEX_TUNIC=None, TEX_EYE=16, TEX_MOUTH=17,
    MAT_GAUNTLET=None, MAT_BOTTLE_GLASS=3, MAT_BOTTLE_CONTENTS=4,
    TUNIC_ANIM=False, BODY_CMAB=None,
    EYE_CMAB='child/misc/childlink_eye.cmab', EYE_NAMES=['c_eye%02d' % i for i in range(1, 9)],
    MOUTH_CMAB='child/misc/childlink_mouth.cmab', MOUTH_NAMES=['c_mouth%02d' % i for i in range(1, 5)],
    # OoT3D Randomizer CustomModel_EditChildLinkToCustomTunic (code/src/custom_models.c)
    RANDO_TUNIC_EDITS={o: None for o in (0x6C4, 0x6CC, 0x6CD, 0x2974, 0x2975, 0x2978, 0x2980, 0x2984,
                                         0x2985, 0x2988, 0x299C, 0x299D, 0x29A0, 0x29AA, 0x29B0)},
    RANDO_OTHER_WRITES=[0x3441, 0x344C],  # tunic texture entry (size, format)
)


def use_profile(profile):
    """The module constants describe the Link model being replaced; switch them to `profile`."""
    globals().update(ADULT)
    globals().update(profile)


RANDO_ASSETS = [  # the randomizer's asset archive (its tunic texture is used as a layout reference)
    os.path.expandvars('%APPDATA%/Citra/load/mods/0004000000033500/romfs/actor/zelda_gi_melody.zar'),
    os.path.join(os.path.dirname(__file__), '..', 'work', 'zelda_gi_melody.zar'),
]


def rando_tunic_reference():
    """(luminance, alpha) of the randomizer's adult tunic texture, or None if not available."""
    for path in RANDO_ASSETS:
        if os.path.exists(path):
            files = dict(zar.read_zar(path)[1])
            d = files.get('misc/link_body.cmab')
            if not d:
                continue
            texdata = struct.unpack_from('<I', d, 0x1C)[0]
            txpt = 0x20 + struct.unpack_from('<I', d, 0x30)[0]
            size, lv, etc, cube, w, h, fmt, doff, ni = struct.unpack_from('<IHBBHHIII', d, txpt + 8)
            px = np.array(pica.decode(fmt, w, h, d[texdata + doff:texdata + doff + size]), float) / 255
            px = px.reshape(h, w, 4)
            print('tunic atlas planned against the randomizer tunic texture:', path)
            return px[..., :3].mean(-1), px[..., 3]
    return None


def rando_tunic_combiners(t, materials):
    """Apply the randomizer's custom-tunic combiner edits ourselves (vanilla layout copy), so the
    tunic material reads constant colour 0, which the randomizer's link_body.cmab animates.
    Constant 0 is set to white, so without the randomizer the tunic shows its own texture."""
    buf = bytearray(t.raw)
    for o, v in RANDO_TUNIC_EDITS.items():
        buf[o] = v
    mat_base = t.header['mats'] + 0xC
    comb_base = mat_base + len(t.materials) * MAT_SIZE
    combiners = [bytes(buf[comb_base + 0x28 * k:comb_base + 0x28 * (k + 1)]) for k in range(len(t.combiners))]
    m1 = bytearray(materials[MAT_TUNIC])
    rec = mat_base + MAT_TUNIC * MAT_SIZE
    m1[0x120:0x12C] = buf[rec + 0x120:rec + 0x12C]
    m1[0xB4:0xB8] = bytes([255, 255, 255, 255])  # constant colour 0
    materials[MAT_TUNIC] = bytes(m1)
    return combiners


def with_verts(tri, vs):
    """Copy of a triangle with new vertices, keeping tags set on it (bottle, gauntlet, src)."""
    out = dataclasses.replace(tri, v=vs)
    for k, v in vars(tri).items():
        if k not in vars(out):
            setattr(out, k, v)
    return out


def decode_tri(m, tri, env=None, base=None):
    """Texture of an N64 triangle with its colour combiner baked in (primitive / env colours).
    Triangles from an equipment pack carry their own file in tri.src."""
    m = getattr(tri, 'src', m)
    px = decode(m, tri.tex, base=base)
    a = np.array(px, float) / 255
    rgb = zobj.combine_rgb(tri, a[:, :3], env=env)
    return [tuple(int(round(c * 255)) for c in col) + (p[3],) for col, p in zip(rgb, px)]


def set_sphere_map(raw):
    """Texture coordinator 0 -> camera sphere environment map (3DS equivalent of N64 TEXGEN)."""
    raw = bytearray(raw)
    raw[0x58 + 2] = 3
    return bytes(raw)


def resize(px, w, h, nw, nh):
    if (w, h) == (nw, nh):
        return px
    im = Image.new('RGBA', (w, h))
    im.putdata(px)
    return list(im.resize((nw, nh), Image.BILINEAR).getdata())


WHITE = (255, 255, 255, 255)
TINT_CONST = 0  # constant colour slot animated by link_body.cmab (unused by Link's template materials)
# Tunic tint, as two TEV stages replacing Link's stage 0 (vertex colour * texture, RGB scale 2):
#   stage 0: texture * constant 0 (RGB), vertex alpha * texture alpha
#   stage 1: previous * vertex colour (RGB, scale 2), alpha passed through
# then Link's stage 1 (the game's fade / flash colour). The animated constant sits on stage 0, the
# same stage and slot the OoT3D Randomizer's working custom-tunic material animates.
TINT_STAGES = [
    struct.pack('<6H3H3H3H3HI', 0x2100, 0x2100, 1, 1, 0x8579, 0x8579,
                0x84C0, 0x8576, 0x8576, 0x300, 0x300, 0x300,
                0x8577, 0x84C0, 0x8576, 0x302, 0x302, 0x302, TINT_CONST),
    struct.pack('<6H3H3H3H3HI', 0x2100, 0x1E01, 2, 1, 0x8579, 0x8579,
                0x8578, 0x8577, 0x8576, 0x300, 0x300, 0x300,
                0x8578, 0x8577, 0x8576, 0x302, 0x302, 0x302, 0),
]


def add_tint_stage(raw, comb_idx, color, combiners):
    """comb_idx: index of TINT_STAGES[0] in the combiner table (TINT_STAGES[1] follows it)."""
    raw = bytearray(raw)
    n = struct.unpack_from('<I', raw, 0x120)[0]
    stages = list(struct.unpack_from('<%dH' % n, raw, 0x124))
    assert combiners[stages[0]][:0x24] == combiners[0][:0x24], 'unexpected template stage 0'
    stages = [comb_idx, comb_idx + 1] + stages[1:]
    assert len(stages) <= 6
    struct.pack_into('<I', raw, 0x120, len(stages))
    struct.pack_into('<%dH' % len(stages), raw, 0x124, *stages)
    raw[0xB4 + 4 * TINT_CONST:0xB8 + 4 * TINT_CONST] = bytes(color[:3]) + b'\xff'
    assert len(raw) == MAT_SIZE
    return bytes(raw)


def cmab_textures(d):
    """(name, w, h, gl_format, data) of a texture-palette cmab's textures."""
    texdata = struct.unpack_from('<I', d, 0x1C)[0]
    strt = struct.unpack_from('<I', d, 0x18)[0]
    txpt = 0x20 + struct.unpack_from('<I', d, 0x30)[0]
    n = struct.unpack_from('<H', d, txpt + 4)[0]
    out = []
    for i in range(n):
        size, lv, etc, cube, w, h, fmt, doff, ni = struct.unpack_from('<IHBBHHIII', d, txpt + 8 + 0x18 * i)
        so = strt + 8 + 4 * n + struct.unpack_from('<I', d, strt + 8 + 4 * ni)[0]
        name = d[so:d.index(b'\0', so)].decode()
        out.append((name, w, h, fmt, d[texdata + doff:texdata + doff + size]))
    return out


log = print  # progress / fit messages (the web page swaps this out)


def model_age(zobj_bytes):
    """'adult' / 'child' for an OoT ML64 zobj, None for anything else (e.g. MM zobjs in the same .pak)."""
    i = zobj_bytes.find(b'MODLOADER64')
    if i != 0x5000:
        return None
    return {0: 'adult', 1: 'child'}.get(zobj_bytes[0x500B])


def target_zar(age):
    """romfs/actor file name a zobj of this age replaces."""
    return (CHILD if age == 'child' else ADULT)['ZAR_NAME']


def item_parts():
    """{equipment key: set of zobj display-list names it is built from}."""
    need = {}
    for ents in ITEMS.values():
        for key, comps, _ in ents:
            if key in EQUIPMENT_LABELS:
                need.setdefault(key, set()).update(c[0] for c in comps)
    return need


def equipment_sources(L, paks, age):
    """{key: [source ids]}: 'model' when the model has every part, a pak's id when the pak supplies
    at least one part and the model / pak together cover the rest. paks: [(id, parsed pak, bytes)]."""
    out = {}
    for key, parts in item_parts().items():
        srcs = ['model'] if parts <= set(L) else []
        for pid, info, _ in paks:
            have = set(info['dls'].get(age, {}))
            if parts & have and parts <= have | set(L):
                srcs.append(pid)
        out[key] = srcs
    return out


def default_source(srcs):
    """Equipment packs win over the model's own items; otherwise the model; otherwise OoT3D's."""
    paks = [s_ for s_ in srcs if s_ != 'model']
    return paks[0] if paks else 'model' if srcs else 'oot3d'


def equipment_options(zobj_src, paks=()):
    """[(key, label, [source ids], default source)] for the zobj's age, in display order."""
    m = zobj.read(zobj_src)
    use_profile(CHILD if zobj.is_child(m) else ADULT)
    age = 'child' if zobj.is_child(m) else 'adult'
    srcs = equipment_sources(zobj.lut(m), list(paks), age)
    return [(k, v, srcs[k], default_source(srcs[k])) for k, v in EQUIPMENT_LABELS.items() if k in srcs]


def back_kind(key, comps):
    """'shield' / 'sword' for equipment parts carried on the back (drawn on the sheath limb, 19)."""
    if key == 'biggoron_back':  # OoT3D's Biggoron scabbard (Link's own meshes only)
        return 'sword'
    if comps and all(c[1] == 19 for c in comps):
        if all(c[0].startswith('SHIELD') for c in comps):
            return 'shield'
        if all(c[0].startswith('SWORD') for c in comps):
            return 'sword'
    return None


def convert(zobj_src, zar_src, equipment=None, paks=(), hide_back=()):
    """Convert one zobj. zobj_src / zar_src: paths or bytes (zar = Link's original archive of the same
    age). paks: equipment packs [(id, equippak.parse() result, zobj bytes)].
    equipment: None (every item from a pack or the model, packs first), a list of keys (those items,
    the rest OoT3D's), or {key: 'model' | 'oot3d' | pack id}.
    hide_back: back items to leave off, {'shield', 'sword'} (still shown in hand), e.g. for long hair
    or a cape they would clip into.
    Returns {'name': romfs/actor file name, 'zar': bytes, 'cmb': bytes}."""
    m = zobj.read(zobj_src)
    use_profile(CHILD if zobj.is_child(m) else ADULT)
    age = 'child' if zobj.is_child(m) else 'adult'
    log('%s model -> %s' % (age, ZAR_NAME))
    L = zobj.lut(m)
    paks = [pk for pk in paks if pk[1]['dls'].get(age)]
    srcs = equipment_sources(L, paks, age)
    if equipment is None:
        choice = {k: default_source(v) for k, v in srcs.items()}
    elif isinstance(equipment, dict):
        choice = {k: equipment.get(k, default_source(v)) for k, v in srcs.items()}
    else:
        choice = {k: default_source(v) if k in equipment else 'oot3d' for k, v in srcs.items()}
    for k, src in list(choice.items()):
        if src != 'oot3d' and src not in srcs[k]:
            log(f'{EQUIPMENT_LABELS[k]}: {src} does not have it, using OoT3D\'s')
            choice[k] = 'oot3d'
    ported = {k for k, src in choice.items() if src != 'oot3d'}
    # display lists taken from equipment packs instead of the model
    pak_models = {pid: zobj.Model(data, m.limbs, mtx_limb=m.mtx_limb) for pid, _, data in paks}
    pak_dls = {pid: info['dls'][age] for pid, info, _ in paks}
    override = {}
    for k, src in choice.items():
        if src not in ('model', 'oot3d'):
            for part in item_parts()[k]:
                if part in pak_dls[src]:
                    override[part] = (pak_models[src], pak_dls[src][part])
    names = {pid: info['name'] or pid for pid, info, _ in paks}
    for k in EQUIPMENT_LABELS:
        if k in choice:
            src = choice[k]
            log(f'  {EQUIPMENT_LABELS[k]}: ' + {'model': 'model', 'oot3d': 'OoT3D'}.get(src, names.get(src, src)))
    zar_bytes = zar_src if isinstance(zar_src, (bytes, bytearray)) else open(zar_src, 'rb').read()
    _, files = zar.read_zar(zar_bytes)
    files = dict(files)
    t = cmb.read(files[CMB_NAME])
    bones, world = cmbskel.read_skeleton(t.raw)
    lw, trans, new_world = pose.fit(m, bones, world)

    def n64_mtx(addr):
        hi = struct.unpack_from('>16h', m.data, addr)
        lo = struct.unpack_from('>16H', m.data, addr + 32)
        return np.array([hi[i] + lo[i] / 65536 for i in range(16)]).reshape(4, 4)

    def dl(name, limb, mtx=None):
        src_model, addr = override.get(name, (m, m.limbs[limb].dl if name == 'limb' else L.get(name)))
        if addr is None:
            return []
        tris = zobj.dl_tris(src_model, addr, limb)
        if src_model is not m:  # an equipment pack: its textures live in its own file
            for tr in tris:
                tr.src = src_model
        if name.startswith('FPS_'):
            tris = [tr for tr in tris
                    if not all(v[0] == limb and np.linalg.norm(v[1]) > FAR_FRAGMENT for v in tr.v)]
        if name == 'BOTTLE':  # ENV-coloured part = contents (game tints mat 3's constant colour)
            for tr in tris:
                tr.bottle = 'contents' if tr.tunic else 'glass'
        if name.startswith('UPGRADE_'):  # ENV here is the gauntlet colour (silver / gold), not the tunic
            for tr in tris:
                if tr.tunic:
                    tr.gauntlet = True
        if mtx is None:
            return tris
        M = n64_mtx(mtx)  # row-vector convention: v' = v @ M (only for vertices in `limb` space)
        if abs(np.linalg.det(M[:3, :3])) < 1e-6:  # zero-scale back matrix: the model hides this item
            if src_model is m or mtx not in BACK_MTX_DEFAULT:
                return []
            M = BACK_MTX_DEFAULT[mtx]  # an equipment pack's item still shows on the back
        out = []
        for tr in tris:
            vs = []
            for vl, pos, st, col in tr.v:
                if vl == limb:
                    pos = tuple(np.array([*pos, 1.0]) @ M)[:3]
                    if tr.lit:
                        n = np.array([c - 256 if c > 127 else c for c in col[:3]], float) @ M[:3, :3]
                        col = tuple(int(c) & 255 for c in np.round(n)) + (col[3],)
                vs.append((vl, pos, st, col))
            out.append(with_verts(tr, vs))
        return out

    group_tris = {g: [tr for src in srcs for tr in dl(*src)] for g, srcs in GROUPS.items()}
    for g, ents in ITEMS.items():
        group_tris[g] = [tr for key, comps, _ in ents
                         if (key is None or key in ported) and back_kind(key, comps) not in hide_back
                         for src in comps for tr in dl(*src)]

    # ---- bow: OoT3D draws the string itself (groups 43/44 on bones 23/24) at Link's bow tips, so
    # the zobj bow is fitted onto Link's bow (tips + grip); the hand follows by the grip offset.
    inv_world = [np.linalg.inv(wm) for wm in world]

    def link_mesh_points(group, mat, bone, with_uv=False):
        pts, uvs = [], []
        for s_, mt, gid in t.meshes:
            if gid == group and mt == mat:
                for p_, vs in cmb.triangles(t, t.sepds[s_]):
                    for v in vs:
                        x = np.array([*v['pos'], 1.0])
                        wp = x if p_.skinning == 2 else world[v['bones'][0]] @ x
                        pts.append((inv_world[bone] @ wp)[:3])
                        uvs.append(v['uv'])
        return (np.array(pts), np.array(uvs)) if with_uv else np.array(pts)

    def aim_pose():
        """Bone world matrices (refit skeleton) in the first-person bow aiming animation."""
        import animview
        _, nodes = csab.read(files[AIM_ANIM])
        nodes = {b: {k: v for k, v in n.items() if b == 1 or not k.startswith('t')} for b, n in nodes.items()}
        refit = [dict(bn, trans=tuple(trans[i])) for i, bn in enumerate(bones)]
        return animview.posed_world(refit, nodes, 0)

    def tips_and_grip(a):
        c0 = a.mean(0)
        ax = np.linalg.svd(a - c0)[2][0]
        pr = (a - c0) @ ax
        span = pr.max() - pr.min()
        return np.array([a[pr < pr.min() + 0.03 * span].mean(0), a[pr > pr.max() - 0.03 * span].mean(0),
                         a[np.abs(pr - (pr.min() + pr.max()) / 2) < 0.1 * span].mean(0)])

    def similarity(src, dst):
        ca, cb = src.mean(0), dst.mean(0)
        u, sv, vt = np.linalg.svd((src - ca).T @ (dst - cb))
        d = np.diag([1, 1, np.sign(np.linalg.det(u @ vt))])
        r = (u @ d @ vt).T
        sc = np.trace(np.diag(sv) @ d) / ((src - ca) ** 2).sum()
        return sc, r, cb - sc * r @ ca

    def moved(tris, limb, fn, rot=None):
        out = []
        for tr in tris:
            vs = []
            for vl, pos, st, col in tr.v:
                if vl == limb:
                    pos = tuple(fn(np.array(pos, float)))
                    if rot is not None and tr.lit:
                        n = rot @ np.array([c - 256 if c > 127 else c for c in col[:3]], float)
                        col = tuple(int(round(c)) & 255 for c in n) + (col[3],)
                vs.append((vl, pos, st, col))
            out.append(with_verts(tr, vs))
        return out

    # Bow: OoT3D draws the string itself and pins it to Link's 3D bow tips, so the zobj bow is fitted
    # onto Link's bow (tips + grip). The hand pivots about the wrist (bone origin) to follow the grip,
    # which keeps the wrist joined to the forearm.
    bow_groups = BOW_GROUPS if 'bow' in ported else {}
    if bow_groups:
        src = tips_and_grip(np.array([v[1] for tr in dl('BOW', 18) for v in tr.v if v[0] == 18], float))
    for g, hand in bow_groups.items():
        dst = tips_and_grip(link_mesh_points(g, LINK_BOW_MAT, 20))
        sc, r, tr_ = similarity(src, dst)
        g_new = sc * r @ src[2] + tr_
        ax_old, ax_new = src[1] - src[0], r @ (src[1] - src[0])
        p_ = np.stack([src[2] / np.linalg.norm(src[2]), ax_old / np.linalg.norm(ax_old)]) * np.array([[3.0], [1.0]])
        q_ = np.stack([g_new / np.linalg.norm(g_new), ax_new / np.linalg.norm(ax_new)])
        u_, _, vt_ = np.linalg.svd(p_.T @ q_)
        rh = (u_ @ np.diag([1, 1, np.sign(np.linalg.det(u_ @ vt_))]) @ vt_).T
        group_tris[g] = (moved(dl('BOW', 18), 18, lambda p: sc * r @ p + tr_, rot=r)
                         + moved(dl(hand, 18), 18, lambda p: rh @ p, rot=rh))

    # Ocarina / slingshot: the 3D animations bring Link's own item to the mouth / aim it, and the
    # game pins the slingshot string to Link's slingshot, so the zobj item is seated (rigid ICP, UV
    # tie-break) where Link's sits in the same hand, per group.
    for g, (key, item, link_mat, hand) in SEATED.items():
        if key not in ported:
            continue
        it_tris = dl(item, 18) if item in L else []
        pts = [(np.array(v[1], float), (v[2][0] / 32 / tr.tex.w, 1 - v[2][1] / 32 / tr.tex.h) if tr.tex else (0.5, 0.5))
               for tr in it_tris for v in tr.v if v[0] == 18]
        if not pts:
            group_tris[g] = dl(hand, 18)
            continue
        src_p, src_uv = np.array([o[0] for o in pts]), np.array([o[1] for o in pts])
        dst_p, dst_uv = link_mesh_points(g, link_mat, 20, with_uv=True)
        if item in FORK_ITEMS:  # string drawn by the game between Link's fork tips: match the tips
            sc, r, tr_, err = fit.fit_fork(src_p, dst_p)
            log('%s group %d: fork tips fitted (scale %.2f, %.1f deg, tip error %.1f)'
                  % (item, g, sc, np.degrees(np.arccos(np.clip((np.trace(r) - 1) / 2, -1, 1))), err))
            group_tris[g] = (moved(it_tris, 18, lambda p, sc=sc, r=r, tr_=tr_: sc * r @ p + tr_, rot=r)
                             + dl(hand, 18))
            continue
        r, tr_, rms = fit.icp(src_p, dst_p, src_uv=src_uv, dst_uv=dst_uv)
        _, before = fit._nearest(np.unique(src_p, axis=0), np.unique(dst_p, axis=0))
        turn = np.degrees(np.arccos(np.clip((np.trace(r) - 1) / 2, -1, 1)))
        gain = rms / before.mean()
        keep_authored = not (gain < SEAT_GOOD_FIT or (gain < SEAT_MIN_GAIN and turn < SEAT_SMALL_TURN))
        log('%s group %d: authored placement %.1f from Link item, fit %.1f after %.1f deg -> %s'
              % (item, g, before.mean(), rms, np.degrees(np.arccos(np.clip((np.trace(r) - 1) / 2, -1, 1))),
                 'kept authored' if keep_authored else 'seated'))
        if keep_authored:
            group_tris[g] = it_tris + dl(hand, 18)
            continue
        group_tris[g] = moved(it_tris, 18, lambda p, r=r, tr_=tr_: r @ p + tr_, rot=r) + dl(hand, 18)

    materials = list(t.materials)
    # OoT3D Randomizer compatibility: it patches link_v2.cmb in memory at fixed vanilla offsets
    # (custom tunic combiners, tunic texture entry, adult deku stick). Pad the material array so all
    # of those bytes land in unused dummy materials, and allocate real materials around them.
    mat_base = t.header['mats'] + 0xC
    reserved = {(o - mat_base) // MAT_SIZE for o in list(RANDO_TUNIC_EDITS) + RANDO_OTHER_WRITES
                if o >= mat_base + len(t.materials) * MAT_SIZE}
    while reserved and len(materials) <= max(reserved):
        materials.append(materials[TEMPLATE_OPAQUE])
    free_slots = [i for i in range(len(t.materials), len(materials)) if i not in reserved]

    def alloc_material(raw):
        if free_slots:
            i = free_slots.pop(0)
            materials[i] = raw
            return i
        materials.append(raw)
        return len(materials) - 1
    textures = [(tx, t.tex_data[tx.data_off:tx.data_off + tx.size]) for tx in t.textures]
    mat_for = {}
    combiners = list(t.combiners)
    tint_comb = len(combiners)
    if TUNIC_ANIM:
        combiners += TINT_STAGES  # shared by every tunic material
    tunic_mats = []

    def set_binding(mat_idx, tex_idx, wrap_s, wrap_t):
        raw = bytearray(materials[mat_idx])
        struct.pack_into('<h', raw, 0x10, tex_idx)
        struct.pack_into('<HH', raw, 0x18, wrap_s, wrap_t)
        materials[mat_idx] = bytes(raw)

    bottle_bound = {}

    gauntlet_bound = []

    def material_for(tri):
        if getattr(tri, 'gauntlet', False) and tri.tex is not None:
            if not gauntlet_bound:  # untinted: the game sets mat 14's constant colour 4 per upgrade
                px, w, h = texenc.pad_to_tiles(decode_tri(m, tri), tri.tex.w, tri.tex.h)
                textures.append(cmbwrite.NewTexture('zgauntlet', w, h, texenc.RGBA8, texenc.encode_rgba8(px, w, h)))
                set_binding(MAT_GAUNTLET, len(textures) - 1, WRAP[tri.tex.cms], WRAP[tri.tex.cmt])
                gauntlet_bound.append(True)
            return MAT_GAUNTLET
        kind = getattr(tri, 'bottle', None)
        if kind and tri.tex is not None:
            mat = MAT_BOTTLE_CONTENTS if kind == 'contents' else MAT_BOTTLE_GLASS
            if mat not in bottle_bound:
                px, w, h = decode_tri(m, tri), tri.tex.w, tri.tex.h  # ENV left white: the game colours it
                px, w, h = texenc.pad_to_tiles(px, w, h)
                textures.append(cmbwrite.NewTexture('zbottle_' + kind, w, h, texenc.RGBA8, texenc.encode_rgba8(px, w, h)))
                set_binding(mat, len(textures) - 1, WRAP[tri.tex.cms], WRAP[tri.tex.cmt])
                if tri.texgen:
                    materials[mat] = set_sphere_map(materials[mat])
                bottle_bound[mat] = True
            return mat
        if not STATIC_FACE_AND_TUNIC:
            if tri.tex is not None and tri.tex.seg == 8:
                return MAT_EYE
            if tri.tex is not None and tri.tex.seg == 9:
                return MAT_MOUTH
        combiner = (tri.combine, tri.prim, tri.env if tri.env_set else None, tri.two_cycle, tri.texgen)
        if tri.tex is None:
            key = ('prim',) + combiner
        else:
            x = tri.tex
            key = (id(getattr(tri, 'src', m)), x.seg, x.addr, x.fmt, x.siz, x.w, x.h, x.tlut, x.cms, x.cmt,
                   tri.alpha_from_texture, tri.tunic) + combiner
        if key in mat_for:
            return mat_for[key]
        if tri.tex is None:
            env = (WHITE if TUNIC_ANIM else TUNICS['kokiri']) if tri.tunic else None
            col = np.broadcast_to(zobj.combine_rgb(tri, np.ones((1, 3)), env=env), (1, 3))[0]
            px, w, h, cms, cmt = [tuple(int(round(c * 255)) for c in col) + (255,)] * 64, 8, 8, 0, 0
        else:
            # adult: tunic colour comes from the material's tint constant; child: always Kokiri
            env = (WHITE if TUNIC_ANIM else TUNICS['kokiri']) if tri.tunic else None
            px, w, h, cms, cmt = decode_tri(m, tri, env=env), tri.tex.w, tri.tex.h, tri.tex.cms, tri.tex.cmt
        px, w, h = texenc.pad_to_tiles(px, w, h)
        textures.append(cmbwrite.NewTexture('z%04x' % len(mat_for), w, h, texenc.RGBA8, texenc.encode_rgba8(px, w, h)))
        idx = alloc_material(materials[TEMPLATE_CUTOUT if (tri.tex and tri.alpha_from_texture) else TEMPLATE_OPAQUE])
        set_binding(idx, len(textures) - 1, WRAP[cms], WRAP[cmt])
        if tri.texgen:
            materials[idx] = set_sphere_map(materials[idx])
        if tri.tunic and TUNIC_ANIM:
            materials[idx] = add_tint_stage(materials[idx], tint_comb, TUNICS['kokiri'], combiners)
            tunic_mats.append(idx)
        mat_for[key] = idx
        return idx

    def convert(tris):
        """N64 triangles -> {material: [3 x (pos, nrm, uv, bone)]} in refit world space."""
        out = {}
        for tr in tris:
            mat = material_for(tr)
            vs = []
            for limb, pos, st, col in tr.v:
                M = lw[limb]
                p = M[:3, :3] @ np.array(pos, float) + M[:3, 3]
                n = np.array([0, 1.0, 0])
                if tr.lit:
                    n = M[:3, :3] @ np.array([c - 256 if c > 127 else c for c in col[:3]], float)
                    ln = np.linalg.norm(n)
                    n = n / ln if ln else np.array([0, 1.0, 0])
                if tr.tex is None:
                    uv = (0.5, 0.5)
                else:
                    u, v = st[0] / 32 / tr.tex.w, st[1] / 32 / tr.tex.h
                    uv = (u, 1 - v)
                vs.append((tuple(p), tuple(n), uv, pose.LIMB_TO_BONE[limb]))
            out.setdefault(mat, []).append(vs)
            if tr.cull == 0:  # double-sided on the N64: add the back face (materials cull back)
                out[mat].append([(p, tuple(-c for c in n), uv, b) for p, n, uv, b in reversed(vs)])
        return out

    new_meshes = []
    for g, tris in group_tris.items():
        for mat, ts in convert(tris).items():
            new_meshes.append(cmbwrite.NewMesh(g, mat, ts, translucent=mat in (MAT_BOTTLE_GLASS, MAT_BOTTLE_CONTENTS)))

    def keep_link(mat, gid):
        """Link's own mesh stays: groups we don't touch, and the parts of items not ported."""
        if gid in GROUPS:
            return False
        for key, comps, mats in ITEMS.get(gid, ()):
            if mat in mats:
                if back_kind(key, comps) in hide_back:
                    return False
                return key is not None and key not in ported
        return gid not in ITEMS

    keep = [i for i, (s, mat, gid) in enumerate(t.meshes) if keep_link(mat, gid)]

    # ---- animated textures, in Link's own slots / sizes / formats
    def slot_texture(slot, px, w, h):
        old = t.textures[slot]
        px = resize(px, w, h, old.w, old.h)
        return pica.encode(old.gl_format, px, old.w, old.h)

    eye_tri = next(tr for tr in m.tris if tr.tex and tr.tex.seg == 8)
    mouth_tri = next(tr for tr in m.tris if tr.tex and tr.tex.seg == 9)

    def face_set(tri, base, count, slot):
        size = tri.tex.w * tri.tex.h * {0: 0.5, 1: 1, 2: 2, 3: 4}[tri.tex.siz]
        return [slot_texture(slot, decode_tri(m, tri, base=base + int(k * size)), tri.tex.w, tri.tex.h)
                for k in range(count)]

    if STATIC_FACE_AND_TUNIC:
        out_cmb = cmbwrite.write(t, [tuple(x) for x in trans], keep, materials, textures, new_meshes)
        return finish(out_cmb, {}, files, bones, trans, zar_bytes, keep, new_meshes, materials, textures)

    eyes = face_set(eye_tri, 0x0, 8, TEX_EYE)
    mouths = face_set(mouth_tri, 0x4000, 4, TEX_MOUTH)

    def replace_slot(slot, data):
        old, _ = textures[slot]
        assert len(data) == old.size
        textures[slot] = (old, data)

    replace_slot(TEX_EYE, eyes[0])
    replace_slot(TEX_MOUTH, mouths[0])
    set_binding(MAT_EYE, TEX_EYE, WRAP[eye_tri.tex.cms], WRAP[eye_tri.tex.cmt])
    set_binding(MAT_MOUTH, TEX_MOUTH, WRAP[mouth_tri.tex.cms], WRAP[mouth_tri.tex.cmt])

    pins = {t.meshes[i][0] for i in keep if t.meshes[i][2] in PINNED_GROUPS}
    out_cmb = cmbwrite.write(t, [tuple(x) for x in trans], keep, materials, textures, new_meshes,
                             combiners=combiners, pin_sepds=pins)

    def remake_cmab(name, mat, frames, slot, names):
        old = t.textures[slot]
        texs = [(n, old.w, old.h, old.gl_format, d) for n, d in zip(names, frames)]
        return cmabwrite.write([(mat, list(range(len(frames))))], texs, len(frames))

    eye_cmab = remake_cmab('eye', MAT_EYE, eyes, TEX_EYE, EYE_NAMES)
    mouth_cmab = remake_cmab('mouth', MAT_MOUTH, mouths, TEX_MOUTH, MOUTH_NAMES)
    cmabs = {EYE_CMAB: eye_cmab, MOUTH_CMAB: mouth_cmab}
    for name, new in cmabs.items():
        assert len(new) == len(files[name]), name + ' layout differs from the original'
    if TUNIC_ANIM:
        # link_body.cmab: Link's own tunic texture swap is kept (material 1, now unused), plus one
        # ConstColor track per tunic material; the game plays frame 0/1/2 for Kokiri/Goron/Zora.
        tint = [[c[k] / 255 for k in range(3)] for c in TUNICS.values()]
        cmabs[BODY_CMAB] = cmabwrite.write([(MAT_TUNIC, [0, 1, 2])], cmab_textures(files[BODY_CMAB]), 3,
                                           const_colors=[(i, TINT_CONST, tint) for i in tunic_mats])
    return finish(out_cmb, cmabs, files, bones, trans, zar_bytes, keep, new_meshes, materials, textures)


def finish(out_cmb, cmabs, files, bones, trans, zar_bytes, keep, new_meshes, materials, textures):

    # ---- animations: constant translation tracks would undo the skeleton refit
    old = [np.array(b['trans']) for b in bones]
    delta = {i: np.array(trans[i]) - old[i] for i in range(len(bones)) if np.linalg.norm(np.array(trans[i]) - old[i]) > 0.01}
    patched = {}
    for name, data in files.items():
        if name.endswith('.csab'):
            nd = csab.patch_translations(data, old, trans, delta)
            if nd != data:
                patched[name] = nd

    repl = {CMB_NAME: out_cmb}
    repl.update(cmabs)
    repl.update(patched)
    new_zar = zar.replace_files(zar_bytes, dict(repl))

    log(f'meshes: kept {len(keep)} Link + {len(new_meshes)} new, materials {len(materials)}, textures {len(textures)}, '
        f'csab patched {len(patched)}, cmab replaced {len(cmabs)}')
    log(f'cmb {len(out_cmb)} bytes, zar {len(new_zar)} bytes (Link {len(zar_bytes)})')
    return {'name': ZAR_NAME, 'zar': new_zar, 'cmb': out_cmb}


def main(zpath, zarpath, outdir):
    out = convert(zpath, zarpath)
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, os.path.basename(CMB_NAME)), 'wb').write(out['cmb'])
    open(os.path.join(outdir, out['name']), 'wb').write(out['zar'])


if __name__ == '__main__':
    main(*sys.argv[1:4])
