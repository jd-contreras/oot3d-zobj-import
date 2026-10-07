"""One-time generator for tools/anim_tables.py (run by a developer, not by the converter).

    python tools/gen_anim_tables.py <OoT N64 ROM> <romfs>/actor/zelda_link_boy_new.zar <romfs>/actor/zelda_link_child_new.zar <link_animetion.xml>

Derives, from the vanilla N64 animations (link_animetion, read from the ROM) and OoT3D's own
animations, only small tables (no game data is shipped):
  ANIMS        N64 animation name, frame count, offset (zeldaret/oot link_animetion.xml)
  VANILLA      per-animation fingerprint of the vanilla frames (to find the ones a pack changed)
  CALIB[age]   per OoT3D bone: the N64 limb driving it and the constant rotation C with
               world_3d(bone) = world_n64(limb) @ C, fitted robustly over animations both games share
  ROOT[age]    root translation map: 3D bone 1 translation = N64 root translation * scale + offset
               (height: ratio on standing frames)
"""
import sys, os, re, struct, hashlib
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import zar, csab, cmb, cmbskel, animview, n64anim

# OoT3D bones driven by an N64 limb (others keep OoT3D's own local motion: 0 model root,
# 13 / 17 clavicles, 22-24 bow string). Bone 10 (chest) is tried against N64 limbs below.
CANDIDATES = {1: [0], 2: [1], 3: [6], 4: [7], 5: [8], 6: [3], 7: [4], 8: [5], 9: [9], 10: [20, 9],
              11: [10], 12: [11], 14: [13], 15: [14], 16: [15], 18: [16], 19: [17], 20: [18], 21: [19]}
N64_PARENTS = [-1, 0, 1, 2, 3, 4, 2, 6, 7, 0, 9, 10, 9, 9, 13, 14, 9, 16, 17, 9, 9]


def find_link_animetion(rom):
    if rom[:4] == b'\x37\x80\x40\x12':  # .v64 byte-swapped
        rom = b''.join(rom[i + 1:i + 2] + rom[i:i + 1] for i in range(0, len(rom), 2))
    i = rom.find(struct.pack('>IIII', 0, 0x1060, 0, 0))
    o = i
    while True:
        vs, ve, ps, pe = struct.unpack_from('>IIII', rom, o)
        if o > i and vs == 0 and ve == 0:
            break
        if ve - vs == 0x265C30 and pe == 0:
            return rom[ps:ps + 0x265C30]
        o += 16
    raise ValueError('link_animetion not found (compressed ROM?)')


def angle(a, b):
    return np.degrees(np.arccos(np.clip((np.trace(a.T @ b) - 1) / 2, -1, 1)))


def proj(m):
    u, _, vt = np.linalg.svd(m)
    return u @ np.diag([1, 1, np.sign(np.linalg.det(u @ vt))]) @ vt


def robust_fit(data, l, b):
    c = proj(sum(w[l].T @ v[b] for w, v, _, _ in data))
    for _ in range(6):  # refit on the best two thirds: Grezzo reworked many animations
        e = np.array([angle(w[l] @ c, v[b]) for w, v, _, _ in data])
        keep = e <= np.percentile(e, 66)
        c = proj(sum(w[l].T @ v[b] for (w, v, _, _), k in zip(data, keep) if k))
    e = np.array([angle(w[l] @ c, v[b]) for w, v, _, _ in data])
    return c, float(np.median(e))


def main(rom_path, adult_zar, child_zar, xml_path):
    van = find_link_animetion(open(rom_path, 'rb').read())
    xml = open(xml_path).read()
    anims = [(m.group(1), int(m.group(2)), int(m.group(3), 16)) for m in re.finditer(
        r'Name="gPlayerAnim_(.+?)_Data" FrameCount="(\d+)" Offset="(0x[0-9A-F]+)"', xml)]
    vanilla = {n: hashlib.sha1(van[o:o + n64anim.FRAME_SIZE * fc]).hexdigest()[:16] for n, fc, o in anims}
    calib, root = {}, {}
    for age, zpath, cmb_name in (('adult', adult_zar, 'boy/model/link_v2.cmb'),
                                 ('child', child_zar, 'child/model/childlink_v2.cmb')):
        files = dict(zar.read_zar(zpath)[1])
        bones, _ = cmbskel.read_skeleton(cmb.read(files[cmb_name]).raw)
        paths = n64anim.csab_paths(files)
        data = []
        for name, fc, off in anims:
            p = n64anim.oot3d_path(name, paths)
            if not p:
                continue
            dur, nodes = csab.read(files[p])
            if dur != fc:
                continue
            tr, rots, _ = n64anim.frames(van, off, fc)
            for f in range(0, fc, max(1, fc // 5)):
                w = n64anim.limb_world(rots[f], N64_PARENTS)
                v = [m[:3, :3] for m in animview.posed_world(bones, nodes, f)]
                t3 = [animview.sample(nodes[1][a], f, False) if 1 in nodes and a in nodes[1] else bones[1]['trans'][k]
                      for k, a in enumerate(('tx', 'ty', 'tz'))]
                data.append((w, v, tr[f], np.array(t3)))
        print(age, 'samples', len(data))
        cal = {}
        for b, limbs in CANDIDATES.items():
            best = min(((robust_fit(data, l, b), l) for l in limbs), key=lambda r: r[0][1])
            (c, err), l = best
            print(f'  bone {b:2} <- limb {l:2}: correction {angle(c, np.eye(3)):5.1f} deg, median residual {err:5.1f}')
            cal[b] = (l, [round(float(x), 6) for x in c.flatten()])
        calib[age] = cal
        # root translation: robust per-axis linear fit
        n64t = np.array([d[2] for d in data])
        t3 = np.array([d[3] for d in data])
        fit = []
        for k in range(3):
            a, b0 = np.polyfit(n64t[:, k], t3[:, k], 1)
            for _ in range(5):
                r = np.abs(t3[:, k] - (a * n64t[:, k] + b0))
                keep = r <= np.percentile(r, 66)
                a, b0 = np.polyfit(n64t[keep, k], t3[keep, k], 1)
            fit.append((round(float(a), 6), round(float(b0), 3)))
        # height: plain ratio on standing frames (the fit above is pulled by crouches and rolls)
        stand = n64t[:, 1] > 3000
        fit[1] = (round(float(np.median(t3[stand, 1] / n64t[stand, 1])), 6), 0.0)
        print('  root translation (scale, offset) per axis:', fit)
        root[age] = fit
    out = os.path.join(os.path.dirname(__file__), 'anim_tables.py')
    with open(out, 'w') as f:
        f.write('"""Generated by gen_anim_tables.py: derived tables only (no game data)."""\n\n')
        f.write('ANIMS = %r\n\n' % anims)
        f.write('VANILLA = %r\n\n' % vanilla)
        f.write('CALIB = %r\n\n' % calib)
        f.write('ROOT = %r\n' % root)
    print('wrote', out)


if __name__ == '__main__':
    main(*sys.argv[1:5])
