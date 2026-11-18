// FFmpeg (WebAssembly) on the visitor's device: used to send only the audio of a video to
// Colab and to put the cleaned audio back on the original picture afterwards.
const ENGINE={classWorkerURL:'/ffmpeg-worker.js',coreURL:'/runtime/ffmpeg-core.js?v=0.12.10',wasmURL:'/runtime/ffmpeg-core.wasm?v=0.12.10'};
const abs=u=>new URL(u,location.origin).href;
export async function engine(report){const {FFmpeg}=await import('@ffmpeg/ffmpeg');const ff=new FFmpeg();if(report)ff.on('progress',e=>report(Math.min(99,Math.max(0,Math.round(e.progress*100)))));await ff.load({classWorkerURL:abs(ENGINE.classWorkerURL),coreURL:abs(ENGINE.coreURL),wasmURL:abs(ENGINE.wasmURL)});return ff;}
const VIDEO=['mp4','mkv','mov','webm','avi','mpeg','m4v','ts'];
export const isVideoName=name=>VIDEO.includes(String(name).split('.').pop().toLowerCase());
// The audio track as it is (no re-encoding, so it takes seconds even for a long episode),
// in Matroska which accepts any audio codec. Returns null if the video has no audio.
export async function extractAudio(file,report=()=>{}){const ff=await engine(report);try{await ff.writeFile('in.bin',new Uint8Array(await file.arrayBuffer()));const code=await ff.exec(['-i','in.bin','-map','0:a:0','-vn','-sn','-dn','-c:a','copy','-map_metadata','-1','audio.mkv']);if(code!==0)return null;const bytes=await ff.readFile('audio.mkv');return bytes.length?new File([bytes],file.name.replace(/\.[^.]+$/,'')+'-audio.mkv',{type:'audio/x-matroska'}):null;}finally{ff.terminate();}}
// The cleaned audio on the original picture (stream copy, no re-encoding).
export async function muxAudio(video,audio,ext,report=()=>{}){const ff=await engine(report);try{await ff.writeFile('video.bin',new Uint8Array(await video.arrayBuffer()));await ff.writeFile('audio.bin',new Uint8Array(await audio.arrayBuffer()));const code=await ff.exec(['-i','video.bin','-i','audio.bin','-map','0:v:0','-map','1:a:0','-c','copy','-shortest','-map_metadata','-1',...(ext==='mp4'||ext==='mov'?['-movflags','+faststart']:[]),'out.'+ext]);if(code!==0)throw Error('ما قدرنا نركّب الصوت النظيف على الفيديو في جهازك');return new Blob([await ff.readFile('out.'+ext)],{type:ext==='mp4'?'video/mp4':ext==='mov'?'video/quicktime':'video/x-matroska'});}finally{ff.terminate();}}
