// Netlify-only static delivery: framing policy, cache rules and the offline service worker.
export const FFMPEG_CORE_VERSION='0.12.10';
export const SW_SHELL=['/','/app.js','/app.css','/ffmpeg-worker.js','/pdf-worker.js','/manifest.webmanifest','/icon.svg','/apple-touch-icon.png','/licenses.html','/fonts/Amiri-Regular.ttf','/fonts/Amiri-Bold.ttf','/fonts/DejaVuSans.ttf','/fonts/DejaVuSans-Bold.ttf'];
const REVALIDATE='no-cache',IMMUTABLE='public, max-age=31536000, immutable';
export const STATIC_CACHE={'/':REVALIDATE,'/index.html':REVALIDATE,'/app.js':REVALIDATE,'/app.css':REVALIDATE,'/ffmpeg-worker.js':REVALIDATE,'/pdf-worker.js':REVALIDATE,'/manifest.webmanifest':REVALIDATE,'/licenses.html':REVALIDATE,'/privacy.html':REVALIDATE,'/terms.html':REVALIDATE,'/icon.svg':REVALIDATE,'/apple-touch-icon.png':REVALIDATE,'/sw.js':REVALIDATE,'/Madar_Colab_Separation.ipynb':REVALIDATE,'/fonts/*':'public, max-age=604800','/runtime/*':IMMUTABLE};
// The Netlify site is never embedded by another site; the ChatGPT Sites build keeps its own policy.
export function netlifySecurity(security){const out={...security};if(out['Content-Security-Policy'])out['Content-Security-Policy']=out['Content-Security-Policy'].replace(/frame-ancestors [^;]*/,"frame-ancestors 'none'");
 // «دبلج» records the visitor's voice, so this site (and only this site) may ask for the microphone.
 if(out['Permissions-Policy'])out['Permissions-Policy']=out['Permissions-Policy'].replace(/microphone=\([^)]*\)/,'microphone=(self)');return out;}
export function netlifyStaticHeaders(security){const{['Cache-Control']:_,...base}=netlifySecurity(security);return '/*\n'+Object.entries(base).map(([k,v])=>'  '+k+': '+v).join('\n')+'\n  X-Robots-Tag: noindex, nofollow\n'+Object.entries(STATIC_CACHE).map(([path,value])=>path+'\n  Cache-Control: '+value).join('\n')+'\n';}
export function renderServiceWorker(source,version,shell=SW_SHELL,core=FFMPEG_CORE_VERSION){if(!/^[a-f0-9]{16}$/.test(version)||!/^\d+\.\d+\.\d+$/.test(core))throw Error('Invalid service worker version');return source.replaceAll('__VERSION__',version).replaceAll('__CORE__',core).replace('__SHELL__',JSON.stringify(shell));}
