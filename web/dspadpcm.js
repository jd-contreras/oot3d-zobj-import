// DSP-ADPCM encoder: a line-for-line port of tools/dspadpcm.py encode() (pure Python is too slow in
// the browser). Returns {data: Uint8Array} of 8-byte frames: header (pred<<4 | scale) + 14 nibbles.
function dspEncode(samples, coefs) {
  const n = samples.length, nframes = Math.ceil(n / 14);
  const pad = new Int32Array(nframes * 14);
  pad.set(samples);
  const out = new Uint8Array(nframes * 8);
  const clamp16 = v => (v < -32768 ? -32768 : v > 32767 ? 32767 : v);
  // Python's round(): half to even
  const roundEven = x => { const r = Math.round(x); return (Math.abs(x % 1) === 0.5 && r % 2 !== 0) ? r - 1 : r; };
  let h1 = 0, h2 = 0;
  const nibs = new Int32Array(14), bestNibs = new Int32Array(14);
  for (let f = 0; f < nframes; f++) {
    let bestErr = Infinity, bestP = 0, bestSc = 0, bestH1 = 0, bestH2 = 0;
    for (let p = 0; p < 8; p++) {
      const c1 = coefs[2 * p], c2 = coefs[2 * p + 1];
      let a1 = h1, a2 = h2, maxr = 0;
      for (let i = 0; i < 14; i++) {
        const s = pad[f * 14 + i];
        const r = s * 2048 - (c1 * a1 + c2 * a2);
        if (Math.abs(r) > maxr) maxr = Math.abs(r);
        a2 = a1; a1 = s;
      }
      let scale = 0;
      while (scale < 12 && Math.floor(maxr / 2048) > (7 << scale)) scale++;
      for (const sc of [scale, Math.min(scale + 1, 12)]) {
        let b1 = h1, b2 = h2, err = 0;
        for (let i = 0; i < 14; i++) {
          const s = pad[f * 14 + i];
          const pred = c1 * b1 + c2 * b2;
          const r = s * 2048 - pred;
          const q = Math.max(-8, Math.min(7, roundEven(r / Math.pow(2, 11 + sc))));
          const dec = clamp16(Math.floor((q * Math.pow(2, sc) * 2048 + 1024 + pred) / 2048));
          err += (dec - s) * (dec - s);
          nibs[i] = q & 15;
          b2 = b1; b1 = dec;
        }
        if (err < bestErr) {
          bestErr = err; bestP = p; bestSc = sc; bestH1 = b1; bestH2 = b2; bestNibs.set(nibs);
        }
      }
    }
    h1 = bestH1; h2 = bestH2;
    out[f * 8] = (bestP << 4) | bestSc;
    for (let i = 0; i < 14; i += 2) out[f * 8 + 1 + i / 2] = (bestNibs[i] << 4) | bestNibs[i + 1];
  }
  return { data: out };
}
if (typeof module !== 'undefined') module.exports = { dspEncode };
