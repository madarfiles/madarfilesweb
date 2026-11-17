import {build} from 'esbuild';import{readFile,writeFile,mkdir,copyFile,rm}from'node:fs/promises';
import{execFileSync}from'node:child_process';
// The original Sites build remains separate; only this target is deployed to Netlify.
execFileSync(process.execPath,['scripts/build.mjs'],{stdio:'inherit'});
const target='netlify-public';await rm(target,{recursive:true,force:true});await mkdir(target,{recursive:true});
const pack=async entry=>(await build({entryPoints:[entry],bundle:true,write:false,minify:true,target:['safari16'],platform:'browser',format:'esm',legalComments:'eof'})).outputFiles[0].text;
let html=await readFile('src/index.html','utf8');
html=html.replace('</head>','<meta name="madar-groq-limit" content="4194304"></head>');
await writeFile(target+'/index.html',html);await writeFile(target+'/app.js',await pack('src/netlify-entry.js'));
await copyFile('src/app.css',target+'/app.css');
for(const name of ['icon.svg','apple-touch-icon.png','licenses.html'])await copyFile('src/'+name,target+'/'+name);await mkdir(target+'/fonts');for(const name of ['DejaVuSans.ttf','DejaVuSans-Bold.ttf','Amiri-Regular.ttf','Amiri-Bold.ttf','OFL.txt','DejaVu-LICENSE.txt'])await copyFile('src/fonts/'+name,target+'/fonts/'+name);
await copyFile('colab/Madar_Colab_Separation.ipynb',target+'/Madar_Colab_Separation.ipynb');
await writeFile(target+'/ffmpeg-worker.js',await pack('node_modules/@ffmpeg/ffmpeg/dist/esm/worker.js'));await copyFile('node_modules/pdfjs-dist/build/pdf.worker.min.mjs',target+'/pdf-worker.js');await mkdir(target+'/runtime');for(const name of ['ffmpeg-core.js','ffmpeg-core.wasm'])await copyFile('node_modules/@ffmpeg/core/dist/esm/'+name,target+'/runtime/'+name);
await writeFile(target+'/manifest.webmanifest',JSON.stringify({id:'/',name:'مدار الملفات',short_name:'مدار',lang:'ar',dir:'rtl',start_url:'/',scope:'/',display:'standalone',background_color:'#f8f6f1',theme_color:'#283c3b',icons:[{src:'/apple-touch-icon.png',sizes:'180x180',type:'image/png'},{src:'/icon.svg',sizes:'any',type:'image/svg+xml'}]}));
const headers=JSON.parse(await readFile('src/headers.json','utf8'));await writeFile(target+'/_headers','/*\n'+Object.entries(headers).map(([k,v])=>'  '+k+': '+v).join('\n')+'\n  X-Robots-Tag: noindex, nofollow\n');
console.log('Netlify public package prepared; cloud authorization uses each visitor’s own provider grant.');
