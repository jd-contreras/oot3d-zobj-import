"""ZAR archive (Grezzo OoT3D/MM3D) reader/writer."""
import struct, sys, os

def read_zar(src):
    """src: file path or the archive bytes."""
    d = src if isinstance(src, (bytes, bytearray)) else open(src, 'rb').read()
    assert d[:4] == b'ZAR\x01', 'not a ZAR'
    size, ntypes, nfiles, types_off, meta_off, data_off = struct.unpack_from('<IHHIII', d, 4)
    def cstr(o):
        return d[o:d.index(b'\0', o)].decode('ascii')
    types = []
    for i in range(ntypes):
        cnt, lst, name_off, _ = struct.unpack_from('<IIIi', d, types_off + i * 16)
        idx = [struct.unpack_from('<I', d, lst + 4 * j)[0] for j in range(cnt)]
        types.append((cstr(name_off), idx))
    files = []
    for i in range(nfiles):
        fsize, name_off = struct.unpack_from('<II', d, meta_off + 8 * i)
        off = struct.unpack_from('<I', d, data_off + 4 * i)[0]
        files.append((cstr(name_off), d[off:off + fsize]))
    return types, files

if __name__ == '__main__':
    types, files = read_zar(sys.argv[1])
    for t, idx in types:
        print(f'{t}: {len(idx)}')
    if len(sys.argv) > 2 and sys.argv[2] == '-l':
        for n, b in files:
            print(f'{len(b):8d} {n}')
    if len(sys.argv) > 3 and sys.argv[2] == '-x':
        out = sys.argv[3]
        for n, b in files:
            p = os.path.join(out, n)
            os.makedirs(os.path.dirname(p) or out, exist_ok=True)
            open(p, 'wb').write(b)


def replace_files(d, replacements):
    """Return a new ZAR with some files' contents replaced (by name). Layout otherwise unchanged."""
    size, ntypes, nfiles, types_off, meta_off, data_off = struct.unpack_from('<IHHIII', d, 4)
    out = bytearray(d)
    names, datas = [], []
    for i in range(nfiles):
        fsize, name_off = struct.unpack_from('<II', d, meta_off + 8 * i)
        off = struct.unpack_from('<I', d, data_off + 4 * i)[0]
        name = d[name_off:d.index(b'\0', name_off)].decode('ascii')
        names.append(name)
        datas.append(replacements.pop(name, d[off:off + fsize]))
    assert not replacements, f'files not in archive: {list(replacements)}'
    first = min(struct.unpack_from('<I', d, data_off + 4 * i)[0] for i in range(nfiles))
    out = out[:first]
    for i, b in enumerate(datas):
        while len(out) % 4:
            out.append(0)
        struct.pack_into('<I', out, data_off + 4 * i, len(out))
        struct.pack_into('<I', out, meta_off + 8 * i, len(b))
        out += b
    while len(out) % 4:
        out.append(0)
    struct.pack_into('<I', out, 4, len(out))
    return bytes(out)
