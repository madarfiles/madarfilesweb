// «دبلج»: record your own voice over a video's speech while keeping its ambient sound.
// One clear step at a time: connect → video → separation → record line by line → export.
import {unzipSync} from 'fflate';
import {mountColabTool} from './colab-tool.js';
import {cloudCatalog} from './cloud-catalog.js';
import {detectSegments,clock,mixArguments,recordingExt,readLines,mergeLines,splitLine,speakerColor} from './dub-core.js';
import {pickerAccept,requireAccepted,mountFilePicker} from './file-picker.js';
import {sourceName} from './output-names.js';

const base=n=>sourceName(n).replace(/\.[A-Za-z0-9]{1,5}$/,''),MAX_VIDEO=300*1048576;
const ENGINE={classWorkerURL:'/ffmpeg-worker.js',coreURL:'/runtime/ffmpeg-core.js?v=0.12.10',wasmURL:'/runtime/ffmpeg-core.wasm?v=0.12.10'};
const abs=u=>new URL(u,location.origin).href;
async function engine(report){const {FFmpeg}=await import('@ffmpeg/ffmpeg');const ff=new FFmpeg();if(report)ff.on('progress',e=>report(Math.min(99,Math.max(0,Math.round(e.progress*100)))));await ff.load({classWorkerURL:abs(ENGINE.classWorkerURL),coreURL:abs(ENGINE.coreURL),wasmURL:abs(ENGINE.wasmURL)});return ff;}
const STEPS=[['connect','الاتصال'],['video','الفيديو'],['split','الفصل'],['record','التسجيل'],['export','التصدير']];

