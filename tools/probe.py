"""Diagnostic: re-encode some of Link's own meshes through cmbwrite's new-mesh path."""
import sys, os, struct
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import cmb, cmbskel, cmbwrite, zar

PROBE_MESHES = [112, 114]  # Link's face (link_f00) and hair/hat (link_01g)


def main(zarpath, outdir):
    zb = open(zarpath, 'rb').read()
    files = dict(zar.read_zar(zarpath)[1])
    t = cmb.read(files['boy/model/link_v2.cmb'])
    bones, world = cmbskel.read_skeleton(t.raw)
    inv = [np.linalg.inv(w) for w in world]
    new = []
    for mi in PROBE_MESHES:
        s, mat, gid = t.meshes[mi]
        tris = []
        for p, vs in cmb.triangles(t, t.sepds[s]):
            tri = []
            for v in vs:
                b = v['bones'][int(np.argmax(v['weights']))]  # rigid: heaviest bone
                pos = np.array(v['pos'])
                if p.skinning != 2:
                    pos = (world[b] @ np.array([*pos, 1]))[:3]
                n = np.array(v['nrm'])
                ln = np.linalg.norm(n)
                tri.append((tuple(pos), tuple(n / ln if ln else n), tuple(v['uv']), b))
            tris.append(tri)
        new.append(cmbwrite.NewMesh(gid, mat, tris))
    n = struct.unpack_from('<I', t.bones_raw, 8)[0]
    trans = [struct.unpack_from('<3f', t.bones_raw, 16 + 40 * i + 0x1C) for i in range(n)]
    keep = [i for i in range(len(t.meshes)) if i not in PROBE_MESHES]
    texs = [(x, t.tex_data[x.data_off:x.data_off + x.size]) for x in t.textures]
    out = cmbwrite.write(t, trans, keep, list(t.materials), texs, new)
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, 'link_v2.cmb'), 'wb').write(out)
    open(os.path.join(outdir, 'zelda_link_boy_new.zar'), 'wb').write(zar.replace_files(zb, {'boy/model/link_v2.cmb': out}))
    print('probe written', len(out))


if __name__ == '__main__':
    main(*sys.argv[1:3])
