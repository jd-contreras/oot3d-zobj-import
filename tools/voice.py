"""Build an OoT3D voice mod (romfs/sound/QueenSound.bcsar) from an ML64 voice pack.

    python tools/voice.py <pack.pak | extracted sounds folder> <romfs>/sound/QueenSound.bcsar <out_dir> [--rate 22050]

Folders are N64 sound ids (6800 = adult attack yell, ...); every .ogg/.wav inside is a variant.
Each id's variants go into the WARC waves its OoT3D sound can play (the game's script already
picks among them at random). Waves shared by several ids go to the lowest id that has clips.
"""
import sys, os, struct, subprocess, tempfile, argparse
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import csar, voicemap, dspadpcm, ml64pak

LINK_VOICE_WAVES = range(250, 330)  # WARC_SE indices of Link's voice samples (330+ = other characters)
FOLDER_ALIASES = {0x6010: 0x6810, 0x6030: 0x6830}  # typos in the common OotO voice template


CLIP_EXT = ('.ogg', '.wav', '.mp3')


def find_clips(files):
    """{sound id: [(clip name, file bytes)]} from a file set {path: bytes} (an extracted .pak or
    folder): clips live in sounds/<hex id>[-description]/ (or any folder named by a hex id)."""
    pack = {}
    for path in sorted(files):
        parts = path.replace('\\', '/').split('/')
        if len(parts) < 2 or not parts[-1].lower().endswith(CLIP_EXT):
            continue
        low = [x.lower() for x in parts]
        folder = parts[low.index('sounds') + 1] if 'sounds' in low[:-2] else parts[-2]
        try:
            sid = int(folder.split('-')[0].strip(), 16)
        except ValueError:
            continue
        sid = FOLDER_ALIASES.get(sid, sid)
        pack.setdefault(sid, []).append((parts[-1], files[path]))
    return pack


def read_files(src):
    """{path: bytes} from a .pak or a folder."""
    if src.lower().endswith('.pak'):
        return ml64pak.read(src)
    out = {}
    for root, _, names in os.walk(src):
        for n in names:
            full = os.path.join(root, n)
            out[os.path.relpath(full, src).replace(os.sep, '/')] = open(full, 'rb').read()
    return out


