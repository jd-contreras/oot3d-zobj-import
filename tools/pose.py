"""Fit a zobj onto the OoT3D Link skeleton and write OBJ + preview PNG.

Each N64 limb takes the orientation of an OoT3D bone (the two games share local axes), but
joint positions come from the N64 skeleton, so seams between limbs line up exactly. The OoT3D
skeleton is then re-fitted to those joint positions (rotations kept, translations replaced).
"""
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import zobj, cmbskel

# N64 player limb -> OoT3D adult Link bone that skins it
LIMB_TO_BONE = {
    0: 0, 1: 2, 2: 2,        # N64 waist frame points down its +X like OoT3D bone 2
    3: 6, 4: 7, 5: 8,        # right leg (OoT3D bones 6-8 are on Link's right, -X)
    6: 3, 7: 4, 8: 5,        # left leg
    9: 9, 20: 9,             # upper body control, torso (N64 torso pivots at the upper-body origin)
    10: 11, 11: 12,          # head, hat
    12: 9,                   # collar
    13: 14, 14: 15, 15: 16,  # left arm (3D bone 13 is a clavicle with no N64 limb)
    16: 18, 17: 19, 18: 20,  # right arm
    19: 21,                  # sheath
}
# OoT3D bone -> N64 limb whose joint position it moves to
BONE_JOINT = {6: 3, 7: 4, 8: 5, 3: 6, 4: 7, 5: 8, 9: 9, 11: 10, 12: 11,
              14: 13, 15: 14, 16: 15, 18: 16, 19: 17, 20: 18, 21: 19}
ROOT_BONE = 1  # N64 root limb sits where OoT3D bone 1 is in bind pose
# Extra rotation (degrees about the bone's local Z, which is Link's left-right axis) for limbs whose
# OoT3D bone is animated for a different shape. OoT3D swings bone 12 for Link's cap, which holds a
# ponytail / hat too far back; negative tilts it down.
LIMB_TILT = {11: -30.0}


def fit(model, bones, world):
    """Return (limb world matrices, new bone translations, new bone world matrices)."""
    lw = []
    for i, l in enumerate(model.limbs):
        m = np.eye(4)
        m[:3, :3] = world[LIMB_TO_BONE[i]][:3, :3]
        if i in LIMB_TILT:
            a = np.radians(LIMB_TILT[i])
            rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
            m[:3, :3] = m[:3, :3] @ rz
        if l.parent < 0:
            m[:3, 3] = world[ROOT_BONE][:3, 3]
        else:
            pw = lw[l.parent]
            m[:3, 3] = pw[:3, 3] + pw[:3, :3] @ np.array(l.pos, float)
        lw.append(m)
    trans, new_world = [], []
    for i, b in enumerate(bones):
        t = np.array(b['trans'], float)
        if i in BONE_JOINT and b['parent'] >= 0:
            pw = new_world[b['parent']]
            t = pw[:3, :3].T @ (lw[BONE_JOINT[i]][:3, 3] - pw[:3, 3])
        local = np.eye(4)
        local[:3, :3] = cmbskel.rot(*b['rot']) * np.array(b['scale'])
        local[:3, 3] = t
        trans.append(t)
        new_world.append(new_world[b['parent']] @ local if b['parent'] >= 0 else local)
    return lw, trans, new_world


def place(model, lw):
    """Return list of (world_xyz[3], world_normal[3] or None, tri)."""
    out = []
    for t in model.tris:
        pts, nrm = [], []
        for limb, pos, uv, col in t.v:
            m = lw[limb]
            pts.append(m[:3, :3] @ np.array(pos, float) + m[:3, 3])
            n = m[:3, :3] @ np.array([c - 256 if c > 127 else c for c in col[:3]], float)
            ln = np.linalg.norm(n)
            nrm.append(n / ln if ln else None)
        out.append((pts, nrm if t.lit and all(n is not None for n in nrm) else None, t))
    return out


def write_obj(placed, path):
    with open(path, 'w') as f:
        k = 1
        for pts, _, _ in placed:
            for p in pts:
                f.write('v %.3f %.3f %.3f\n' % tuple(p))
            f.write('f %d %d %d\n' % (k, k + 1, k + 2))
            k += 3


if __name__ == '__main__':
    import render
    zpath, cmbpath, out = sys.argv[1:4]
    model = zobj.read(zpath)
    bones, world = cmbskel.read_skeleton(open(cmbpath, 'rb').read())
    lw, trans, new_world = fit(model, bones, world)
    for i, (b, t) in enumerate(zip(bones, trans)):
        d = np.linalg.norm(t - np.array(b['trans']))
        if d > 1:
            print(f'bone {i:2d} moved {d:6.1f}  {np.round(b["trans"], 1)} -> {np.round(t, 1)}')
    placed = place(model, lw)
    write_obj(placed, out + '.obj')
    render.render(placed, model, out + '.png')
