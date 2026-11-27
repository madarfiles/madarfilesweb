// Music removal on the visitor's own device (WebGPU). It is tried first; whatever it cannot do
// well — no WebGPU, no half-precision support, too little memory, a long file, or a device that
// turns out slower than the clip itself — goes on to the quick engine and then Colab as before.
import {separateVocals, GEN, RATE, DIM_F, DIM_T} from './lab/mdx.js';

export const ORT_URL = '/lab/ort/1.31.1/ort-webgpu.js', ORT_WASM = '/lab/ort/1.31.1/ort-wasm-simd-threaded.asyncify.wasm';
export const MODEL_URL = '/lab/models/mdx-voc-ft-fp16-v1.onnx', MODEL_BYTES = 33.4e6;
export const DEVICE_MAX_SECONDS = 600;     // longer audio needs too much memory on a phone
const CHUNK_SECONDS = GEN / RATE;           // ≈ 5.75 s of audio per model run

let support = null, session = null;

// Does this browser have what the on-device path needs? Cached for the page.
export function deviceSupport() {
  support ??= (async () => {
    try {
      if (!navigator.gpu || !globalThis.caches) return {ok: false, why: 'no-webgpu'};
      if ((navigator.deviceMemory || 8) < 4) return {ok: false, why: 'memory'};
      const adapter = await navigator.gpu.requestAdapter({powerPreference: 'high-performance'});
      if (!adapter) return {ok: false, why: 'no-adapter'};
      if (!adapter.features.has('shader-f16')) return {ok: false, why: 'no-f16'};
      const info = adapter.info || {};
      return {ok: true, gpu: [info.vendor, info.architecture].filter(Boolean).join(' · ')};
    } catch (e) { return {ok: false, why: 'error: ' + (e?.message || e)}; }
  })();
  return support;
}

// A slow device is remembered for a while so it goes straight to the quick engine next time.
const SLOW_KEY = 'madar-device-slow';
export function markedSlow(store = globalThis.localStorage) { try { return Number(store?.getItem(SLOW_KEY) || 0) > Date.now(); } catch { return false; } }
export function markSlow(store = globalThis.localStorage, days = 7) { try { store?.setItem(SLOW_KEY, String(Date.now() + days * 864e5)); } catch {} }

async function modelBytes(onProgress) {
  const cache = await caches.open('madar-models').catch(() => null);
  const hit = await cache?.match(MODEL_URL);
  if (hit) return new Uint8Array(await hit.arrayBuffer());
  const res = await fetch(MODEL_URL);
  if (!res.ok || !res.body) throw Error('model HTTP ' + res.status);
  const total = Number(res.headers.get('Content-Length')) || MODEL_BYTES, reader = res.body.getReader(), parts = []; let got = 0;
  for (;;) { const {done, value} = await reader.read(); if (done) break; parts.push(value); got += value.length; onProgress?.(Math.min(1, got / total)); }
  const bytes = new Uint8Array(got); let o = 0; for (const p of parts) { bytes.set(p, o); o += p.length; }
  await cache?.put(MODEL_URL, new Response(bytes, {headers: {'Content-Type': 'application/octet-stream'}})).catch(() => {});
  return bytes;
}

// Has the model already been saved on this device (so preparing takes seconds)?
export async function modelSaved() { try { return !!(await (await caches.open('madar-models')).match(MODEL_URL)); } catch { return false; } }

// Loads ONNX Runtime and the model once per page.
export function prepareSeparator(onProgress) {
  session ??= (async () => {
    const ort = await import(/* webpackIgnore: true */ ORT_URL);
    ort.env.wasm.wasmPaths = {wasm: ORT_WASM}; ort.env.wasm.numThreads = 1;
    const bytes = await modelBytes(onProgress);
    const s = await ort.InferenceSession.create(bytes, {executionProviders: ['webgpu'], graphOptimizationLevel: 'all'});
    return {ort, s};
  })().catch(e => { session = null; throw e; });
  return session;
}

// Separates the speech. onChunk(done, total, secondsPerChunk) after every piece. Throws
// Error('DEVICE_SLOW') when the device turns out slower than real time, so the caller can move on.
export async function separateOnDevice(left, right, {signal, onChunk} = {}) {
  const {ort, s} = await prepareSeparator();
  const run = async spec => {
    const out = await s.run({input: new ort.Tensor('float32', spec, [1, 4, DIM_F, DIM_T])});
    const t = out.output; return t.data instanceof Float32Array ? t.data : await t.getData();
  };
  const began = performance.now(); let warm = 0;
  return separateVocals(left, right, run, {signal, onChunk(done, total) {
    const at = performance.now();
    if (done === 1) warm = at;              // the first piece includes shader warm-up
    const per = done === 1 ? (at - began) / 1000 : (at - warm) / 1000 / (done - 1);
    // Slower than real time after the warm-up: the quick engine will beat this device.
    if (done >= 3 && done < total && per > CHUNK_SECONDS * 0.9) throw Error('DEVICE_SLOW');
    onChunk?.(done, total, per);
  }});
}

// Frees the model and the graphics memory it holds, so a phone that moves on to the quick
// engine (or Colab) starts with room to spare. The next on-device run loads it again from the
// saved copy in a few seconds.
export async function releaseSeparator() {
  const pending = session; session = null;
  if (!pending) return;
  try { const {s} = await pending; await s.release?.(); } catch {}
}

// A phone browser may close the page outright when it runs short of memory (Safari does this
// without any message). A mark is kept while the device works; finding it on the next run means
// the page died, so that device goes straight to the quick engine from then on.
const RUN_KEY = 'madar-device-running';
export function markRunning(info, store = globalThis.localStorage) { try { store?.setItem(RUN_KEY, JSON.stringify({...info, at: Date.now()})); } catch {} }
export function clearRunning(store = globalThis.localStorage) { try { store?.removeItem(RUN_KEY); } catch {} }
export function takeCrash(store = globalThis.localStorage, now = Date.now()) {
  try {
    const raw = store?.getItem(RUN_KEY); if (!raw) return null;
    store.removeItem(RUN_KEY);
    const info = JSON.parse(raw);
    return info && now - Number(info.at || 0) < 6 * 3600e3 ? info : null;
  } catch { return null; }
}
// Closing the page on purpose is not a crash.
try { globalThis.addEventListener?.('pagehide', () => clearRunning()); } catch {}
