"""Textured bind-pose render of a CMB, decoding its 3DS textures (checks UVs / texture slots)."""
import sys, os, struct
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
import cmb, cmbskel, pica


def render(c, path, groups=None, size=600, tex_override=None, flip=True, tint=None):
    """tint: RGB 0-255 for materials with the tunic tint stage (default: their constant colour 0)."""
    _, world = cmbskel.read_skeleton(c.raw)
    inv = [np.linalg.inv(w) for w in world]
    cache = {}

    def tex_for(mat):
        ti = struct.unpack_from('<h', c.materials[mat], 0x10)[0]
        if tex_override and mat in tex_override:
            return tex_override[mat]
        m = c.materials[mat]
        n = struct.unpack_from('<I', m, 0x120)[0]
        tinted = n > 1 and struct.unpack_from('<H', m, 0x124)[0] == len(c.combiners) - 2             and c.combiners[-2][12:14] == bytes.fromhex('c084')  # build.TINT_STAGES[0]: texture * constant
        if ti not in cache:
            t = c.textures[ti]
            px = pica.decode(t.gl_format, t.w, t.h, c.tex_data[t.data_off:t.data_off + t.size])
            cache[ti] = np.array(px, np.float32).reshape(t.h, t.w, 4) / 255
        if not tinted:
            return cache[ti]
        col = np.array(list(tint or m[0xB4:0xB7]) + [255], np.float32) / 255
        return cache[ti] * col

    tris = []
    for s, mat, gid in c.meshes:
        if groups is not None and gid not in groups:
            continue
        for p, vs in cmb.triangles(c, c.sepds[s]):
            pts = []
            for v in vs:
                x = np.array([*v['pos'], 1.0])
                if p.skinning == 2:
                    pts.append(sum(w * (world[b] @ inv[b] @ x) for b, w in zip(v['bones'], v['weights']))[:3])
                else:
                    pts.append((world[v['bones'][0]] @ x)[:3])
            tris.append((np.array(pts), [v['uv'] for v in vs], mat))
    S = size
    allp = np.concatenate([t[0] for t in tris])
    lo, hi = allp.min(0), allp.max(0)
    scale = S * 0.9 / (hi[1] - lo[1])
    panels = []
    for ax, az, sign in ((0, 2, 1), (2, 0, -1), (0, 2, -1)):
        img = np.zeros((S, S, 3)) + 0.16
        zb = np.full((S, S), -np.inf)
        cx = (lo[ax] + hi[ax]) / 2
        for p, uv, mat in tris:
            sx = S / 2 + sign * (p[:, ax] - cx) * scale
            sy = S * 0.95 - (p[:, 1] - lo[1]) * scale
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
            tx = tex_for(mat)
            th, tw = tx.shape[:2]
            u = w0 * uv[0][0] + w1 * uv[1][0] + w2 * uv[2][0]
            v = w0 * uv[0][1] + w1 * uv[1][1] + w2 * uv[2][1]
            iu = np.mod(np.floor(u * tw).astype(int), tw)
            iv = np.mod(np.floor(((1 - v) if flip else v) * th).astype(int), th)  # data row 0 = v 1 (matches Link on hardware)
            col = tx[iv, iu][..., :3]
            mask = inside & (z > zb[y0:y1, x0:x1])
            zb[y0:y1, x0:x1][mask] = z[mask]
            img[y0:y1, x0:x1][mask] = col[mask]
        panels.append(img)
    Image.fromarray((np.concatenate(panels, 1) * 255).astype(np.uint8)).save(path)


if __name__ == '__main__':
    c = cmb.read(open(sys.argv[1], 'rb').read())
    groups = set(int(x) for x in sys.argv[3].split(',')) if len(sys.argv) > 3 else None
    render(c, sys.argv[2], groups)
