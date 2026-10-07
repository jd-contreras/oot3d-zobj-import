"""Render a CMB in bind pose (flat grey, per-mesh-group colours optional) to check reader/writer output."""
import sys, os
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
import cmb, cmbskel


def world_tris(c, groups=None):
    _, world = cmbskel.read_skeleton(c.raw)
    inv = [np.linalg.inv(w) for w in world]
    out = []
    for mi, (s, m, gid) in enumerate(c.meshes):
        if groups is not None and gid not in groups:
            continue
        sepd = c.sepds[s]
        for p, vs in cmb.triangles(c, sepd):
            pts = []
            for v in vs:
                x = np.array([*v['pos'], 1.0])
                if p.skinning == 2:
                    acc = np.zeros(4)
                    for b, w in zip(v['bones'], v['weights']):
                        acc += w * (world[b] @ inv[b] @ x)
                    pts.append(acc[:3])
                else:
                    pts.append((world[v['bones'][0]] @ x)[:3])
            out.append((pts, gid))
    return out


def render(tris, path, size=600):
    S = size
    views = [(0, 1, 2, 1), (2, 1, 0, -1)]
    allp = np.array([p for pts, _ in tris for p in pts])
    lo, hi = allp.min(0), allp.max(0)
    scale = S * 0.9 / max(hi[1] - lo[1], 1e-3)
    light = np.array([0.4, 0.6, 0.7]); light /= np.linalg.norm(light)
    panels = []
    for ax, ay, az, sign in views:
        img = np.zeros((S, S, 3)) + 0.16
        zb = np.full((S, S), -np.inf)
        cx = (lo[ax] + hi[ax]) / 2
        for pts, gid in tris:
            p = np.array(pts)
            sx = S / 2 + sign * (p[:, ax] - cx) * scale
            sy = S * 0.95 - (p[:, ay] - lo[1]) * scale
            sz = sign * p[:, az]
            x0, x1 = int(max(sx.min(), 0)), int(min(sx.max() + 1, S))
            y0, y1 = int(max(sy.min(), 0)), int(min(sy.max() + 1, S))
            if x1 <= x0 or y1 <= y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            d = (sy[1] - sy[2]) * (sx[0] - sx[2]) + (sx[2] - sx[1]) * (sy[0] - sy[2])
            if abs(d) < 1e-9:
                continue
            w0 = ((sy[1] - sy[2]) * (gx - sx[2]) + (sx[2] - sx[1]) * (gy - sy[2])) / d
            w1 = ((sy[2] - sy[0]) * (gx - sx[2]) + (sx[0] - sx[2]) * (gy - sy[2])) / d
            w2 = 1 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            z = w0 * sz[0] + w1 * sz[1] + w2 * sz[2]
            n = np.cross(p[1] - p[0], p[2] - p[0]); ln = np.linalg.norm(n)
            sh = 0.35 + 0.65 * abs(np.dot(n / ln, light)) if ln else 0.6
            col = np.array([((gid * 67) % 255), ((gid * 131) % 255), ((gid * 199) % 255)]) / 255 * 0.6 + 0.4
            mask = inside & (z > zb[y0:y1, x0:x1])
            zb[y0:y1, x0:x1][mask] = z[mask]
            img[y0:y1, x0:x1][mask] = col * sh
        panels.append(img)
    Image.fromarray((np.concatenate(panels, 1) * 255).astype(np.uint8)).save(path)


if __name__ == '__main__':
    c = cmb.read(open(sys.argv[1], 'rb').read())
    groups = set(int(x) for x in sys.argv[3].split(',')) if len(sys.argv) > 3 else None
    render(world_tris(c, groups), sys.argv[2])
