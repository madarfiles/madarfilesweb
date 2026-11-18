import {MEDIA_INPUTS,AUDIO_OUTPUTS,VIDEO_OUTPUTS} from './media-formats.js';
import {sourceName} from './output-names.js';
import {validateCloudConfig} from './cloud-catalog.js';
import {downloadURL} from './colab-core.js';
import {PublicError,boundedBody} from './cloud-server.js';
import {jobSource,engineSource,downloadSource,cloudSource,serviceSource,fontSource,captionSource} from './colab-sources.js';
const rawUnavailable=new Map(),runtimeCaches=new WeakMap();
const PROJECT='madarfiles',BASE='https://colaboratory.googleapis.com/';
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
const OWN=/^runtimes\/madarweb-[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
const EXTS=MEDIA_INPUTS;
export function allocationFailure(error){const reason=(error?.details||[]).map(d=>d.reason).find(r=>typeof r==='string'&&/^[A-Z][A-Z0-9_]{0,99}$/.test(r));return reason||([8,9].includes(error?.code)?'RESOURCE_LIMIT_OR_UNAVAILABLE':'ASSIGNMENT_REJECTED');}
// Every Colab tool the page may address; must include each cloudCatalog task.
export const COLAB_TOOLS=['separate','download','ocr','cutout','word','asr','translate','burn','convert','resize','imagegen','videogen','dub'];
export const WARM_TOOLS=['separate','dub','asr','translate'];
export function warmCode(tool){if(!WARM_TOOLS.includes(tool))throw new PublicError('أداة غير صالحة');return `import subprocess, sys\nfrom pathlib import Path\nroots=[Path.cwd()/'madar_web',Path('/content/madar_web'),Path('/madar_web'),Path('/root/madar_web')]\np=next((d for d in roots if (d/'service.py').is_file()),None)\nif p is not None and not (p/'warm-${tool}.json').exists():\n subprocess.Popen([sys.executable,'-u',str(p/'service.py'),'warm','${tool}'],cwd=str(p),stdout=open(p/'warm.log','a'),stderr=subprocess.STDOUT,start_new_session=True)\n`;}
export function gpuSpecs(response){return (response.runtimeSpecs||[]).filter(s=>s.eligible===true&&s.key?.variant==='VARIANT_GPU'&&s.key.shape==='SHAPE_STANDARD'&&['T4','L4','A100'].includes(s.key.accelerator)).map(s=>s.key).sort((a,b)=>['T4','L4','A100'].indexOf(a.accelerator)-['T4','L4','A100'].indexOf(b.accelerator));}
export function runtimeURL(value){let u;try{u=new URL(value);}catch{throw new PublicError('عنوان جلسة Colab غير صالح',502);}if(u.protocol!=='https:'||u.username||u.password||u.port||u.search||u.hash||!u.hostname.includes('.')||u.hostname.includes(':')||/^[\d.]+$/.test(u.hostname)||/\.(local|localhost|internal|invalid)\.?$/.test(u.hostname)||u.hostname.endsWith('.'))throw new PublicError('عنوان جلسة Colab غير صالح',502);if(!u.pathname.endsWith('/'))u.pathname+='/';return u;}
export function validateConfig(b){try{const cloud=validateCloudConfig(b);if(cloud)return cloud;}catch(e){throw new PublicError(e.message);}if(b.task==='download'){try{return{task:'download',url:downloadURL(b.url)};}catch(e){throw new PublicError(e.message);}}if(b.outputFormat!==undefined&&!(b.mode==='video'?VIDEO_OUTPUTS:AUDIO_OUTPUTS).some(o=>o[0]===b.outputFormat))throw new PublicError('صيغة الناتج لا تناسب نوع الملف');if(!EXTS.includes(b.ext)||!Number.isSafeInteger(b.size)||b.size<1||b.size>512*1048576||b.chunks!==Math.ceil(b.size/(2*1048576))||! /^[a-f0-9]{64}$/.test(b.sha256)||!['audio','video'].includes(b.mode)||!Number.isFinite(b.start)||b.start<0||b.start>604800||!Number.isFinite(b.duration)||b.duration<0||b.duration>604800)throw new PublicError('إعدادات الملف أو الجزء غير صالحة');return{...(b.outputFormat!==undefined?{outputFormat:b.outputFormat}:{}),...(b.sourceName!==undefined?{sourceName:sourceName(b.sourceName)}:{}),ext:b.ext,size:b.size,chunks:b.chunks,sha256:b.sha256,mode:b.mode,start:b.start,duration:b.duration};}
async function rejectRedirect(r){if(r.status>=300&&r.status<400){await r.body?.cancel();throw new PublicError('رُفض تحويل اتصال Colab إلى عنوان آخر لحماية تصريح الحساب',502);}}
function advice(status,body){const reasons=(body?.error?.details||[]).map(d=>d.reason);const known={SERVICE_DISABLED:'فعّل Colab API في مشروع madarfiles ثم أعد الاتصال',SERVICE_NOT_VISIBLE:'مشروع madarfiles غير مصرح له بخدمة Colab؛ يلزم السماح له من Google',ACCESS_TOKEN_SCOPE_INSUFFICIENT:'لم تُمنح صلاحية Colab؛ أعد الاتصال ووافق عليها',USER_PROJECT_DENIED:'حساب Google المحدد لا يملك صلاحية استخدام مشروع madarfiles',CONSUMER_INVALID:'تحقق من معرّف مشروع Google Cloud وإعداد الخدمة'};for(const code of reasons)if(known[code])return known[code]+' · '+code;return status===401?'انتهى تصريح Google؛ اضغط الاتصال مجددًا':status===403?'رفضت Google الطلب؛ تحقق من حساب الاختبار وصلاحية Colab بالمشروع':status===429?'وصل حسابك إلى حد الموارد أو الطلبات؛ أعد المحاولة لاحقًا':status===404?'الجلسة أو الملف غير موجود؛ قد تكون جلسة Colab انتهت':'تعذرت خدمة Colab · HTTP '+status;}
async function readJSON(r,max=1048576){try{return JSON.parse(new TextDecoder().decode(await boundedBody(r,max)));}catch(e){if(e instanceof PublicError)throw e;throw new PublicError('استجابة Colab غير صالحة',502);}}
export function kernelMessage(data){
 let text=data;
 if(typeof data!=='string'){
  const bytes=data instanceof ArrayBuffer?new Uint8Array(data):ArrayBuffer.isView(data)?new Uint8Array(data.buffer,data.byteOffset,data.byteLength):null;
  if(!bytes||bytes.byteLength<8||bytes.byteLength>1048576)throw new PublicError('إطار محرك Colab غير صالح · WS_FRAME_SIZE',502);
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),count=view.getUint32(0,false);
  if(count<1||count>64||4*(count+1)>bytes.byteLength)throw new PublicError('إطار محرك Colab غير صالح · WS_FRAME_FORMAT',502);
  let previous=4*(count+1);const offsets=[];for(let i=0;i<count;i++){const at=view.getUint32(4+i*4,false);if(at<previous||at>bytes.byteLength)throw new PublicError('إطار محرك Colab غير صالح · WS_FRAME_FORMAT',502);offsets.push(at);previous=at;}
  text=new TextDecoder('utf-8',{fatal:true}).decode(bytes.subarray(offsets[0],count===1?bytes.byteLength:offsets[1]));
 }
 if(text.length>1048576)throw new PublicError('رد محرك Colab أكبر من الحد · WS_FRAME_SIZE',502);
 return JSON.parse(text);
}
export async function execute(ws,code,signal,session=crypto.randomUUID()){
 const id=crypto.randomUUID();
 return new Promise((resolve,reject)=>{
  let done=false;const transport=(code)=>{const e=new PublicError('تعذر تأكيد بدء المحرك · '+code,502);e.kernelCode=code;e.retryable=true;return e;};
  const finish=(err)=>{if(done)return;done=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);try{ws.close(1000,'done');}catch{}err?reject(err):resolve();};
  const abort=()=>finish(new PublicError('أُلغي الانتظار؛ استرجع الجلسة للتحقق من المهمة',409));
  const timer=setTimeout(()=>finish(transport('WS_ACK_TIMEOUT')),12000);
  signal?.addEventListener('abort',abort,{once:true});
  ws.addEventListener('message',ev=>{if(done)return;try{const m=kernelMessage(ev.data);if(m.parent_header?.msg_id!==id||m.header?.msg_type!=='execute_reply')return;if(m.content?.status==='ok')finish();else{const known={AssertionError:'PY_SOURCE_PATH',FileNotFoundError:'PY_FILE_NOT_FOUND',PermissionError:'PY_PERMISSION',ModuleNotFoundError:'PY_MODULE_MISSING',SyntaxError:'PY_SYNTAX'};finish(new PublicError('تعذر إطلاق محرك الفصل · '+(known[m.content?.ename]||'PY_EXECUTION'),502));}}catch{finish(transport('WS_FRAME_FORMAT'));}});
  ws.addEventListener('error',()=>finish(transport('WS_ERROR')));
  ws.addEventListener('close',ev=>finish(transport('WS_CLOSED_'+(Number.isInteger(ev.code)&&ev.code>=1000&&ev.code<=4999?ev.code:0))));
  try{ws.accept();if(signal?.aborted){abort();return;}ws.send(JSON.stringify({header:{msg_id:id,username:'madar',session,date:new Date().toISOString(),msg_type:'execute_request',version:'5.3'},parent_header:{},metadata:{},channel:'shell',content:{code,silent:true,store_history:false,user_expressions:{},allow_stdin:false,stop_on_error:true},buffers:[]}));}catch{finish(transport('WS_SEND'));}
 });
}
const delay=(ms,signal)=>new Promise((resolve,reject)=>{if(signal.aborted){reject(new PublicError('أُلغي الانتظار',409));return;}const onAbort=()=>{clearTimeout(t);reject(new PublicError('أُلغي الانتظار',409));};const t=setTimeout(()=>{signal.removeEventListener('abort',onAbort);resolve();},ms);signal.addEventListener('abort',onAbort,{once:true});});
export async function colabAPI(request,security={},fetcher=fetch,context=null){
 let runtimeConnections=runtimeCaches.get(fetcher);if(!runtimeConnections){runtimeConnections=new Map();runtimeCaches.set(fetcher,runtimeConnections);}
 const controller=new AbortController(),disconnect=()=>controller.abort();
 const incoming=request.signal;
 if(incoming?.aborted)controller.abort();
 else incoming?.addEventListener?.('abort',disconnect,{once:true});
 const timer=setTimeout(disconnect,45000),signal=controller.signal;
 let stage='request';
 const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{...security,'Content-Type':'application/json; charset=utf-8','Cache-Control':'private, no-store'}});
 try{
  const action=new URL(request.url).pathname.slice('/api/colab/'.length);
  if(!['check','create','operation','stop','prepare','upload','run','status','download','closeall','pulse','sessions','config','warm'].includes(action))throw new PublicError('غير موجود',404);
  if(request.method!=='POST')throw new PublicError('طريقة غير مسموحة',405);
  if(!request.headers.get('oai-authenticated-user-id'))throw new PublicError('سجّل الدخول إلى مدار أولًا',401);
  if(request.headers.get('Origin')!==new URL(request.url).origin)throw new PublicError('مصدر الطلب غير مسموح',403);
  if(!request.headers.get('Content-Type')?.startsWith('application/json'))throw new PublicError('صيغة الطلب غير صالحة');
  const b=await readJSON(request,3*1048576);
  if(b.jobId!==undefined&&!UUID.test(b.jobId))throw new PublicError('معرّف عملية غير صالح');
  const jobPath=b.jobId?'madar_web/jobs/'+b.jobId:'madar_web';
  const token=b.googleToken;delete b.googleToken;
  if(typeof token!=='string'||!/^[A-Za-z0-9._~+\/-]{20,16384}$/.test(token))throw new PublicError('اتصل بحساب Google أولًا',401);
  const cloud=async(method,path,body)=>{stage=path==='v1beta/subscription'?'subscription':path==='v1beta/runtimespecs'?'gpu-eligibility':path==='v1beta/runtimes'?'sessions':'runtime-control';const r=await fetcher(BASE+path,{method,headers:{Authorization:'Bearer '+token,'X-Goog-User-Project':PROJECT,Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,redirect:'manual',signal});await rejectRedirect(r);if(!r.ok){let data={};try{data=await readJSON(r);}catch{}throw new PublicError(advice(r.status,data),[401,403,404,429].includes(r.status)?r.status:502);}return r.status===204?{}:readJSON(r);};
  if(action==='closeall'){
   if(!Array.isArray(b.runtimes)||b.runtimes.length>32||b.runtimes.some(n=>!OWN.test(n)))throw new PublicError('قائمة الجلسات غير صالحة');
   const runtimes=[...new Set(b.runtimes)];const cleanup=async()=>{const closed=[],failed=[];await Promise.all(runtimes.map(async name=>{try{const c=new AbortController(),t=setTimeout(()=>c.abort(),12000);try{const r=await fetcher(BASE+'v1beta/'+name+'?allowMissing=true',{method:'DELETE',headers:{Authorization:'Bearer '+token,'X-Goog-User-Project':PROJECT},redirect:'manual',signal:c.signal});await r.body?.cancel();if(r.ok)closed.push(name);else failed.push(name);}finally{clearTimeout(t);}}catch{failed.push(name);}}));return{closed,failed};};
   // A keepalive request must outlive the closed browser connection.
   const work=cleanup();if(context?.waitUntil&&b.background===true){context.waitUntil(work);return json({accepted:true},202);}return json(await work);
  }
  if(action==='sessions'){const r=await cloud('GET','v1beta/runtimes');return json({runtimes:(r.runtimes||[]).filter(r=>OWN.test(r.name)).map(r=>r.name)});}
  if(action==='check'){const subscription=await cloud('GET','v1beta/subscription'),allSpecs=await cloud('GET','v1beta/runtimespecs'),specs=gpuSpecs(allSpecs),cpu=(allSpecs.runtimeSpecs||[]).find(s=>s.eligible===true&&s.key?.variant==='VARIANT_CPU'&&s.key.shape==='SHAPE_STANDARD')?.key||null,runtimes=await cloud('GET','v1beta/runtimes');return json({activeTotal:(runtimes.runtimes||[]).length,tier:subscription.tier||'UNKNOWN',specs,cpu,highMemorySpecs:(allSpecs.runtimeSpecs||[]).filter(s=>s.eligible===true&&s.key?.variant==='VARIANT_GPU'&&s.key.shape==='SHAPE_HIGHMEM').map(s=>s.key),runtimes:(runtimes.runtimes||[]).filter(r=>OWN.test(r.name)).map(r=>({name:r.name,gpu:r.runtimeSpec?.accelerator,shape:r.runtimeSpec?.shape}))});}
  if(action==='create'){
   if(!UUID.test(b.id)||!UUID.test(b.requestId)||!['T4','L4','A100','CPU'].includes(b.gpu))throw new PublicError('طلب جلسة غير صالح');
   const available=await cloud('GET','v1beta/runtimespecs'),spec=b.gpu==='CPU'?(available.runtimeSpecs||[]).find(s=>s.eligible===true&&s.key?.variant==='VARIANT_CPU'&&s.key.shape==='SHAPE_STANDARD')?.key:b.highMemory===true?(available.runtimeSpecs||[]).find(s=>s.eligible===true&&s.key?.variant==='VARIANT_GPU'&&s.key.shape==='SHAPE_HIGHMEM'&&s.key.accelerator===b.gpu)?.key:gpuSpecs(available).find(s=>s.accelerator===b.gpu);if(!spec)throw new PublicError('لا يوجد GPU من النوع المختار مؤهل لحسابك حاليًا',409);
   const op=await cloud('POST','v1beta/runtimes?runtimeId=madarweb-'+b.id+'&requestId='+b.requestId,{runtimeSpec:spec});return json({name:op.name,done:!!op.done,failed:!!op.error,failureCode:op.error?allocationFailure(op.error):undefined});
  }
  if(action==='operation'){if(typeof b.operation!=='string'||!/^operations\/[A-Za-z0-9_/-]{1,300}$/.test(b.operation))throw new PublicError('معرّف انتظار غير صالح');const op=await cloud('GET','v1/'+b.operation);return json({done:!!op.done,failed:!!op.error,failureCode:op.error?allocationFailure(op.error):undefined});}
  if(!OWN.test(b.runtime))throw new PublicError('جلسة مدار غير صالحة');
  if(action==='stop'){for(const key of runtimeConnections.keys())if(key.startsWith(b.runtime+':'))runtimeConnections.delete(key);await cloud('DELETE','v1beta/'+b.runtime+'?allowMissing=true');return json({stopped:true});}
  // Only trust connection addresses returned by Google's authenticated API for this user's runtime.
  const tokenHash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(token))),x=>x.toString(16).padStart(2,'0')).join('');
  const connectionKey=b.runtime+':'+tokenHash;
  const getRuntime=async(refresh=false)=>{let item=runtimeConnections.get(connectionKey);if(refresh||!item||item.until<Date.now()){
   const pending=cloud('GET','v1beta/'+b.runtime);item={pending,until:Date.now()+15000};if(runtimeConnections.size>=64)runtimeConnections.clear();runtimeConnections.set(connectionKey,item);
   pending.catch(()=>{if(runtimeConnections.get(connectionKey)===item)runtimeConnections.delete(connectionKey);});
  }const value=await item.pending;if(value.name!==b.runtime)throw new PublicError('معرّف الجلسة لا يطابق حسابك',502);return value;};
  let runtime=await getRuntime();
  const connection=()=>{const info=runtime.connectionInfo;if(!info?.url||!info.token)throw new PublicError('جلسة Colab ما زالت تتهيأ؛ أعد المحاولة',409);return{base:runtimeURL(info.url),headers:{'X-Colab-Runtime-Proxy-Token':info.token,'X-Colab-Client-Agent':'madarfiles-web'}};};
  let {base,headers}=connection();
  const jup=async(method,path,data)=>{stage='jupyter';for(let attempt=0;;attempt++){
   const r=await fetcher(new URL(path,base).href,{method,headers:{...headers,...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined,redirect:'manual',signal});await rejectRedirect(r);
   if([401,403].includes(r.status)&&attempt===0){await r.body?.cancel();runtime=await getRuntime(true);({base,headers}=connection());continue;}
   if(!r.ok){await r.body?.cancel();if([401,403].includes(r.status))throw new PublicError('تعذر تصريح اتصال هذه الجلسة بعد تجديده؛ أعد الاتصال بالجسلة · RUNTIME_PROXY_AUTH',409);throw new PublicError(advice(r.status,{}),r.status===404?404:502);}return r.status===204?{}:readJSON(r,4*1048576);
  }};
  const allowedTools=COLAB_TOOLS;
  if(b.tool!==undefined){if(!allowedTools.includes(b.tool))throw new PublicError('أداة غير صالحة');let owner;try{const f=await jup('GET','api/contents/madar_web/tool.json?content=1&format=text');owner=JSON.parse(f.content).tool;}catch(e){if(e.status!==404)throw e;}
   if(owner&&owner!==b.tool)throw new PublicError('هذه الجلسة تخص أداة أخرى',409);
   if(!owner){if(action!=='prepare')throw new PublicError('هيّئ جلسة مستقلة لهذه الأداة أولًا',409);await jup('PUT','api/contents/madar_web',{type:'directory'});await jup('PUT','api/contents/madar_web/tool.json',{type:'file',format:'text',content:JSON.stringify({tool:b.tool})});}
  }
  if(action==='config'){const file=await jup('GET','api/contents/'+jobPath+'/config.json?content=1&format=text');return json(validateConfig(JSON.parse(file.content)));}
  if(action==='pulse'){await jup('PUT','api/contents/madar_web/lease.json',{type:'file',format:'text',content:JSON.stringify({updated:Date.now()/1000})});return json({alive:true});}
  const put=(file,content,format='text')=>jup('PUT','api/contents/'+jobPath+'/'+file,{type:'file',format,content});
  // Early preparation: while the file uploads, the session installs the tool's libraries and
  // downloads its models in the background. Best effort: a failure here never blocks the tool.
  const warmTool=async(kernelId,tool,limit)=>{const stop=AbortSignal.any([signal,AbortSignal.timeout(limit)].filter(Boolean));try{
   const session=crypto.randomUUID();const r=await fetcher(new URL('api/kernels/'+kernelId+'/channels?session_id='+session,base).href,{headers:{...headers,Origin:base.origin,Upgrade:'websocket'},redirect:'manual',signal:stop});
   if(r.status>=300&&r.status<400||!r.webSocket){await r.body?.cancel?.();return false;}
   await execute(r.webSocket,warmCode(tool),stop,session);return true;
  }catch{return false;}};
  if(action==='prepare'){const ks=await jup('GET','api/kernelspecs');const name=ks.default||'python3';if(!/^[A-Za-z0-9_.-]{1,80}$/.test(name))throw new PublicError('محرك Python غير صالح',502);const list=await jup('GET','api/kernels');const kernel=Array.isArray(list)&&list.find(k=>k.name===name&&k.execution_state!=='dead')||await jup('POST','api/kernels',{name});if(!/^[A-Za-z0-9-]{1,100}$/.test(kernel.id))throw new PublicError('معرّف Python غير صالح',502);await jup('PUT','api/contents/madar_web',{type:'directory'});if(b.jobId){await jup('PUT','api/contents/madar_web/jobs',{type:'directory'});await jup('PUT','api/contents/'+jobPath,{type:'directory'});}await Promise.all([['runner.py',jobSource],['madar_colab_runtime.py',engineSource],['madar_download.py',downloadSource],['madar_cloud_tasks.py',cloudSource],['service.py',serviceSource],['madar_captions.py',captionSource],...(['asr','burn'].includes(b.tool)?[['madar_fonts.py',fontSource]]:[])].map(([name,content])=>jup('PUT','api/contents/madar_web/'+name,{type:'file',format:'text',content})));if(b.tool)await jup('PUT','api/contents/madar_web/lease.json',{type:'file',format:'text',content:JSON.stringify({updated:Date.now()/1000})});return json({kernel:kernel.id,gpu:runtime.runtimeSpec?.variant==='VARIANT_CPU'?'CPU':runtime.runtimeSpec?.accelerator,shape:runtime.runtimeSpec?.shape});}
  // Early preparation runs in its own request (never inside prepare: a slow kernel channel there
  // pushed prepare past Netlify's 30 s limit and broke every tool). Hard cap 15 s, best effort.
  if(action==='warm'){if(!WARM_TOOLS.includes(b.tool)||typeof b.kernel!=='string'||!/^[A-Za-z0-9-]{1,100}$/.test(b.kernel))throw new PublicError('طلب غير صالح');const ok=await warmTool(b.kernel,b.tool,15000);return json({started:ok});}
  if(action==='upload'){if(!Number.isSafeInteger(b.index)||b.index<0||b.index>255||typeof b.data!=='string'||b.data.length>2796204||! /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(b.data)||!b.data)throw new PublicError('جزء رفع غير صالح');const part='input_'+String(b.index).padStart(5,'0')+'.bin';
   // 404 here means a stale connection address or a job folder that is gone: refresh the
   // runtime address, recreate the folders, and try the part once more.
   try{await put(part,b.data,'base64');}catch(e){if(e.status!==404)throw e;runtime=await getRuntime(true);({base,headers}=connection());for(const dir of ['madar_web','madar_web/jobs',jobPath])await jup('PUT','api/contents/'+dir,{type:'directory'});await put(part,b.data,'base64');}
   return json({uploaded:b.index});}
  if(action==='run'){
   const stateFile='api/contents/'+jobPath+'/state.json?content=1&format=text';
   const currentState=async()=>{try{const file=await jup('GET',stateFile);const state=JSON.parse(file.content);if(['queued','setup','gpu','separating','downloading','processing','done','error'].includes(state.state))return state;throw new PublicError('حالة محرك الفصل غير صالحة',502);}catch(e){if(e.status===404)return null;throw e;}};
   const existing=await currentState();if(existing&&existing.state!=='queued')return json({started:true,state:existing.state});
   let cfg;if(b.ext===undefined&&(!b.task||b.task==='separate')){try{const file=await jup('GET','api/contents/'+jobPath+'/config.json?content=1&format=text');cfg=validateConfig(JSON.parse(file.content));}catch(e){if(e.status===404)throw new PublicError('رفع الملف لم يكتمل في هذه الجلسة؛ أنهِها ثم اختر الملف مجددًا',409);throw e;}}else cfg=validateConfig(b);
   if(b.tool&&(cfg.task||'separate')!==b.tool)throw new PublicError('العملية لا تخص هذه الأداة',409);
   let kernel=b.kernel;if(kernel!==undefined&&!/^[A-Za-z0-9-]{1,100}$/.test(kernel))throw new PublicError('معرّف Python غير صالح');
   const kernels=await jup('GET','api/kernels');
   kernel=Array.isArray(kernels)&&(kernels.find(k=>k.id===kernel&&k.execution_state!=='dead')||kernels.find(k=>k.name==='python3'&&k.execution_state!=='dead'))?.id;
   if(!kernel){const made=await jup('POST','api/kernels',{name:'python3'});kernel=made.id;}
   if(!/^[A-Za-z0-9-]{1,100}$/.test(kernel))throw new PublicError('محرك Python غير متاح',502);
   await put('config.json',JSON.stringify(cfg));
   // Upgrade the runner in existing uploaded sessions without uploading media again.
   if(!b.jobId)await Promise.all([put('runner.py',jobSource),put('madar_colab_runtime.py',engineSource),put('madar_download.py',downloadSource),put('madar_cloud_tasks.py',cloudSource)]);
   const legacyCode="import subprocess, sys\nfrom pathlib import Path\ncandidates=[Path.cwd()/'madar_web',Path('/content/madar_web'),Path('/madar_web'),Path('/root/madar_web')]\np=next((d for d in candidates if (d/'runner.py').is_file() and (d/'config.json').is_file()),None)\nassert p is not None\nif not (p/'started.lock').exists():\n subprocess.Popen([sys.executable,'-u',str(p/'runner.py')],cwd=str(p),stdout=open(p/'job.log','a'),stderr=subprocess.STDOUT,start_new_session=True)\n";
   const code=b.jobId?`import subprocess, sys\nfrom pathlib import Path\nroots=[Path.cwd()/'madar_web',Path('/content/madar_web'),Path('/madar_web'),Path('/root/madar_web')]\np=next((d for d in roots if (d/'service.py').is_file()),None)\nassert p is not None\njob=p/'jobs'/'${b.jobId}'\n(job/'ready').touch()\nsubprocess.Popen([sys.executable,'-u',str(p/'service.py')],cwd=str(p),stdout=open(p/'bootstrap.log','a'),stderr=subprocess.STDOUT,start_new_session=True)\n`:legacyCode;
   if(b.jobId)await put('state.json',JSON.stringify({state:'queued',message:'العملية في انتظار عامل الجلسة المشتركة…',updated:Date.now()/1000}));
   let last;
   for(let attempt=0;attempt<2;attempt++){
    last=null;
    if(attempt){const fresh=await cloud('GET','v1beta/'+b.runtime);if(fresh.name!==b.runtime||!fresh.connectionInfo?.url||!fresh.connectionInfo.token)throw new PublicError('تعذر تجديد اتصال الجلسة',502);base=runtimeURL(fresh.connectionInfo.url);headers={'X-Colab-Runtime-Proxy-Token':fresh.connectionInfo.token,'X-Colab-Client-Agent':'madarfiles'};}
    try{
     const session=crypto.randomUUID();stage='kernel-start';
     const r=await fetcher(new URL('api/kernels/'+kernel+'/channels?session_id='+session,base).href,{headers:{...headers,Origin:base.origin,Upgrade:'websocket'},redirect:'manual',signal});
     await rejectRedirect(r);if(!r.webSocket){await r.body?.cancel();const e=new PublicError('تعذر فتح قناة محرك Colab · WS_HTTP_'+r.status,502);e.retryable=[401,403,429,500,502,503,504].includes(r.status);throw e;}
     await execute(r.webSocket,code,signal,session);
     // The job's status file is authoritative, even when the websocket closes after launch.
    }catch(e){last=e;if(signal.aborted)throw e;}
    for(let poll=0;poll<6;poll++){const state=await currentState();if(state)return json({started:true,state:state.state});await delay(500,signal);}
    if(last&&!last.retryable)throw last;
   }
   if(last)throw last;throw new PublicError('وصل أمر التشغيل لكن لم يظهر تقدم المحرك · WORKER_NOT_STARTED؛ استرجع الجلسة لإعادة التحقق',502);
  }
  if(action==='status'){try{const [file,healthFile]=await Promise.all([jup('GET','api/contents/'+jobPath+'/state.json?content=1&format=text'),b.jobId?jup('GET','api/contents/madar_web/service.json?content=1&format=text').catch(()=>null):null]);const state=JSON.parse(file.content);if(!['queued','setup','gpu','separating','downloading','processing','done','error'].includes(state.state)||typeof state.message!=='string')throw new Error();if(b.jobId){try{const health=healthFile?JSON.parse(healthFile.content):{};state.service={heartbeat:health.heartbeat,state:health.state,activeJob:health.activeJob};}catch{}}return json(state);}catch(e){if(e.status===404)return json({state:'waiting',message:'لم يبدأ المحرك بعد؛ إذا اكتمل الرفع اضغط بدء الفصل'});throw e;}}
  if(action==='download'){if(b.artifact!==undefined&&b.artifact!=='captions')throw new PublicError('ملف نتيجة غير صالح');const outputPrefix=b.artifact==='captions'?'captions':'output';if(!Number.isSafeInteger(b.index)||b.index<0||b.index>127)throw new PublicError('جزء تنزيل غير صالح');if(b.binary===true&&(rawUnavailable.get(b.runtime)||0)<Date.now()){
   try{
    stage='result-file';const r=await fetcher(new URL('files/'+jobPath+'/'+outputPrefix+'_'+String(b.index).padStart(5,'0')+'.bin?download=1',base).href,{headers,redirect:'manual',signal});
    if(r.status===200&&r.headers.get('Content-Type')?.startsWith('application/octet-stream')){
     const bytes=await boundedBody(r,2*1048576);if(!bytes.length)throw new PublicError('جزء نتيجة فارغ',502);
     return new Response(bytes,{headers:{...security,'Content-Type':'application/octet-stream','Cache-Control':'private, no-store','Content-Length':String(bytes.length)}});
    }
    await r.body?.cancel();if([200,301,302,303,307,308,400,403,404,405].includes(r.status)){if(rawUnavailable.size>=64)rawUnavailable.clear();rawUnavailable.set(b.runtime,Date.now()+300000);}
   }catch(e){if(signal.aborted||e instanceof PublicError&&e.status===413)throw e;}
  }
  const file=await jup('GET','api/contents/'+jobPath+'/'+outputPrefix+'_'+String(b.index).padStart(5,'0')+'.bin?content=1&format=base64');if(file.format!=='base64'||typeof file.content!=='string')throw new PublicError('جزء تنزيل غير صالح',502);if(b.binary===true){const raw=atob(file.content.replace(/\s/g,''));if(!raw.length||raw.length>2*1048576)throw new PublicError('حجم جزء تنزيل غير صالح',502);const bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);return new Response(bytes,{headers:{...security,'Content-Type':'application/octet-stream','Cache-Control':'private, no-store','Content-Length':String(bytes.length)}});}return json({data:file.content});}
  throw new PublicError('غير موجود',404);
 }catch(e){const code=e instanceof PublicError?'COLAB_HTTP_'+e.status:signal.aborted?'COLAB_TIMEOUT':['TypeError','SyntaxError','RangeError'].includes(e?.name)?'COLAB_'+e.name.toUpperCase():'COLAB_CONNECTION';return json({error:(e instanceof PublicError?e.message:signal.aborted?'انتهت مهلة الاتصال بـColab؛ أعد المحاولة أو استرجع الجلسة':'تعذر اتصال Colab أثناء '+stage)+' · '+code,code,stage},e instanceof PublicError?e.status:502);
 }finally{clearTimeout(timer);incoming?.removeEventListener?.('abort',disconnect);}
}
