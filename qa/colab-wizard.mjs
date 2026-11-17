// Colab tools step flow (connect → file → run → result) without Google: node qa/colab-wizard.mjs "$PWD"
import http from 'node:http';import {readFile} from 'node:fs/promises';
const root=process.argv[2];const {build}=await import(root+'/node_modules/esbuild/lib/main.js');const {chromium}=await import('/opt/npm-tools/node_modules/playwright/index.mjs');
const harness=(await build({stdin:{contents:"import {mountColabTool} from './src/colab-tool.js';window.t=mountColabTool(document.querySelector('#toolContent'),{onResult(){}});",resolveDir:root},bundle:true,write:false,format:'esm'})).outputFiles[0].text;
const server=http.createServer(async(req,res)=>{let p=new URL(req.url,'http://x').pathname;if(p==='/h.js'){res.writeHead(200,{'content-type':'text/javascript'});return res.end(harness);}if(p==='/'){res.writeHead(200,{'content-type':'text/html'});return res.end('<!doctype html><html dir=rtl><link rel=stylesheet href=/app.css><div id=toolContent></div><script type=module src=/h.js></script>');}try{const b=await readFile(root+'/netlify-public'+p);res.writeHead(200);res.end(b);}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>window.t);
const vis=()=>page.evaluate(()=>[...document.querySelector('#toolContent').children].filter(e=>e.offsetParent!==null).map(e=>e.id||e.className||e.tagName).join(' | '));
await page.evaluate(()=>t.steps.go('file'));console.log('file:',await vis());
await page.evaluate(()=>{t.load([new File([new Uint8Array(1000)],'song.mp3',{type:'audio/mpeg'})]);});
await page.evaluate(()=>document.querySelector('#colabRun').click());console.log('no consent -> step',await page.evaluate(()=>t.steps.current),'hint:',await page.evaluate(()=>document.querySelector('[data-ws="file"].inline-error').textContent));
await page.check('#colabConsent');await page.evaluate(()=>document.querySelector('#colabRun').click());await page.waitForTimeout(400);console.log('with consent -> step',await page.evaluate(()=>t.steps.current),'| visible:',await vis(),'| error:',await page.locator('#colabError').textContent());
await page.click('.wizard-back');console.log('back ->',await page.evaluate(()=>t.steps.current));
await page.evaluate(()=>{const d=document.createElement('a');d.textContent='x';document.querySelector('#colabResult').append(d);});await page.waitForTimeout(100);console.log('result shown ->',await page.evaluate(()=>t.steps.current),'|',await vis());
console.log('errors:',JSON.stringify(errors));await browser.close();server.close();
