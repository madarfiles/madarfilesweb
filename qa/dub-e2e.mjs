// Dub studio end-to-end in Chrome with a fake microphone and a stand-in for the Colab step.
// node qa/dub-e2e.mjs "$PWD" after npm run build:netlify. Fixtures are generated here with system ffmpeg.
import http from 'node:http';import {readFile,writeFile,mkdir} from 'node:fs/promises';import {execFileSync} from 'node:child_process';
const root=process.argv[2],fx='/tmp/madar-dub-fx';await mkdir(fx,{recursive:true});
const ff=a=>execFileSync('ffmpeg',['-v','error','-y',...a]);
ff(['-f','lavfi','-i','color=c=0x283c3b:s=320x180:r=15','-f','lavfi','-i','sine=f=300:sample_rate=44100','-t','7','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',fx+'/video.mp4']);
ff(['-f','lavfi','-i','sine=f=500:sample_rate=44100:d=7','-af',"volume='if(between(t,1,2.5)+between(t,4,5),1,0)':eval=frame",'-ac','2','-c:a','aac',fx+'/voice.m4a']);
ff(['-f','lavfi','-i','anoisesrc=a=0.03:d=7:r=44100','-ac','2','-c:a','aac',fx+'/background.m4a']);
const {build}=await import(root+'/node_modules/esbuild/lib/main.js');const {chromium}=await import(process.env.PLAYWRIGHT||'/opt/npm-tools/node_modules/playwright/index.mjs');
const fake={name:'fake-colab',setup(b){b.onResolve({filter:/colab-tool\.js$/},()=>({path:root+'/qa/fake-colab.js'}));}};
const harness=(await build({stdin:{contents:"import {mountDub} from './src/dub.js';window.results=[];window.tool=mountDub(document.querySelector('#content'),{onResult:(blob,name,kind)=>{window.results.push({name,kind,size:blob.size});window.lastBlob=blob;}});",resolveDir:root},bundle:true,write:false,format:'esm',plugins:[fake],nodePaths:[root+'/node_modules']})).outputFiles[0].text;
const types={js:'text/javascript',css:'text/css',html:'text/html',wasm:'application/wasm',m4a:'audio/mp4',mp4:'video/mp4'};
const server=http.createServer(async(req,res)=>{const path=new URL(req.url,'http://x').pathname;
 if(path==='/harness.js'){res.writeHead(200,{'content-type':'text/javascript'});return res.end(harness);}
 if(path==='/'){res.writeHead(200,{'content-type':'text/html'});return res.end('<!doctype html><html dir=rtl lang=ar><link rel=stylesheet href=/app.css><body style="padding:16px;max-width:620px"><div id=content></div><script type=module src=/harness.js></script>');}
 const file=path.startsWith('/fixtures/')?fx+path.slice(9):root+'/netlify-public'+path;try{const b=await readFile(file);res.writeHead(200,{'content-type':types[file.split('.').pop()]||'application/octet-stream'});res.end(b);}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--autoplay-policy=no-user-gesture-required']});
const ctx=await browser.newContext({permissions:['microphone'],viewport:{width:430,height:900}});const page=await ctx.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/404/.test(m.text()))errors.push(m.text());});
const visible=()=>page.evaluate(()=>[...document.querySelectorAll('section[data-step]')].filter(s=>!s.hidden).map(s=>s.dataset.step).join(','));const shot=n=>page.screenshot({path:'/tmp/dub-'+n+'.png',fullPage:true});
await page.goto(base);console.log('1 visible:',await visible(),'| back hidden:',await page.locator('#dubBack').isHidden());await shot('1-connect');
await page.click('#fakeConnect');console.log('2 visible:',await visible(),'| start disabled:',await page.locator('#dubStart').isDisabled());
await page.setInputFiles('#dubFile',fx+'/video.mp4');await shot('2-video');await page.click('#dubStart');console.log('3 visible:',await visible());
await page.waitForFunction(()=>!document.querySelector('section[data-step="record"]').hidden,null,{timeout:120000});console.log('uploaded:',JSON.stringify(await page.evaluate(()=>window.fakeUploaded)));
console.log('4 visible:',await visible(),'|',await page.locator('#dubLineTitle').textContent(),await page.locator('#dubLineTime').textContent(),'| dots:',await page.locator('.dub-dot').count(),'| text lang sent:',await page.evaluate(()=>window.fakeTextLang));console.log('line 1 text:',await page.locator('#dubText').innerText());await shot('3-record');
for(let i=0;i<2;i++){await page.click('#dubRec');await page.waitForFunction(()=>!document.querySelector('#dubCount').hidden,null,{timeout:5000});if(i===0)console.log('countdown on picture:',await page.locator('#dubCount').textContent());await page.waitForFunction(()=>/إيقاف/.test(document.querySelector('#dubRec').textContent),null,{timeout:10000});if(i===1){await page.waitForTimeout(500);console.log('line 2 words while recording:',await page.evaluate(()=>[...document.querySelectorAll('#dubText span')].map(s=>s.textContent.trim()+':'+(s.className||'-')).join(' ')));await shot('3b-recording');}await page.waitForTimeout(1200);await page.click('#dubRec');await page.locator('#dubMine').waitFor({state:'visible',timeout:10000});if(i===0){await page.click('#dubMine');await page.waitForTimeout(600);await shot('4-recorded');}await page.click('#dubNext');}
console.log('5 visible:',await visible(),'|',await page.locator('#dubSummary').textContent());
await page.click('#dubBack');console.log('back ->',await visible(),await page.locator('#dubLineTitle').textContent());await page.click('#dubNext');
await page.click('#dubExport');await page.waitForSelector('#dubResult video',{timeout:180000});await shot('5-done');
const out=await page.evaluate(async()=>{const b=new Uint8Array(await window.lastBlob.arrayBuffer());let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode(...b.subarray(i,i+32768));return {results:window.results,data:btoa(s)};});
await writeFile('/tmp/dubbed.mp4',Buffer.from(out.data,'base64'));console.log('result:',JSON.stringify(out.results),'|',await page.locator('#dubStatus').textContent());
const level=(t,d)=>Number(/max_volume: (-?[\d.]+)/.exec(execFileSync('sh',['-c',`ffmpeg -hide_banner -ss ${t} -t ${d} -i /tmp/dubbed.mp4 -af volumedetect -f null - 2>&1 | grep max_volume`]).toString())[1]);
const lv=[[0.2,0.6],[1,1.5],[3,0.8],[3.95,1.5]].map(([t,d])=>level(t,d));console.log('peak dB: before line1, line1, gap, line2:',lv.join(' '));
console.log('errors:',JSON.stringify(errors));await browser.close();server.close();
if(errors.length||!(lv[1]>lv[0]+10&&lv[3]>lv[2]+10))process.exit(1);
