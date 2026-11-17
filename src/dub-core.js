// Pure helpers for the «دبلج» tool (no DOM), so they can be tested in Node.

// Finds the time ranges where people speak, from the separated voice track.
// samples: Float32Array (mono), rate: sample rate. Returns [{start,end}] in seconds.
export function detectSegments(samples,rate,{frame=0.03,minGap=0.5,minLength=0.35,pad=0.12,maxLength=12}={}){
 const size=Math.max(1,Math.round(frame*rate)),count=Math.floor(samples.length/size);if(!count)return[];
 const rms=new Float32Array(count);for(let f=0;f<count;f++){let sum=0;const at=f*size;for(let i=0;i<size;i++){const v=samples[at+i];sum+=v*v;}rms[f]=Math.sqrt(sum/size);}
 const sorted=Float32Array.from(rms).sort(),pick=p=>sorted[Math.min(count-1,Math.floor(p*(count-1)))];
 const floor=pick(0.2),peak=pick(0.95);if(peak<0.003)return[];
 const threshold=Math.max(floor*3,peak*0.12,0.004);
 const raw=[];let open=-1;for(let f=0;f<=count;f++){const on=f<count&&rms[f]>threshold;if(on&&open<0)open=f;if(!on&&open>=0){raw.push([open,f]);open=-1;}}
 const merged=[];for(const [a,b] of raw){const last=merged.at(-1);if(last&&(a-last[1])*frame<minGap)last[1]=b;else merged.push([a,b]);}
 const total=samples.length/rate,out=[];
 // Very short blips (a cough, a click) are ignored before padding is added.
 const push=(a,b)=>{if((b-a)*frame<minLength)return;out.push({start:round(Math.max(0,a*frame-pad)),end:round(Math.min(total,b*frame+pad))});};
 for(let [a,b] of merged){
  // Long speeches are split at the quietest moment so each recording stays short.
  while((b-a)*frame>maxLength){const from=a+Math.round(4/frame),to=Math.min(b-1,a+Math.round(maxLength/frame));let cut=from;for(let f=from;f<=to;f++)if(rms[f]<rms[cut])cut=f;push(a,cut);a=cut;}
  push(a,b);}
 // Padding can make neighbours touch; never let two segments overlap.
 const clean=[];for(const s of out){const prev=clean.at(-1);if(prev&&s.start<prev.end)s.start=prev.end;if(s.end-s.start>=minLength)clean.push(s);}
 return clean;
}
const round=n=>Math.round(n*100)/100;

export function clock(seconds){const s=Math.max(0,seconds),m=Math.floor(s/60),r=s-m*60;return m+':'+(r<10?'0':'')+r.toFixed(1);}

// FFmpeg arguments that lay each recording at its start time over the background track
// and keep the original picture. inputs: 0 = video, 1 = background, 2.. = recordings.
export function mixArguments(clips,{output='dubbed.mp4',videoCodec=['-c:v','copy']}={}){
 if(!Array.isArray(clips)||!clips.length)throw Error('سجّل مقطعًا واحدًا على الأقل قبل التصدير');
 const norm='aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo';
 const parts=['[1:a]'+norm+'[bg]'],labels=['[bg]'];
 clips.forEach((clip,i)=>{const ms=Math.max(0,Math.round(clip.start*1000));if(!Number.isFinite(ms))throw Error('توقيت غير صالح');parts.push('['+(i+2)+':a]'+norm+',adelay='+ms+'|'+ms+',volume='+(clip.volume??1).toFixed(2)+'[d'+i+']');labels.push('[d'+i+']');});
 parts.push(labels.join('')+'amix=inputs='+labels.length+':normalize=0:duration=first:dropout_transition=0[mix]');
 const args=['-i','video.bin','-i','background.m4a'];clips.forEach((c,i)=>args.push('-i','rec'+i+'.'+c.ext));
 return [...args,'-filter_complex',parts.join(';'),'-map','0:v:0','-map','[mix]',...videoCodec,'-c:a','aac','-b:a','192k','-movflags','+faststart',output];
}

export const recordingExt=type=>/mp4|aac|m4a/.test(type)?'m4a':/ogg/.test(type)?'ogg':'webm';

// lines.json from Colab: [{start,end,text,words:[{w,s,e}],tr?}] → dubbing lines (invalid entries dropped).
export function readLines(bytes){
 if(!bytes)return {lines:[]};let data;try{data=JSON.parse(new TextDecoder().decode(bytes));}catch{return {lines:[],error:'bad json'};}
 const num=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0,str=v=>typeof v==='string'?v.slice(0,500):'';
 const lines=(Array.isArray(data?.lines)?data.lines:[]).filter(l=>num(l?.start)&&num(l?.end)&&l.end>l.start).slice(0,2000).map(l=>({start:l.start,end:l.end,text:str(l.text),...(l.tr?{tr:str(l.tr)}:{}),words:(Array.isArray(l.words)?l.words:[]).filter(w=>num(w?.s)&&num(w?.e)).slice(0,200).map(w=>({w:str(w.w).slice(0,80),s:w.s,e:w.e}))}));
 lines.sort((a,b)=>a.start-b.start);for(let i=1;i<lines.length;i++)if(lines[i].start<lines[i-1].end)lines[i].start=lines[i-1].end;
 return {lines:lines.filter(l=>l.end-l.start>=0.2),error:data?.error?String(data.error).slice(0,300):undefined,note:str(data?.note),language:str(data?.language)};
}
