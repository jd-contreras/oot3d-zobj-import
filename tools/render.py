"""Textured z-buffer preview of placed triangles (orthographic front/side/back)."""
import numpy as np
from PIL import Image

import zobj

EYES = {8: 0x0, 9: 0x4000}  # ML64 layout: default eye / mouth textures at the start of the file


def _texture(model, tex, cache):
    key = (tex.seg, tex.addr, tex.fmt, tex.siz, tex.w, tex.h, tex.tlut)
    if key not in cache:
        px = zobj.decode_texture(model, tex, eyes=EYES)
        cache[key] = np.array(px, dtype=np.float32).reshape(tex.h, tex.w, 4) / 255
    return cache[key]


def _wrap(c, n, mode):
    if mode & 1:  # mirror
        p = np.mod(c, 2 * n)
        c = np.where(p >= n, 2 * n - 1 - p, p)
    if mode & 2:  # clamp
        return np.clip(c, 0, n - 1)
    return np.mod(c, n)


def _bilinear(tx, u, v, tex):
    """Bilinear filtering like the N64/3DS texture units (texel centres at +0.5)."""
    u, v = u - 0.5, v - 0.5
    u0, v0 = np.floor(u), np.floor(v)
    fu, fv = (u - u0)[..., None], (v - v0)[..., None]
    u0, v0 = u0.astype(int), v0.astype(int)
    a = lambda du, dv: tx[_wrap(v0 + dv, tex.h, tex.cmt), _wrap(u0 + du, tex.w, tex.cms)]
    return (a(0, 0) * (1 - fu) * (1 - fv) + a(1, 0) * fu * (1 - fv)
            + a(0, 1) * (1 - fu) * fv + a(1, 1) * fu * fv)


def render(placed, model, path, size=700, ss=2, tunic=None):
    S = size * ss
    views = [(0, 1, 2, 1), (2, 1, 0, -1), (0, 1, 2, -1)]  # front, side, back
    allp = np.array([p for pts, _, _ in placed for p in pts])
    lo, hi = allp.min(0), allp.max(0)
    scale = S * 0.9 / (hi[1] - lo[1])
    light = np.array([0.4, 0.6, 0.7]); light /= np.linalg.norm(light)
    cache, panels = {}, []
    for ax, ay, az, sign in views:
        img = np.zeros((S, S, 3), np.float32) + np.array([0.16, 0.16, 0.19])
        zb = np.full((S, S), -np.inf)
        cx = (lo[ax] + hi[ax]) / 2
        for pts, nrm, t in placed:
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
            if not inside.any():
                continue
            z = w0 * sz[0] + w1 * sz[1] + w2 * sz[2]
            cols = np.array([v[3] for v in t.v], np.float32) / 255
            if t.tex is not None:
                tx = _texture(model, t.tex, cache)
                uv = np.array([v[2] for v in t.v], np.float32) / 32.0
                u = w0 * uv[0, 0] + w1 * uv[1, 0] + w2 * uv[2, 0]
                v = w0 * uv[0, 1] + w1 * uv[1, 1] + w2 * uv[2, 1]
                texel = _bilinear(tx, u, v, t.tex)
                rgb, a = texel[..., :3], texel[..., 3]
                if not t.alpha_from_texture:
                    a = np.ones(gx.shape)
                if not t.lit:
                    vc = w0[..., None] * cols[0, :3] + w1[..., None] * cols[1, :3] + w2[..., None] * cols[2, :3]
                    rgb = rgb * vc
            else:
                base = np.array(t.prim[:3], np.float32) / 255
                rgb = np.broadcast_to(base, gx.shape + (3,)).copy()
                a = np.ones(gx.shape)
            if tunic is not None and t.tunic:
                rgb = rgb * (np.array(tunic, np.float32) / 255)
            if nrm is not None:  # smooth: interpolate vertex normals
                nv = np.array(nrm)
                n = w0[..., None] * nv[0] + w1[..., None] * nv[1] + w2[..., None] * nv[2]
                n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
                shade = (0.45 + 0.55 * np.clip(n @ light, 0, 1))[..., None]
            else:
                n = np.cross(p[1] - p[0], p[2] - p[0])
                ln = np.linalg.norm(n)
                shade = 0.55 + 0.45 * abs(np.dot(n / ln, light)) if ln else 0.8
            mask = inside & (a > 0.5) & (z > zb[y0:y1, x0:x1])
            zb[y0:y1, x0:x1][mask] = z[mask]
            img[y0:y1, x0:x1][mask] = np.clip((rgb * shade)[mask], 0, 1)
        panels.append(img)
    out = np.concatenate(panels, axis=1)
    im = Image.fromarray((out * 255).astype(np.uint8))
    im = im.resize((im.width // ss, im.height // ss), Image.LANCZOS)
    if path:
        im.save(path)
    return im
