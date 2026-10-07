"""N64 OoT player animations (link_animetion) and their OoT3D counterparts.

link_animetion: per animation `frames` x 134 bytes: root translation (3 x s16), 21 limb rotations
(3 x s16 binary angles, applied Z then Y then X like OoT3D's bones), then a face index (u16).
Animation names / offsets / frame counts: zeldaret/oot assets/xml/misc/link_animetion.xml
(ANIMS below). OoT3D names drop the 'link_' prefixes Grezzo abbreviated (NAME_PREFIXES).
"""
import struct
import numpy as np

FRAME_SIZE = 134
ROT = np.pi / 0x8000

NAME_PREFIXES = [
    ('link_normal_', 'nml_'), ('link_fighter_', 'ft_'), ('link_bow_', 'bow_'), ('link_hook_', 'hook_'),
    ('link_demo_', 'dm_'), ('link_uma_', 'uma_'), ('link_swimer_', 'sw_'), ('link_anchor_', 'ac_'),
    ('link_hammer_', 'hm_'), ('link_boom_', 'boom_'), ('link_bottle_', 'bt_'), ('link_silver_', 'silver_'),
    ('link_last_', 'last_'), ('link_magic_', 'mg_'), ('link_okarina_', 'okarina_'), ('link_keep_', 'keep_'),
    ('clink_demo_', 'cl_dm_'), ('clink_normal_', 'cl_nml_'), ('clink_op3_', 'cl_op3_'), ('Link_', ''),
    ('link_', ''),
]


def oot3d_name(n64_name, available):
    """OoT3D csab base name for an N64 animation name, or None."""
    if n64_name in available:
        return n64_name
    for a, b in NAME_PREFIXES:
        if n64_name.startswith(a) and b + n64_name[len(a):] in available:
            return b + n64_name[len(a):]
    return None


def frames(data, offset, count):
    """(root translations (count, 3), limb rotations in radians (count, 21, 3), face (count,))."""
    a = np.array(struct.unpack_from('>%dh' % (67 * count), data, offset), float).reshape(count, 67)
    return a[:, :3], a[:, 3:66].reshape(count, 21, 3) * ROT, a[:, 66].astype(int)


def rot(x, y, z):
    """Rz @ Ry @ Rx (the order both games use)."""
    cx, sx, cy, sy, cz, sz = np.cos(x), np.sin(x), np.cos(y), np.sin(y), np.cos(z), np.sin(z)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


def euler(m):
    """Inverse of rot(): (x, y, z) radians for R = Rz Ry Rx."""
    sy = -m[2, 0]
    y = np.arcsin(np.clip(sy, -1, 1))
    if abs(sy) < 0.99999:
        x = np.arctan2(m[2, 1], m[2, 2])
        z = np.arctan2(m[1, 0], m[0, 0])
    else:  # gimbal lock
        x = np.arctan2(-m[1, 2], m[1, 1])
        z = 0.0
    return x, y, z


def limb_world(rots, parents):
    """World rotation matrices of the N64 limbs for one frame (rotation only)."""
    out = []
    for i, p in enumerate(parents):
        r = rot(*rots[i])
        out.append(out[p] @ r if p >= 0 else r)
    return out


def csab_paths(files):
    """{csab base name: [paths]} of a zar's animations (boy/anim and child/anim variants)."""
    out = {}
    for k in files:
        if k.endswith('.csab'):
            out.setdefault(k.split('/')[-1][:-5], []).append(k)
    return out


def oot3d_paths(n64_name, paths):
    """Every csab path in the zar for an N64 animation (child/anim variants included)."""
    base = oot3d_name(n64_name, paths)
    return sorted(paths[base]) if base else []


def oot3d_path(n64_name, paths):
    """The shared (boy/anim) csab for an N64 animation, else any variant, or None."""
    ps = oot3d_paths(n64_name, paths)
    return next((p for p in ps if p.startswith('boy/')), ps[0] if ps else None)
