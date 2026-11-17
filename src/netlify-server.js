import {cloudAPI} from './cloud-server.js';
import {colabAPI} from './colab-server.js';
import {driveAPI} from './drive-server.js';
export function trustedRequest(request,user){const headers=new Headers(request.headers);for(const key of [...headers.keys()])if(key.startsWith('oai-authenticated-'))headers.delete(key);headers.set('oai-authenticated-user-id',user.id);if(user.email)headers.set('oai-authenticated-user-email',user.email);return new Request(request,{headers});}
export function createNetlifyHandler({authenticate,fetcher=fetch,security={}}){return async(request,context={})=>{
 const reply=(body,status=200)=>Response.json(body,{status,headers:{...security,'Cache-Control':'private, no-store'}});
 try{const user=await authenticate(request,context);if(!user?.id)return reply({error:'سجّل الدخول بحساب مدعو أولًا'},401);const path=new URL(request.url).pathname;if(path==='/api/session')return reply({authenticated:true,provider:user.provider||'netlify'});const secure=trustedRequest(request,user);if(path.startsWith('/api/colab/'))return colabAPI(secure,security,fetcher,context);if(path.startsWith('/api/drive/'))return driveAPI(secure,security,fetcher);return cloudAPI(secure,security,fetcher);}catch{return reply({error:'تعذر التحقق من الدخول؛ أعد تسجيل الدخول'},401);}
};}
