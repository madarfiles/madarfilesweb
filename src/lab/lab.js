// Lab page: separates speech from music on this device and reports how fast it was.
import {separateVocals, RATE, DIM_F, DIM_T} from './mdx.js';
import {report, watchErrors} from '../error-report.js';

const ORT_DIR = '/lab/ort/1.31.1/', MODELS = {f16: '/lab/models/mdx-voc-ft-fp16-v1.onnx', f32: '/lab/models/mdx-voc-ft-fp32-v1.onnx'};
const $ = s => document.querySelector(s);
const status = t => { $('#labStatus').textContent = t; };
const bar = f => { $('#labBar i').style.width = Math.round(f * 100) + '%'; };
const row = (k, v) => { const d = document.createElement('div'); d.className = 'lab-row'; const a = document.createElement('span'); a.textContent = k; const b = document.createElement('b'); b.textContent = v; d.append(a, b); return d; };
const secs = ms => (ms / 1000).toFixed(1) + ' ث';
watchErrors();

const device = {ua: navigator.userAgent, cores: navigator.hardwareConcurrency || 0, memory: navigator.deviceMemory || 0, webgpu: !!navigator.gpu, f16: false, gpu: ''};
let adapter = null;

async function inspect() {
  try {
    adapter = navigator.gpu ? await navigator.gpu.requestAdapter({powerPreference: 'high-performance'}) : null;
    if (adapter) {
      device.f16 = adapter.features.has('shader-f16');
      const info = adapter.info || (adapter.requestAdapterInfo ? await adapter.requestAdapterInfo() : {});
      device.gpu = [info.vendor, info.architecture, info.device, info.description].filter(Boolean).join(' · ');
    }
  } catch (e) { device.gpuError = String(e?.message || e); }
  const box = $('#labDevice');
  box.replaceChildren(
    row('كرت الشاشة في المتصفح (WebGPU)', adapter ? 'متوفر ✅' : 'غير متوفر ❌'),
    row('دقة نصفية (أسرع وأخف)', device.f16 ? 'مدعومة ✅' : 'غير مدعومة (نستخدم النسخة الكاملة)'),
    row('الكرت', device.gpu || '—'),
    row('أنوية المعالج', String(device.cores || '—')),
    row('الذاكرة', device.memory ? device.memory + ' GB' : '—'));
  if (!adapter) status('متصفحك ما يدعم WebGPU؛ جرّب Chrome محدّث. (هذا نفسه معلومة مفيدة لنا)');
  report('lab', {tool: 'device', message: (adapter ? 'webgpu' : 'no-webgpu') + (device.f16 ? '+f16' : ''), stage: device.gpu.slice(0, 120), log: JSON.stringify(device)});
}

// Decodes any audio/video file to 44.1 kHz stereo.
async function decode(file, limitSeconds) {
  const data = await file.arrayBuffer();
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const decoded = await ctx.decodeAudioData(data); ctx.close?.();
  const seconds = Math.min(decoded.duration, limitSeconds || Infinity);
  const off = new OfflineAudioContext(2, Math.ceil(seconds * RATE), RATE);
  const src = off.createBufferSource(); src.buffer = decoded; src.connect(off.destination); src.start();
  const out = await off.startRendering();
  const right = decoded.numberOfChannels > 1 ? out.getChannelData(1) : out.getChannelData(0);
  return {left: out.getChannelData(0), right, seconds};
}

async function cachedModel(MODEL_URL, onProgress) {
  const cache = await caches.open('madar-models').catch(() => null);
  const hit = await cache?.match(MODEL_URL);
  if (hit) return {bytes: new Uint8Array(await hit.arrayBuffer()), cached: true};
  const res = await fetch(MODEL_URL);
  if (!res.ok) throw Error('تعذر تحميل النموذج (' + res.status + ')');
  const total = Number(res.headers.get('Content-Length')) || (MODEL_URL.includes('fp16') ? 33.4e6 : 66.8e6), reader = res.body.getReader(), parts = []; let got = 0;
  for (;;) { const {done, value} = await reader.read(); if (done) break; parts.push(value); got += value.length; onProgress(got / total); }
  const bytes = new Uint8Array(got); let o = 0; for (const p of parts) { bytes.set(p, o); o += p.length; }
  await cache?.put(MODEL_URL, new Response(bytes, {headers: {'Content-Type': 'application/octet-stream'}})).catch(() => {});
  return {bytes, cached: false};
}

function wav(left, right) {
  const n = left.length, buf = new ArrayBuffer(44 + n * 4), v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); v.setUint32(4, 36 + n * 4, true); w(8, 'WAVE'); w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 2, true);
  v.setUint32(24, RATE, true); v.setUint32(28, RATE * 4, true); v.setUint16(32, 4, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, n * 4, true);
  for (let i = 0, o = 44; i < n; i++, o += 4) { v.setInt16(o, Math.max(-1, Math.min(1, left[i])) * 32767, true); v.setInt16(o + 2, Math.max(-1, Math.min(1, right[i])) * 32767, true); }
  return new Blob([buf], {type: 'audio/wav'});
}