export function mountDub(content,{onResult}){
 content.innerHTML=`<div class="dub-intro"><span class="dub-badge">🎙 دبلج</span><h3>دبلج المقطع بصوتك</h3></div>
 <ol class="wizard-steps" id="dubSteps"></ol><button type="button" class="wizard-back" id="dubBack">→ رجوع</button>
 <section data-step="connect"><p class="dub-lead">أول شي اتصل بحساب Google، لأن فصل الأصوات يصير على Colab بحسابك أنت.</p><div id="dubColab"></div></section>
 <section data-step="video"><p class="dub-lead">اختر الفيديو اللي تبي تدبلجه.</p><label class="field">الفيديو<input type="file" id="dubFile"></label><video id="dubSource" class="dub-video" playsinline controls hidden></video>
  <label class="field">الكلام يطلع لك مكتوب وقت التسجيل<select id="dubTextLang"><option value="ar">مترجم للعربي</option><option value="original">بلغة المقطع الأصلية</option><option value="none">بدون نص</option></select></label>
  <button class="button full" id="dubStart" disabled>ابدأ</button><p class="micro">بالضغط على «ابدأ» توافق إننا نرسل <b>صوت</b> الفيديو فقط إلى Colab بحسابك ونستخدم رصيده.</p></section>
 <section data-step="split"><p class="dub-lead">نفصل كلام الأشخاص عن صوت المحيط… خلّ الصفحة مفتوحة.</p><p class="notice" id="dubSplitStatus" role="status"></p><div id="dubColabRun"></div></section>
 <section data-step="record"><div class="dub-card"><div class="dub-card-head"><b id="dubLineTitle"></b><button type="button" class="dub-spk" id="dubSpk" title="اضغط لتغيير الشخصية" hidden></button><span id="dubLineTime"></span></div>
  <div class="dub-stage"><video id="dubPlayer" class="dub-video" playsinline muted></video><div class="dub-count" id="dubCount" hidden></div></div><div class="dub-text" id="dubText"></div><button type="button" class="dub-chip dub-split" id="dubSplit" hidden></button>
  <div class="dub-main"><button class="button secondary" id="dubHear">▶ اسمع الأصل</button><button class="button dub-rec" id="dubRec">🎙 سجّل صوتك</button><button class="button secondary" id="dubMine" hidden>▶ اسمع تسجيلك</button></div>
  <div class="dub-dots" id="dubDots"></div>
  <div class="dub-nav"><button class="button secondary" id="dubPrev">→ السابق</button><button class="button" id="dubNext">التالي ←</button></div>
  <details class="cloud-settings"><summary>ضبط وقت الجملة</summary><div class="dub-fine"><button class="dub-chip" data-nudge="s-">البداية −</button><button class="dub-chip" data-nudge="s+">البداية +</button><button class="dub-chip" data-nudge="e-">النهاية −</button><button class="dub-chip" data-nudge="e+">النهاية +</button><button class="dub-chip" id="dubDelete">حذف الجملة</button><button class="dub-chip" id="dubAdd">+ جملة جديدة بعدها</button><button class="dub-chip" id="dubMerge">دمج مع الجملة التالية</button></div></details></div></section>
 <section data-step="export"><p class="dub-lead" id="dubSummary"></p><button class="button secondary full" id="dubPlayAll">▶ معاينة الدبلجة كاملة</button><button class="button full" id="dubExport">تصدير الفيديو المدبلج</button><div id="dubResult"></div></section>
 <p class="notice" id="dubStatus" role="status"></p><div class="inline-error" id="dubError" role="alert"></div>`;
 const q=s=>content.querySelector(s),urls=[],track=u=>(urls.push(u),u);
 let video,colab,stems,segments=[],line=0,speakers=0,mic,recorder,disposed=false,audioCtx,playing,busy=false,step,visited=new Set();
 const status=t=>{if(!disposed)q('#dubStatus').textContent=t||'';},fail=e=>{if(!disposed)q('#dubError').textContent=e?.message||String(e||'');};
 const guard=async fn=>{if(busy)return;busy=true;fail('');try{await fn();}catch(e){if(!disposed)fail(e);}finally{busy=false;}};

 function go(next){step=next;visited.add(next);fail('');for(const s of content.querySelectorAll('section[data-step]'))s.hidden=s.dataset.step!==next;
  // The Colab panel lives in the connect step, then moves under the separation step.
  if(colab)(next==='split'?q('#dubColabRun'):q('section[data-step="connect"]')).append(colab.host);
  q('#dubSteps').replaceChildren(...STEPS.map(([id,label],i)=>{const li=document.createElement('li');li.textContent=(i+1)+'. '+label;const done=visited.has(id)&&id!==next;li.className=id===next?'active':done?'done':'';if(done&&!(id==='split'&&!stems)){li.tabIndex=0;li.setAttribute('role','button');li.onclick=()=>go(id);}return li;}));
  q('#dubBack').hidden=next==='connect'||next==='split';
  if(next==='record')showLine();if(next==='export')summary();if(next!=='record'&&next!=='export')status('');
  (content.closest('dialog')||content).scrollTo?.({top:0,behavior:'smooth'});
 }
 q('#dubBack').onclick=()=>go({video:'connect',record:'video',export:'record'}[step]||'video');

 // Step 1: the visitor's own Google/Colab connection (the Colab panel shows only its connect part).
 const host=document.createElement('div');host.className='dub-colab';q('#dubColab').replaceWith(host);
 colab=mountColabTool(host,{wizard:'embedded',taskSpec:cloudCatalog.find(t=>t.task==='dub'),onEvent:type=>{if(type==='connected'&&step==='connect')go('video');},onResult:blob=>{loadStems(blob).catch(e=>fail(e));return {};}});colab.host=host;
 host.querySelector('.colab-intro')?.remove();

 // Step 2: pick the video.
 q('#dubFile').accept=pickerAccept('video/*');
 q('#dubFile').onchange=()=>{const f=q('#dubFile').files[0];fail('');try{if(!f)return;requireAccepted([f],'video/*');if(f.size>MAX_VIDEO)throw Error('حد الدبلجة 300 MB للفيديو');video=f;const v=q('#dubSource');v.src=track(URL.createObjectURL(f));v.hidden=false;q('#dubStart').disabled=false;}catch(e){video=null;q('#dubFile').value='';q('#dubStart').disabled=true;fail(e);}};

 // Step 3: extract the audio locally (small upload), then Colab splits voice / background.
 q('#dubStart').onclick=()=>guard(async()=>{
  if(!video)throw Error('اختر الفيديو أولًا');stems=null;go('split');colab.steps?.go('run',{scroll:false});const say=t=>q('#dubSplitStatus').textContent=t;say('نجهز صوت الفيديو في جهازك…');
  const ff=await engine(p=>say('نجهز صوت الفيديو في جهازك · '+p+'٪'));
  try{await ff.writeFile('video.bin',new Uint8Array(await video.arrayBuffer()));const code=await ff.exec(['-i','video.bin','-map','0:a:0','-vn','-ac','2','-ar','44100','-c:a','aac','-b:a','192k','audio.m4a']);if(code!==0)throw Error('ما قدرنا نقرأ صوت هذا الفيديو؛ تأكد إن فيه صوت');
   const audio=new File([await ff.readFile('audio.m4a')],base(video.name)+'-صوت.m4a',{type:'audio/mp4'});say('نرفع الصوت ('+(audio.size/1048576).toFixed(1)+' MB) ونفصله على Colab…');const lang=host.querySelector('#cloud-textLang');if(lang)lang.value=q('#dubTextLang').value;colab.load([audio]);colab.run();
  }finally{ff.terminate();}
 });

 async function loadStems(zip){
  const files=unzipSync(new Uint8Array(await zip.arrayBuffer()));if(!files['voice.m4a']||!files['background.m4a'])throw Error('نتيجة Colab ناقصة؛ أعد المحاولة');
  stems={voice:new Blob([files['voice.m4a']],{type:'audio/mp4'}),background:new Blob([files['background.m4a']],{type:'audio/mp4'})};
  q('#dubSplitStatus').textContent='نحدد أماكن الكلام…';audioCtx??=new AudioContext();
  const decoded=await audioCtx.decodeAudioData(await stems.voice.arrayBuffer());const mono=new Float32Array(decoded.length);for(let c=0;c<decoded.numberOfChannels;c++){const d=decoded.getChannelData(c);for(let i=0;i<d.length;i++)mono[i]+=d[i]/decoded.numberOfChannels;}
  stems.backgroundBuffer=await audioCtx.decodeAudioData(await stems.background.arrayBuffer());
  const text=readLines(files['lines.json']);let note=text.note||'';speakers=text.speakers||0;
  segments=text.lines.length?text.lines:detectSegments(mono,decoded.sampleRate).map(s=>({...s}));
  if(!text.lines.length&&text.error)note='ما قدرنا نفرّغ الكلام هالمرة، فقسّمنا الجمل حسب الصوت.';
  const empty=!segments.length;if(empty){segments=[{start:0,end:Math.min(3,stems.backgroundBuffer.duration)}];note='ما لقينا كلام واضح؛ عدّل الوقت من «ضبط وقت الجملة».';}
  line=0;q('#dubPlayer').src=track(URL.createObjectURL(video));go('record');if(note)status(note);
 }

 // Playback through Web Audio keeps picture, background and recordings in sync.
 function stopPlayback(){stopSync();if(!playing)return;for(const s of playing.sources)try{s.stop();}catch{}const v=q('#dubPlayer');v.pause();v.muted=true;clearTimeout(playing.timer);playing=null;}
 async function play(from,to,{only}={}){
  stopPlayback();audioCtx??=new AudioContext();await audioCtx.resume();const v=q('#dubPlayer'),at=audioCtx.currentTime+0.15,sources=[];
  const start=(buffer,offset,when)=>{const s=audioCtx.createBufferSource();s.buffer=buffer;s.connect(audioCtx.destination);s.start(when,Math.max(0,offset));sources.push(s);};
  start(stems.backgroundBuffer,from,at);
  for(const seg of only?[only]:segments)if(seg.buffer&&seg.start+seg.buffer.duration>from&&seg.start<to)start(seg.buffer,Math.max(0,from-seg.start),at+Math.max(0,seg.start-from));
  v.currentTime=from;setTimeout(()=>{v.play().catch(()=>{});startSync();},150);playing={sources,timer:setTimeout(stopPlayback,(to-from)*1000+300)};
 }

 // The line's words, highlighted as the picture plays (or a filling bar for a translation).
 let raf;
 function renderText(seg){const box=q('#dubText');box.replaceChildren();if(!seg.text&&!seg.tr){box.hidden=true;return;}box.hidden=false;
  const main=document.createElement('p');main.className='dub-say';
  // Tapping a word offers «قسّم هنا» (cut the line before it) when the voices were mixed up.
  const words=(into,cls)=>{const list=seg.words?.length?seg.words:[{w:seg.text,s:seg.start,e:seg.end}];list.forEach((w,i)=>{const span=document.createElement('span');span.textContent=w.w+' ';if(cls){span.dataset.s=w.s;span.dataset.e=w.e;}if(w.k)span.dataset.k=w.k;if(i>0&&seg.words?.length)span.onclick=()=>offerSplit(i);into.append(span);});};
  if(seg.tr){main.textContent=seg.tr;main.dir='auto';const bar=document.createElement('div');bar.className='dub-bar';bar.append(document.createElement('i'));box.append(main,bar);const orig=document.createElement('p');orig.className='dub-orig';orig.dir='auto';words(orig,false);box.append(orig);}
  else{main.dir='auto';words(main,true);box.append(main);}
  paint(q('#dubPlayer').currentTime);}
 let splitAt=0;
 function offerSplit(i){if(recorder)return;const seg=segments[line],w=seg?.words?.[i];if(!w)return;splitAt=i;const b=q('#dubSplit');b.textContent='✂ قسّم الجملة قبل «'+w.w.slice(0,20)+'»';b.hidden=false;}
 function paint(t){const seg=segments[line];if(!seg)return;for(const span of q('#dubText').querySelectorAll('span[data-s]')){span.className=t>=Number(span.dataset.e)?'said':t>=Number(span.dataset.s)-0.05?'now':'';}
  const bar=q('#dubText .dub-bar i');if(bar)bar.style.width=Math.max(0,Math.min(100,(t-seg.start)/Math.max(0.1,seg.end-seg.start)*100))+'%';}
 function startSync(){stopSync();const tick=()=>{paint(q('#dubPlayer').currentTime);raf=requestAnimationFrame(tick);};raf=requestAnimationFrame(tick);}
 function stopSync(){if(raf)cancelAnimationFrame(raf);raf=null;}
 // Step 4: one line at a time.
 function showLine(){
  const seg=segments[line];if(!seg)return;q('#dubLineTitle').textContent='الجملة '+(line+1)+' من '+segments.length;const chip=q('#dubSpk');chip.hidden=!speakers;chip.textContent=seg.spk?'الشخصية '+seg.spk:'شخصية ؟';chip.style.setProperty('--spk',speakerColor(seg.spk));q('#dubSplit').hidden=true;splitAt=0;q('#dubLineTime').textContent=clock(seg.start)+' – '+clock(seg.end);
  renderText(seg);q('#dubRec').textContent=seg.blob?'🎙 أعد التسجيل':'🎙 سجّل صوتك';q('#dubMine').hidden=!seg.blob;q('#dubPrev').disabled=line===0;q('#dubNext').textContent=line===segments.length-1?'إنهاء والتصدير ←':'التالي ←';
  const v=q('#dubPlayer');if(v.readyState)v.currentTime=seg.start;else v.onloadedmetadata=()=>{v.currentTime=segments[line]?.start||0;};
  q('#dubDots').replaceChildren(...segments.map((s,i)=>{const b=document.createElement('button');b.type='button';b.className='dub-dot'+(i===line?' current':s.blob?' done':'');if(speakers)b.style.setProperty('--spk',speakerColor(s.spk));b.title='الجملة '+(i+1);b.onclick=()=>{if(recorder)return;stopPlayback();line=i;showLine();};return b;}));
  status(seg.blob?'تسجيلك جاهز. اسمعه، وإذا عجبك اضغط «التالي».':'اسمع الأصل، وبعدها سجّل الجملة بصوتك.');
 }
 q('#dubHear').onclick=()=>{if(recorder)return;const seg=segments[line];stopPlayback();const v=q('#dubPlayer');v.muted=false;v.currentTime=seg.start;v.play().catch(()=>{});startSync();playing={sources:[],timer:setTimeout(stopPlayback,(seg.end-seg.start)*1000+200)};};
 q('#dubMine').onclick=()=>guard(()=>{const seg=segments[line];return play(Math.max(0,seg.start-0.4),Math.max(seg.end,seg.start+seg.buffer.duration)+0.4,{only:seg});});
 q('#dubRec').onclick=async()=>{
  if(recorder){recorder.stop();return;}const seg=segments[line];fail('');
  try{stopPlayback();mic??=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});}catch{fail(Error('اسمح للمتصفح باستخدام المايكروفون'));return;}
  q('#dubRec').disabled=true;q('#dubRec').textContent='استعد…';const count=q('#dubCount');count.hidden=false;for(const n of ['3','2','1']){count.textContent=n;await new Promise(r=>setTimeout(r,700));}count.hidden=true;q('#dubRec').disabled=false;
  const chunks=[];recorder=new MediaRecorder(mic);recorder.ondataavailable=e=>e.data.size&&chunks.push(e.data);
  const v=q('#dubPlayer');v.muted=true;v.currentTime=seg.start;const limit=setTimeout(()=>recorder?.state==='recording'&&recorder.stop(),(seg.end-seg.start+4)*1000);
  recorder.onstop=async()=>{clearTimeout(limit);v.pause();stopSync();const type=recorder.mimeType||chunks[0]?.type||'audio/webm';recorder=null;q('#dubRec').classList.remove('live');
   try{audioCtx??=new AudioContext();const blob=new Blob(chunks,{type});const buffer=await audioCtx.decodeAudioData(await blob.arrayBuffer());Object.assign(seg,{blob,buffer,ext:recordingExt(type)});}catch{fail(Error('التسجيل ما انقرأ؛ جرّب مرة ثانية'));}showLine();};
  recorder.start();v.play().catch(()=>{});startSync();q('#dubRec').textContent='⏹ إيقاف التسجيل';q('#dubRec').classList.add('live');status('يسجّل… تكلم الحين');
 };
 q('#dubPrev').onclick=()=>{if(recorder)return;stopPlayback();if(line>0){line--;showLine();}};
 q('#dubNext').onclick=()=>{if(recorder)return;stopPlayback();if(line<segments.length-1){line++;showLine();}else go('export');};
 for(const b of content.querySelectorAll('[data-nudge]'))b.onclick=()=>{const seg=segments[line],prev=segments[line-1],next=segments[line+1],d=0.25;
  ({'s-':()=>seg.start=Math.max(prev?prev.end:0,seg.start-d),'s+':()=>seg.start=Math.min(seg.end-0.3,seg.start+d),'e-':()=>seg.end=Math.max(seg.start+0.3,seg.end-d),'e+':()=>seg.end=Math.min(next?next.start:Infinity,seg.end+d)})[b.dataset.nudge]();showLine();};
 q('#dubDelete').onclick=()=>{if(segments.length<2)return fail(Error('لازم تبقى جملة وحدة على الأقل'));segments.splice(line,1);line=Math.min(line,segments.length-1);showLine();};
 q('#dubSplit').onclick=()=>{if(recorder)return;const parts=splitLine(segments[line],splitAt);if(!parts)return;stopPlayback();const had=segments[line].blob;segments.splice(line,1,...parts);showLine();status(had?'قسّمنا الجملة؛ سجّل الجزأين من جديد.':'قسّمنا الجملة لجزأين.');};
 // The speaker colour: tap to move this line to the next character (or a new one).
 q('#dubSpk').onclick=()=>{if(recorder)return;const seg=segments[line];const known=[...new Set(segments.filter(s=>s!==seg&&s.spk).map(s=>s.spk))].sort((a,b)=>a-b);const options=[...known,(known.at(-1)||0)+1];seg.spk=options[(options.indexOf(seg.spk)+1)%options.length];showLine();};
 q('#dubMerge').onclick=()=>{if(recorder)return;const next=segments[line+1];if(!next)return fail(Error('هذي آخر جملة؛ ما فيه جملة بعدها'));stopPlayback();const had=segments[line].blob||next.blob;segments.splice(line,2,mergeLines(segments[line],next));showLine();if(had)status('دمجنا الجملتين؛ سجّل الجملة الجديدة كاملة.');};
 q('#dubAdd').onclick=()=>{const seg=segments[line],next=segments[line+1],start=seg.end+0.1,end=Math.min(start+3,next?next.start:start+3);if(end-start<0.3)return fail(Error('ما فيه مكان بعد هذي الجملة'));segments.splice(line+1,0,{start,end});line++;showLine();};

 // Step 5: export.
 function summary(){const n=segments.filter(s=>s.blob).length;q('#dubSummary').textContent=n?'سجّلت '+n+' من '+segments.length+' جملة. اسمع الدبلجة كاملة، وبعدها صدّر الفيديو.':'ما سجلت أي جملة للحين؛ ارجع لخطوة التسجيل.';q('#dubExport').disabled=!n;q('#dubPlayAll').disabled=!stems;status('');}
 q('#dubPlayAll').onclick=()=>guard(()=>play(0,stems.backgroundBuffer.duration));
 q('#dubExport').onclick=()=>guard(async()=>{
  stopPlayback();const clips=segments.filter(s=>s.blob);if(!clips.length)throw Error('سجّل جملة وحدة على الأقل');
  const ff=await engine(p=>status('ندمج الدبلجة في جهازك · '+p+'٪'));
  try{await ff.writeFile('video.bin',new Uint8Array(await video.arrayBuffer()));await ff.writeFile('background.m4a',new Uint8Array(await stems.background.arrayBuffer()));
   for(const [i,c] of clips.entries())await ff.writeFile('rec'+i+'.'+c.ext,new Uint8Array(await c.blob.arrayBuffer()));
   let out='dubbed.mp4',code=await ff.exec(mixArguments(clips,{output:out}));if(code!==0){out='dubbed.mkv';code=await ff.exec(mixArguments(clips,{output:out}));}
   if(code!==0)throw Error('تعذر دمج الفيديو؛ جرّب مقطعًا أقصر');
   const blob=new Blob([await ff.readFile(out)],{type:out.endsWith('mp4')?'video/mp4':'video/x-matroska'}),name=base(video.name)+'-مدبلج.'+out.split('.').pop();
   // The page's own result box («النتيجة جاهزة للمعاينة» + «حفظ النتيجة») shows the video once;
   // a second player here only repeated it. Without that box (tool opened elsewhere) we show it here.
   const saved=onResult?.(blob,name,'video');
   if(saved?.url){q('#dubResult').replaceChildren();status('اكتملت الدبلجة 🎉 عاين الفيديو تحت واحفظه');setTimeout(()=>document.getElementById('universalResult')?.scrollIntoView({behavior:'smooth',block:'start'}),300);}
   else{const url=track(URL.createObjectURL(blob));const v=document.createElement('video');v.src=url;v.controls=true;v.playsInline=true;v.className='dub-video';const a=document.createElement('a');a.href=url;a.download=name;a.className='button full';a.textContent='حفظ الفيديو المدبلج';
    q('#dubResult').replaceChildren(v,a);status('اكتملت الدبلجة 🎉');}
  }finally{ff.terminate();}
 });
 const picker=mountFilePicker(q('#dubFile'),{accept:'video/*'});
 go(colab.steps?.current==='file'?'video':'connect');
 return{pick(){if(step==='video')picker.open();},load(files){const f=files?.[0];if(f&&f.type.startsWith('video/')){const t=new DataTransfer();t.items.add(f);q('#dubFile').files=t.files;q('#dubFile').onchange();}},dispose(){disposed=true;stopPlayback();try{recorder?.stop();}catch{}mic?.getTracks().forEach(t=>t.stop());colab?.dispose?.();picker.dispose();audioCtx?.close?.();for(const u of urls)URL.revokeObjectURL(u);}};
}
