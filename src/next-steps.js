// «وش تبي تسوي فيه؟» after any result: the tools that fit the result's kind (minus the one that
// made it), one-click recipes that run several tools in a row, and share/QR. The page decides
// nothing about what the media contains: suggestions follow the file type and the tool it came from.

export const RECIPES = [
  {id: 'clean-translate', label: 'بدون موسيقى + ترجمة عربية مكتوبة', note: 'إزالة الموسيقى ← تفريغ وترجمة ← كتابة الترجمة على الفيديو',
   kinds: ['video'], steps: [{tool: 'separate'}, {tool: 'cloudasr', opts: {fields: {operation: 'transcribeTranslateBurn', target: 'ar'}}}]},
  {id: 'clean-captions', label: 'بدون موسيقى + الكلام مكتوب', note: 'إزالة الموسيقى ← تفريغ ← كتابة الكلام على الفيديو',
   kinds: ['video'], steps: [{tool: 'separate'}, {tool: 'cloudasr', opts: {fields: {operation: 'transcribeBurn'}}}]},
];

export function kindOf(blob, name = '') {
  const type = blob?.type || '', ext = String(name).split('.').pop().toLowerCase();
  if (type.startsWith('video/') || /^(mp4|mov|mkv|webm|m4v)$/.test(ext)) return 'video';
  if (type.startsWith('audio/') || /^(mp3|m4a|wav|flac|ogg|aac|opus)$/.test(ext)) return 'audio';
  if (type.startsWith('image/') || /^(png|jpe?g|webp|gif|heic)$/.test(ext)) return 'image';
  if (ext === 'pdf') return 'pdf';
  if (/^(srt|vtt|txt)$/.test(ext)) return 'text';
  return 'other';
}

const SMALL = 80 * 1048576;
// [id, mark, label, open(file) → [toolId, opts]]
const ITEMS = {
  video: [
    ['separate', '🎵', 'إزالة الموسيقى'], ['dub', '🎙️', 'دبلجة بصوتك'], ['cloudasr', '📝', 'تفريغ وترجمة'],
    ['cloudresize', '📱', 'مقاس ريلز وتيك توك'], ['mp3', '🎧', 'استخراج الصوت MP3'], ['compress', '🗜️', 'تصغير الحجم'], ['qrmedia', '📲', 'إرسال لجوال ثاني'],
  ],
  audio: [['separate', '🎵', 'إزالة الموسيقى'], ['cloudasr', '📝', 'تفريغ وترجمة'], ['mp3', '🎧', 'تحويل إلى MP3'], ['qrmedia', '📲', 'إرسال لجوال ثاني']],
  image: [['cloudcutout', '✂️', 'إزالة الخلفية'], ['cloudocr', '🔤', 'استخراج النص'], ['imagepdf', '📄', 'تحويلها PDF'], ['qrimage', '📲', 'إرسال لجوال ثاني']],
  pdf: [['cloudword', '📝', 'تحويل إلى Word'], ['cloudocr', '🔤', 'استخراج النص'], ['qrdocument', '📲', 'إرسال لجوال ثاني']],
  text: [['cloudtranslate', '🌐', 'ترجمة النص'], ['subtitles', '✏️', 'تعديل الترجمة']],
};
// Tools that already did the job (no point suggesting them again).
const SAME = {separate: ['separate'], cloudasr: ['cloudasr'], dub: ['dub'], cloudresize: ['cloudresize'], cloudcutout: ['cloudcutout'],
  cloudocr: ['cloudocr'], cloudword: ['cloudword'], cloudtranslate: ['cloudtranslate'], convert: ['mp3', 'compress'], cloudconvert: ['mp3', 'compress']};

export function suggestions(kind, from = '', available = () => true) {
  const skip = new Set(SAME[from] || [from]);
  return (ITEMS[kind] || []).filter(([id]) => !skip.has(id) && available(target(id)));
}

function target(id) {
  return id === 'mp3' || id === 'compress' ? 'convert' : id;
}

export function openArgs(id, file) {
  const small = file.size <= SMALL;
  if (id === 'mp3') return [small ? 'convert' : 'cloudconvert', {convertMode: 'audio', format: 'mp3'}];
  if (id === 'compress') return [small ? 'convert' : 'cloudconvert', {convertMode: 'video', format: 'mp4'}];
  return [id, {}];
}

export function recipesFor(kind, from = '') {
  return RECIPES.filter(r => r.kinds.includes(kind) && from !== 'separate' && from !== 'cloudasr');
}

// The share sheet holds the file itself where the browser allows it (phones, some laptops).
export function canShareFile(file) {
  try { return !!navigator.canShare?.({files: [file]}); } catch { return false; }
}

export function mountNextSteps(box, {blob, name, from = '', onOpen, onRecipe, available}) {
  if (!onOpen || !blob) return null;
  const kind = kindOf(blob, name), file = new File([blob], name, {type: blob.type || 'application/octet-stream'});
  const items = suggestions(kind, from, available), recipes = onRecipe ? recipesFor(kind, from) : [];
  const share = canShareFile(file);
  if (!items.length && !recipes.length && !share) return null;
  const section = document.createElement('section'); section.className = 'chain-actions';
  if (share) {
    const row = document.createElement('div'); row.className = 'share-row';
    const button = document.createElement('button'); button.type = 'button'; button.className = 'button secondary'; button.textContent = 'مشاركة';
    button.onclick = () => navigator.share({files: [file]}).catch(() => {});
    row.append(button); section.append(row);
  }
  if (recipes.length) {
    const title = document.createElement('h4'); title.textContent = 'بضغطة وحدة'; section.append(title);
    for (const recipe of recipes) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'recipe-btn';
      const strong = document.createElement('b'); strong.textContent = recipe.label; const small = document.createElement('small'); small.textContent = recipe.note;
      b.append(strong, small); b.onclick = () => onRecipe(recipe, file); section.append(b);
    }
  }
  if (items.length) {
    const title = document.createElement('h4'); title.textContent = 'وش تبي تسوي فيه؟';
    const grid = document.createElement('div'); grid.className = 'chain-grid';
    for (const [id, mark, label] of items) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'chain-btn';
      const i = document.createElement('span'); i.setAttribute('aria-hidden', 'true'); i.textContent = mark; b.append(i, label);
      b.onclick = () => { const [tool, opts] = openArgs(id, file); onOpen(tool, [file], opts); };
      grid.append(b);
    }
    section.append(title, grid);
  }
  box.append(section);
  return {file, kind};
}
