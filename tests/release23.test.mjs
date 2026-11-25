import test from 'node:test';
import assert from 'node:assert/strict';
import {understand, qrPayload, kindOfFile, PROMPTS} from '../src/chat-intent.js';
import {createEta, announcedSeconds, remainingText, phaseLabel} from '../src/progress-eta.js';
import {orbitSlots, orbitRange} from '../src/orbit-tools.js';
import {readFileSync} from 'node:fs';

const f = (name, type, size = 1000) => ({name, type, size});
const video = f('clip.mp4', 'video/mp4'), audio = f('a.mp3', 'audio/mpeg'), image = f('p.png', 'image/png'), pdf = f('d.pdf', 'application/pdf');

test('assistant: QR for text and links is made right in the chat', () => {
  assert.deepEqual(understand('أنشئ كيو آر لـ https://example.com/x'), {type: 'qrText', text: 'https://example.com/x'});
  assert.equal(understand('سوي باركود: مرحبا بكم').text, 'مرحبا بكم');
  assert.equal(understand('أنشئ كيو آر').type, 'askText');
  assert.equal(qrPayload('qr'), '');
});

test('assistant: QR with a file asks direct or Drive and picks the right tool', () => {
  const plan = understand('أنشئ QR', [image]);
  assert.equal(plan.type, 'ask');
  assert.deepEqual(plan.options.map(o => [o.plan.tool, o.plan.opts.qrMode]), [['qrimage', 'direct'], ['qrimage', 'drive']]);
  assert.equal(understand('كيو ار', [video]).options[0].plan.tool, 'qrmedia');
  assert.equal(understand('كيو ار', [pdf]).options[0].plan.tool, 'qrdocument');
});

test('assistant: music removal asks video or audio for a video, runs straight for audio, needs a file otherwise', () => {
  const v = understand('شيل الموسيقى', [video]);
  assert.equal(v.type, 'ask');
  assert.deepEqual(v.options.map(o => o.plan.opts.mode), ['video', 'audio']);
  assert.deepEqual(understand('ازل الموسيقى', [audio]), {type: 'run', tool: 'separate', opts: {mode: 'audio'}, title: 'إزالة الموسيقى'});
  const need = understand('شيل الموسيقى', [image]);
  assert.equal(need.type, 'need');
  assert.deepEqual(need.kinds, ['video', 'audio']);
});

test('assistant: links download; translation, compression, mp3 and the rest map to tools', () => {
  assert.deepEqual(understand('نزل https://youtu.be/dQw4w9WgXcQ'), {type: 'run', tool: 'download', opts: {link: 'https://youtu.be/dQw4w9WgXcQ'}, title: 'تحميل المقطع'});
  assert.equal(understand('https://youtu.be/dQw4w9WgXcQ').tool, 'download');
  const tr = understand('ترجم المقطع للعربي', [video]);
  assert.deepEqual(tr.options.map(o => o.plan.opts.fields.operation), ['transcribeTranslateBurn', 'transcribeTranslate']);
  assert.equal(understand('ترجم', [audio]).opts.fields.operation, 'transcribeTranslate');
  assert.equal(understand('صغر الفيديو', [video]).tool, 'convert');
  assert.equal(understand('صغر الفيديو', [f('big.mp4', 'video/mp4', 200 * 1048576)]).tool, 'cloudconvert');
  assert.equal(understand('استخرج الصوت mp3', [video]).opts.convertMode, 'audio');
  assert.equal(understand('شيل الخلفية', [image]).tool, 'cloudcutout');
  assert.equal(understand('حول الصورة png', [image]).opts.format, 'png');
  assert.equal(understand('ادمج ملفات pdf', [pdf, pdf]).opts.mode, 'merge');
  assert.equal(understand('ادمج ملفات pdf', [pdf]).type, 'need');
  assert.equal(understand('حولها pdf', [image, image]).tool, 'imagepdf');
  assert.equal(understand('استخرج النص', [pdf]).tool, 'pdfread');
  assert.equal(understand('استخرج النص', [image]).tool, 'cloudocr');
  assert.equal(understand('خله مقاس ريلز', [video]).opts.fields.ratio, 'portrait');
  assert.equal(understand('حوله word', [pdf]).tool, 'cloudword');
  assert.equal(understand('', [video]).type, 'suggest');
  assert.equal(understand('كلام عشوائي').type, 'unknown');
  assert.ok(PROMPTS.length >= 10);
  assert.equal(kindOfFile(f('x.srt', '')), 'text');
});

