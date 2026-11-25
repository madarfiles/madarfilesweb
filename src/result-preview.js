import {validatePreviewArchive} from './archive-security.js';
import {unzipSync,strFromU8} from 'fflate';
import {wireSave,saveBlob} from './save-file.js';
export function archivePreviews(bytes){validatePreviewArchive(bytes);let total=0;const files=unzipSync(bytes,{filter:file=>{const good=/\.(txt|srt|vtt)$/i.test(file.name)||file.name==='word/document.xml';if(!good)return false;if(file.originalSize>2*1048576||total+file.originalSize>8*1048576)throw Error('تجاوزت محتويات المعاينة حد القراءة');total+=file.originalSize;return true;}});return Object.entries(files).map(([name,data])=>({name,text:strFromU8(data)}));}
const activePreviews=new WeakMap();
export async function renderResultPreview(root,{blob,url,name},{documents=[],onSave,signal}={}){
 const host=root;activePreviews.get(host)?.();let disposed=false,loadingTask,renderTask,pdf;
 const destroy=value=>{try{value?.destroy?.()?.catch?.(()=>{});}catch{}};
 const cleanup=()=>{if(disposed)return;disposed=true;signal?.removeEventListener('abort',cleanup);renderTask?.cancel();destroy(loadingTask||pdf);for(const media of root.querySelectorAll('video,audio')){media.pause();media.removeAttribute('src');media.load();}if(activePreviews.get(host)===cleanup)activePreviews.delete(host);};
 activePreviews.set(host,cleanup);signal?.addEventListener('abort',cleanup,{once:true});
 root=document.createElement('div');host.replaceChildren(root);if(signal?.aborted){cleanup();return cleanup;}
 root.className='result-preview-box';const heading=document.createElement('h3');heading.textContent='النتيجة جاهزة للمعاينة';root.replaceChildren(heading);const ext=name.split('.').pop().toLowerCase(),mime=blob.type;
 const link=document.createElement('a');link.href=url;link.download=name;link.className='button full';link.textContent='حفظ النتيجة · '+(blob.size<1048576?Math.ceil(blob.size/1024)+' KB':(blob.size/1048576).toFixed(1)+' MB');link.onclick=()=>onSave?.();wireSave(link,blob,name);
 if(mime.startsWith('image/')||/^(png|jpe?g|webp)$/.test(ext)){const img=document.createElement('img');img.src=url;img.alt='معاينة النتيجة';root.append(img);}
 else if(mime.startsWith('video/')||/^(mp4|mkv|webm|mov)$/.test(ext)){const media=document.createElement('video');media.src=url;media.controls=true;media.preload='metadata';media.setAttribute('playsinline','');media.disablePictureInPicture=true;media.setAttribute('disablepictureinpicture','');media.setAttribute('controlslist','nodownload noremoteplayback');root.append(media);media.addEventListener('error',()=>{const note=document.createElement('p');note.textContent='المتصفح لا يدعم معاينة هذه الصيغة؛ احفظها وافتحها في مشغل مناسب.';root.append(note);},{once:true});}
 else if(mime.startsWith('audio/')||/^(mp3|m4a|wav|flac|ogg)$/.test(ext)){const audio=document.createElement('audio');audio.controls=true;audio.src=url;root.append(audio);}
 else if(ext==='pdf'){
  try{
   const pdfjs=await import('pdfjs-dist/build/pdf.mjs');if(disposed)return cleanup;pdfjs.GlobalWorkerOptions.workerSrc='/pdf-worker.js';const data=await blob.arrayBuffer();if(disposed)return cleanup;
   loadingTask=pdfjs.getDocument({data,isEvalSupported:false,useSystemFonts:true,useWasm:false});pdf=await loadingTask.promise;if(disposed){destroy(pdf);return cleanup;}
   let page=1,painting=false;const canvas=document.createElement('canvas'),controls=document.createElement('div');controls.className='workflow-actions';const prev=document.createElement('button'),next=document.createElement('button'),label=document.createElement('span');prev.textContent='الصفحة السابقة';next.textContent='الصفحة التالية';prev.className=next.className='button secondary';
   const paint=async(target=page)=>{
    if(disposed||painting||target<1||target>pdf.numPages)return;
    painting=true;prev.disabled=next.disabled=true;
    try{
     const p=await pdf.getPage(target);if(disposed)return;const base=p.getViewport({scale:1}),vp=p.getViewport({scale:Math.min(1.4,800/base.width)});
     if(vp.width*vp.height>16000000)throw Error('preview dimensions');
     canvas.width=vp.width;canvas.height=vp.height;renderTask=p.render({canvasContext:canvas.getContext('2d'),viewport:vp});await renderTask.promise;if(disposed)return;page=target;label.textContent=page+' / '+pdf.numPages;
    }catch{if(!disposed)label.textContent='تعذّرت معاينة الصفحة؛ الملف متاح للحفظ.';}
    finally{painting=false;renderTask=null;if(!disposed){prev.disabled=page<=1;next.disabled=page>=pdf.numPages;}}
   };
   prev.onclick=()=>paint(page-1);next.onclick=()=>paint(page+1);controls.append(prev,label,next);root.append(canvas,controls);await paint();if(disposed)return cleanup;
  }catch{if(disposed)return cleanup;const p=document.createElement('p');p.textContent='تعذرت معاينة PDF في هذا المتصفح؛ الملف متاح للحفظ.';root.append(p);}
 }
 let docs=documents;
 if(!docs.length&&['zip','docx'].includes(ext)&&blob.size<16*1048576){try{const bytes=await blob.arrayBuffer();if(disposed)return cleanup;docs=archivePreviews(new Uint8Array(bytes));}catch{const p=document.createElement('p');p.textContent='ملف جاهز للحفظ؛ لم يمكن فتح محتوياته للمعاينة.';root.append(p);}}
 if(!docs.length&&['txt','srt','vtt'].includes(ext))docs=[{name,text:await blob.slice(0,2*1048576).text()}];
 if(disposed)return cleanup;
 for(const doc of docs){const box=document.createElement('details'),summary=document.createElement('summary'),text=document.createElement('textarea');summary.textContent=doc.name;box.open=docs.length<=2;text.readOnly=true;text.dir='auto';let value=doc.text;if(doc.name==='word/document.xml'){const xml=new DOMParser().parseFromString(value,'application/xml');value=[...xml.getElementsByTagNameNS('*','p')].map(p=>p.textContent).join('\n');summary.textContent='معاينة نص Word؛ التخطيط الكامل داخل الملف';}text.value=value;box.append(summary,text);if(doc.name!=='word/document.xml'){const save=document.createElement('button');save.className='button secondary';save.textContent='حفظ '+doc.name;save.onclick=()=>saveBlob(new Blob([doc.text],{type:'text/plain;charset=utf-8'}),doc.name.split('/').pop());box.append(save);}root.append(box);}
 if(!docs.length&&!root.querySelector('video,audio,img,canvas')){const p=document.createElement('p');p.textContent='هذا النوع يُراجع في التطبيق الذي يدعمه بعد الحفظ.';root.append(p);}root.append(link);return cleanup;
}