async function run() {
  const file = $('#labFile').files[0]; if (!file) return;
  $('#labRun').disabled = true; $('#labResult').hidden = true; bar(0);
  const t = {start: performance.now()}, result = {file: file.type || file.name.split('.').pop(), mb: +(file.size / 1048576).toFixed(1)};
  try {
    status('نجهّز الصوت…');
    const audio = await decode(file, $('#labShort').checked ? 60 : 0);
    t.decoded = performance.now(); result.seconds = +audio.seconds.toFixed(1);

    status('نحمّل محرك التشغيل…');
    const ort = await import(ORT_DIR + 'ort-webgpu.js');
    ort.env.wasm.wasmPaths = {wasm: ORT_DIR + 'ort-wasm-simd-threaded.asyncify.wasm'}; ort.env.wasm.numThreads = 1;
    const modelUrl = device.f16 && new URLSearchParams(location.search).get('ep') !== 'wasm' ? MODELS.f16 : MODELS.f32; result.precision = device.f16 ? 'f16' : 'f32';
    status('نحمّل النموذج (مرة وحدة بس، ' + (device.f16 ? 33 : 67) + ' MB)…');
    const model = await cachedModel(modelUrl, f => { bar(f * 0.3); status('نحمّل النموذج · ' + Math.round(f * 100) + '٪'); });
    t.model = performance.now(); result.modelCached = model.cached;

    status('نجهّز كرت الشاشة…');
    // ?ep=wasm runs on the processor instead (slow; for checking results only).
    const ep = new URLSearchParams(location.search).get('ep') === 'wasm' ? 'wasm' : 'webgpu'; result.ep = ep;
    if (ep === 'webgpu' && !adapter) throw Error('المتصفح ما يدعم WebGPU');
    const session = await ort.InferenceSession.create(model.bytes, {executionProviders: [ep], graphOptimizationLevel: 'all'});
    t.session = performance.now();

    const runOnce = async spec => { const out = await session.run({input: new ort.Tensor('float32', spec, [1, 4, DIM_F, DIM_T])}); return out.output.data instanceof Float32Array ? out.output.data : await out.output.getData(); };
    status('جاري إزالة الموسيقى…');
    const voc = await separateVocals(audio.left, audio.right, runOnce, {onProgress: (f, tm) => { bar(0.3 + f * 0.7); status('جاري إزالة الموسيقى · ' + Math.round(f * 100) + '٪'); }});
    t.done = performance.now();

    if (result.ep === 'wasm') window.madarLabLast = voc; // checking mode only
    const blob = wav(voc.left, voc.right), url = URL.createObjectURL(blob);
    $('#labAudio').src = url; $('#labSave').href = url;
    Object.assign(result, {chunks: voc.chunks, decode: Math.round(t.decoded - t.start), load: Math.round(t.model - t.decoded), init: Math.round(t.session - t.model),
      separate: Math.round(t.done - t.session), spectrum: Math.round(voc.timing.spectrum), modelRun: Math.round(voc.timing.model), wave: Math.round(voc.timing.wave)});
    result.speed = +(result.seconds / (result.separate / 1000)).toFixed(2);
    $('#labTimes').replaceChildren(
      row('طول المقطع', result.seconds + ' ث'),
      row('وقت الفصل نفسه', secs(result.separate)),
      row('السرعة', result.speed + '× (أسرع من طول المقطع إذا فوق 1)'),
      row('تحميل النموذج', model.cached ? 'محفوظ من قبل' : secs(result.load)),
      row('تجهيز الكرت', secs(result.init)),
      row('الكرت / الحسابات في المعالج', secs(result.modelRun) + ' / ' + secs(result.spectrum + result.wave)));
    $('#labResult').hidden = false; status('تم ✅ أرسلنا الأوقات لمدار.');
    report('lab', {tool: 'result', message: 'ok ' + result.seconds + 's in ' + (result.separate / 1000).toFixed(1) + 's', stage: device.gpu.slice(0, 120), log: JSON.stringify({...result, device})});
  } catch (e) {
    status('ما زبطت: ' + (e?.message || e));
    report('lab', {tool: 'fail', message: String(e?.message || e).slice(0, 280), stage: device.gpu.slice(0, 120), log: JSON.stringify({...result, device, stack: String(e?.stack || '').slice(0, 1500)})});
  } finally { $('#labRun').disabled = false; }
}

$('#labFile').addEventListener('change', () => { $('#labRun').disabled = !$('#labFile').files.length; });
$('#labRun').addEventListener('click', run);
inspect();
