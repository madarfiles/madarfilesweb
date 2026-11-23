// The assistant does the work itself, right in the conversation: it asks what is missing with
// buttons, runs the tool out of sight, shows one progress line, and hands the result back here
// with download, share and "what next". Tools that need hand adjustments still open as a window.
import QRCode from 'qrcode';
import {renderResultPreview} from './result-preview.js';
import {mountNextSteps, kindOf} from './next-steps.js';
import {understand, kindOfFile, PROMPTS, LINK} from './chat-intent.js';
import {safeQR} from './core.js';

const LOCAL_RUN = {image: '#imageExport', pdf: '#pdfExport', imagepdf: '#imagePdfExport', convert: '#convertRun', pdfread: '#readRun'};
const QR_TOOLS = ['qrimage', 'qrmedia', 'qrdocument'];
const isColab = id => id === 'separate' || id === 'download' || /^cloud/.test(id);
const PICK = [
  ['image', '🖼️', 'صورة', 'image/*'], ['video', '🎬', 'فيديو', 'video/*'], ['audio', '🎧', 'صوت', 'audio/*'],
  ['pdf', '📄', 'PDF', 'application/pdf,.pdf'], ['text', '📝', 'نص أو ترجمة', '.srt,.vtt,.txt,text/plain'],
];
const KIND_ICON = {image: '🖼️', video: '🎬', audio: '🎧', pdf: '📄', text: '📝', other: '📎'};
const sizeText = n => n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';

