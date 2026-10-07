"""ModLoader64 .pak reader (header 'ModLoader64', entries: tag, name offset, start, end; 0xFF-terminated names)."""
import struct, zlib, os, sys


def read(src):
    """{name: bytes} of every file in a .pak (src: path or bytes)."""
    d = src if isinstance(src, (bytes, bytearray)) else open(src, 'rb').read()
    assert d[:11] == b'ModLoader64', 'not a ModLoader64 .pak'
    out = {}
    for i in range(d[0x0E]):
        tag, name_off, start, end = struct.unpack_from('>4sIII', d, 0x10 + 16 * i)
        name = d[name_off:d.index(b'\xff', name_off)].decode('utf-8')
        raw = d[start:end]
        out[name] = zlib.decompress(raw) if tag == b'DEFL' else raw
    return out


def extract(path, outdir):
    files = read(path)
    for name, data in files.items():
        p = os.path.join(outdir, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(data)
    return list(files)


if __name__ == '__main__':
    names = extract(sys.argv[1], sys.argv[2])
    print(len(names), 'files')
