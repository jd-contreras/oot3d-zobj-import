"""Minimal CTR sound archive (BCSAR) reader: names, sounds, banks, wave archives, files."""
import struct
from dataclasses import dataclass, field


def _ref(d, o):
    t, off = struct.unpack_from('<Hxxi', d, o)
    return t, off


def _table(d, base, o):
    """Reference table at absolute `o`; entry offsets are relative to the table start."""
    n = struct.unpack_from('<I', d, o)[0]
    out = []
    for i in range(n):
        t, off = _ref(d, o + 4 + 8 * i)
        out.append((t, o + off if off >= 0 else None))
    return out


@dataclass
class Sound:
    index: int
    name: str
    file_id: int
    player: int
    kind: int  # 0x2201 stream, 0x2202 wave, 0x2203 sequence
    detail: int  # absolute offset of the detail info
    start_offset: int = None  # sequence sounds: offset into the CSEQ data
    banks: list = field(default_factory=list)


@dataclass
class CSAR:
    raw: bytes
    strings: list
    sounds: list
    banks: list  # (name, file_id, [warc ids])
    warcs: list  # (name, file_id)
    files: list  # (abs offset or None, size)
    file_info_offs: list  # absolute offset of each file's internal sized-reference (for patching)

    def file(self, i):
        o, n = self.files[i]
        return self.raw[o:o + n]


def read(d):
    assert d[:4] == b'CSAR'
    nblocks = struct.unpack_from('<I', d, 0x10)[0]
    blocks = {}
    for i in range(nblocks):
        t, off = _ref(d, 0x14 + 12 * i)
        blocks[t] = off
    strg, info, fileb = blocks[0x2000], blocks[0x2001], blocks[0x2002]

    # strings
    _, st_off = _ref(d, strg + 8)
    st = strg + 8 + st_off
    n = struct.unpack_from('<I', d, st)[0]
    strings = []
    for i in range(n):
        _, off, size = struct.unpack_from('<Hxxii', d, st + 4 + 12 * i)
        strings.append(d[st + off:st + off + size].split(b'\0')[0].decode('ascii', 'replace'))

    body = info + 8
    refs = {}
    for k in range(8):
        t, off = _ref(d, body + 8 * k)
        refs[t] = body + off

    def name_of(flags_o):
        flags = struct.unpack_from('<I', d, flags_o)[0]
        return strings[struct.unpack_from('<I', d, flags_o + 4)[0]] if flags & 1 else None

    sounds = []
    for i, (t, o) in enumerate(_table(d, body, refs[0x2100])):
        file_id, player, vol = struct.unpack_from('<IIB', d, o)
        dt, doff = _ref(d, o + 0x0C)
        s = Sound(i, name_of(o + 0x14), file_id, player, dt, o + doff)
        if dt == 0x2203:
            bt, boff = _ref(d, s.detail)
            bank_tab = s.detail + boff
            nb = struct.unpack_from('<I', d, bank_tab)[0]
            s.banks = list(struct.unpack_from('<%dI' % nb, d, bank_tab + 4))
            # flags at +0x0C: bit0 = start offset
            flags = struct.unpack_from('<I', d, s.detail + 0x0C)[0]
            if flags & 1:
                s.start_offset = struct.unpack_from('<I', d, s.detail + 0x10)[0]
        sounds.append(s)

    banks = []
    for t, o in _table(d, body, refs[0x2101]):
        file_id = struct.unpack_from('<I', d, o)[0]
        wt, woff = _ref(d, o + 4)
        wtab = o + woff
        nw = struct.unpack_from('<I', d, wtab)[0]
        banks.append((name_of(o + 0x0C), file_id, list(struct.unpack_from('<%dI' % nw, d, wtab + 4))))

    warcs = []
    for t, o in _table(d, body, refs[0x2103]):
        file_id = struct.unpack_from('<I', d, o)[0]
        warcs.append((name_of(o + 8), file_id))

    files, file_info = [], []
    for t, o in _table(d, body, refs[0x2106]):
        ft, foff = _ref(d, o)
        if ft == 0x220C:  # internal: sized reference into the FILE block body
            p = o + foff
            rt, roff, size = struct.unpack_from('<Hxxii', d, p)
            files.append((fileb + 8 + roff if roff >= 0 else None, size))
            file_info.append(p)
        else:
            files.append((None, 0))
            file_info.append(None)
    return CSAR(d, strings, sounds, banks, warcs, files, file_info)


def _align(n, a):
    return n + (-n % a)


def rebuild_warc(w, replace):
    """CWAR with some waves replaced (dict index -> CWAV bytes). Waves stay 0x20-aligned."""
    i = w.index(b'INFO')
    fb = w.index(b'FILE')
    n = struct.unpack_from('<I', w, i + 8)[0]
    ents = [struct.unpack_from('<Hxxii', w, i + 12 + 12 * k) for k in range(n)]
    out = bytearray(w[:fb + 8])
    for k, (t, off, size) in enumerate(ents):
        data = replace.get(k, w[fb + 8 + off:fb + 8 + off + size])
        out += b'\0' * (_align(len(out), 0x20) - len(out))
        struct.pack_into('<Hxxii', out, i + 12 + 12 * k, t, len(out) - (fb + 8), len(data))
        out += data
    orig_end = fb + struct.unpack_from('<I', w, fb + 4)[0]
    last = ents[-1][1] + ents[-1][2] + fb + 8
    out += b'\0' * (orig_end - last)  # keep the original tail padding
    struct.pack_into('<I', out, fb + 4, len(out) - fb)
    struct.pack_into('<I', out, 0x28, len(out) - fb)  # FILE block size in the header ref
    struct.pack_into('<I', out, 0x0C, len(out))
    return bytes(out)


def rebuild(c, replace):
    """BCSAR with some internal files replaced (dict file id -> bytes). Files stay 0x20-aligned."""
    d = c.raw
    fbk = struct.unpack_from('<i', d, 0x14 + 12 * 2 + 4)[0]
    out = bytearray(d[:fbk + 8])
    order = sorted((o, k) for k, (o, size) in enumerate(c.files) if o is not None)
    last_end = 0
    for o, k in order:
        size = c.files[k][1]
        data = replace.get(k, d[o:o + size])
        out += b'\0' * (_align(len(out), 0x20) - len(out))
        p = c.file_info_offs[k]
        struct.pack_into('<ii', out, p + 4, len(out) - (fbk + 8), len(data))
        out += data
        last_end = max(last_end, o + size)
    orig_end = fbk + struct.unpack_from('<I', d, fbk + 4)[0]
    out += b'\0' * (orig_end - last_end)
    struct.pack_into('<I', out, fbk + 4, len(out) - fbk)
    struct.pack_into('<I', out, 0x14 + 12 * 2 + 8, len(out) - fbk)
    struct.pack_into('<I', out, 0x0C, len(out))
    return bytes(out)
