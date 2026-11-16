import{SafeError}from'./security.mjs';
export const PART=2*1048576,MAX=512*1048576,RESULT_MAX=256*1048576;
export const AUDIO=['mp3','m4a','wav','flac','ogg','opus','aac'],VIDEO=['mp4','mkv','mov','webm','avi','ts'];
export const INPUTS=[...AUDIO,...VIDEO,'mpeg','mpg','m4b','aiff','aif','wma','amr','ac3','eac3','mp2','3gp','3g2','m4v','m2ts','mts','vob','wmv','flv','ogv'];
export const MIME={mp3:'audio/mpeg',m4a:'audio/mp4',wav:'audio/wav',flac:'audio/flac',ogg:'audio/ogg',opus:'audio/ogg',aac:'audio/aac',mp4:'video/mp4',mkv:'video/x-matroska',mov:'video/quicktime',webm:'video/webm',avi:'video/x-msvideo',ts:'video/mp2t',png:'image/png',jpg:'image/jpeg',webp:'image/webp',txt:'text/plain;charset=utf-8',srt:'application/x-subrip',zip:'application/zip',pdf:'application/pdf',docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'};
export const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
export const RUNTIME=/^runtimes\/madarweb-[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
export const TASKS=['separate','asr','burn','translate','convert','resize','download','ocr','cutout','word','imagegen','videogen'];
export const LANGS=['auto','ar','en','ja','fr','es','de','tr','ko','zh','ur'];
export function cleanName(name){return String(name||'ملف').normalize('NFC').replace(/[\u0000-\u001f\u007f<>:"/\\|?*\u202a-\u202e\u2066-\u2069]/g,'_').slice(0,100)||'ملف';}
export function outputName(source,ext,task){const suffix={frame:'لقطة',mute:'صامت',audio:'معدل-الصوت',image:'معدل',pdf:'مرتب',imagepdf:'صور',subtitle:'توقيت',original:'أصلي',separate:'بدون-موسيقى',asr:'مفرغ',burn:'مكتوب',translate:'مترجم',convert:'محول',resize:'معدل-المقاس',cutout:'بدون-خلفية',ocr:'النص',word:'وورد'}[task]||'نتيجة';return cleanName(source).replace(/\.[^.]+$/,'')+'-'+suffix+'.'+ext;}
function must(ok,msg='إعدادات العملية غير صالحة'){if(!ok)throw new SafeError(msg);}
const text=(v,max=1500)=>typeof v==='string'&&v.length<=max;
const num=(v,a,b)=>Number.isFinite(v)&&v>=a&&v<=b;
export function mediaURL(value){let u;try{u=new URL(value);}catch{throw new SafeError('رابط غير صالح');}const hosts=['youtube.com','youtu.be','tiktok.com','instagram.com','x.com','twitter.com','facebook.com','fb.watch','vimeo.com','snapchat.com','dailymotion.com','twitch.tv','reddit.com','redd.it','pinterest.com','pin.it'];must(u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&u.pathname!=='/'&&u.href.length<=2000&&hosts.some(h=>u.hostname===h||u.hostname.endsWith('.'+h)),'اختر رابط مقطع عام من منصة مدعومة');u.hash='';return u.href;}
export function validateConfig(b){
must(b&&typeof b==='object'&&TASKS.includes(b.task));const out={task:b.task,sourceName:cleanName(b.sourceName)};
if(!['imagegen','videogen','download'].includes(b.task)){const video=['mp4','mkv','mov','webm','avi','ts','mpeg','mpg','3gp','3g2','m4v','m2ts','mts','vob','wmv','flv','ogv'];const image=['png','jpg','jpeg','webp'];const allowed=({ocr:[...image,'pdf'],word:['pdf'],cutout:image,translate:['txt','srt','vtt'],resize:video,burn:video})[b.task]||INPUTS;must(allowed.includes(b.ext)&&Number.isSafeInteger(b.size)&&b.size>0&&b.size<=MAX&&b.chunks===Math.ceil(b.size/PART)&&/^[a-f0-9]{64}$/.test(b.sha256));Object.assign(out,{ext:b.ext,size:b.size,chunks:b.chunks,sha256:b.sha256});}
if(b.task==='separate'){must(['audio','video'].includes(b.mode));must((b.mode==='audio'?AUDIO:VIDEO).includes(b.format));must(num(b.start,0,604800)&&num(b.duration,0,604800));Object.assign(out,{mode:b.mode,format:b.format,start:b.start,duration:b.duration});}
if(b.task==='convert'){must([...AUDIO,...VIDEO].includes(b.format)&&['high','balanced','small'].includes(b.quality));Object.assign(out,{format:b.format,quality:b.quality});}
if(b.task==='resize'){must(['portrait','landscape','square'].includes(b.ratio)&&['blur','crop','stretch'].includes(b.fit)&&num(b.stretch,0,100));Object.assign(out,{ratio:b.ratio,fit:b.fit,stretch:b.stretch});}
if(b.task==='asr'){must(['transcribe','transcribeTranslate','transcribeBurn','transcribeTranslateBurn'].includes(b.operation));must(LANGS.includes(b.language)&&LANGS.slice(1).includes(b.target));Object.assign(out,{operation:b.operation,language:b.language,target:b.target});}
if(b.task==='translate'){must(LANGS.slice(1).includes(b.source)&&LANGS.slice(1).includes(b.target)&&b.source!==b.target);Object.assign(out,{source:b.source,target:b.target});}
if(b.task==='burn'){must(text(b.subtitles,200000)&&b.subtitles.includes('-->'));out.subtitles=b.subtitles;}
if(['asr','burn'].includes(b.task)){const s=b.style||{};must(num(s.x,0,100)&&num(s.y,0,100)&&num(s.size,1,12)&&/^#[a-f0-9]{6}$/i.test(s.color)&&['sans','serif'].includes(s.font)&&[400,700].includes(s.weight));out.style={x:s.x,y:s.y,size:s.size,color:s.color,font:s.font,weight:s.weight};if(b.logo){must(text(b.logo,1400000)&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(b.logo));must(num(b.logoX,0,100)&&num(b.logoY,0,100)&&num(b.logoSize,2,40));Object.assign(out,{logo:b.logo,logoX:b.logoX,logoY:b.logoY,logoSize:b.logoSize});}}
if(['imagegen','videogen'].includes(b.task)){must(text(b.prompt,1500)&&b.prompt.trim());out.prompt=b.prompt.trim();if(b.task==='videogen'){must([2,5,8].includes(b.seconds));out.seconds=b.seconds;}}
if(b.task==='download')out.url=mediaURL(b.url);
return out;
}
export function specs(data,gpu,highMemory='auto'){const rows=(data.runtimeSpecs||[]).filter(s=>s.eligible===true&&s.key?.variant===(gpu==='CPU'?'VARIANT_CPU':'VARIANT_GPU')&&(gpu==='CPU'||s.key.accelerator===gpu));const shape=highMemory==='high'?'SHAPE_HIGHMEM':'SHAPE_STANDARD';const r=rows.find(s=>s.key.shape===shape)||(highMemory==='auto'?rows[0]:null);if(!r)throw new SafeError('البطاقة مع إعداد الذاكرة المختار غير مؤهلة لحسابك',409,'RESOURCE_UNAVAILABLE');return r.key;}
