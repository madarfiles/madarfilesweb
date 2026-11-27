// Optional "mute the intros and musical breaks": after the fast model has taken the voice out,
// a small speech detector (Silero VAD v5, MIT, ~2 MB) finds where someone is actually talking,
// and everything else is faded to silence. It removes instrument-only stretches the fast model
// keeps (wind instruments, flutes, keyboards); music playing under the speech is not touched.
// Runs on the visitor's device with ONNX Runtime's plain WebAssembly backend (no GPU needed).
import {ORT_URL, ORT_WASM} from './device-separate.js';

export const VAD_URL = '/lab/models/silero-vad-v5-v1.onnx';
const VAD_RATE = 16000, FRAME = 512, CONTEXT = 64;

let vad = null;
async function vadBytes() {
  const cache = await caches.open('madar-models').catch(() => null);
  const hit = await cache?.match(VAD_URL);
  if (hit) return new Uint8Array(await hit.arrayBuffer());
  const res = await fetch(VAD_URL);
  if (!res.ok) throw Error('vad HTTP ' + res.status);
  const bytes = new Uint8Array(await res.arrayBuffer());
  await cache?.put(VAD_URL, new Response(bytes, {headers: {'Content-Type': 'application/octet-stream'}})).catch(() => {});
  return bytes;
}
function loadVad(ortModule) {
  vad ??= (async () => {
    const ort = ortModule || await import(/* webpackIgnore: true */ ORT_URL);
    if (!ortModule) { ort.env.wasm.wasmPaths = {wasm: ORT_WASM}; ort.env.wasm.numThreads = 1; }
    const s = await ort.InferenceSession.create(await vadBytes(), {executionProviders: ['wasm']});
    return {ort, s};
  })().catch(e => { vad = null; throw e; });
  return vad;
}
export async function releaseVad() { const p = vad; vad = null; if (!p) return; try { const {s} = await p; await s.release?.(); } catch {} }

// 44.1 kHz stereo → 16 kHz mono. A short average before picking each sample keeps it clean enough
// for speech detection (this audio is only listened to by the detector, never by a person).
export function toVadRate(left, right, rate = 44100) {
  const step = rate / VAD_RATE, n = Math.floor(left.length / step), out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const c = i * step, a = Math.max(0, Math.floor(c - 1)), b = Math.min(left.length - 1, Math.ceil(c + 1));
    let sum = 0; for (let j = a; j <= b; j++) sum += left[j] + (right ? right[j] : left[j]);
    out[i] = sum / (2 * (b - a + 1));
  }
  return out;
}

// Chance of speech for every 32 ms frame.
export async function speechProbs(mono, {signal, ort: ortModule} = {}) {
  const {ort, s} = await loadVad(ortModule);
  const frames = Math.floor(mono.length / FRAME), probs = new Float32Array(frames);
  let state = new ort.Tensor('float32', new Float32Array(2 * 128), [2, 1, 128]);
  const sr = new ort.Tensor('int64', BigInt64Array.from([16000n]), []);
  const input = new Float32Array(CONTEXT + FRAME);
  for (let f = 0; f < frames; f++) {
    input.copyWithin(0, FRAME, FRAME + CONTEXT);             // keep the tail of the previous frame
    input.set(mono.subarray(f * FRAME, f * FRAME + FRAME), CONTEXT);
    const out = await s.run({input: new ort.Tensor('float32', input.slice(), [1, CONTEXT + FRAME]), state, sr});
    state = out.stateN; probs[f] = out.output.data[0];
    if (f % 400 === 399) { if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError'); await new Promise(r => setTimeout(r, 0)); }
  }
  return probs;
}

// Speech stretches in seconds, following Silero's own rules, but generous: short pauses inside
// speech are kept, and each stretch gets padding so first and last syllables are never clipped.
export function speechSegments(probs, {on = 0.5, off = 0.35, minSpeech = 0.25, minSilence = 0.8, pad = 0.3} = {}) {
  const sec = FRAME / VAD_RATE, segs = [];
  let start = -1, lastSpeech = -1;
  for (let f = 0; f < probs.length; f++) {
    const p = probs[f];
    if (p >= on) { if (start < 0) start = f; lastSpeech = f; }
    else if (start >= 0 && p < off && (f - lastSpeech) * sec >= minSilence) {
      if ((lastSpeech - start + 1) * sec >= minSpeech) segs.push([start * sec, (lastSpeech + 1) * sec]);
      start = -1;
    }
  }
  if (start >= 0 && (lastSpeech - start + 1) * sec >= minSpeech) segs.push([start * sec, (lastSpeech + 1) * sec]);
  const merged = [];
  for (const [a, b] of segs.map(([a, b]) => [Math.max(0, a - pad), b + pad])) {
    const last = merged[merged.length - 1];
    if (last && a <= last[1]) last[1] = Math.max(last[1], b); else merged.push([a, b]);
  }
  return merged;
}

// Silence outside the speech stretches, with short fades so nothing clicks. Works in place.
export function applyGate(left, right, segments, rate = 44100, fade = 0.06) {
  const n = left.length, f = Math.max(1, Math.round(fade * rate)), gain = new Float32Array(n);
  for (const [a, b] of segments) {
    const s = Math.max(0, Math.round(a * rate)), e = Math.min(n, Math.round(b * rate));
    for (let i = s; i < e; i++) {
      const g = Math.min(1, (i - s + 1) / f, (e - i) / f);
      if (g > gain[i]) gain[i] = g;
    }
  }
  for (let i = 0; i < n; i++) { left[i] *= gain[i]; if (right && right !== left) right[i] *= gain[i]; }
}

// The whole step. When almost no speech is found (a sung track, say) the audio is left as it is,
// so the option can never hand back silence.
export async function gateSpeech(left, right, {rate = 44100, signal, ort} = {}) {
  const probs = await speechProbs(toVadRate(left, right, rate), {signal, ort});
  const segments = speechSegments(probs), seconds = left.length / rate;
  const kept = segments.reduce((t, [a, b]) => t + Math.min(b, seconds) - a, 0) / Math.max(seconds, 1e-6);
  if (kept < 0.03) return {applied: false, kept, segments};
  applyGate(left, right, segments, rate);
  return {applied: true, kept, segments};
}
