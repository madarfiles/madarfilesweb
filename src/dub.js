// «دبلج»: record your own voice over a video's speech while keeping its ambient sound.
// 1) the voice track is extracted locally, 2) Colab (the visitor's own account) splits it into
// voice + background, 3) speech timings are found in the browser, 4) the visitor records each
// line, 5) everything is mixed locally with FFmpeg and saved.
import {unzipSync} from 'fflate';
import {mountColabTool} from './colab-tool.js';
import {cloudCatalog} from './cloud-catalog.js';
import {detectSegments,clock,mixArguments,recordingExt} from './dub-core.js';
import {pickerAccept,requireAccepted,mountFilePicker} from './file-picker.js';
import {sourceName} from './output-names.js';

const base=n=>sourceName(n).replace(/\.[A-Za-z0-9]{1,5}$/,''),MAX_VIDEO=300*1048576,ENGINE={classWorkerURL:'/ffmpeg-worker.js',coreURL:'/runtime/ffmpeg-core.js?v=0.12.10',wasmURL:'/runtime/ffmpeg-core.wasm?v=0.12.10'};
const abs=u=>new URL(u,location.origin).href;
async function engine(report){const {FFmpeg}=await import('@ffmpeg/ffmpeg');const ff=new FFmpeg();if(report)ff.on('progress',e=>report(Math.min(99,Math.max(0,Math.round(e.progress*100)))));await ff.load({classWorkerURL:abs(ENGINE.classWorkerURL),coreURL:abs(ENGINE.coreURL),wasmURL:abs(ENGINE.wasmURL)});return ff;}

