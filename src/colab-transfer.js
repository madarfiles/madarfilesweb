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
