"""Write OoT3D CMAB texture-palette animations (layout copied from link_body/link_eye.cmab)."""
import struct


def _pad(b, a):
    return b + b'\0' * (-len(b) % a)


def _const_color_mmad(mat, const_idx, frames):
    """ConstColor (type 4) animation: one linear track per channel R, G, B (layout as in the OoT3D
    Randomizer's custom-tunic link_body.cmab)."""
    tracks, offs = b'', []
    for ch in range(3):
        offs.append(0x18 + len(tracks))
        keys = b''.join(struct.pack('<If', i, float(f[ch])) for i, f in enumerate(frames))
        tracks += struct.pack('<IIII', 1, len(frames), 0, len(frames) - 1) + keys
    return b'mmad' + struct.pack('<III', 4, mat, const_idx) + struct.pack('<4H', *offs, 0) + tracks


def write(anims, textures, duration, loop=0, const_colors=()):
    """anims: list of (material_index, [texture index per frame]).
    textures: list of (name, w, h, gl_format, data).
    const_colors: list of (material_index, constant_index, [(r, g, b) 0-1 per frame])."""
    mmads = []
    for mat, frames in anims:
        keys = b''.join(struct.pack('<If', i, float(v)) for i, v in enumerate(frames))
        track = struct.pack('<IIII', 3, len(frames), 0, len(frames) - 1) + keys
        mmads.append(b'mmad' + struct.pack('<IIIHH', 2, mat, 0, 0x14, 0) + track)
    mmads += [_const_color_mmad(*c) for c in const_colors]
    mads_head = 8 + 4 * len(mmads)
    offs, o = [], mads_head
    for m in mmads:
        offs.append(o)
        o += len(m)
    mads = b'mads' + struct.pack('<I', len(mmads)) + struct.pack('<%dI' % len(offs), *offs) + b''.join(mmads)

    txpt_off_abs = 0x34 + len(mads)
    data, entries = bytearray(), []
    for i, (name, w, h, fmt, d) in enumerate(textures):
        data += b'\0' * (-len(data) % 0x80)
        entries.append(struct.pack('<IHBBHHIII', len(d), 1, 1 if fmt in (0x675A, 0x675B) else 0, 0, w, h, fmt, len(data), i))
        data += d
    txpt = b'txpt' + struct.pack('<HH', len(textures), 0) + b''.join(entries)

    strt_off = txpt_off_abs + len(txpt)
    names = [t[0].encode() + b'\0' for t in textures]
    so, soffs = 0, []
    for n in names:
        soffs.append(so)
        so += len(n)
    strt = b'strt' + struct.pack('<I', len(names)) + struct.pack('<%dI' % len(names), *soffs) + b''.join(names)
    head_and_body = 0x34 + len(mads) + len(txpt) + len(strt)
    texdata_off = head_and_body + (-head_and_body % 0x10)  # Link's files align this to 16
    total = texdata_off + len(data)

    out = b'cmab' + struct.pack('<IIIIIII', 1, total, 0, 1, 0x20, strt_off, texdata_off)
    out += struct.pack('<iIIII', -1, duration, loop, 0x14, txpt_off_abs - 0x20)
    out += mads + txpt + strt
    out += b'\0' * (texdata_off - len(out)) + bytes(data)
    assert len(out) == total
    return out