def decode_clip(data, rate):
    """Mono int16 PCM at `rate` (ffmpeg; the web page decodes in the browser instead)."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-ac', '1', '-ar', str(rate), '-f', 's16le', '-'],
                         input=data, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype='<i2').astype(np.int64)


def estimate_coefs(x):
    """8 DSP predictor pairs from per-frame least squares, clustered (k-means), one fixed at (0, 0)."""
    x = np.asarray(x, float)
    pairs, weights = np.zeros((0, 2)), np.zeros(0)
    nf = (len(x) - 16) // 14 + 1 if len(x) > 16 else 0
    if nf > 0:
        f0 = 2 + 14 * np.arange(nf)
        idx = f0[:, None] + np.arange(14)[None]  # (frames, 14)
        y, a1, a2 = x[idx], x[idx - 1], x[idx - 2]
        e = (y ** 2).sum(1)
        # 2x2 normal equations per frame (same solution as per-frame lstsq when well conditioned)
        m11, m12, m22 = (a1 * a1).sum(1), (a1 * a2).sum(1), (a2 * a2).sum(1)
        b1, b2 = (a1 * y).sum(1), (a2 * y).sum(1)
        det = m11 * m22 - m12 * m12
        ok = (e >= 1e3) & (np.abs(det) > 1e-9 * np.maximum(m11 * m22, 1))
        sol = np.stack([(b1 * m22 - b2 * m12), (b2 * m11 - b1 * m12)], 1)[ok] / det[ok, None]
        pairs, weights = np.clip(sol, -15.9, 15.9), e[ok]
    centers = [np.zeros(2)]
    if len(pairs):
        p, w = pairs, weights
        k = min(7, len(p))
        cen = p[np.linspace(0, len(p) - 1, k).astype(int)].copy()
        for _ in range(20):
            lab = np.argmin(((p[:, None, :] - cen[None]) ** 2).sum(-1), 1)
            for j in range(k):
                m = lab == j
                if m.any():
                    cen[j] = (p[m] * w[m, None]).sum(0) / w[m].sum()
        centers += list(cen)
    while len(centers) < 8:
        centers.append(np.array([1.0, 0.0]) if len(centers) == 1 else np.array([1.5, -0.6]))
    return [int(round(v * 2048)) for c in centers[:8] for v in c]


def make_cwav(template, pcm, rate, coefs):
    """New CWAV using `template` (an original voice CWAV) for its header layout."""
    t = bytearray(template)
    assert t[:4] == b'CWAV' and t[0x40:0x44] == b'INFO' and t[0xC0:0xC4] == b'DATA' and t[0x48] == 2
    data, ps = dspadpcm.encode(pcm, coefs)
    head = t[:0xE0]
    struct.pack_into('<I', head, 0x4C, rate)
    struct.pack_into('<II', head, 0x50, 0, len(pcm))  # loop start / end (= sample count)
    struct.pack_into('<16h', head, 0x7C, *coefs)
    struct.pack_into('<Hhh', head, 0x9C, ps, 0, 0)
    struct.pack_into('<Hhh', head, 0xA2, ps, 0, 0)
    out = bytes(head) + data
    out = bytearray(out)
    struct.pack_into('<I', out, 0xC4, len(out) - 0xC0)  # DATA block size
    struct.pack_into('<I', out, 0x28, len(out) - 0xC0)  # DATA block size in the header ref
    struct.pack_into('<I', out, 0x0C, len(out))
    return bytes(out)


def build(clips, bcsar, rate=22050, keep_link=False, log=print):
    """clips: {sound id: [(name, mono int16 PCM at `rate`)]}. bcsar: the game's QueenSound.bcsar bytes.
    Returns (new bcsar bytes, report lines)."""
    c = csar.read(bcsar)
    byname = {s.name: s for s in c.sounds if s.name}
    warc_file = None
    assign = {}  # wave index -> (sound id, (name, pcm) or None)
    report = []
    for sid in sorted(clips):
        name = voicemap.sound_name(sid)
        s_ = byname.get(name)
        if s_ is None:
            report.append(f'{sid:04X}: no OoT3D sound ({name}), skipped')
            continue
        waves, sequential = voicemap.voice_waves(c, s_, with_kind=True)
        cl = clips[sid]
        used, shared = [], []
        for j, (warc_id, idx) in enumerate(waves):
            wf = c.warcs[warc_id & 0xFFFFFF][1]
            warc_file = warc_file or wf
            assert wf == warc_file
            if idx in assign:
                shared.append(f'{idx} (kept {assign[idx][0]:04X})')
                continue
            if sequential and j > 0:
                assign[idx] = (sid, None)  # later notes of a one-shot sequence: silence
                used.append('(silence)')
                continue
            assign[idx] = (sid, cl[j % len(cl)])
            used.append(cl[j % len(cl)][0])
        line = (f'{sid:04X} {name}: {len(cl)} clip(s) -> waves {[w[1] for w in waves]}'
                f'{" (played in sequence)" if sequential else ""} using {used}')
        if shared:
            line += f'; shared waves left to an earlier id: {shared}'
        slots = 1 if sequential else len(waves)
        if len(cl) > slots:
            line += f'; {len(cl) - slots} extra clip(s) unused (OoT3D has {slots} slot(s))'
        report.append(line)

    if not keep_link:  # no original Link voice may remain: silence every unfilled Link voice wave
        silenced = []
        for s_ in c.sounds:
            if s_.name and (s_.name.startswith('NA_SE_VO_LI_') or s_.name.startswith('NA_SE_VO_BL_DOWN')):
                for warc_id, idx in voicemap.voice_waves(c, s_):
                    if idx not in assign:
                        assign[idx] = (None, None)
                        silenced.append(f'{idx} ({s_.name})')
        # Link's whole voice block in BANK_VOICE (adult + child) is WARC_SE waves 250-329; some of
        # them are not reached by any script (played by game code): silence those too.
        for idx in LINK_VOICE_WAVES:
            if idx not in assign:
                assign[idx] = (None, None)
                silenced.append(f'{idx} (unreferenced)')
        if silenced:
            report.append(f'silenced {len(silenced)} other Link voice wave(s): ' + ', '.join(silenced))

    if warc_file is None:
        raise ValueError('no voice clips matched an OoT3D sound')
    w = c.file(warc_file)
    i = w.index(b'INFO')
    fb = w.index(b'FILE')
    new_waves = {}
    for n, (idx, (sid, clip)) in enumerate(sorted(assign.items())):
        t, off, size = struct.unpack_from('<Hxxii', w, i + 12 + 12 * idx)
        template = w[fb + 8 + off:fb + 8 + off + size]
        pcm = np.zeros(14, dtype=np.int64) if clip is None else np.clip(np.asarray(clip[1], np.int64), -32768, 32767)
        new_waves[idx] = make_cwav(template, pcm, rate, estimate_coefs(pcm))
        if n % 10 == 0:
            log(f'encoding voice waves {n}/{len(assign)}')
    out = csar.rebuild(c, {warc_file: csar.rebuild_warc(w, new_waves)})
    report.append(f'{len(new_waves)} waves replaced; bcsar {len(c.raw)} -> {len(out)} bytes')
    return out, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pack')
    ap.add_argument('bcsar')
    ap.add_argument('out')
    ap.add_argument('--rate', type=int, default=22050)
    ap.add_argument('--keep-link', action='store_true',
                    help="leave Link's own voice in slots the pack does not fill (default: silence them)")
    a = ap.parse_args()
    found = find_clips(read_files(a.pack))
    clips = {sid: [(n, decode_clip(d, a.rate)) for n, d in cl] for sid, cl in found.items()}
    out, report = build(clips, open(a.bcsar, 'rb').read(), a.rate, a.keep_link)
    dst = os.path.join(a.out, 'romfs', 'sound')
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, 'QueenSound.bcsar'), 'wb').write(out)
    open(os.path.join(a.out, 'voice_report.txt'), 'w').write('\n'.join(report) + '\n')
    print('\n'.join(report))


if __name__ == '__main__':
    main()
