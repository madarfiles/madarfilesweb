// Direct device-to-device transfer over WebRTC. The file goes straight from the
// sender's browser to the receiver's; the server only relays the short connection
// descriptions (see p2p-server.js). No Google account is needed.
import QRCode from 'qrcode';
import {pickerAccept,requireAccepted,mountFilePicker} from './file-picker.js';
import {mountDriveQR} from './drive-qr.js';

export const P2P_MAX=1024*1048576;
const ICE={iceServers:[{urls:['stun:stun.l.google.com:19302','stun:stun1.l.google.com:19302']}]};
const CHUNK=65536,HIGH=8*1048576,LOW=1048576,POLL=1500,OPEN_TIMEOUT=30000;
const SAFE_TYPE=/^(image\/(png|jpeg|webp|gif|heic|heif)|video\/[\w.+-]+|audio\/[\w.+-]+|application\/pdf)$/;

export const safeName=name=>{const clean=String(name||'').replace(/[\\/:*?"<>|\x00-\x1f\x7f]/g,'_').replace(/^\.+/,'').trim().slice(0,120);return clean||'madar-file';};
export const safeType=type=>SAFE_TYPE.test(String(type||''))?type:'application/octet-stream';
const size=n=>n>=1048576?(n/1048576).toFixed(1)+' MB':Math.max(1,Math.round(n/1024))+' KB';

async function signal(action,body,abort){const r=await fetch('/api/p2p/'+action,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',signal:abort,body:JSON.stringify(body)});let data={};try{data=await r.json();}catch{}if(!r.ok)throw Error(data.error||'تعذر الاتصال بمدار');return data;}
function gathered(pc,ms=5000){return new Promise(ok=>{if(pc.iceGatheringState==='complete')return ok();const t=setTimeout(done,ms);function done(){clearTimeout(t);pc.removeEventListener('icegatheringstatechange',check);ok();}function check(){if(pc.iceGatheringState==='complete')done();}pc.addEventListener('icegatheringstatechange',check);});}
const failed='تعذر الاتصال المباشر بين الجهازين. جرّبوا نفس شبكة الواي فاي، أو استخدم «رابط Drive».';

// Sender: returns {stop()}; report(text) shows status; onCode(url) receives the link to put in the QR.
export async function sendFile(file,{report,onCode,onDone,abort}){
 if(!file||!file.size)throw Error('اختر ملفًا غير فارغ');if(file.size>P2P_MAX)throw Error('حد الإرسال المباشر 1 GB');
 const pc=new RTCPeerConnection(ICE),dc=pc.createDataChannel('madar-file',{ordered:true});dc.binaryType='arraybuffer';dc.bufferedAmountLowThreshold=LOW;
 let code,stopped=false,timer;const stop=async()=>{if(stopped)return;stopped=true;clearTimeout(timer);try{dc.close();pc.close();}catch{}if(code)try{await signal('cancel',{id:code.id,secret:code.secret});}catch{}};
 abort?.addEventListener('abort',stop,{once:true});
 try{
  await pc.setLocalDescription(await pc.createOffer());await gathered(pc);
  code=await signal('offer',{sdp:pc.localDescription.sdp},abort);
  onCode(location.origin+'/#get='+code.id);report('امسح الرمز من الجهاز الآخر، أو أرسل له الرابط. الرمز صالح 10 دقائق ولجهاز واحد.');
  let answer;while(!stopped&&!answer){if(Date.now()>code.expires)throw Error('انتهت صلاحية الرمز؛ أنشئ رمزًا جديدًا');await new Promise(r=>setTimeout(r,POLL));if(stopped)return;const r=await signal('poll',{id:code.id,secret:code.secret},abort);if(r.sdp)answer=r.sdp;}
  if(stopped)return;code=null;report('الجهاز الآخر فتح الرمز؛ نجهز الاتصال…');
  await pc.setRemoteDescription({type:'answer',sdp:answer});
  await new Promise((ok,bad)=>{if(dc.readyState==='open')return ok();timer=setTimeout(()=>bad(Error(failed)),OPEN_TIMEOUT);dc.onopen=()=>{clearTimeout(timer);ok();};pc.onconnectionstatechange=()=>{if(pc.connectionState==='failed'){clearTimeout(timer);bad(Error(failed));}};});
  const max=Math.min(CHUNK,pc.sctp?.maxMessageSize||16384);
  dc.send(JSON.stringify({t:'meta',name:safeName(file.name),size:file.size,type:safeType(file.type)}));
  const acknowledged=new Promise((ok,bad)=>{dc.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.t==='ok')ok();if(m.t==='error')bad(Error(m.message||'رفض الجهاز الآخر الملف'));}catch{}};dc.onclose=()=>bad(Error('انقطع الاتصال قبل اكتمال الإرسال'));});
  acknowledged.catch(()=>{});
  for(let offset=0;offset<file.size&&!stopped;){const end=Math.min(file.size,offset+4*1048576),buffer=await file.slice(offset,end).arrayBuffer();
   for(let at=0;at<buffer.byteLength&&!stopped;at+=max){if(dc.readyState!=='open')throw Error('انقطع الاتصال قبل اكتمال الإرسال');if(dc.bufferedAmount>HIGH)await new Promise(r=>dc.addEventListener('bufferedamountlow',r,{once:true}));dc.send(buffer.slice(at,Math.min(at+max,buffer.byteLength)));}
   offset=end;report('إرسال مباشر · '+Math.round(offset/file.size*100)+'٪ ('+size(offset)+' من '+size(file.size)+')');}
  if(stopped)return;dc.send(JSON.stringify({t:'end'}));await acknowledged;report('تم الإرسال ✓ وصل الملف كاملًا للجهاز الآخر.');onDone?.();
 }finally{await stop();}
}

// Receiver: runs when the page opens with #get=<id>.
export async function receiveFile(id,{report,onMeta,onProgress,abort}){
 const offer=await signal('get',{id},abort);const pc=new RTCPeerConnection(ICE);
 try{
  const channel=new Promise((ok,bad)=>{const t=setTimeout(()=>bad(Error(failed)),OPEN_TIMEOUT);pc.ondatachannel=e=>{clearTimeout(t);ok(e.channel);};pc.onconnectionstatechange=()=>{if(pc.connectionState==='failed'){clearTimeout(t);bad(Error(failed));}};});
  await pc.setRemoteDescription({type:'offer',sdp:offer.sdp});await pc.setLocalDescription(await pc.createAnswer());await gathered(pc);
  await signal('answer',{id,sdp:pc.localDescription.sdp},abort);report('نتصل بالجهاز المرسل…');
  const dc=await channel;dc.binaryType='arraybuffer';
  return await new Promise((ok,bad)=>{let meta,parts=[],got=0;
   const fail=message=>{try{dc.send(JSON.stringify({t:'error',message}));}catch{}bad(Error(message));};
   dc.onclose=()=>bad(Error('انقطع الاتصال قبل اكتمال الاستلام'));
   dc.onmessage=e=>{if(typeof e.data==='string'){let m;try{m=JSON.parse(e.data);}catch{return fail('رسالة غير صالحة');}
     if(m.t==='meta'){if(meta)return fail('رسالة مكررة');if(!Number.isSafeInteger(m.size)||m.size<1||m.size>P2P_MAX)return fail('حجم الملف غير مقبول');meta={name:safeName(m.name),size:m.size,type:safeType(m.type)};onMeta?.(meta);return;}
     if(m.t==='end'){if(!meta||got!==meta.size)return fail('وصل الملف ناقصًا؛ أعد الإرسال');const blob=new Blob(parts,{type:meta.type});parts=[];dc.send(JSON.stringify({t:'ok'}));return ok({blob,...meta});}
     return;}
    if(!meta)return fail('بيانات قبل وصف الملف');got+=e.data.byteLength;if(got>meta.size)return fail('الملف أكبر من المعلن');parts.push(e.data);onProgress?.(got,meta.size);};});
 }finally{setTimeout(()=>{try{pc.close();}catch{}},1500);}
}

// QR tools: direct transfer by default, Drive link as the alternative.
export function mountQRShare(content,spec,ctx){
 content.innerHTML='<div class="qr-modes" role="tablist"><button type="button" class="button" data-mode="direct" role="tab">إرسال مباشر · بدون حساب</button><button type="button" class="button secondary" data-mode="drive" role="tab">رابط دائم عبر Drive</button></div><div id="qrModeBody"></div>';
 const body=content.querySelector('#qrModeBody');let active,mode;
 const show=next=>{if(mode===next)return;active?.dispose();mode=next;for(const b of content.querySelectorAll('[data-mode]')){const on=b.dataset.mode===next;b.className='button'+(on?'':' secondary');b.setAttribute('aria-selected',String(on));}active=next==='drive'?mountDriveQR(body,spec,ctx):mountDirect(body,spec,ctx);};
 for(const b of content.querySelectorAll('[data-mode]'))b.onclick=()=>show(b.dataset.mode);
 show('direct');return{pick(){active?.pick?.();},dispose(){active?.dispose();}};
}

function mountDirect(content,spec,{onResult}){
 content.innerHTML='<p class="tool-note">الملف ينتقل مباشرة من جهازك إلى الجهاز اللي يمسح الرمز، بدون رفع لأي سيرفر وبدون تسجيل دخول. خلّ هذي الصفحة مفتوحة لين يكتمل الإرسال. حتى 1 GB. أفضل نتيجة لما يكون الجهازين على نفس الواي فاي.</p><label class="field">ملفك<input type="file" id="p2pFile"></label><button class="button full" id="p2pRun">أنشئ رمز الإرسال</button><p class="notice" id="p2pStatus" role="status">اختر ملفًا.</p><div id="p2pResult"></div>';
 const q=s=>content.querySelector(s);q('#p2pFile').accept=pickerAccept(spec.mime);let controller,disposed=false;const msg=t=>{if(!disposed)q('#p2pStatus').textContent=t;};
 q('#p2pRun').onclick=async()=>{if(controller){controller.abort();return;}const file=q('#p2pFile').files[0];try{if(file)requireAccepted([file],spec.mime);if(!file)throw Error('اختر ملفًا أولًا');controller=new AbortController();q('#p2pRun').textContent='إيقاف الإرسال';q('#p2pFile').disabled=true;q('#p2pResult').replaceChildren();msg('نجهز رمز الإرسال…');
   await sendFile(file,{abort:controller.signal,report:msg,onCode:async url=>{if(disposed)return;const canvas=document.createElement('canvas');await QRCode.toCanvas(canvas,url,{width:768,margin:4,errorCorrectionLevel:'M'});canvas.className='design-preview';const copy=document.createElement('button');copy.type='button';copy.className='button secondary full';copy.textContent='نسخ رابط الاستلام';copy.onclick=async()=>{try{await navigator.clipboard.writeText(url);copy.textContent='تم النسخ ✓';}catch{copy.textContent=url;}};q('#p2pResult').replaceChildren(canvas,copy);canvas.toBlob(blob=>{if(blob&&!disposed)onResult(blob,'madar-send-qr.png','image');},'image/png');}});
   if(controller?.signal.aborted)msg('أُوقف الإرسال.');
  }catch(e){if(e.name!=='AbortError'&&!controller?.signal.aborted)msg(e.message);else msg('أُوقف الإرسال.');}
  finally{controller=null;if(!disposed){q('#p2pRun').textContent='أنشئ رمز الإرسال';q('#p2pFile').disabled=false;}}};
 const picker=mountFilePicker(q('#p2pFile'),{accept:spec.mime});
 return{pick(){picker.open();},dispose(){disposed=true;picker.dispose();controller?.abort();}};
}

// Opens the receive screen when the page URL carries #get=<id>.
export function startReceiveFromLocation(){
 const m=/^#get=([a-f0-9]{32})$/.exec(location.hash);if(!m||typeof RTCPeerConnection==='undefined')return;
 history.replaceState(null,'',location.pathname+location.search);
 const dialog=document.createElement('dialog');dialog.className='p2p-dialog';dialog.innerHTML='<div class="dialog-head"><h2>استلام ملف</h2><button type="button" class="icon-button p2p-close" aria-label="إغلاق">×</button></div><p class="notice" role="status">نجهز الاستلام…</p><p class="p2p-name"></p><progress max="100" value="0" hidden></progress><div class="p2p-result"></div>';
 document.body.append(dialog);const status=dialog.querySelector('[role=status]'),bar=dialog.querySelector('progress'),abort=new AbortController();let url;
 dialog.querySelector('.p2p-close').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{abort.abort();if(url)setTimeout(()=>URL.revokeObjectURL(url),60000);dialog.remove();});dialog.showModal();
 receiveFile(m[1],{abort:abort.signal,report:t=>status.textContent=t,onMeta:meta=>{dialog.querySelector('.p2p-name').textContent=meta.name+' · '+size(meta.size);bar.hidden=false;status.textContent='يستلم…';},onProgress:(got,total)=>{bar.value=Math.round(got/total*100);status.textContent='يستلم · '+bar.value+'٪';}})
 .then(({blob,name,type})=>{url=URL.createObjectURL(blob);const box=dialog.querySelector('.p2p-result'),items=[];
  if(type.startsWith('image/')){const img=document.createElement('img');img.src=url;img.alt=name;img.className='design-preview';items.push(img);}
  else if(type.startsWith('video/')||type.startsWith('audio/')){const media=document.createElement(type.startsWith('video/')?'video':'audio');media.src=url;media.controls=true;media.className='design-preview';items.push(media);}
  const a=document.createElement('a');a.href=url;a.download=name;a.className='button full';a.textContent='حفظ الملف في جهازك';items.push(a);box.replaceChildren(...items);bar.hidden=true;status.textContent='وصل الملف كاملًا ✓';})
 .catch(e=>{if(!abort.signal.aborted)status.textContent=e.message;});
}
