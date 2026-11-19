// MIME families make mobile pickers open the relevant media category.
const mimeByExtension={m4b:'audio/mp4',aiff:'audio/aiff',aif:'audio/aiff',wma:'audio/x-ms-wma',amr:'audio/amr',ac3:'audio/ac3',eac3:'audio/eac3',mp2:'audio/mpeg',alac:'audio/mp4',mpg:'video/mpeg','3gp':'video/3gpp','3g2':'video/3gpp2',m4v:'video/mp4',ts:'video/mp2t',m2ts:'video/mp2t',mts:'video/mp2t',vob:'video/mpeg',wmv:'video/x-ms-wmv',flv:'video/x-flv',ogv:'video/ogg',jpg:'image/jpeg',jpeg:'image/jpeg',png:'image/png',webp:'image/webp',heic:'image/heic',heif:'image/heif',gif:'image/gif',pdf:'application/pdf',mp4:'video/mp4',mkv:'video/x-matroska',mov:'video/quicktime',webm:'video/webm',avi:'video/x-msvideo',mpeg:'video/mpeg',mp3:'audio/mpeg',m4a:'audio/mp4',aac:'audio/aac',wav:'audio/wav',flac:'audio/flac',ogg:'audio/ogg',opus:'audio/opus',srt:'application/x-subrip',vtt:'text/vtt',txt:'text/plain'};
export function pickerAccept(accept=''){
 const types=[...new Set(accept.split(',').map(x=>x.trim().toLowerCase()).filter(Boolean).map(x=>x.startsWith('.')?mimeByExtension[x.slice(1)]||x:x))];
 for(const family of ['image','video','audio'])if(types.some(t=>t.startsWith(family+'/'))){for(let i=types.length-1;i>=0;i--)if(types[i].startsWith(family+'/'))types.splice(i,1);types.push(family+'/*');}
 return types.join(',');
}
export function acceptsFile(file,accept=''){
 if(!accept)return true;const ext=file.name.split('.').pop().toLowerCase(),mime=file.type?.toLowerCase()||mimeByExtension[ext]||'';
 return accept.split(',').some(token=>{const t=token.trim().toLowerCase();return t.startsWith('.')?ext===t.slice(1):t.endsWith('/*')?(mime.startsWith(t.slice(0,-1))||(mimeByExtension[ext]||'').startsWith(t.slice(0,-1))):mime===t||mimeByExtension[ext]===t;});
}
export function requireAccepted(files,accept){if(files.some(f=>!acceptsFile(f,accept)))throw Error('نوع الملف لا يناسب هذه الأداة. اختر '+(pickerAccept(accept)==='image/*'?'صورة':pickerAccept(accept)==='video/*'?'فيديو':pickerAccept(accept)==='application/pdf'?'ملف PDF':'ملفًا من الأنواع المطلوبة')+'.');}
export function pickerKinds(accept=''){
 const tokens=pickerAccept(accept).split(',').filter(Boolean),groups=[];
 for(const[type,label,filter]of [['image','صورة','image/*'],['video','فيديو','video/*'],['audio','صوت','audio/*'],['pdf','PDF','application/pdf']])if(tokens.includes(filter))groups.push({type,label,accept:filter});
 const rest=tokens.filter(t=>!['image/*','video/*','audio/*','application/pdf'].includes(t));if(rest.length)groups.push({type:'document',label:'ملف نص أو ترجمة',accept:rest.join(',')});return groups;
}
export function fileKind(file){const ext=file.name.split('.').pop().toLowerCase(),t=(file.type||mimeByExtension[ext]||'').toLowerCase();return t.startsWith('video/')?'video':t.startsWith('audio/')?'audio':t.startsWith('image/')?'image':t==='application/pdf'?'pdf':'document';}
const KIND_LABEL={video:'فيديو',audio:'صوت',image:'صورة',pdf:'PDF',document:'ملف'};
const sizeText=n=>n>=1073741824?(n/1073741824).toFixed(2)+' GB':n>=1048576?(n/1048576).toFixed(1)+' MB':Math.max(1,Math.round(n/1024))+' KB';
// A clear "your file is attached" card: what was picked, its type and size, and a way to change it.
export function pickedCard(files,onChange){
 const card=document.createElement('div');card.className='picked-card';card.setAttribute('role','status');
 const mark=document.createElement('span');mark.className='picked-mark';mark.textContent='✓';
 const text=document.createElement('div');text.className='picked-text';const name=document.createElement('b');name.textContent=files.length>1?files.length+' ملفات جاهزة':files[0].name;name.title=files.map(f=>f.name).join('\n');
 const meta=document.createElement('small');const total=files.reduce((n,f)=>n+f.size,0);meta.textContent=(files.length>1?files.map(f=>f.name).slice(0,3).join('، ')+(files.length>3?'…':''):'تم إرفاق '+KIND_LABEL[fileKind(files[0])])+' · '+sizeText(total);text.append(name,meta);card.append(mark,text);
 if(onChange){const change=document.createElement('button');change.type='button';change.className='text-btn picked-change';change.textContent='تغيير';change.onclick=e=>{e.preventDefault();onChange();};card.append(change);}
 return card;
}
// After a file is picked, bring the main button into view so the next step is obvious.
export function revealAction(from){setTimeout(()=>{if(!from?.isConnected)return;const root=from.closest('dialog')||document.body;const next=[...root.querySelectorAll('button.button.full:not(.secondary):not([hidden])')].find(b=>b.offsetParent&&!b.disabled&&(from.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING));(next||from).scrollIntoView({behavior:'smooth',block:next?'end':'nearest'});},280);}
export function openNativePicker(input,accept){input.accept=pickerAccept(accept);if(input.disabled)return;try{if(typeof input.showPicker==='function'){input.showPicker();return;}}catch{}input.click();}
export function mountFilePicker(input,{accept=input.accept}={}){
 const label=input.closest('label');if(label)label.hidden=true;else input.hidden=true;
 const panel=document.createElement('div');panel.className='typed-picker';const kinds=pickerKinds(accept),heading=document.createElement('p');heading.textContent=kinds.length>1?'اختر نوع الملف':'اختر '+(kinds[0]?.label||'ملفك');panel.append(heading);const actions=document.createElement('div');actions.className='typed-picker-actions';panel.append(actions);let selected=accept;
 const choose=kind=>{selected=kind.accept;openNativePicker(input,selected);};
 for(const kind of kinds){const b=document.createElement('button');b.type='button';b.className='button secondary';b.textContent='اختيار '+kind.label;b.onclick=e=>{e.preventDefault();if(!input.disabled)choose(kind);};actions.append(b);}
 const status=document.createElement('p');status.className='micro';status.setAttribute('role','status');panel.append(status);(label||input).after(panel);
 let card=null;const reopen=()=>{if(kinds.length===1)choose(kinds[0]);else{card?.remove();card=null;heading.hidden=actions.hidden=false;actions.querySelector('button')?.focus({preventScroll:true});}};
 const validate=e=>{try{requireAccepted([...input.files],selected);status.textContent='';}catch(error){input.value='';status.textContent=error.message;e.stopImmediatePropagation();}};input.addEventListener('change',validate,true);
 const picked=()=>{const list=[...input.files];card?.remove();card=null;if(!list.length){heading.hidden=actions.hidden=false;return;}heading.hidden=actions.hidden=true;card=pickedCard(list,reopen);panel.prepend(card);panel.classList.add('has-file');input.dispatchEvent(new CustomEvent('madar:picked',{detail:{kind:fileKind(list[0]),files:list}}));revealAction(panel);};input.addEventListener('change',picked);
 return{open(){if(kinds.length===1)choose(kinds[0]);else{actions.querySelector('button')?.focus({preventScroll:true});panel.scrollIntoView({block:'nearest'});}},reset(){card?.remove();card=null;heading.hidden=actions.hidden=false;panel.classList.remove('has-file');},dispose(){input.removeEventListener('change',validate,true);input.removeEventListener('change',picked);panel.remove();}};
}
