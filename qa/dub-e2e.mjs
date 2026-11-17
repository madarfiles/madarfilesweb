// Dub studio end-to-end in Chrome with a fake microphone and a stand-in for the Colab step.
// Fixtures (video.mp4, voice.m4a, background.m4a) are generated with system ffmpeg in /home/claude/qa/dubfx.
import http from 'node:http';import {readFile,writeFile} from 'node:fs/promises';import {execFileSync} from 'node:child_process';
const root=process.argv[2],fx='/home/claude/qa/dubfx';const {build}=await import(root+'/node_modules/esbuild/lib/main.js');const {chromium}=await import('/opt/npm-tools/node_modules/playwright/index.mjs');
const fake={name:'fake-colab',setup(b){b.onResolve({filter:/colab-tool\.js$/},()=>({path:''+root+'/qa/fake-colab.js'}));}};
const harness=(await build({stdin:{contents:"import {mountDub} from './src/dub.js';window.results=[];window.tool=mountDub(document.querySelector('#content'),{onResult:(blob,name,kind)=>{window.results.push({name,kind,size:blob.size});window.lastBlob=blob;}});",resolveDir:root},bundle:true,write:false,format:'esm',plugins:[fake],nodePaths:[root+'/node_modules']})).outputFiles[0].text;
const types={js:'text/javascript',css:'text/css',html:'text/html',wasm:'application/wasm',m4a:'audio/mp4',mp4:'video/mp4'};
const server=http.createServer(async(req,res)=>{const path=new URL(req.url,'http://x').pathname;
 if(path==='/harness.js'){res.writeHead(200,{'content-type':'text/javascript'});return res.end(harness);}
 if(path==='/'){res.writeHead(200,{'content-type':'text/html'});return res.end('<!doctype html><html dir=rtl lang=ar><link rel=stylesheet href=/app.css><body style="padding:16px;max-width:620px"><div id=content></div><script type=module src=/harness.js></script>');}
 const file=path.startsWith('/fixtures/')?fx+path.slice(9):root+'/netlify-public'+path;try{const b=await readFile(file);res.writeHead(200,{'content-type':types[file.split('.').pop()]||'application/octet-stream'});res.end(b);}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--autoplay-policy=no-user-gesture-required']});
const ctx=await browser.newContext({permissions:['microphone'],viewport:{width:430,height:900}});const page=await ctx.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/404/.test(m.text()))errors.push(m.text());});
const status=()=>page.locator('#dubStatus').textContent();
await page.goto(base);await page.setInputFiles('#dubFile',fx+'/video.mp4');await page.click('#dubPrepare');
await page.waitForSelector('[data-stage="2"]:not([hidden]) #fakeRun',{timeout:120000});console.log('stage2:',await status());
await page.click('#fakeRun');await page.waitForSelector('[data-stage="3"]:not([hidden]) .dub-item',{timeout:60000});
console.log('uploaded to colab:',JSON.stringify(await page.evaluate(()=>window.fakeUploaded)));
console.log('segments:',JSON.stringify(await page.$$eval('.dub-time',e=>e.map(x=>x.textContent))),'|',await status());
await page.screenshot({path:'/home/claude/qa/dub-stage3.png',fullPage:true});
for(const i of [0,1]){const item=page.locator('.dub-item').nth(i);await item.getByRole('button',{name:/سجّل/}).click();await page.waitForFunction(()=>/يسجّل/.test(document.querySelector('#dubStatus').textContent),null,{timeout:10000});await page.waitForTimeout(1300);await page.locator('.dub-item').nth(i).getByRole('button',{name:/إيقاف/}).click();
 await page.locator('.dub-item').nth(i).getByRole('button',{name:/معاينة/}).waitFor({timeout:10000});await page.locator('.dub-item').nth(i).getByRole('button',{name:/✓ تم/}).click();}
console.log('progress:',await page.locator('#dubProgress').textContent());
await page.locator('.dub-item').nth(0).getByRole('button',{name:/معاينة/}).click();await page.waitForTimeout(800);
await page.screenshot({path:'/home/claude/qa/dub-recorded.png',fullPage:true});
await page.click('#dubExport');await page.waitForSelector('[data-stage="4"]:not([hidden]) video',{timeout:180000});
const out=await page.evaluate(async()=>{const b=new Uint8Array(await window.lastBlob.arrayBuffer());let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode(...b.subarray(i,i+32768));return {results:window.results,data:btoa(s)};});
await writeFile('/home/claude/qa/dubbed.mp4',Buffer.from(out.data,'base64'));console.log('result:',JSON.stringify(out.results),'|',await status());
await page.screenshot({path:'/home/claude/qa/dub-done.png',fullPage:true});
console.log('errors:',JSON.stringify(errors));await browser.close();server.close();
