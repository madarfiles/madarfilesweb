// Turns what the visitor typed (plus the kinds of files attached) into a job the assistant runs
// inside the chat. Pure functions so they can be tested without a browser.

const norm = t => String(t || '').toLowerCase().replace(/[أإآ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي').replace(/[ًٌٍَُِّْـ]/g, '');
export const LINK = /https?:\/\/[^\s<>"']+/i;
const SMALL = 80 * 1048576;

export function kindOfFile(file) {
  const ext = String(file?.name || '').split('.').pop().toLowerCase(), type = String(file?.type || '');
  if (type.startsWith('video/') || /^(mp4|mov|mkv|webm|m4v|avi|3gp)$/.test(ext)) return 'video';
  if (type.startsWith('audio/') || /^(mp3|m4a|wav|flac|ogg|aac|opus|amr)$/.test(ext)) return 'audio';
  if (type.startsWith('image/') || /^(png|jpe?g|webp|gif|heic|heif)$/.test(ext)) return 'image';
  if (type === 'application/pdf' || ext === 'pdf') return 'pdf';
  if (/^(srt|vtt|txt)$/.test(ext)) return 'text';
  return 'other';
}

// What the QR text should be, from "أنشئ كيو آر لـ https://…" or "سوي باركود: مرحبا".
export function qrPayload(text) {
  const link = String(text).match(LINK);
  if (link) return link[0];
  const rest = String(text)
    .replace(/(انشئ|أنشئ|سوي|سوّي|اعمل|ابي|أبي|ابغى|أبغى|ابغي|اصنع|حط|لي|ممكن|رمز|كود|كيو\s*[اأإآ]?ر|كيو[اأإآ]ر|qr|باركود)/gi, ' ')
    .replace(/^[\s:،,.\-–—]+|[\s:،,.\-–—]+$/g, '')
    .replace(/^(ل|لـ|ل\s|عن|في|فيه|حق|حقه|حقت)\s*/u, '')
    .trim();
  return rest.length >= 2 ? rest : '';
}

const ask = (question, options) => ({ type: 'ask', question, options });
const run = (tool, opts = {}, title = '') => ({ type: 'run', tool, opts, title });
const need = (kinds, label, then) => ({ type: 'need', kinds, label, then });

// Returns one of:
//  {type:'run', tool, opts, title}        run now in the chat
//  {type:'ask', question, options:[{label, plan}]}   one question with buttons first
//  {type:'need', kinds, label, then}       a file is missing; `then` re-plans once it is attached
//  {type:'qrText', text}                   a QR for text or a link, made right in the chat
//  {type:'askText', question, then}        needs a line of text from the visitor
//  {type:'open', tool}                     hand-made adjustments: open the tool window
//  {type:'unknown'}
export function understand(text, files = [], size = 0) {
  const t = norm(text), kinds = files.map(kindOfFile), first = kinds[0] || '', big = (size || files[0]?.size || 0) > SMALL;
  const has = k => kinds.includes(k);
  const link = String(text).match(LINK)?.[0] || '';
  const media = has('video') || has('audio');

  if (/كيو|qr|باركود|كيوار/.test(t)) {
    if (files.length && first !== 'text' && first !== 'other') {
      const tool = first === 'image' ? 'qrimage' : first === 'pdf' ? 'qrdocument' : 'qrmedia';
      return ask('تبي الرمز يرسل الملف مباشرة لجوال ثاني، ولا رابط دائم في Drive؟', [
        { label: '📲 مباشر · بدون حساب', plan: run(tool, { qrMode: 'direct' }, 'رمز إرسال مباشر') },
        { label: '🔗 رابط دائم عبر Drive', plan: run(tool, { qrMode: 'drive' }, 'رمز برابط Drive دائم') },
      ]);
    }
    const payload = qrPayload(text);
    if (payload) return { type: 'qrText', text: payload };
    return { type: 'askText', question: 'وش النص أو الرابط اللي تبيه في الرمز؟', then: 'qrText' };
  }

  if (link && (/حمل|نزل|تحميل|تنزيل|download|احفظ|جيب/.test(t) || norm(text.replace(link, '')).trim().length < 3))
    return run('download', { link }, 'تحميل المقطع');

  if (/موسيق|اغاني|اغنيه|المعازف|فصل الصوت|افصل/.test(t)) {
    if (!media) return need(['video', 'audio'], 'أرفق الفيديو أو الصوت اللي تبي تشيل منه الموسيقى', text);
    if (has('video') && !/صوت فقط|الصوت بس|صوت بس/.test(t))
      return ask('تبي النتيجة فيديو بدون موسيقى، ولا الصوت بس؟', [
        { label: '🎬 فيديو بدون موسيقى', plan: run('separate', { mode: 'video' }, 'إزالة الموسيقى') },
        { label: '🎧 الصوت بس', plan: run('separate', { mode: 'audio' }, 'إزالة الموسيقى') },
      ]);
    return run('separate', { mode: 'audio' }, 'إزالة الموسيقى');
  }

  if (/ترجم/.test(t) && has('text')) return run('cloudtranslate', { fields: { target: 'ar' } }, 'ترجمة النص');
  if (/ترجم|ترجمه/.test(t)) {
    if (!media) return need(['video', 'audio'], 'أرفق الفيديو أو الصوت اللي تبي تترجمه', text);
    const options = [];
    if (has('video')) options.push({ label: '🎬 ترجمة عربية مكتوبة على الفيديو', plan: run('cloudasr', { fields: { operation: 'transcribeTranslateBurn', target: 'ar' } }, 'ترجمة المقطع') });
    options.push({ label: '📄 ملف ترجمة عربي (SRT)', plan: run('cloudasr', { fields: { operation: 'transcribeTranslate', target: 'ar' } }, 'ترجمة المقطع') });
    return options.length > 1 ? ask('كيف تبي الترجمة؟', options) : options[0].plan;
  }
  if (/تفريغ|فرغ|اكتب الكلام|كلام المقطع|نص المقطع|تفريغ الصوت/.test(t)) {
    if (!media) return need(['video', 'audio'], 'أرفق المقطع اللي تبي تفرغ كلامه', text);
    if (has('video')) return ask('تبي الكلام ملف نص، ولا مكتوب على الفيديو؟', [
      { label: '📄 ملف نص وSRT', plan: run('cloudasr', { fields: { operation: 'transcribe' } }, 'تفريغ الكلام') },
      { label: '🎬 مكتوب على الفيديو', plan: run('cloudasr', { fields: { operation: 'transcribeBurn' } }, 'تفريغ الكلام') },
    ]);
    return run('cloudasr', { fields: { operation: 'transcribe' } }, 'تفريغ الكلام');
  }

  if (/mp3|استخرج الصوت|طلع الصوت|الصوت فقط|صوت فقط|حوله صوت|حوله لصوت/.test(t)) {
    if (!media) return need(['video', 'audio'], 'أرفق الفيديو اللي تبي صوته', text);
    return big ? run('cloudconvert', { fields: { format: 'mp3' } }, 'استخراج الصوت') : run('convert', { convertMode: 'audio', set: { '#convertFormat': 'mp3' } }, 'استخراج الصوت');
  }
  if (/صغر|ضغط|اضغط|قلل حجم|قلل الحجم|حجمه|تصغير|خفف/.test(t) && !has('image') && !has('pdf')) {
    if (!media) return need(['video', 'audio'], 'أرفق الفيديو اللي تبي تصغّره', text);
    return big ? run('cloudconvert', { fields: { format: 'mp4', quality: 'small' } }, 'تصغير الفيديو') : run('convert', { convertMode: 'video', set: { '#convertQuality': '32' } }, 'تصغير الفيديو');
  }
  if (/مقاس|ريلز|تيك ?توك|طولي|9:16|عرضي|مربع/.test(t) && !has('image')) {
    if (!has('video')) return need(['video'], 'أرفق الفيديو اللي تبي تغيّر مقاسه', text);
    const ratio = /عرضي|16:9/.test(t) ? 'landscape' : /مربع/.test(t) ? 'square' : 'portrait';
    return run('cloudresize', { fields: { ratio } }, 'تغيير المقاس');
  }

  if (/خلفيه|الخلفيه|بدون خلفيه|شيل الخلفيه/.test(t)) {
    if (!has('image')) return need(['image'], 'أرفق الصورة اللي تبي تشيل خلفيتها', text);
    return run('cloudcutout', {}, 'إزالة الخلفية');
  }
  if (/word|وورد/.test(t)) {
    if (!has('pdf')) return need(['pdf'], 'أرفق ملف PDF', text);
    return run('cloudword', {}, 'تحويل إلى Word');
  }
  if (/استخرج النص|النص من|نص الصوره|اقرا النص|ocr|نسخ النص/.test(t)) {
    if (has('pdf')) return run('pdfread', { set: { '#readMode': 'text' } }, 'استخراج النص');
    if (!has('image')) return need(['image', 'pdf'], 'أرفق الصورة أو ملف PDF', text);
    return run('cloudocr', {}, 'استخراج النص');
  }
  if (/pdf|بي دي اف|بدف/.test(t)) {
    if (has('image') && !has('pdf')) return run('imagepdf', {}, 'تحويل الصور إلى PDF');
    if (/صور|صوره/.test(t) && has('pdf')) return run('pdfread', { set: { '#readMode': 'images' } }, 'صفحات PDF كصور');
    if (/دمج|ادمج|اجمع|جمع/.test(t)) {
      if (kinds.filter(k => k === 'pdf').length < 2) return need(['pdf'], 'أرفق ملفين PDF أو أكثر بالترتيب اللي تبيه', text);
      return run('pdf', { mode: 'merge' }, 'دمج ملفات PDF');
    }
    if (!files.length) return need(['image', 'pdf'], 'أرفق الصور أو ملفات PDF', text);
    return { type: 'open', tool: has('pdf') ? 'pdf' : 'imagepdf' };
  }
  if (/png|jpg|jpeg|webp|حول الصوره|حول صوره|صيغه/.test(t) || (has('image') && /حول|غير/.test(t))) {
    if (!has('image')) return need(['image'], 'أرفق الصورة', text);
    const format = /png/.test(t) ? 'png' : /webp/.test(t) ? 'webp' : 'jpeg';
    return run('image', { format }, 'تحويل الصورة إلى ' + format.toUpperCase().replace('JPEG', 'JPG'));
  }
  if (/صمم|تصميم اسم|اسم/.test(t) && /اسم/.test(t)) return { type: 'open', tool: 'namedesign' };
  if (/دبلج|بصوتي/.test(t)) return { type: 'open', tool: 'dub' };
  if (/عدل الصوت|قص الصوت|تعديل الصوت/.test(t)) return { type: 'open', tool: 'audio' };
  if (/عدل الصوره|قص الصوره|تعديل الصوره|استوديو/.test(t)) return { type: 'open', tool: 'image' };
  if (/srt|محرر الترجمه|عدل الترجمه/.test(t)) return { type: 'open', tool: 'subtitles' };

  // A file with no clear instruction: offer what fits that kind.
  if (files.length && t.length < 3) return { type: 'suggest', kind: first };
  return { type: 'unknown' };
}

// Ideas shown as buttons above the box so people discover what the assistant can do.
export const PROMPTS = [
  ['🎵', 'شيل الموسيقى', 'شيل الموسيقى'],
  ['🌐', 'ترجم مقطع للعربي', 'ترجم المقطع للعربي'],
  ['⬇️', 'نزّل من رابط', 'نزّل المقطع من الرابط: '],
  ['📝', 'فرّغ الكلام', 'فرّغ كلام المقطع'],
  ['🗜️', 'صغّر فيديو', 'صغّر حجم الفيديو'],
  ['🎧', 'استخرج الصوت', 'استخرج الصوت MP3'],
  ['✂️', 'شيل خلفية صورة', 'شيل خلفية الصورة'],
  ['📱', 'مقاس ريلز', 'خلّه مقاس ريلز طولي'],
  ['🖼️', 'حوّل صورة PNG', 'حوّل الصورة إلى PNG'],
  ['📄', 'ادمج PDF', 'ادمج ملفات PDF'],
  ['🔤', 'استخرج نص', 'استخرج النص'],
  ['📲', 'أنشئ QR', 'أنشئ كيو آر'],
];
