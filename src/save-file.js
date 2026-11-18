// Saving results on iPhone/iPad: Safari (and above all the home-screen app) often shows
// «تنزيل؟» for a blob link and then saves nothing. The share sheet works everywhere on iOS
// and offers «حفظ الفيديو» (Photos) and «حفظ في الملفات», so iOS saves through it; other
// systems keep the normal download link.
export const isIOS=()=>/iP(hone|ad|od)/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
function shareable(blob,name){if(!isIOS()||!navigator.canShare)return null;try{const file=new File([blob],name,{type:blob.type||'application/octet-stream'});return navigator.canShare({files:[file]})?file:null;}catch{return null;}}
export function wireSave(link,blob,name){if(typeof link.addEventListener!=='function')return link;link.addEventListener('click',e=>{const file=shareable(blob,name);if(!file)return;e.preventDefault();navigator.share({files:[file]}).catch(err=>{if(err?.name==='AbortError')return;const a=document.createElement('a');a.href=link.href;a.download=name;document.body.append(a);a.click();a.remove();});});return link;}
export async function saveBlob(blob,name,url){const file=shareable(blob,name);if(file){try{await navigator.share({files:[file]});return 'shared';}catch(e){if(e?.name==='AbortError')return 'cancelled';}}
 const own=!url;const href=url||URL.createObjectURL(blob);const a=document.createElement('a');a.href=href;a.download=name;a.rel='noopener';document.body.append(a);a.click();a.remove();if(own)setTimeout(()=>URL.revokeObjectURL(href),60000);return 'downloaded';}
