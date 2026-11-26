// Music removal on the visitor's own device: the same MDX-Net vocal model the servers use
// (UVR-MDX-NET-Voc_FT), with the spectrogram work done here in plain JavaScript and the network
// run by ONNX Runtime (WebGPU when the browser has it). Matches audio-separator's MDX pipeline:
// 44.1 kHz stereo, n_fft 7680, hop 1024, 3072 frequency bins, 256 frames per chunk.
export const N_FFT = 7680, HOP = 1024, DIM_F = 3072, DIM_T = 256, RATE = 44100;
export const CHUNK = HOP * (DIM_T - 1), TRIM = N_FFT / 2, GEN = CHUNK - 2 * TRIM, COMPENSATE = 1.021;

// Mixed-radix complex FFT (7680 = 4^4 · 2 · 3 · 5), planned once: a precomputed input order,
// then iterative butterfly stages (radix 4 and 2 written out, 3 and 5 as small DFTs).
export function planFFT(n) {
  const factors = []; let m = n;
  for (const p of [4, 2, 3, 5]) while (m % p === 0) { factors.push(p); m /= p; }
  if (m !== 1) throw Error('unsupported FFT size ' + n);
  const cos = new Float64Array(n), sin = new Float64Array(n);
  for (let k = 0; k < n; k++) { cos[k] = Math.cos(2 * Math.PI * k / n); sin[k] = -Math.sin(2 * Math.PI * k / n); }
  const perm = new Int32Array(n);
  (function place(off, stride, outOff, size, level) {
    if (size === 1) { perm[outOff] = off; return; }
    const p = factors[level], q = size / p;
    for (let j = 0; j < p; j++) place(off + j * stride, stride * p, outOff + j * q, q, level + 1);
  })(0, 1, 0, n, 0);
  const wr = new Float64Array(n), wi = new Float64Array(n), tr = new Float64Array(5), ti = new Float64Array(5);
  function forward(re, im) {
    for (let i = 0; i < n; i++) { wr[i] = re[perm[i]]; wi[i] = im[perm[i]]; }
    let q = 1;
    for (let level = factors.length - 1; level >= 0; level--) {
      const p = factors[level], size = p * q, tw = n / size;
      for (let base = 0; base < n; base += size) {
        for (let k = 0; k < q; k++) {
          const a = base + k;
          if (p === 2) {
            const b = a + q, w = k * tw, br = wr[b] * cos[w] - wi[b] * sin[w], bi = wr[b] * sin[w] + wi[b] * cos[w], ar = wr[a], ai = wi[a];
            wr[a] = ar + br; wi[a] = ai + bi; wr[b] = ar - br; wi[b] = ai - bi;
          } else if (p === 4) {
            const b = a + q, c = b + q, d = c + q, w1 = k * tw, w2 = 2 * w1, w3 = 3 * w1;
            const x0r = wr[a], x0i = wi[a];
            const x1r = wr[b] * cos[w1] - wi[b] * sin[w1], x1i = wr[b] * sin[w1] + wi[b] * cos[w1];
            const x2r = wr[c] * cos[w2] - wi[c] * sin[w2], x2i = wr[c] * sin[w2] + wi[c] * cos[w2];
            const x3r = wr[d] * cos[w3] - wi[d] * sin[w3], x3i = wr[d] * sin[w3] + wi[d] * cos[w3];
            const s0r = x0r + x2r, s0i = x0i + x2i, s1r = x0r - x2r, s1i = x0i - x2i;
            const s2r = x1r + x3r, s2i = x1i + x3i, s3r = x1r - x3r, s3i = x1i - x3i;
            wr[a] = s0r + s2r; wi[a] = s0i + s2i; wr[c] = s0r - s2r; wi[c] = s0i - s2i;
            // forward transform: multiply by -i
            wr[b] = s1r + s3i; wi[b] = s1i - s3r; wr[d] = s1r - s3i; wi[d] = s1i + s3r;
          } else {
            for (let j = 0; j < p; j++) { const idx = a + j * q, w = (j * k * tw) % n; tr[j] = wr[idx] * cos[w] - wi[idx] * sin[w]; ti[j] = wr[idx] * sin[w] + wi[idx] * cos[w]; }
            const step = n / p;
            for (let s = 0; s < p; s++) {
              let sr = 0, si = 0;
              for (let j = 0; j < p; j++) { const w = (j * s * step) % n; sr += tr[j] * cos[w] - ti[j] * sin[w]; si += tr[j] * sin[w] + ti[j] * cos[w]; }
              wr[a + s * q] = sr; wi[a + s * q] = si;
            }
          }
        }
      }
      q = size;
    }
    re.set(wr); im.set(wi);
  }
  return {
    n, forward,
    inverse(re, im) { for (let i = 0; i < n; i++) im[i] = -im[i]; forward(re, im); for (let i = 0; i < n; i++) { re[i] /= n; im[i] = -im[i] / n; } },
  };
}

export function hann(n) { const w = new Float64Array(n); for (let i = 0; i < n; i++) w[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / n); return w; }

