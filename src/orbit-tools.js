const PAGE=6,STEP=2*Math.PI/PAGE,SEAM=Math.PI/2;
export function orbitPage(items,page){const pages=Math.max(1,Math.ceil(items.length/PAGE)),index=((page%pages)+pages)%pages;return{items:items.slice(index*PAGE,(index+1)*PAGE),page:index,pages,total:items.length};}
const mod=(a,n)=>((a%n)+n)%n;
// Which tools sit on the wheel for a rotation angle. Six seats; with more than six tools the wheel
// never ends: at one quiet spot (the bottom) the tool leaving fades out while the next one fades
// in, so turning the wheel walks through every tool in both directions.
export function orbitSlots(count,phase){
 if(!count)return[];
 if(count<=PAGE)return Array.from({length:count},(_,i)=>({index:i,key:i,angle:phase+2*Math.PI*i/count,weight:1}));
 const u=-phase/STEP,b=Math.floor(u),f=u-b,out=[];
 for(let k=b;k<=b+PAGE;k++){const weight=k===b?1-f:k===b+PAGE?f:1;out.push({index:mod(k,count),key:k,angle:phase+k*STEP+SEAM,weight});}
 return out;
}
export function orbitRange(count,phase){if(!count)return'لا توجد نتائج';if(count<=PAGE)return'1–'+count+' من '+count;const first=mod(Math.round(-phase/STEP),count);return(first+1)+'–'+(mod(first+PAGE-1,count)+1)+' من '+count;}
export function mountOrbit(root,{icon,onOpen,onPick}){
 let items=[],phase=0,paused=matchMedia('(prefers-reduced-motion: reduce)').matches,hover=false,keyboard=false,frame=0,lastTime=0,diameter=0,glide=null,lastRange='';
 // One gesture at a time: 'turn' rotates the wheel with the finger, 'carry' lifts a tool to drop on
 // the centre, 'scroll' hands the finger back to the page.
 let gesture=null;
 root.className='orbit-workspace';root.innerHTML='<div class="orbit-heading"><span class="orbit-live"><i></i> مساحة أدواتك</span><span class="orbit-total"></span></div><div class="tools-orbit" role="group" aria-label="مدار الأدوات؛ دوّره بإصبعك"><div class="orbit-track track-outer"></div><div class="orbit-track track-inner"></div><div class="orbit-glow"></div><button class="orbit-hub" aria-label="اختيار ملف للبدء"><span class="hub-mark">م</span><b>مدار</b><small>ارمِ الأداة هنا</small></button><div class="orbit-nodes"></div></div><div class="orbit-toolbar"><button class="orbit-previous" aria-label="الأدوات السابقة">→</button><p class="orbit-range" aria-live="polite"></p><button class="orbit-next" aria-label="الأدوات التالية">←</button><button class="orbit-pause" aria-label="إيقاف دوران الأدوات"></button></div><p class="orbit-caption">دوّر المدار بإصبعك، واضغط الأداة أو اسحبها للمركز.</p>';
 const q=s=>root.querySelector(s),stage=q('.tools-orbit'),nodes=q('.orbit-nodes'),hub=q('.orbit-hub');hub.onclick=()=>{if(!gesture)onPick();};
 const pool=new Map();
 function button(tool){let b=pool.get(tool.id);if(b)return b;b=document.createElement('button');b.className='orbit-tool';b.dataset.category=tool.cat;b.dataset.tool=tool.id;b.setAttribute('aria-label',tool.title+'، '+tool.desc);b.title=tool.title+' — '+tool.desc;const glyph=document.createElement('span');glyph.className='orbit-glyph';glyph.innerHTML=icon(tool.icon);const title=document.createElement('strong');title.textContent=tool.title;const tag=document.createElement('span');tag.className='orbit-tag';tag.textContent=tool.experimental?'تجريبي':tool.cloud?'سحابي':'محلي';b.append(glyph,title,tag);b.onclick=()=>{if(gesture)return;onOpen(tool.id);};pool.set(tool.id,b);return b;}
 function position(){
  if(!diameter)diameter=stage.clientWidth;const width=diameter<410?84:diameter<520?98:112,radius=(diameter-width)/2-9;
  const slots=orbitSlots(items.length,phase),shown=new Set();
  for(const s of slots){const tool=items[s.index];if(!tool)continue;const b=button(tool);if(shown.has(b))continue;shown.add(b);if(b.parentNode!==nodes&&nodes.append)nodes.append(b);
   if(gesture?.mode==='carry'&&gesture.button===b)continue;
   const w=Math.max(0,Math.min(1,s.weight));b.style.transform='translate(-50%,-50%) translate('+(Math.cos(s.angle)*radius).toFixed(1)+'px,'+(Math.sin(s.angle)*radius).toFixed(1)+'px) scale('+(0.55+0.45*w).toFixed(3)+')';b.style.opacity=w.toFixed(3);b.style.pointerEvents=w<.5?'none':'';b.style.width=width+'px';b.style.height=width+'px';}
  for(const b of pool.values())if(!shown.has(b)&&!(gesture?.mode==='carry'&&gesture.button===b)){if(b.parentNode===nodes)b.remove?.();}
  const range=orbitRange(items.length,phase);if(range!==lastRange){lastRange=range;q('.orbit-range').textContent=range;}
 }
 function paint(){if(nodes.replaceChildren)nodes.replaceChildren();pool.clear();q('.orbit-total').textContent=items.length+' أداة في مدارك';q('.orbit-previous').disabled=q('.orbit-next').disabled=items.length<=PAGE;q('.orbit-pause').textContent=paused?'تشغيل الدوران':'إيقاف الدوران';q('.orbit-pause').setAttribute('aria-pressed',String(paused));stage.hidden=!items.length;lastRange='';position();}
 // Arrows turn the wheel by a full set of six, smoothly.
 const turn=by=>{glide={from:phase,to:phase+by,began:performance.now(),ms:650};};
 q('.orbit-previous').onclick=()=>turn(STEP*PAGE);q('.orbit-next').onclick=()=>turn(-STEP*PAGE);q('.orbit-pause').onclick=()=>{paused=!paused;q('.orbit-pause').textContent=paused?'تشغيل الدوران':'إيقاف الدوران';q('.orbit-pause').setAttribute('aria-pressed',String(paused));};
 stage.addEventListener('pointerenter',e=>{hover=e.pointerType==='mouse'&&matchMedia('(hover: hover)').matches;});stage.addEventListener('pointerleave',()=>{hover=false;});stage.addEventListener('keydown',e=>{if(e.key==='Tab'||e.key.startsWith('Arrow'))keyboard=true;if(e.key==='ArrowLeft')turn(-STEP);if(e.key==='ArrowRight')turn(STEP);});stage.addEventListener('focusout',()=>keyboard=false);
 const centre=()=>{const r=stage.getBoundingClientRect?.();return r?{x:r.left+r.width/2,y:r.top+r.height/2,r:r.width/2}:{x:0,y:0,r:200};};
 const angleAt=(x,y,c)=>Math.atan2(y-c.y,x-c.x);
 stage.addEventListener('pointerdown',e=>{keyboard=false;if(e.pointerType!=='mouse')hover=false;if(e.button>0)return;glide=null;const c=centre();const target=e.target?.closest?.('.orbit-tool');gesture={id:e.pointerId,mode:null,c,x0:e.clientX,y0:e.clientY,x:e.clientX,y:e.clientY,a:angleAt(e.clientX,e.clientY,c),button:target||null,moved:false,v:0,t:performance.now()};});
 stage.addEventListener('pointermove',e=>{const g=gesture;if(!g||g.id!==e.pointerId)return;const dx=e.clientX-g.x0,dy=e.clientY-g.y0;
  if(!g.mode){if(Math.hypot(dx,dy)<9)return;
   // Split the movement into "around the centre" and "towards/away from the centre".
   const rx=g.x0-g.c.x,ry=g.y0-g.c.y,len=Math.hypot(rx,ry)||1,radial=Math.abs((dx*rx+dy*ry)/len),around=Math.abs((dx*-ry+dy*rx)/len);
   if(g.button&&radial>around*0.8)g.mode='carry';else if(around>=radial*0.9)g.mode='turn';else g.mode='scroll';
   g.moved=true;try{stage.setPointerCapture?.(e.pointerId);}catch{}
   if(g.mode==='carry'){g.button.classList?.add('carrying');hub.classList?.add('waiting');}}
  if(g.mode==='turn'){const a=angleAt(e.clientX,e.clientY,g.c);let d=a-g.a;if(d>Math.PI)d-=2*Math.PI;if(d<-Math.PI)d+=2*Math.PI;phase+=d;g.a=a;const now=performance.now();g.v=d/Math.max(8,now-g.t);g.t=now;position();}
  else if(g.mode==='carry'){const r=stage.getBoundingClientRect();g.button.style.transform='translate(-50%,-50%) translate('+(e.clientX-r.left-r.width/2).toFixed(1)+'px,'+(e.clientY-r.top-r.height/2).toFixed(1)+'px) scale(1.08)';const near=Math.hypot(e.clientX-g.c.x,e.clientY-g.c.y)<g.c.r*0.32;hub.classList?.toggle('ready',near);}
  else if(g.mode==='scroll'){globalThis.scrollBy?.(0,g.y-e.clientY);const now=performance.now();g.v=(g.y-e.clientY)/Math.max(8,now-g.t);g.t=now;}
  g.x=e.clientX;g.y=e.clientY;if(e.cancelable)e.preventDefault();},{passive:false});
 const finish=e=>{const g=gesture;if(!g||(e&&e.pointerId!==undefined&&g.id!==undefined&&e.pointerId!==g.id))return;
  if(g.mode==='turn'&&Math.abs(g.v)>0.0015){const v=g.v;glide={spin:v,began:performance.now()};}
  if(g.mode==='scroll'&&Math.abs(g.v)>0.2){let v=g.v*16;const coast=()=>{if(Math.abs(v)<0.5)return;globalThis.scrollBy?.(0,v);v*=0.93;requestAnimationFrame(coast);};requestAnimationFrame(coast);}
  if(g.mode==='carry'){const b=g.button;b.classList?.remove('carrying');hub.classList?.remove('waiting');const dropped=Math.hypot(g.x-g.c.x,g.y-g.c.y)<g.c.r*0.32;hub.classList?.remove('ready');
   if(dropped){const id=b.dataset.tool;b.classList?.add('landing');hub.classList?.add('landed');b.style.transform='translate(-50%,-50%) scale(.35)';b.style.opacity='0';setTimeout(()=>{b.classList?.remove('landing');hub.classList?.remove('landed');gesture=null;position();onOpen(id);},280);return;}
   b.classList?.add('returning');setTimeout(()=>b.classList?.remove('returning'),320);}
  // A drag must not also count as a tap on the tool under the finger.
  if(g.moved)setTimeout(()=>{if(gesture===g)gesture=null;},0);else gesture=null;position();};
 stage.addEventListener('pointerup',finish);stage.addEventListener('pointercancel',finish);stage.addEventListener('lostpointercapture',e=>{if(e.target===stage)finish(e);});
 const observer=new ResizeObserver(()=>{diameter=stage.clientWidth;position();});observer.observe(stage);
 function animate(now){if(!lastTime)lastTime=now;if(now-lastTime>=16){const dt=Math.min(now-lastTime,80);
   if(glide?.to!==undefined){const k=Math.min(1,(now-glide.began)/glide.ms),ease=1-Math.pow(1-k,3);phase=glide.from+(glide.to-glide.from)*ease;if(k>=1)glide=null;position();}
   else if(glide?.spin!==undefined){phase+=glide.spin*dt;glide.spin*=Math.pow(0.94,dt/16);if(Math.abs(glide.spin)<0.00008)glide=null;position();}
   else if(!paused&&!hover&&!keyboard&&!gesture&&!document.hidden&&!document.querySelector('dialog[open]')&&root.getClientRects().length){phase+=dt*0.000065;position();}
   lastTime=now;}frame=requestAnimationFrame(animate);}frame=requestAnimationFrame(animate);
 return{setTools(value){items=value;paint();},dispose(){observer.disconnect();cancelAnimationFrame(frame);}};
}
