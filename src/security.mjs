export const SECURITY_HEADERS={
'Content-Security-Policy':"default-src 'none'; script-src 'self' 'wasm-unsafe-eval' https://accounts.google.com/gsi/client; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; worker-src 'self' blob:; connect-src 'self' https://accounts.google.com/gsi/; frame-src https://accounts.google.com/gsi/; font-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; upgrade-insecure-requests",
'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cross-Origin-Resource-Policy':'same-origin','Cross-Origin-Opener-Policy':'same-origin-allow-popups','Permissions-Policy':'camera=(), microphone=(), geolocation=(), payment=(), usb=()'
};
export const HEADERS={...SECURITY_HEADERS,'Cache-Control':'private, no-store'};
export const FFMPEG_CORE_VERSION='0.12.10';
const REVALIDATE='no-cache',IMMUTABLE='public, max-age=31536000, immutable';
export const STATIC_CACHE={'/':REVALIDATE,'/index.html':REVALIDATE,'/app.js':REVALIDATE,'/app.css':REVALIDATE,'/ffmpeg-worker.js':REVALIDATE,'/pdf-worker.js':REVALIDATE,'/manifest.webmanifest':REVALIDATE,'/licenses.html':REVALIDATE,'/icon.svg':REVALIDATE,'/sw.js':REVALIDATE,'/fonts/*':'public, max-age=604800','/runtime/*':IMMUTABLE};
export function staticHeaders(){return '/*\n'+Object.entries(SECURITY_HEADERS).map(([k,v])=>'  '+k+': '+v).join('\n')+'\n'+Object.entries(STATIC_CACHE).map(([path,value])=>path+'\n  Cache-Control: '+value).join('\n')+'\n';}
export class SafeError extends Error{constructor(message,status=400,code='INVALID_REQUEST'){super(message);this.status=status;this.code=code;}}
export async function bounded(request,max){const size=Number(request.headers.get('content-length'));if(size>max)throw new SafeError('الطلب أكبر من الحد المسموح',413);const r=request.body?.getReader();if(!r)throw new SafeError('طلب فارغ');const chunks=[];let n=0;while(true){const v=await r.read();if(v.done)break;n+=v.value.length;if(n>max){await r.cancel();throw new SafeError('الطلب أكبر من الحد المسموح',413);}chunks.push(v.value);}const out=new Uint8Array(n);let at=0;for(const c of chunks){out.set(c,at);at+=c.length;}return out;}
export async function jsonBody(r,max=3*1048576){if(!r.headers.get('content-type')?.startsWith('application/json'))throw new SafeError('صيغة الطلب غير صالحة');try{return JSON.parse(new TextDecoder().decode(await bounded(r,max)));}catch(e){if(e instanceof SafeError)throw e;throw new SafeError('طلب غير صالح');}}
export const reply=(body,status=200)=>Response.json(body,{status,headers:HEADERS});

export function renderServiceWorker(source,version,shell,core){if(!/^[a-f0-9]{16}$/.test(version)||!/^\d+\.\d+\.\d+$/.test(core))throw Error('Invalid service worker version');return source.replaceAll('__VERSION__',version).replaceAll('__CORE__',core).replace('__SHELL__',JSON.stringify(shell));}
