"""Pose a CMB with a CSAB frame and render it (checks seams under animation)."""
import sys, os, math
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(__file__))
import cmb, cmbskel, csab, cmbview

ROT16 = math.pi / 0x8000


def sample(track, frame, is_rot):
    typ, keys = track
    if len(keys) == 1 or frame <= keys[0][0]:
        v = keys[0][1]
    elif frame >= keys[-1][0]:
        v = keys[-1][1]
    else:
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if t0 <= frame <= t1:
                a = (frame - t0) / (t1 - t0)
                if is_rot and isinstance(v0, int):
                    d = (v1 - v0 + 0x8000) % 0x10000 - 0x8000
                    v = v0 + d * a
                else:
                    v = v0 + (v1 - v0) * a
                break
    if is_rot and isinstance(keys[0][1], int):
        return v * ROT16
    return v


def posed_world(bones, nodes, frame):
    world = []
    for i, b in enumerate(bones):
        s, r, t = list(b['scale']), list(b['rot']), list(b['trans'])
        for k, ax in enumerate('xyz'):
            n = nodes.get(i, {})
            if 's' + ax in n: s[k] = sample(n['s' + ax], frame, False)
            if 'r' + ax in n: r[k] = sample(n['r' + ax], frame, True)
            if 't' + ax in n: t[k] = sample(n['t' + ax], frame, False)
        m = np.eye(4)
        m[:3, :3] = cmbskel.rot(*r) * np.array(s)
        m[:3, 3] = t
        world.append(world[b['parent']] @ m if b['parent'] >= 0 else m)
    return world


def posed_tris(c, anim_world, groups=None):
    bones, bind = cmbskel.read_skeleton(c.raw)
    inv = [np.linalg.inv(w) for w in bind]
    out = []
    for s, mat, gid in c.meshes:
        if groups is not None and gid not in groups:
            continue
        for p, vs in cmb.triangles(c, c.sepds[s]):
            pts = []
            for v in vs:
                x = np.array([*v['pos'], 1.0])
                if p.skinning == 2:
                    acc = sum(w * (anim_world[b] @ inv[b] @ x) for b, w in zip(v['bones'], v['weights']))
                    pts.append(acc[:3])
                else:
                    pts.append((anim_world[v['bones'][0]] @ x)[:3])
            out.append((pts, gid))
    return out


if __name__ == '__main__':
    cmb_path, anim_dir, out = sys.argv[1:4]
    groups = set(int(x) for x in sys.argv[4].split(',')) if len(sys.argv) > 4 else None
    shots = [('ft_run', 4), ('ft_Lpow_jump_kiru', 10), ('dm_get_itemA', 30), ('ft_defense_wait', 0)]
    c = cmb.read(open(cmb_path, 'rb').read())
    bones, _ = cmbskel.read_skeleton(c.raw)
    tiles = []
    for name, frame in shots:
        dur, nodes = csab.read(open(os.path.join(anim_dir, name + '.csab'), 'rb').read())
        w = posed_world(bones, nodes, min(frame, dur - 1))
        cmbview.render(posed_tris(c, w, groups), '_pose.png', size=420)
        im = Image.open('_pose.png')
        ImageDraw.Draw(im).text((6, 6), f'{name} f{frame}', fill=(255, 255, 0))
        tiles.append(im)
    os.remove('_pose.png')
    sheet = Image.new('RGB', (tiles[0].width * 2, tiles[0].height * 2))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % 2) * im.width, (i // 2) * im.height))
    sheet.save(out)