test('progress: one sentence, a countdown that only goes down, learning from past runs', () => {
  let now = 0; const store = new Map(); const s = {getItem: k => store.get(k) || null, setItem: (k, v) => store.set(k, v)};
  const steps = ['تجهيز الجلسة', 'الرفع', 'تجهيز الأداة', 'المعالجة', 'التنزيل'];
  const eta = createEta({tool: 'separate', steps, mediaSeconds: 120, bytes: 10 * 1048576, store: s, now: () => now});
  let v = eta.view(); assert.equal(v.label, 'جاري التجهيز…'); const first = v.remaining; assert.ok(first > 60 && first < 200, String(first));
  now = 5000; v = eta.view(); assert.ok(v.remaining <= first - 4.5);
  eta.enter('المعالجة'); eta.hint('فصل على GPU · المتبقي تقريبًا 30 ثانية'); now = 6000; v = eta.view();
  assert.equal(v.label, 'جاري إزالة الموسيقى…'); assert.ok(v.remaining < 45, String(v.remaining));
  now = 60000; v = eta.view(); assert.equal(v.text.includes('لحظات') || v.remaining < 20, true);
  eta.enter('التنزيل'); assert.equal(eta.view().label, 'جاري تجهيز النتيجة…'); eta.finish(); assert.equal(eta.view().percent, 100);
  assert.ok(JSON.parse(store.get('madar-eta')).separate['تجهيز الجلسة'] > 0, 'remembers how long a step took');
  assert.equal(announcedSeconds('رفع الملف · 40٪ · 2 MB/s · باقي 1:05 دقيقة'), 65);
  assert.equal(announcedSeconds('شيء آخر'), null);
  assert.equal(remainingText(2), 'لحظات ويخلص…'); assert.equal(remainingText(45), 'متبقي 45 ثانية'); assert.equal(remainingText(90), 'متبقي دقيقة ونص');
  assert.equal(phaseLabel('download', 'المعالجة'), 'جاري تحميل المقطع…');
});

test('wheel: six seats, never-ending through all tools in both directions, crossfade at one spot', () => {
  const STEP = Math.PI / 3;
  assert.equal(orbitSlots(4, 0).length, 4);
  let slots = orbitSlots(24, 0);
  assert.equal(slots.length, 7); assert.deepEqual(slots.filter(s => s.weight === 1).map(s => s.index), [0, 1, 2, 3, 4, 5]);
  slots = orbitSlots(24, -STEP * 0.5);
  assert.deepEqual(slots.map(s => +s.weight.toFixed(2)), [0.5, 1, 1, 1, 1, 1, 0.5]);
  assert.equal(slots[6].index, 6);
  assert.equal(orbitRange(24, -STEP * 6), '7–12 من 24');
  assert.equal(orbitRange(24, STEP), '24–5 من 24');
  const seen = new Set(); for (let k = 0; k < 24; k++) for (const s of orbitSlots(24, -STEP * k)) seen.add(s.index);
  assert.equal(seen.size, 24);
});

test('cloud tools hide the support panel and GPU choice; terms page and verification tag ship', () => {
  const css = readFileSync('src/app.css', 'utf8');
  assert.match(css, /#colabSupport,#colabDiagnostic,label:has\(>#colabGPU\)/);
  assert.match(readFileSync('src/index.html', 'utf8'), /google-site-verification" content="BGsCrNmhr9G_wK9kgIR47qIEW4qSoP4NwT2pF-hoVm8"/);
  assert.match(readFileSync('src/terms.html', 'utf8'), /شروط الاستخدام/);
  assert.match(readFileSync('netlify.toml', 'utf8'), /from = "\/terms"/);
});

test('search: public pages are indexable, technical files are not, sitemap/robots/structured data ship', async () => {
  const {netlifyStaticHeaders, NOINDEX} = await import('../src/netlify-static.js');
  const headers = netlifyStaticHeaders({'X-Content-Type-Options': 'nosniff'});
  const global = headers.split('\n/')[0];
  assert.doesNotMatch(global, /noindex/);
  assert.ok(NOINDEX.includes('/oauth-return.html'));
  assert.match(headers, /\/oauth-return\.html\n  X-Robots-Tag: noindex, nofollow/);
  const html = readFileSync('src/index.html', 'utf8');
  assert.match(html, /<link rel="canonical" href="https:\/\/madarfiles\.com\/">/);
  assert.match(html, /property="og:image" content="https:\/\/madarfiles\.com\/og-image\.jpg"/);
  const ld = JSON.parse(html.match(/<script type="application\/ld\+json">([^<]+)<\/script>/)[1]);
  assert.equal(ld['@graph'][1]['@type'], 'WebApplication');
  assert.match(readFileSync('src/robots.txt', 'utf8'), /Sitemap: https:\/\/madarfiles\.com\/sitemap\.xml/);
  assert.match(readFileSync('src/sitemap.xml', 'utf8'), /<loc>https:\/\/madarfiles\.com\/terms<\/loc>/);
});
