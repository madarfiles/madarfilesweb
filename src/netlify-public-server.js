import {boundedBody} from './cloud-server.js';
import {createNetlifyHandler} from './netlify-server.js';
import {handleP2P} from './p2p-server.js';

// Public visitors bring their own provider credentials. The digest is only an
// isolation namespace; authorization is still checked by Google/Groq upstream.
export function createPublicHandler({fetcher=fetch,security={},p2pStore}={}) {
 return async(request,context={})=>{
  const reply=(body,status=200)=>Response.json(body,{status,headers:{...security,'Cache-Control':'private, no-store'}});
  const url=new URL(request.url),path=url.pathname;
  if(path==='/api/session')return request.method==='GET'?reply({authenticated:false,access:'public'}):reply({error:'طريقة غير مسموحة'},405);
  if(!path.startsWith('/api/colab/')&&!path.startsWith('/api/drive/')&&!path.startsWith('/api/p2p/')&&!['/api/transcribe','/api/translate'].includes(path))return reply({error:'غير موجود'},404);
  if(request.method!=='POST')return reply({error:'طريقة غير مسموحة'},405);
  if(request.headers.get('Origin')!==url.origin)return reply({error:'مصدر الطلب غير مسموح'},403);
  if(path.startsWith('/api/p2p/')){
   // Direct transfer needs no account: only short-lived connection descriptions are stored.
   if(!p2pStore)return reply({error:'الإرسال المباشر غير متاح في هذه الاستضافة'},503);
   if(!request.headers.get('Content-Type')?.startsWith('application/json'))return reply({error:'صيغة غير صالحة'},400);
   try{const body=JSON.parse(new TextDecoder().decode(await boundedBody(request,65536)));const[status,data]=await handleP2P(path.slice(9),body,typeof p2pStore==='function'?p2pStore():p2pStore);return reply(data,status);}
   catch(error){return reply({error:error?.status===413?'الطلب أكبر من الحد المسموح':'طلب غير صالح'},error?.status===413?413:400);}
  }
  let credential,provider,forward=request;
  try {
   if(path.startsWith('/api/colab/')||path.startsWith('/api/drive/')){
    if(!request.headers.get('Content-Type')?.startsWith('application/json'))return reply({error:'صيغة غير صالحة'},400);
    const bytes=await boundedBody(request,3*1048576),body=JSON.parse(new TextDecoder().decode(bytes));
    provider=path.startsWith('/api/colab/')?'colab':'drive';
    credential=provider==='colab'?body.googleToken:body.driveToken;
    if(typeof credential!=='string'||!/^[A-Za-z0-9._~+\/-]{20,16384}$/.test(credential))return reply({error:'اتصل بحساب Google الخاص بك أولًا'},401);
    forward=new Request(request.url,{method:'POST',headers:request.headers,body:bytes,signal:request.signal});
   }else{
    provider='groq';credential=request.headers.get('X-Madar-Key')||'';
    if(!/^gsk_[A-Za-z0-9_-]{20,200}$/.test(credential))return reply({error:'أدخل مفتاح Groq الخاص بك أولًا'},401);
   }
   const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(credential))),x=>x.toString(16).padStart(2,'0')).join('');
   return createNetlifyHandler({authenticate:async()=>({id:'grant:'+provider+':'+digest,provider}),fetcher,security})(forward,context);
  }catch(error){return reply({error:error?.status===413?'الطلب أكبر من الحد المسموح':'طلب غير صالح'},error?.status===413?413:400);}
 };
}
