const PART=2*1048576;
const abortError=()=>new DOMException('توقف التنزيل','AbortError');
const hex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');
const sleep=(ms,signal)=>new Promise((resolve,reject)=>{if(signal.aborted)return reject(abortError());const cancel=()=>{clearTimeout(t);reject(abortError());};const t=setTimeout(()=>{signal.removeEventListener('abort',cancel);resolve();},ms);signal.addEventListener('abort',cancel,{once:true});});
// Three in-flight parts at most. Only checksummed parts enter the reusable page-memory cache.
export async function downloadParts(state,fetchPart,{signal,cache=new Map(),onProgress=()=>{},concurrency=3}={}){
 if(!Number.isSafeInteger(state.size)||state.size<1||state.size>256*1048576||!Array.isArray(state.chunks)||state.chunks.length!==Math.ceil(state.size/PART)||state.chunks.some(x=>! /^(?:[a-f0-9]{64})$/.test(x)))throw Error('بيانات الناتج غير صالحة');
 const controller=new AbortController(),cancel=()=>controller.abort();signal?.addEventListener('abort',cancel,{once:true});if(signal?.aborted)cancel();
 const parts=new Array(state.chunks.length),started=performance.now();let verified=0,transferred=0,next=0,firstError;
 const report=()=>{const elapsed=(performance.now()-started)/1000,rate=elapsed>.05?transferred/elapsed:0;onProgress({bytes:verified,total:state.size,percent:100*verified/state.size,bytesPerSecond:rate,remainingSeconds:rate>0?Math.ceil((state.size-verified)/rate):null});};
 const valid=async(index,bytes)=>bytes instanceof Uint8Array&&bytes.length===Math.min(PART,state.size-index*PART)&&hex(await crypto.subtle.digest('SHA-256',bytes))===state.chunks[index];
 try{
  for(let i=0;i<parts.length;i++){if(controller.signal.aborted)throw abortError();const bytes=cache.get(i);if(bytes&&await valid(i,bytes)){parts[i]=bytes;verified+=bytes.length;}else cache.delete(i);}
  report();
  async function work(){while(next<parts.length){if(controller.signal.aborted)throw abortError();const index=next++;if(parts[index])continue;for(let attempt=0;;attempt++){
   try{const bytes=await fetchPart(index,controller.signal);if(controller.signal.aborted)throw abortError();if(!await valid(index,bytes)){const e=Error('لم يصل جزء التنزيل بشكل سليم');e.code='HASH_MISMATCH';throw e;}if(controller.signal.aborted)throw abortError();cache.set(index,bytes);parts[index]=bytes;verified+=bytes.length;transferred+=bytes.length;report();break;
   }catch(e){const retryable=e?.code==='HASH_MISMATCH'||e instanceof TypeError||[408,429,500,502,503,504].includes(e.status);if(controller.signal.aborted||attempt>=2||!retryable){firstError??=e;controller.abort();throw e;}await sleep(Math.max(400*(attempt+1),Math.min(15000,e.retryAfterMs||0)),controller.signal);}
  }}}
  const results=await Promise.allSettled(Array.from({length:Math.min(parts.length,Math.max(1,Math.min(3,concurrency)))},work));
  if(firstError)throw firstError;const failed=results.find(r=>r.status==='rejected');if(failed)throw failed.reason;if(verified!==state.size)throw Error('حجم الناتج غير مكتمل');return parts;
 }finally{signal?.removeEventListener('abort',cancel);}
}

