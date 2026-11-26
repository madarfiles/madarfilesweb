import {keepReport} from './report-store.js';
import {cloudAPI} from './cloud-server.js';
import {colabAPI} from './colab-server.js';
import {driveAPI} from './drive-server.js';
// Error reports from the page land in the function log (Netlify → Logs) as one JSON line each.
// Only short technical text is kept; nothing identifies the visitor.
const REPORT_KEYS={kind:20,tool:40,message:300,code:60,stage:120,log:4000,page:60,ua:200,at:40};
export async function errorReport(request,security={},store=null){const done=new Response(null,{status:204,headers:{...security,'Cache-Control':'no-store'}});if(request.method!=='POST')return done;try{const text=await request.text();if(text.length>16000)return done;const data=JSON.parse(text),out={};for(const [key,max] of Object.entries(REPORT_KEYS))if(typeof data[key]==='string')out[key]=data[key].slice(-max);if(Number.isFinite(data.status))out.status=Math.trunc(data.status);console.log('MADAR_REPORT '+JSON.stringify(out));if(store)await keepReport(typeof store==='function'?store():store,out).catch(()=>{});}catch{}return done;}
export function trustedRequest(request,user){const headers=new Headers(request.headers);for(const key of [...headers.keys()])if(key.startsWith('oai-authenticated-'))headers.delete(key);headers.set('oai-authenticated-user-id',user.id);if(user.email)headers.set('oai-authenticated-user-email',user.email);return new Request(request,{headers});}
export function createNetlifyHandler({authenticate,fetcher=fetch,security={}}){return async(request,context={})=>{
 const reply=(body,status=200)=>Response.json(body,{status,headers:{...security,'Cache-Control':'private, no-store'}});
 try{const user=await authenticate(request,context);if(!user?.id)return reply({error:'سجّل الدخول بحساب مدعو أولًا'},401);const path=new URL(request.url).pathname;if(path==='/api/session')return reply({authenticated:true,provider:user.provider||'netlify'});if(path==='/api/report')return errorReport(request,security);const secure=trustedRequest(request,user);if(path.startsWith('/api/colab/'))return colabAPI(secure,security,fetcher,context);if(path.startsWith('/api/drive/'))return driveAPI(secure,security,fetcher);return cloudAPI(secure,security,fetcher);}catch{return reply({error:'تعذر التحقق من الدخول؛ أعد تسجيل الدخول'},401);}
};}
