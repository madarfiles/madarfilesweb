// What a visitor sees while a cloud tool works: one short sentence, one bar and a time that
// counts down. Steps, sizes and engine names stay out of sight (they go to the error report).
// Estimates start from sensible defaults and learn from this device's own past runs.

const PREP = new Set(['تجهيز الصوت في جهازك', 'تجهيز الجلسة', 'الرفع', 'تجهيز الأداة']);
const FINISH = new Set(['التنزيل', 'تركيب الفيديو في جهازك']);

const VERB = {
  separate: 'جاري إزالة الموسيقى…', 'separate-fast': 'جاري إزالة الموسيقى…', download: 'جاري تحميل المقطع…', dub: 'جاري تجهيز الدبلجة…',
  asr: 'جاري تفريغ الكلام…', translate: 'جاري الترجمة…', burn: 'جاري كتابة الترجمة على الفيديو…',
  convert: 'جاري التحويل…', resize: 'جاري تغيير المقاس…', cutout: 'جاري إزالة الخلفية…',
  ocr: 'جاري استخراج النص…', word: 'جاري التحويل إلى Word…', imagegen: 'جاري توليد الصورة…',
  videogen: 'جاري توليد المقطع…'
};
// Seconds of processing per second of media, before this device has measured its own.
const PER_MEDIA_SECOND = { separate: 0.22, 'separate-fast': 0.07, dub: 0.9, asr: 0.25, translate: 0.35, burn: 0.45, convert: 0.3, resize: 0.35, download: 0.05 };
const FIXED = { cutout: 25, ocr: 30, word: 40, imagegen: 60, videogen: 240, translate: 30 };

export function phaseLabel(tool, step) {
  if (PREP.has(step)) return 'جاري التجهيز…';
  if (FINISH.has(step)) return 'جاري تجهيز النتيجة…';
  return VERB[tool] || 'جاري المعالجة…';
}

// Remaining seconds that the engine or a transfer already announced, if the text has one.
export function announcedSeconds(text) {
  const s = String(text || '');
  let m = s.match(/(?:باقي|المتبقي تقريبًا|متبقي)\s*(\d+):(\d{2})/);
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  m = s.match(/(?:باقي|المتبقي تقريبًا|متبقي)\s*(\d+)\s*ثانية/);
  if (m) return Number(m[1]);
  return null;
}

export function remainingText(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s <= 3) return 'لحظات ويخلص…';
  if (s < 60) return 'متبقي ' + s + ' ثانية';
  const m = Math.floor(s / 60), r = s % 60;
  if (m === 1 && r < 15) return 'متبقي دقيقة';
  if (m === 1 && r >= 20 && r <= 45) return 'متبقي دقيقة ونص';
  if (m === 2 && r < 15) return 'متبقي دقيقتين';
  return 'متبقي ' + m + ':' + String(r).padStart(2, '0') + ' دقيقة';
}

function load(store) {
  try { return JSON.parse(store?.getItem('madar-eta') || '{}') || {}; } catch { return {}; }
}
function save(store, data) {
  try { store?.setItem('madar-eta', JSON.stringify(data)); } catch {}
}

export function createEta({ tool, steps, mediaSeconds = 0, bytes = 0, store = globalThis.localStorage, now = () => Date.now() }) {
  const learned = load(store);
  const mine = learned[tool] || {};
  let media = Number.isFinite(mediaSeconds) && mediaSeconds > 0 ? mediaSeconds : 0;
  const mb = Math.max(0, bytes) / 1048576;
  const guess = step => {
    const seen = mine[step];
    if (step === 'الرفع') return Math.max(2, mb / (seen || 1.5)) + 2;
    if (step === 'التنزيل') return Math.max(2, (mb * 0.8) / (seen || 3)) + 2;
    if (step === 'المعالجة') {
      if (media && (seen?.perSecond || PER_MEDIA_SECOND[tool])) return Math.max(10, media * (seen?.perSecond || PER_MEDIA_SECOND[tool]));
      return seen?.seconds || FIXED[tool] || 60;
    }
    if (step === 'تجهيز الصوت في جهازك' || step === 'تركيب الفيديو في جهازك') return (typeof seen === 'number' ? seen : 3 + media * 0.06);
    if (typeof seen === 'number') return seen;
    return step === 'تجهيز الجلسة' ? 25 : step === 'تجهيز الأداة' ? 45 : 15;
  };
  const began = now();
  let at = 0, stepAt = began, hint = null, shown = null, lastTick = began, finished = false;
  let estimates = steps.map(guess);
  const remember = (step, seconds) => {
    if (!(seconds > 0)) return;
    const blend = (old, value) => (old ? old * 0.5 + value * 0.5 : value);
    if (step === 'الرفع' && mb > 1) mine[step] = blend(mine[step], mb / seconds);
    else if (step === 'التنزيل' && mb > 1) mine[step] = blend(mine[step], (mb * 0.8) / seconds);
    else if (step === 'المعالجة') {
      const old = mine[step] || {};
      mine[step] = media ? { perSecond: blend(old.perSecond, seconds / media) } : { seconds: blend(old.seconds, seconds) };
    } else if (step !== 'الرفع' && step !== 'التنزيل') mine[step] = blend(typeof mine[step] === 'number' ? mine[step] : 0, seconds);
    learned[tool] = mine; save(store, learned);
  };
  return {
    enter(step) {
      const i = steps.indexOf(step);
      if (i < 0 || i <= at) return;
      remember(steps[at], (now() - stepAt) / 1000);
      at = i; stepAt = now(); hint = null;
    },
    setMedia(seconds) {
      if (!(seconds > 0) || media) return;
      media = seconds;
      estimates = steps.map((step, i) => (i < at ? estimates[i] : guess(step)));
    },
    hint(text) {
      const s = announcedSeconds(text);
      if (s !== null) hint = { seconds: s, at: now() };
    },
    finish() {
      if (finished) return;
      finished = true;
      remember(steps[at], (now() - stepAt) / 1000);
    },
    view() {
      const t = now();
      const inStep = (t - stepAt) / 1000;
      const current = hint ? Math.max(0, hint.seconds - (t - hint.at) / 1000) : Math.max(estimates[at] - inStep, Math.min(8, estimates[at] * 0.15));
      let target = current;
      for (let i = at + 1; i < steps.length; i++) target += estimates[i];
      const dt = (t - lastTick) / 1000; lastTick = t;
      if (shown === null) shown = target;
      else if (target < shown) shown = target;                       // good news shows at once
      else if (target > shown * 1.3 + 15) shown = target;            // a real re-estimate
      else shown = Math.max(1, shown - dt);                          // otherwise it keeps counting down
      const elapsed = (t - began) / 1000;
      const percent = finished ? 100 : Math.min(97, Math.max(2, (100 * elapsed) / (elapsed + shown)));
      return { label: phaseLabel(tool, steps[at]), remaining: shown, text: remainingText(shown), percent };
    }
  };
}