// Direct transfers with the visitor's own Drive (hidden Madar app folder): the file goes from
// the device to Google at the device's full speed, and Colab picks it up inside Google's
// network; results come back the same way. Netlify is not on this path at all.
const DRIVE_UPLOAD='https://www.googleapis.com/upload/drive/v3/files',DRIVE_FILES='https://www.googleapis.com/drive/v3/files';
function driveError(status,code='DRIVE'){const e=Error('تعذر النقل عبر Google Drive');e.status=status;e.code=code;return e;}
function putChunk(url,bytes,range,signal,onLoaded){return new Promise((resolve,reject)=>{const x=new XMLHttpRequest();x.open('PUT',url);x.setRequestHeader('Content-Range',range);x.upload.onprogress=e=>onLoaded(e.loaded);x.onload=()=>resolve({status:x.status,range:x.getResponseHeader('Range'),body:x.responseText});x.onerror=()=>reject(driveError(0,'NETWORK'));x.ontimeout=()=>reject(driveError(0,'TIMEOUT'));const stop=()=>{x.abort();reject(abortError());};if(signal){if(signal.aborted)return stop();signal.addEventListener('abort',stop,{once:true});}x.timeout=180000;x.send(bytes);});}
// Returns the Drive file id and the same 2 MB part hashes the Colab job verifies.
export async function driveUpload(file,token,{name,signal,onProgress=()=>{}}={}){
 const start=await fetch(DRIVE_UPLOAD+'?uploadType=resumable&fields=id',{method:'POST',signal,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json; charset=UTF-8','X-Upload-Content-Type':'application/octet-stream','X-Upload-Content-Length':String(file.size)},body:JSON.stringify({name,parents:['appDataFolder']})});
 const url=start.headers.get('Location');if(!start.ok||!url||!url.startsWith(DRIVE_UPLOAD))throw driveError(start.status,'START');
 const STEP=4*PART,hashes=new Array(Math.ceil(file.size/PART)),began=performance.now();let offset=0;
 const report=done=>{const elapsed=(performance.now()-began)/1000,rate=elapsed>.3?done/elapsed:0;onProgress({bytes:done,total:file.size,percent:100*done/file.size,bytesPerSecond:rate,remainingSeconds:rate>0?Math.ceil((file.size-done)/rate):null});};
 report(0);let result=null;
 while(offset<file.size){
  const end=Math.min(file.size,offset+STEP),bytes=new Uint8Array(await file.slice(offset,end).arrayBuffer());
  for(let p=offset/PART;p*PART<end;p++)hashes[p]=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes.subarray(p*PART-offset,Math.min(end,(p+1)*PART)-offset)));
  let sent=offset,attempt=0;
  for(;;){
   let r;try{r=await putChunk(url,bytes.subarray(sent-offset),`bytes ${sent}-${end-1}/${file.size}`,signal,loaded=>report(sent+loaded));}catch(e){if(e.name==='AbortError'||attempt++>=3)throw e;r=null;}
   if(r&&(r.status===200||r.status===201)){result=JSON.parse(r.body||'{}');sent=end;break;}
   if(r&&r.status===308){const got=/bytes=0-(\d+)/.exec(r.range||'');
    // Some browsers can't read Google's Range header; a 308 after a full chunk means it was stored
    // (Colab still verifies every part's hash, so a wrong guess can't corrupt the result).
    const next=got?Number(got[1])+1:(r.range==null?end:sent);if(next>=end){sent=end;break;}if(attempt++>=3)throw driveError(308,'INCOMPLETE');sent=Math.max(offset,next);continue;}
   if(r&&![408,429,500,502,503,504].includes(r.status))throw driveError(r.status,'CHUNK');
   if(attempt>3)throw driveError(r?.status||0,'RETRIES');onRetry('جزء '+sent+'-'+(end-1)+' · '+(r?'HTTP '+r.status:'انقطع الاتصال'));await sleep(800*attempt,signal||new AbortController().signal);
   // Ask Google how much it has, then continue from there.
   const q=await putChunk(url,new Uint8Array(0),`bytes */${file.size}`,signal,()=>{}).catch(()=>null);const got=/bytes=0-(\d+)/.exec(q?.range||'');sent=Math.min(end,Math.max(offset,got?Number(got[1])+1:offset));if(q&&(q.status===200||q.status===201)){result=JSON.parse(q.body||'{}');sent=end;break;}
  }
  offset=end;report(offset);
 }
 if(!result?.id||!/^[A-Za-z0-9_-]{10,200}$/.test(result.id))throw driveError(0,'NO_ID');
 if(hashes.some(h=>!h))throw driveError(0,'HASH');
 return {id:result.id,hashes};
}
export function driveFetchPart(fileId,token,size){return async(index,signal)=>{const a=index*PART,b=Math.min(size,a+PART)-1;const r=await fetch(DRIVE_FILES+'/'+encodeURIComponent(fileId)+'?alt=media',{headers:{Authorization:'Bearer '+token,Range:`bytes=${a}-${b}`},signal});if(!(r.status===206||r.status===200&&size<=PART)){const e=driveError(r.status,'PART');await r.body?.cancel?.();throw e;}return new Uint8Array(await r.arrayBuffer());};}
export function driveDelete(fileId,token){return fetch(DRIVE_FILES+'/'+encodeURIComponent(fileId),{method:'DELETE',headers:{Authorization:'Bearer '+token}}).catch(()=>{});}