export function mountChat(ctx) {
  const $ = s => document.querySelector(s);
  const log = $('#chatLog'), input = $('#chatInput'), form = $('#chatForm'), chips = $('#chatFiles'), menu = $('#chatAttachMenu'), ideas = $('#chatSuggestions');
  let attachments = [], fromResult = false, waitingFiles = null, waitingText = null, job = null, recipe = null;

  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  // Keep the newest message in view without the whole page jumping.
  const settle = () => requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
  function say(role, text) { const m = el('div', 'chat-message ' + role, text); log.append(m); settle(); return m; }
  function buttons(msg, list) {
    const row = el('div', 'chat-choices');
    for (const [label, fn] of list) { const b = el('button', 'chat-choice', label); b.type = 'button'; b.onclick = () => { row.querySelectorAll('button').forEach(x => x.disabled = true); b.classList.add('chosen'); fn(); }; row.append(b); }
    msg.append(row); settle(); return row;
  }

  // ---------- attachments ----------
  function renderChips() {
    chips.replaceChildren();
    chips.hidden = !attachments.length;
    attachments.forEach((f, i) => {
      const chip = el('div', 'attach-chip' + (fromResult ? ' from-result' : ''));
      const mark = el('span', 'attach-kind', fromResult ? '↩' : KIND_ICON[kindOfFile(f)]);
      const name = el('b', '', f.name); name.title = f.name;
      const size = el('small', '', sizeText(f.size));
      const x = el('button', 'attach-x', '✕'); x.type = 'button'; x.setAttribute('aria-label', 'إزالة ' + f.name);
      x.onclick = () => { attachments.splice(i, 1); if (!attachments.length) fromResult = false; renderChips(); };
      const text = el('span', 'attach-text'); text.append(name, size);
      chip.append(mark, text, x); chips.append(chip);
    });
  }
  function attach(list, auto = false) {
    const files = [...list].filter(f => f && f.size);
    if (!files.length) return;
    if (files.length > 20) { ctx.toast('اختر حتى 20 ملفًا'); return; }
    attachments = auto ? files : (fromResult ? files : [...attachments, ...files]).slice(0, 20); fromResult = auto;
    renderChips();
    if (!auto && waitingFiles) { const wait = waitingFiles; waitingFiles = null; setTimeout(() => (typeof wait === 'string' ? handle(wait, true) : start(wait.plan, attachments.slice())), 150); }
  }
  // The paper clip opens a small sheet above the box: pick the kind, then the phone's own picker.
  const picker = el('input'); picker.id = 'chatPicker'; picker.type = 'file'; picker.multiple = true; picker.hidden = true; document.body.append(picker);
  picker.onchange = () => { attach(picker.files); picker.value = ''; };
  function openPicker(accept) { menu.hidden = true; picker.accept = accept; try { picker.showPicker ? picker.showPicker() : picker.click(); } catch { picker.click(); } }
  function buildMenu(only) {
    menu.replaceChildren();
    const title = el('p', 'attach-title', 'وش تبي ترفق؟'); menu.append(title);
    const grid = el('div', 'attach-grid');
    for (const [kind, mark, label, accept] of PICK) {
      if (only && !only.includes(kind)) continue;
      const b = el('button', 'attach-option'); b.type = 'button'; b.append(el('span', '', mark), el('b', '', label)); b.onclick = () => openPicker(accept); grid.append(b);
    }
    menu.append(grid);
  }
  $('#chatAttach').onclick = e => { e.stopPropagation(); if (!menu.hidden) { menu.hidden = true; return; } buildMenu(); menu.hidden = false; };
  document.addEventListener('pointerdown', e => { if (!menu.hidden && !menu.contains(e.target) && e.target !== $('#chatAttach') && !$('#chatAttach').contains(e.target)) menu.hidden = true; });

  // ---------- ideas ----------
  ideas.replaceChildren();
  for (const [mark, label, prompt] of PROMPTS) {
    const b = el('button', 'idea'); b.type = 'button'; b.append(el('span', '', mark), document.createTextNode(label));
    b.onclick = () => { if (prompt.endsWith(': ')) { input.value = prompt; input.focus(); grow(); return; } send(prompt); };
    ideas.append(b);
  }

  // ---------- typing ----------
  const grow = () => { input.style.height = 'auto'; input.style.height = Math.min(140, input.scrollHeight) + 'px'; };
  input.addEventListener('input', grow);
  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && matchMedia('(hover: hover)').matches) { e.preventDefault(); form.requestSubmit(); } });
  form.onsubmit = e => { e.preventDefault(); const text = input.value.trim(); if (!text && !attachments.length) return; input.value = ''; grow(); send(text); };
  function send(text) {
    menu.hidden = true;
    say('user', text || attachments.map(f => f.name).join('، '));
    if (attachments.length && text) { const m = log.lastElementChild; m.append(el('small', 'chat-attached', '📎 ' + attachments.map(f => f.name).join('، '))); }
    handle(text);
  }

  function welcome() {
    say('assistant', 'هلا 👋 أنا مساعد مدار.\nأرفق ملفك (📎) وقل وش تبي، وأنا أسويه لك هنا: أشيل الموسيقى، أترجم، أنزّل من رابط، أصغّر، أحوّل… أو اختر فكرة من تحت.');
  }

  // ---------- understanding ----------
  function handle(text, retry = false) {
    if (waitingText && text) { const want = waitingText; waitingText = null; if (want === 'qrText') return qrText(text); }
    if (job?.busy) {
      const m = say('assistant', 'خلّني أخلص الطلب الحالي أول، أو ألغيه.');
      buttons(m, [['إلغاء الطلب الحالي', () => cancel()]]); return;
    }
    const files = attachments.slice();
    const plan = understand(text, files);
    if (plan.type === 'qrText') return qrText(plan.text);
    if (plan.type === 'askText') { waitingText = plan.then; say('assistant', plan.question); input.focus(); return; }
    if (plan.type === 'need') {
      waitingFiles = text;
      const m = say('assistant', plan.label + ' 📎');
      buttons(m, [['📎 أرفق الحين', () => { buildMenu(plan.kinds); menu.hidden = false; }]]); return;
    }
    if (plan.type === 'ask') {
      const m = say('assistant', plan.question);
      buttons(m, plan.options.map(o => [o.label, () => start(o.plan, files)])); return;
    }
    if (plan.type === 'run') return start(plan, files);
    if (plan.type === 'open') { say('assistant', 'هذي تحتاج تعديل بيدك، فتحت لك الأداة.'); ctx.openTool(plan.tool, files, {fromChat: true}); consume(); return; }
    if (plan.type === 'suggest') return suggest(files);
    if (retry) return;
    const m = say('assistant', LINK.test(text) ? 'هذا رابط؟ إذا تبي تنزّله قل «نزّله».' : 'ما فهمت عليك تمامًا 🙏 جرّب مثلًا: «شيل الموسيقى»، «ترجم للعربي»، «صغّر الفيديو»، «أنشئ QR».');
    if (files.length) buttons(m, [['وش أقدر أسوي بالملف؟', () => suggest(files)]]);
  }
  function suggest(files) {
    const kind = kindOfFile(files[0]);
    const map = {
      video: [['🎵 شيل الموسيقى', 'شيل الموسيقى'], ['🌐 ترجمة عربية', 'ترجم للعربي'], ['🗜️ صغّره', 'صغّر الفيديو'], ['🎧 استخرج الصوت', 'استخرج الصوت'], ['📱 مقاس ريلز', 'مقاس ريلز'], ['📲 أرسله بـQR', 'أنشئ كيو آر']],
      audio: [['🎵 شيل الموسيقى', 'شيل الموسيقى'], ['📝 فرّغ الكلام', 'فرغ الكلام'], ['🌐 ترجمة', 'ترجم للعربي'], ['🎧 MP3', 'حوله mp3']],
      image: [['✂️ شيل الخلفية', 'شيل الخلفية'], ['🔤 استخرج النص', 'استخرج النص'], ['🖼️ حوّلها PNG', 'حول الصورة png'], ['📄 حوّلها PDF', 'حولها pdf'], ['📲 أرسلها بـQR', 'أنشئ كيو آر']],
      pdf: [['📝 إلى Word', 'حوله word'], ['🔤 استخرج النص', 'استخرج النص'], ['🖼️ الصفحات صور', 'pdf الى صور'], ['📄 ادمجها', 'ادمج pdf'], ['📲 أرسله بـQR', 'أنشئ كيو آر']],
      text: [['🌐 ترجمه للعربي', 'ترجم']],
    }[kind] || [];
    const m = say('assistant', map.length ? 'وش تبي أسوي فيه؟' : 'هذا النوع من الملفات ما أقدر أسوي فيه شي للحين.');
    if (map.length) buttons(m, map.map(([label, cmd]) => [label, () => { say('user', label.replace(/^\S+\s/, '')); handle(cmd); }]));
  }
  function consume() { attachments = []; fromResult = false; renderChips(); }

  // ---------- a QR for text or a link, made right here ----------
  async function qrText(text) {
    try {
      const value = safeQR(text);
      const canvas = document.createElement('canvas');
      await QRCode.toCanvas(canvas, value, {width: 768, margin: 4, errorCorrectionLevel: 'M', color: {dark: '#182c2aff', light: '#ffffffff'}});
      const blob = await new Promise(r => canvas.toBlob(r, 'image/png'));
      canvas.width = canvas.height = 0;
      job = {busy: false, tool: 'qr', card: null};
      ctx.addResult(blob, 'madar-qr.png', 'image', {toChat: true});
    } catch (e) { say('assistant', e.message || 'تعذر إنشاء الرمز'); }
  }

  // ---------- running a tool out of sight ----------
  function card(title) {
    const m = el('div', 'chat-message assistant job-card');
    const head = el('b', 'job-title', title);
    const label = el('span', 'job-label', 'جاري التجهيز…');
    const track = el('span', 'progress-track'); const fill = el('i'); track.append(fill);
    const sub = el('small', 'job-sub', '');
    const actions = el('div', 'job-actions');
    m.append(head, label, track, sub, actions); log.append(m); settle();
    return {m, head, label, fill, sub, actions, track};
  }
  function setProgress(c, label, percent, sub) {
    if (label) c.label.textContent = label;
    if (percent !== null && percent !== undefined) c.fill.style.width = Math.max(2, Math.min(100, percent)).toFixed(1) + '%';
    c.sub.textContent = sub || '';
  }
  function start(plan, files) {
    const tool = plan.tool;
    if (!ctx.toolExists(tool)) { say('assistant', 'هذي الأداة غير متاحة الحين.'); return; }
    const needsFile = tool !== 'download';
    if (needsFile && !files.length) { waitingFiles = {plan}; const m = say('assistant', 'أرفق الملف أول 📎'); buttons(m, [['📎 أرفق الحين', () => { buildMenu(); menu.hidden = false; }]]); return; }
    consume();
    const title = (plan.title || ctx.toolTitle(tool)) + (files[0] ? ' · ' + files[0].name : '');
    const c = card(title);
    job = {busy: true, tool, plan, files, card: c, started: Date.now(), timer: 0, moved: false, connectShown: false};
    const opts = {...(plan.opts || {}), background: true, fromChat: true};
    if (isColab(tool)) opts.autoRun = 'wait';
    try { ctx.openTool(tool, files, opts); } catch (e) { fail(e.message); return; }
    const cancelBtn = el('button', 'text-btn job-cancel', 'إلغاء'); cancelBtn.type = 'button'; cancelBtn.onclick = () => cancel(); c.actions.append(cancelBtn);
    if (LOCAL_RUN[tool]) runLocal(job); else if (QR_TOOLS.includes(tool)) runQR(job);
    job.timer = setInterval(() => watch(job), 400);
  }
  async function waitFor(fn, ms = 15000) { const end = Date.now() + ms; while (Date.now() < end) { const v = fn(); if (v) return v; await new Promise(r => setTimeout(r, 150)); } return null; }
  async function runLocal(j) {
    const body = ctx.body();
    const button = await waitFor(() => { const b = body.querySelector(LOCAL_RUN[j.tool]); return b && !b.disabled ? b : null; });
    if (job !== j) return;
    if (!button) { const err = body.querySelector('#toolError')?.textContent; fail(err || 'ما قدرت أجهز الملف لهذي الأداة.'); return; }
    for (const [sel, value] of Object.entries(j.plan.opts?.set || {})) { const n = body.querySelector(sel); if (n) { n.value = value; n.dispatchEvent(new Event('input', {bubbles: true})); n.dispatchEvent(new Event('change', {bubbles: true})); } }
    await new Promise(r => setTimeout(r, 120));
    if (job === j) button.click();
  }
  async function runQR(j) {
    const body = ctx.body();
    if (j.plan.opts?.qrMode === 'drive') {
      const tab = await waitFor(() => body.querySelector('[data-mode="drive"]'));
      tab?.click();
      const connect = await waitFor(() => body.querySelector('#driveConnect'));
      if (!connect || job !== j) return;
      const b = el('button', 'button job-connect', 'اتصل بـGoogle Drive'); b.type = 'button';
      b.onclick = () => { body.querySelector('#driveConnect')?.click(); };
      j.card.actions.prepend(b); j.card.connect = b; setProgress(j.card, 'نحتاج نتصل بحسابك في Google Drive', 4, 'الرمز يفتح رابط ملفك في Drive حقك.');
      const ok = await waitFor(() => /تم الاتصال/.test(body.querySelector('#driveStatus')?.textContent || ''), 180000);
      if (!ok || job !== j) return;
      b.remove(); j.card.connect = null; body.querySelector('#driveConsent').checked = true; body.querySelector('#driveRun')?.click();
      return;
    }
    const run = await waitFor(() => { const r = body.querySelector('#p2pRun'); return r && body.querySelector('#p2pFile')?.files?.length ? r : null; });
    if (run && job === j) run.click(); else if (job === j) fail('ما قدرت أجهز الإرسال.');
  }
  // Copies the hidden tool's own progress into the chat card, and notices failures.
  function watch(j) {
    if (job !== j || !j.busy) { clearInterval(j.timer); return; }
    const body = ctx.body(); if (!body) return;
    const c = j.card;
    if (isColab(j.tool)) {
      const inst = ctx.instance();
      const need = inst?.needsGoogle?.() && !inst?.isBusy?.();
      if (need && !j.connectShown && inst?.canConnect?.()) {
        j.connectShown = true;
        const b = el('button', 'button job-connect', 'اتصل بـGoogle (مرة وحدة)'); b.type = 'button';
        b.onclick = () => { ctx.instance()?.connect?.(); b.disabled = true; b.textContent = 'نفتح Google…'; setTimeout(() => { b.disabled = false; b.textContent = 'اتصل بـGoogle (مرة وحدة)'; }, 6000); };
        c.actions.prepend(b); c.connect = b;
      }
      if (!need && c.connect) { c.connect.remove(); c.connect = null; }
      const live = body.querySelector('#colabProgress.live-progress');
      if (live) setProgress(c, live.querySelector('b')?.textContent, parseFloat(live.querySelector('i')?.style.width) || 3, live.querySelector('small')?.textContent);
      else if (need) setProgress(c, 'نحتاج نتصل بحسابك في Google', 3, 'المعالجة تصير في حسابك أنت، ونرجع لك النتيجة هنا.');
      else setProgress(c, 'جاري التجهيز…', 3, '');
      const err = body.querySelector('#colabError')?.textContent?.trim();
      if (err && !inst?.isBusy?.()) fail(err);
      return;
    }
    if (QR_TOOLS.includes(j.tool)) {
      const status = (body.querySelector('#p2pStatus:not([hidden])') || body.querySelector('#driveStatus'))?.textContent?.trim();
      const pct = Number(status?.match(/(\d+)\s*٪/)?.[1]);
      if (status && !c.connect) setProgress(c, status, Number.isFinite(pct) && pct ? pct : j.moved ? 100 : 30, j.moved ? 'خلّ الصفحة مفتوحة لين يوصل الملف.' : '');
      const result = body.querySelector('#p2pResult');
      if (!j.moved && result?.querySelector('canvas')) {
        j.moved = true; const box = el('div', 'job-qr'); box.append(...result.childNodes); c.m.insertBefore(box, c.actions); c.track.hidden = true;
        c.label.textContent = 'امسح الرمز من الجوال الثاني 📲'; settle();
      }
      if (/اكتمل|وصل الملف|تم الإرسال/.test(status || '')) { c.label.textContent = 'وصل الملف ✓'; done(j); }
      return;
    }
    const process = body.querySelector('#toolProcess');
    if (process && !process.hidden) {
      const bar = body.querySelector('#processBar');
      setProgress(c, body.querySelector('#processText')?.textContent || 'جاري المعالجة…', bar ? bar.value : null, '');
    }
    const err = (body.querySelector('#toolError')?.textContent || body.querySelector('.extra-error')?.textContent || '').trim();
    if (err && (!process || process.hidden)) fail(err);
  }
  function done(j) { if (!j) return; j.busy = false; clearInterval(j.timer); j.card?.actions.querySelector('.job-cancel')?.remove(); }
  function fail(message) {
    const j = job; if (!j) { say('assistant', message); return; }
    done(j); const c = j.card;
    c.m.classList.add('failed'); c.label.textContent = 'ما زبطت 😕'; c.track.hidden = true; c.sub.textContent = message;
    c.actions.replaceChildren();
    const again = el('button', 'button secondary', 'جرّب مرة ثانية'); again.type = 'button'; again.onclick = () => { attachments = j.files.slice(); renderChips(); start(j.plan, j.files); };
    const open = el('button', 'text-btn', 'افتح الأداة'); open.type = 'button'; open.onclick = () => ctx.showTool();
    c.actions.append(again, open); recipe = null; settle();
  }
  function cancel() {
    const j = job; if (!j) return;
    const inst = ctx.instance();
    if (isColab(j.tool)) inst?.cancel?.(); else ctx.body()?.querySelector('#cancelProcess')?.click();
    done(j); job = null; recipe = null;
    if (!isColab(j.tool)) ctx.closeTool();
    if (j.card) { j.card.label.textContent = 'ألغيت الطلب.'; j.card.track.hidden = true; j.card.sub.textContent = ''; j.card.actions.replaceChildren(); }
  }

  // ---------- results come back here ----------
  function result(r) {
    const j = job;
    let c = j?.card;
    if (!c) { c = card(r.name); }
    done(j);
    c.m.classList.add('done'); c.track.hidden = true; c.label.textContent = 'جاهز ✓'; c.sub.textContent = '';
    c.actions.replaceChildren();
    const preview = el('div', 'job-preview'); c.m.insertBefore(preview, c.actions);
    renderResultPreview(preview, r).catch(() => {});
    if (j && QR_TOOLS.includes(j.tool)) { const a = ctx.body()?.querySelector('#driveQRResult a'); if (a) c.actions.append(a); }
    const file = new File([r.blob], r.name, {type: r.blob.type || 'application/octet-stream'});
    const next = el('div', 'job-next'); c.m.append(next);
    mountNextSteps(next, {blob: r.blob, name: r.name, from: j?.tool || '', onOpen: (tool, files, opts) => runFromChat(tool, files, opts), onRecipe: (rec, f) => runRecipe(rec, f), available: ctx.toolExists});
    // The result is ready for the next request ("ترجمه الحين").
    if (r.type !== 'subtitle' && kindOf(r.blob, r.name) !== 'other' && (!recipe)) attach([file], true);
    if (recipe && j) {
      recipe.index++;
      if (recipe.index < recipe.steps.length) { const step = recipe.steps[recipe.index]; setTimeout(() => start({tool: step.tool, opts: step.opts || {}, title: recipe.label}, [file]), 600); }
      else { recipe = null; attach([file], true); }
    }
    if (document.querySelector('#chatView')?.hidden) ctx.toast('النتيجة جاهزة في المساعد ✓');
    job = null; settle();
  }
  function runFromChat(tool, files, opts = {}) {
    const step = {tool, opts, title: ctx.toolTitle(tool)};
    if (opts.convertMode === 'video' && tool === 'convert') step.opts = {...opts, set: {'#convertQuality': '32'}};
    if (LOCAL_RUN[tool] || isColab(tool)) { say('user', step.title); start(step, files); return; }
    if (QR_TOOLS.includes(tool)) { const m = say('assistant', 'تبي الرمز يرسل الملف مباشرة، ولا رابط دائم في Drive؟'); buttons(m, [['📲 مباشر', () => start({tool, opts: {qrMode: 'direct'}, title: 'رمز إرسال مباشر'}, files)], ['🔗 رابط Drive', () => start({tool, opts: {qrMode: 'drive'}, title: 'رمز برابط Drive'}, files)]]); return; }
    ctx.openTool(tool, files, {...opts, fromChat: true});
  }
  function runRecipe(rec, file) {
    if (!rec.steps.every(s => ctx.toolExists(s.tool))) { ctx.toast('هذي الوصفة غير متاحة الحين'); return; }
    say('user', rec.label); recipe = {...rec, index: 0};
    start({tool: rec.steps[0].tool, opts: rec.steps[0].opts || {}, title: rec.label}, [file]);
  }

  $('#clearChat').onclick = () => { if (job?.busy) cancel(); log.replaceChildren(); consume(); waitingFiles = waitingText = null; welcome(); };
  welcome();
  return {result, attach, busy: () => !!job?.busy, cancel};
}