export function mountDub(content,{onResult}){
 content.innerHTML=`<div class="dub-intro"><span class="dub-badge">🎙 دبلج</span><h3>دبلج المقطع بصوتك</h3><p>نشيل كلام الأشخاص ونخلي صوت المحيط، وأنت تسجل كل جملة بصوتك في وقتها، وبعدها ندمج كل شي في فيديو واحد.</p></div>
 <ol class="dub-steps"><li data-step="1" class="active">الفيديو</li><li data-step="2">الفصل على Colab</li><li data-step="3">التسجيل</li><li data-step="4">التصدير</li></ol>
 <section data-stage="1"><label class="field">الفيديو<input type="file" id="dubFile"></label><video id="dubSource" class="dub-video" playsinline controls hidden></video><button class="button full" id="dubPrepare">تجهيز الصوت محليًا والمتابعة</button></section>
 <section data-stage="2" hidden><p class="tool-note">نرسل <b>الصوت فقط</b> (مو الفيديو) إلى Colab بحسابك، ليفصل كلام الأشخاص عن صوت المحيط. اتصل بـGoogle ووافق ثم اضغط زر البدء.</p><div id="dubColab"></div></section>
 <section data-stage="3" hidden><video id="dubPlayer" class="dub-video" playsinline muted></video><p class="notice" id="dubProgress" role="status"></p><div class="dub-tools"><button class="button secondary" id="dubAdd">+ مقطع من الوقت الحالي</button><button class="button secondary" id="dubPlayAll">▶ معاينة الدبلجة كاملة</button></div><ol id="dubList" class="dub-list"></ol><button class="button full" id="dubExport">دمج التسجيلات وتصدير الفيديو</button></section>
 <section data-stage="4" hidden><div id="dubResult"></div><button class="button secondary full" id="dubBack">رجوع للتسجيلات</button></section>
 <p class="notice" id="dubStatus" role="status">اختر فيديو فيه كلام. حتى 300 MB و30 دقيقة.</p><div class="inline-error" id="dubError" role="alert"></div>
 <p class="micro">التسجيلات تبقى في هذه الصفحة؛ صدّر الفيديو قبل إغلاقها. يفضّل سماعة لتسجيل نظيف.</p>`;
 const q=s=>content.querySelector(s),urls=[],track=u=>(urls.push(u),u);
 let video,colab,stems,segments=[],mic,recorder,disposed=false,audioCtx,playing,busy=false;
 const status=t=>{if(!disposed)q('#dubStatus').textContent=t;},fail=e=>{if(!disposed)q('#dubError').textContent=e?.message||String(e);};
 const stage=n=>{for(const s of content.querySelectorAll('[data-stage]'))s.hidden=s.dataset.stage!==String(n);for(const li of content.querySelectorAll('.dub-steps li'))li.className=Number(li.dataset.step)<n?'done':Number(li.dataset.step)===n?'active':'';};
 const guard=async fn=>{if(busy)return;busy=true;q('#dubError').textContent='';try{await fn();}catch(e){if(!disposed)fail(e);}finally{busy=false;}};
 q('#dubFile').accept=pickerAccept('video/*');
 q('#dubFile').onchange=()=>{const f=q('#dubFile').files[0];q('#dubError').textContent='';try{if(!f)return;requireAccepted([f],'video/*');if(f.size>MAX_VIDEO)throw Error('حد الدبلجة 300 MB للفيديو');video=f;const v=q('#dubSource');v.src=track(URL.createObjectURL(f));v.hidden=false;status('جاهز: '+f.name);}catch(e){video=null;q('#dubFile').value='';fail(e);}};

 // Step 1: extract a clean stereo audio track locally (small upload instead of the whole video).
 q('#dubPrepare').onclick=()=>guard(async()=>{
  if(!video)throw Error('اختر الفيديو أولًا');status('تجهيز محرك الصوت المحلي…');const ff=await engine(p=>status('استخراج الصوت محليًا · '+p+'٪'));
  try{await ff.writeFile('video.bin',new Uint8Array(await video.arrayBuffer()));const code=await ff.exec(['-i','video.bin','-map','0:a:0','-vn','-ac','2','-ar','44100','-c:a','aac','-b:a','192k','audio.m4a']);if(code!==0)throw Error('ما قدرنا نقرأ صوت هذا الفيديو؛ تأكد إن فيه صوت');
   const audio=new File([await ff.readFile('audio.m4a')],base(video.name)+'-audio.m4a',{type:'audio/mp4'});
   stage(2);status('الصوت جاهز ('+(audio.size/1048576).toFixed(1)+' MB). اتصل بـGoogle وابدأ الفصل.');
   colab?.dispose?.();colab=mountColabTool(q('#dubColab'),{taskSpec:cloudCatalog.find(t=>t.task==='dub'),onResult:(blob)=>{loadStems(blob).catch(fail);return {};}});
   colab.load?.([audio]);const label=q('#dubColab #colabFile')?.closest('label');if(label)label.hidden=true;
  }finally{ff.terminate();}
 });

 // Step 2 result: voice.m4a + background.m4a → speech timings.
 async function loadStems(zip){
  const files=unzipSync(new Uint8Array(await zip.arrayBuffer()));if(!files['voice.m4a']||!files['background.m4a'])throw Error('نتيجة Colab ناقصة؛ أعد المحاولة');
  stems={voice:new Blob([files['voice.m4a']],{type:'audio/mp4'}),background:new Blob([files['background.m4a']],{type:'audio/mp4'})};
  status('تحديد أماكن الكلام…');audioCtx??=new AudioContext();
  const decoded=await audioCtx.decodeAudioData(await stems.voice.arrayBuffer());const mono=new Float32Array(decoded.length);for(let c=0;c<decoded.numberOfChannels;c++){const d=decoded.getChannelData(c);for(let i=0;i<d.length;i++)mono[i]+=d[i]/decoded.numberOfChannels;}
  stems.backgroundBuffer=await audioCtx.decodeAudioData(await stems.background.arrayBuffer());
  segments=detectSegments(mono,decoded.sampleRate).map(s=>({...s}));
  q('#dubPlayer').src=track(URL.createObjectURL(video));stage(3);render();
  status(segments.length?'لقينا '+segments.length+' مقطع كلام. سجّل كل واحد بصوتك.':'ما لقينا كلام واضح؛ أضف المقاطع يدويًا من زر «مقطع من الوقت الحالي».');
 }

 // Playback through Web Audio so the picture, the background and the recordings stay in sync.
 function stopPlayback(){if(!playing)return;for(const s of playing.sources)try{s.stop();}catch{}q('#dubPlayer').pause();clearTimeout(playing.timer);playing=null;}
 async function play(from,to,{withRecordings=true,only}={}){
  stopPlayback();audioCtx??=new AudioContext();await audioCtx.resume();const v=q('#dubPlayer'),at=audioCtx.currentTime+0.15,sources=[];
  const start=(buffer,offset,when)=>{const s=audioCtx.createBufferSource();s.buffer=buffer;s.connect(audioCtx.destination);s.start(when,Math.max(0,offset));sources.push(s);};
  start(stems.backgroundBuffer,from,at);
  if(withRecordings)for(const seg of only?[only]:segments)if(seg.buffer&&seg.start+seg.buffer.duration>from&&seg.start<to)start(seg.buffer,Math.max(0,from-seg.start),at+Math.max(0,seg.start-from));
  v.currentTime=from;setTimeout(()=>v.play().catch(()=>{}),150);
  playing={sources,timer:setTimeout(stopPlayback,(to-from)*1000+300)};
 }
 const playOriginal=seg=>{stopPlayback();const v=q('#dubPlayer');v.muted=false;v.currentTime=seg.start;v.play().catch(()=>{});playing={sources:[],timer:setTimeout(()=>{v.pause();v.muted=true;playing=null;},(seg.end-seg.start)*1000+200)};};

 async function record(seg,button){
  if(recorder){recorder.stop();return;}
  stopPlayback();mic??=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}}).catch(()=>{throw Error('اسمح للمتصفح باستخدام المايكروفون');});
  for(const n of [3,2,1]){status('استعد… '+n);await new Promise(r=>setTimeout(r,700));}
  const chunks=[];recorder=new MediaRecorder(mic);recorder.ondataavailable=e=>e.data.size&&chunks.push(e.data);
  const v=q('#dubPlayer');v.muted=true;v.currentTime=seg.start;const limit=setTimeout(()=>recorder?.state==='recording'&&recorder.stop(),(seg.end-seg.start+4)*1000);
  recorder.onstop=async()=>{clearTimeout(limit);v.pause();const type=recorder.mimeType||chunks[0]?.type||'audio/webm';recorder=null;button.textContent='🎙 سجّل';
   const blob=new Blob(chunks,{type});try{seg.blob=blob;seg.ext=recordingExt(type);seg.buffer=await audioCtx.decodeAudioData(await blob.arrayBuffer());seg.done=false;status('اسمع تسجيلك بزر «معاينة»، وإذا عجبك اضغط ✓.');}catch{seg.blob=null;fail(Error('التسجيل فاضي أو ما انقرأ؛ جرّب مرة ثانية'));}render();};
  recorder.start();v.play().catch(()=>{});button.textContent='⏹ إيقاف';status('يسجّل… تكلم الحين ('+clock(seg.start)+' – '+clock(seg.end)+')');
 }

 function render(){
  const list=q('#dubList');list.replaceChildren();const doneCount=segments.filter(s=>s.done).length;q('#dubProgress').textContent='تم '+doneCount+' من '+segments.length;
  segments.forEach((seg,i)=>{const li=document.createElement('li');li.className='dub-item'+(seg.done?' done':seg.blob?' recorded':'');
   const head=document.createElement('div');head.className='dub-time';head.textContent='مقطع '+(i+1)+' · '+clock(seg.start)+' – '+clock(seg.end)+(seg.done?' ✓':'');
   const row=document.createElement('div');row.className='dub-actions';
   const btn=(text,fn,cls='button secondary')=>{const b=document.createElement('button');b.type='button';b.className=cls;b.textContent=text;b.onclick=()=>guard(()=>fn(b));row.append(b);return b;};
   btn('▶ الأصل',()=>playOriginal(seg));btn('🎙 '+(seg.blob?'أعد التسجيل':'سجّل'),b=>record(seg,b),'button');
   if(seg.blob){btn('▶ معاينة',()=>play(Math.max(0,seg.start-0.5),Math.max(seg.end,seg.start+seg.buffer.duration)+0.5,{only:seg}));btn(seg.done?'إلغاء ✓':'✓ تم',()=>{seg.done=!seg.done;render();});}
   const fine=document.createElement('div');fine.className='dub-fine';
   const nudge=(text,fn)=>{const b=document.createElement('button');b.type='button';b.className='dub-chip';b.textContent=text;b.onclick=()=>{fn();seg.end=Math.max(seg.start+0.3,seg.end);render();};fine.append(b);};
   nudge('البداية −',()=>seg.start=Math.max(i?segments[i-1].end:0,seg.start-0.25));nudge('البداية +',()=>seg.start=Math.min(seg.end-0.3,seg.start+0.25));nudge('النهاية −',()=>seg.end=Math.max(seg.start+0.3,seg.end-0.25));nudge('النهاية +',()=>seg.end=Math.min(segments[i+1]?.start??Infinity,seg.end+0.25));nudge('حذف',()=>{segments.splice(i,1);});
   li.append(head,row,fine);list.append(li);});
 }
 q('#dubAdd').onclick=()=>{const t=q('#dubPlayer').currentTime||0;segments.push({start:t,end:t+3});segments.sort((a,b)=>a.start-b.start);render();};
 q('#dubPlayAll').onclick=()=>guard(async()=>{if(!stems)return;await play(0,stems.backgroundBuffer.duration);});

 // Step 4: mix locally and save.
 q('#dubExport').onclick=()=>guard(async()=>{
  stopPlayback();const clips=segments.filter(s=>s.blob);if(!clips.length)throw Error('سجّل مقطعًا واحدًا على الأقل');
  if(clips.some(s=>!s.done)&&!confirm('فيه تسجيلات ما ضغطت عليها ✓. تبي تكمل التصدير؟'))return;
  status('تجهيز محرك الدمج…');const ff=await engine(p=>status('دمج الدبلجة محليًا · '+p+'٪'));
  try{await ff.writeFile('video.bin',new Uint8Array(await video.arrayBuffer()));await ff.writeFile('background.m4a',new Uint8Array(await stems.background.arrayBuffer()));
   for(const [i,c] of clips.entries())await ff.writeFile('rec'+i+'.'+c.ext,new Uint8Array(await c.blob.arrayBuffer()));
   let out='dubbed.mp4',code=await ff.exec(mixArguments(clips,{output:out}));
   if(code!==0){out='dubbed.mkv';code=await ff.exec(mixArguments(clips,{output:out}));}
   if(code!==0)throw Error('تعذر دمج الفيديو محليًا؛ جرّب مقطعًا أقصر');
   const blob=new Blob([await ff.readFile(out)],{type:out.endsWith('mp4')?'video/mp4':'video/x-matroska'}),name=base(video.name)+'-مدبلج.'+out.split('.').pop();
   const saved=onResult?.(blob,name,'video'),url=saved?.url||track(URL.createObjectURL(blob));
   const v=document.createElement('video');v.src=url;v.controls=true;v.playsInline=true;v.className='dub-video';const a=document.createElement('a');a.href=url;a.download=name;a.className='button full';a.textContent='حفظ الفيديو المدبلج';
   q('#dubResult').replaceChildren(v,a);stage(4);status('اكتملت الدبلجة 🎉');
  }finally{ff.terminate();}
 });
 q('#dubBack').onclick=()=>stage(3);
 const picker=mountFilePicker(q('#dubFile'),{accept:'video/*'});
 return{pick(){picker.open();},load(files){const f=files?.[0];if(f&&f.type.startsWith('video/')){const t=new DataTransfer();t.items.add(f);q('#dubFile').files=t.files;q('#dubFile').onchange();}},dispose(){disposed=true;stopPlayback();try{recorder?.stop();}catch{}mic?.getTracks().forEach(t=>t.stop());colab?.dispose?.();picker.dispose();audioCtx?.close?.();for(const u of urls)URL.revokeObjectURL(u);}};
}