const reflect = (x, i) => { const n = x.length; while (i < 0 || i >= n) i = i < 0 ? -i : 2 * (n - 1) - i; return x[i]; };

// One chunk (2 × CHUNK samples) → model input [4, DIM_F, DIM_T]: L real, L imag, R real, R imag.
export function chunkSpectrum(left, right, fft, win, out = new Float32Array(4 * DIM_F * DIM_T)) {
  const re = new Float64Array(N_FFT), im = new Float64Array(N_FFT), pad = N_FFT / 2, plane = DIM_F * DIM_T;
  // Reflect-pad each channel once (as torch.stft(center=True) does), then frames are plain slices.
  const len = left.length + 2 * pad, pl = new Float64Array(len), pr = new Float64Array(len);
  for (let i = 0; i < len; i++) { pl[i] = reflect(left, i - pad); pr[i] = reflect(right, i - pad); }
  for (let t = 0; t < DIM_T; t++) {
    const start = t * HOP;
    for (let i = 0; i < N_FFT; i++) { re[i] = pl[start + i] * win[i]; im[i] = pr[start + i] * win[i]; }
    fft.forward(re, im);
    // Two real signals packed as one complex: split the spectra.
    for (let k = 0; k < DIM_F; k++) {
      const j = k === 0 ? 0 : N_FFT - k;
      const lr = (re[k] + re[j]) / 2, li = (im[k] - im[j]) / 2, rr = (im[k] + im[j]) / 2, ri = (re[j] - re[k]) / 2;
      const at = k * DIM_T + t;
      out[at] = lr; out[plane + at] = li; out[2 * plane + at] = rr; out[3 * plane + at] = ri;
    }
  }
  return out;
}

// Model output [4, DIM_F, DIM_T] → 2 × CHUNK samples (inverse STFT, centred, overlap-added).
export function chunkWave(spec, fft, win) {
  const plane = DIM_F * DIM_T, len = N_FFT + HOP * (DIM_T - 1);
  const yl = new Float64Array(len), yr = new Float64Array(len), norm = new Float64Array(len);
  const re = new Float64Array(N_FFT), im = new Float64Array(N_FFT);
  for (let t = 0; t < DIM_T; t++) {
    re.fill(0); im.fill(0);
    for (let k = 0; k < DIM_F; k++) {
      const at = k * DIM_T + t, lr = spec[at], li = spec[plane + at], rr = spec[2 * plane + at], ri = spec[3 * plane + at];
      // Z_k = L_k + i R_k, Z_{N-k} = conj(L_k) + i conj(R_k)
      if (k === 0) { re[0] = lr; im[0] = rr; continue; } // a real signal's DC bin has no imaginary part
      re[k] = lr - ri; im[k] = li + rr;
      const j = N_FFT - k; re[j] = lr + ri; im[j] = -li + rr;
    }
    fft.inverse(re, im);
    const o = t * HOP;
    for (let i = 0; i < N_FFT; i++) { yl[o + i] += re[i] * win[i]; yr[o + i] += im[i] * win[i]; norm[o + i] += win[i] * win[i]; }
  }
  const left = new Float32Array(CHUNK), right = new Float32Array(CHUNK), pad = N_FFT / 2;
  for (let i = 0; i < CHUNK; i++) { const w = Math.max(norm[pad + i], 1e-8); left[i] = yl[pad + i] / w; right[i] = yr[pad + i] / w; }
  return [left, right];
}

// Whole song: run(specFloat32) must resolve to the model's output Float32Array.
export async function separateVocals(left, right, run, {onProgress = () => {}, onChunk = () => {}, signal} = {}) {
  const n = left.length, padEnd = GEN - (n % GEN), total = TRIM + n + padEnd + TRIM;
  const L = new Float32Array(total), R = new Float32Array(total);
  L.set(left, TRIM); R.set(right, TRIM);
  const fft = planFFT(N_FFT), win = hann(N_FFT), vl = new Float32Array(n), vr = new Float32Array(n);
  const chunks = (n + padEnd) / GEN; let done = 0;
  const timing = {spectrum: 0, model: 0, wave: 0};
  for (let i = 0; i < n + padEnd; i += GEN) {
    if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
    let t = performance.now();
    const spec = chunkSpectrum(L.subarray(i, i + CHUNK), R.subarray(i, i + CHUNK), fft, win);
    timing.spectrum += performance.now() - t; t = performance.now();
    const out = await run(spec);
    timing.model += performance.now() - t; t = performance.now();
    const [wl, wr] = chunkWave(out, fft, win);
    timing.wave += performance.now() - t;
    for (let j = 0; j < GEN && i + j < n; j++) { vl[i + j] = wl[TRIM + j] * COMPENSATE; vr[i + j] = wr[TRIM + j] * COMPENSATE; }
    onProgress(++done / chunks, timing);
    onChunk(done, chunks);
    await new Promise(r => setTimeout(r, 0)); // let the page breathe between pieces
  }
  return {left: vl, right: vr, timing, chunks};
}
