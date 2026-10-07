"""Nintendo DSP-ADPCM (GC/Wii/3DS) encode/decode. 8-byte frames: header (pred<<4 | scale) + 14 nibbles."""
import numpy as np

SAMPLES_PER_FRAME = 14


def _clamp16(v):
    return -32768 if v < -32768 else 32767 if v > 32767 else v


def decode(data, nsamples, coefs, hist1=0, hist2=0):
    out = []
    c = [(coefs[2 * i], coefs[2 * i + 1]) for i in range(8)]
    for f in range(0, len(data), 8):
        ps = data[f]
        c1, c2 = c[ps >> 4]
        scale = 1 << (ps & 15)
        for i in range(14):
            b = data[f + 1 + i // 2]
            n = (b >> 4) if i % 2 == 0 else (b & 15)
            if n >= 8:
                n -= 16
            s = _clamp16(((n * scale) << 11) + 1024 + c1 * hist1 + c2 * hist2 >> 11)
            hist2, hist1 = hist1, s
            out.append(s)
            if len(out) == nsamples:
                return out
    return out


try:  # in the browser (Pyodide) the same encoder runs as JavaScript (web/worker.js: dspEncode)
    from js import dspEncode as _js_encode
except ImportError:
    _js_encode = None


def encode(samples, coefs):
    """samples: int16 sequence. coefs: 16 ints (8 predictor pairs). Returns (bytes, first header)."""
    if _js_encode is not None:
        from pyodide.ffi import to_js
        res = _js_encode(to_js(np.asarray(samples, dtype=np.int16)), to_js(list(coefs)))
        data = bytes(res.data.to_py())
        return data, data[0]
    pcm = np.asarray(samples, dtype=np.int64)
    n = len(pcm)
    nframes = (n + 13) // 14
    pad = np.zeros(nframes * 14, dtype=np.int64)
    pad[:n] = pcm
    cs = [(coefs[2 * i], coefs[2 * i + 1]) for i in range(8)]
    out = bytearray()
    h1 = h2 = 0
    for f in range(nframes):
        frame = pad[f * 14:f * 14 + 14]
        best = None
        for p, (c1, c2) in enumerate(cs):
            # estimate scale from the ideal (undistorted) prediction residual
            a1, a2, maxr = h1, h2, 0
            for s in frame:
                r = int(s) * 2048 - (c1 * a1 + c2 * a2)
                maxr = max(maxr, abs(r))
                a2, a1 = a1, int(s)
            scale = 0
            while scale < 12 and (maxr >> 11) > (7 << scale):
                scale += 1
            for sc in (scale, min(scale + 1, 12)):
                a1, a2, err, nibs = h1, h2, 0, []
                for s in frame:
                    pred = c1 * a1 + c2 * a2
                    r = int(s) * 2048 - pred
                    q = max(-8, min(7, int(round(r / float(1 << (11 + sc))))))
                    dec = _clamp16(((q << sc) << 11) + 1024 + pred >> 11)
                    err += (dec - int(s)) ** 2
                    nibs.append(q & 15)
                    a2, a1 = a1, dec
                if best is None or err < best[0]:
                    best = (err, p, sc, nibs, a1, a2)
        _, p, sc, nibs, h1, h2 = best
        out.append((p << 4) | sc)
        for i in range(0, 14, 2):
            out.append((nibs[i] << 4) | nibs[i + 1])
    return bytes(out), out[0]
