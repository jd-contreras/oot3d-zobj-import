"""Read the skeleton chunk of an OoT3D CMB and compute bind-pose world matrices."""
import struct
import numpy as np


def rot(rx, ry, rz):
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    X = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Z @ Y @ X


def read_skeleton(d):
    o = d.index(b'skl ')
    size, n = struct.unpack_from('<II', d, o + 4)
    stride = (size - 16) // n
    bones = []
    for i in range(n):
        p = o + 16 + stride * i
        bid, par = struct.unpack_from('<Hh', d, p)
        v = struct.unpack_from('<9f', d, p + 4)
        bones.append(dict(id=bid & 0xFFF, parent=par, scale=v[0:3], rot=v[3:6], trans=v[6:9]))
    world = []
    for b in bones:
        m = np.eye(4)
        m[:3, :3] = rot(*b['rot']) * np.array(b['scale'])
        m[:3, 3] = b['trans']
        world.append(world[b['parent']] @ m if b['parent'] >= 0 else m)
    return bones, world


if __name__ == '__main__':
    import sys
    bones, world = read_skeleton(open(sys.argv[1], 'rb').read())
    for i, (b, w) in enumerate(zip(bones, world)):
        print(i, b['parent'], np.round(w[:3, 3], 1), 'xaxis', np.round(w[:3, 0], 2))
