import{build}from'esbuild';import{readFile,writeFile,mkdir,copyFile,rm}from'node:fs/promises';import{bounded,staticHeaders,FFMPEG_CORE_VERSION,renderServiceWorker}from'../src/security.mjs';
await rm('dist',{recursive:true,force:true});const coreVersion=JSON.parse(await readFile('node_modules/@ffmpeg/core/package.json','utf8')).version;if(coreVersion!==FFMPEG_CORE_VERSION)throw Error('FFMPEG_CORE_VERSION '+FFMPEG_CORE_VERSION+' does not match installed @ffmpeg/core '+coreVersion);await mkdir('dist/runtime/'+coreVersion,{recursive:true});await mkdir('dist/fonts',{recursive:true});await mkdir('generated',{recursive:true});
const pack=async(entry,outfile)=>build({entryPoints:[entry],outfile,bundle:true,minify:true,target:['safari16'],platform:'browser',format:'esm',legalComments:'eof'});
const fonts={};
for(const name of['Amiri-Regular.ttf','Amiri-Bold.ttf','OFL.txt']){
 const url='https://raw.githubusercontent.com/google/fonts/7af0d90b4d532ffa4b041937b560c6df4e7b1e95/ofl/amiri/'+name;
 const r=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(30000)});if(!r.ok)throw Error('Font asset unavailable: '+r.status);
 const bytes=await bounded(r,3*1048576);if(name.endsWith('.ttf')&&!(bytes[0]===0&&bytes[1]===1&&bytes[2]===0&&bytes[3]===0))throw Error('Invalid TTF');
 await writeFile('dist/fonts/'+name,bytes);if(name.endsWith('.ttf'))fonts[name]=Buffer.from(bytes).toString('base64');
}
await writeFile('generated/worker.mjs','export const WORKER_SOURCE='+JSON.stringify(await readFile('colab/worker.py','utf8'))+';\nexport const FONT_ASSETS='+JSON.stringify(fonts)+';\n');
await pack('src/app.mjs','dist/app.js');await pack('node_modules/@ffmpeg/ffmpeg/dist/esm/worker.js','dist/ffmpeg-worker.js');
await copyFile('src/index.html','dist/index.html');await copyFile('src/app.css','dist/app.css');
await copyFile('node_modules/pdfjs-dist/build/pdf.worker.min.mjs','dist/pdf-worker.js');
for(const name of['ffmpeg-core.js','ffmpeg-core.wasm'])await copyFile('node_modules/@ffmpeg/core/dist/esm/'+name,'dist/runtime/'+coreVersion+'/'+name);
await writeFile('dist/_headers',staticHeaders());
await writeFile('dist/icon.svg','<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect width="128" height="128" rx="28" fill="#253e3c"/><circle cx="64" cy="64" r="43" fill="none" stroke="#eee5c9" stroke-width="3"/><text x="64" y="82" text-anchor="middle" fill="#eee5c9" font-size="68">م</text></svg>');
await writeFile('dist/manifest.webmanifest',JSON.stringify({name:'مدار الملفات',short_name:'مدار',lang:'ar',dir:'rtl',id:'/',start_url:'/',scope:'/',display:'standalone',background_color:'#efeee6',theme_color:'#253e3c',icons:[{src:'/icon.svg',sizes:'any',type:'image/svg+xml',purpose:'any'}]}));
await writeFile('dist/licenses.html','<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>تراخيص مدار</title><h1>تراخيص المكتبات</h1><p>المكتبات لها تراخيص مستقلة: pdf-lib وFFlate وQRCode وesbuild وws (MIT)، PDF.js (Apache-2.0)، Fontkit (MIT)، Amiri (SIL OFL).</p><p>FFmpeg وFFmpeg.wasm يتضمنان مكونات LGPL/GPL وفق بناء المحرك. مصدر FFmpeg: <a href="https://github.com/FFmpeg/FFmpeg">FFmpeg</a>، ومصدر بناء المتصفح: <a href="https://github.com/ffmpegwasm/ffmpeg.wasm">ffmpeg.wasm</a>.</p><p>للنماذج تراخيص مستقلة، منها NLLB وWan وSDXL وUVR. راجع بطاقات النماذج قبل الاستخدام التجاري أو إعادة التوزيع.</p><a href="/fonts/OFL.txt">ترخيص خط أميري</a><p>مصدر التطبيق في مستودع مالكه. لم يُمنح ترخيص عام للكود المخصص ضمن هذا الملف.</p></html>');
const SHELL=['/','/app.js','/app.css','/ffmpeg-worker.js','/pdf-worker.js','/manifest.webmanifest','/icon.svg','/fonts/Amiri-Regular.ttf','/fonts/Amiri-Bold.ttf'];
const {createHash}=await import('node:crypto');const hash=createHash('sha256');for(const path of SHELL)hash.update(await readFile('dist'+(path==='/'?'/index.html':path)));
await writeFile('dist/sw.js',renderServiceWorker(await readFile('src/sw.js','utf8'),hash.digest('hex').slice(0,16),SHELL,coreVersion));
console.log('Built MadarFiles Web: self-hosted assets and fixed Colab worker.');
