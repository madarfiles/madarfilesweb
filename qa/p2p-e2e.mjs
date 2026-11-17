// Real two-browser transfer: node qa/p2p-e2e.mjs "$PWD" [bytes] (needs Chrome + Playwright; run after npm run build:netlify)
import http from 'node:http';import {readFile} from 'node:fs/promises';const root0=process.argv[2];const {build}=await import(root0+'/node_modules/esbuild/lib/main.js');const {chromium}=await import('/opt/npm-tools/node_modules/playwright/index.mjs');
const root=process.argv[2];const {createPublicHandler}=await import(root+'/src/netlify-public-server.js');
const m=new Map(),store={get:async k=>m.has(k)?JSON.parse(m.get(k)):null,setJSON:async(k,v,o={})=>{if(o.onlyIfNew&&m.has(k))return{modified:false};m.set(k,JSON.stringify(v));return{modified:true};},delete:async k=>{m.delete(k);}};
const api=createPublicHandler({p2pStore:store});
const harness=(await build({stdin:{contents:"import {sendFile} from './src/p2p.js';window.sendFile=sendFile;",resolveDir:root},bundle:true,write:false,format:'esm'})).outputFiles[0].text;
const types={js:'text/javascript',css:'text/css',html:'text/html',svg:'image/svg+xml',wasm:'application/wasm',ttf:'font/ttf',png:'image/png'};
const server=http.createServer(async(req,res)=>{const url='http://127.0.0.1:'+server.address().port+req.url;
 if(req.url.startsWith('/api/')){const chunks=[];for await(const c of req)chunks.push(c);const r=await api(new Request(url,{method:req.method,headers:req.headers,body:req.method==='POST'?Buffer.concat(chunks):undefined}));res.writeHead(r.status,Object.fromEntries(r.headers));return res.end(Buffer.from(await r.arrayBuffer()));}
 if(req.url==='/harness.js'){res.writeHead(200,{'content-type':'text/javascript'});return res.end(harness);}
 if(req.url==='/send.html'){res.writeHead(200,{'content-type':'text/html'});return res.end('<!doctype html><script type=module src=/harness.js></script>');}
 const path=new URL(url).pathname,file=root+'/netlify-public'+(path==='/'?'/index.html':path);try{const b=await readFile(file);res.writeHead(200,{'content-type':types[file.split('.').pop()]||'application/octet-stream'});res.end(b);}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const sender=await (await browser.newContext()).newPage(),receiver=await (await browser.newContext({acceptDownloads:true})).newPage();
for(const[p,n]of[[sender,'sender'],[receiver,'receiver']])p.on('console',m=>{if(m.type()==='error')console.log(n,'console:',m.text());});
await sender.goto(base+'/send.html');await sender.waitForFunction(()=>window.sendFile);
const SIZE=Number(process.argv[3]||6*1048576+12345);
const linkPromise=new Promise(async ok=>{await sender.exposeFunction('gotLink',ok);});
const sent=sender.evaluate(async SIZE=>{const bytes=new Uint8Array(SIZE);for(let i=0;i<SIZE;i++)bytes[i]=(i*31+7)&255;const file=new File([bytes],'مقطع تجربة.mp4',{type:'video/mp4'});const log=[];await window.sendFile(file,{report:t=>log.push(t),onCode:u=>window.gotLink(u)});return log.at(-1);},SIZE);
const link=await linkPromise;console.log('link',link.replace(/[a-f0-9]{32}/,'<id>'));
const t0=Date.now();await receiver.goto(link.replace(/^https?:\/\/[^/]+/,base));
await receiver.waitForSelector('.p2p-dialog a[download]',{timeout:60000});const last=await sent;
const info=await receiver.evaluate(async()=>{const a=document.querySelector('.p2p-dialog a[download]');const b=new Uint8Array(await (await fetch(a.href)).arrayBuffer());let bad=0;for(let i=0;i<b.length;i++)if(b[i]!==((i*31+7)&255)){bad++;break;}return{name:a.download,size:b.length,bad,status:document.querySelector('.p2p-dialog [role=status]').textContent,hash:location.hash,video:!!document.querySelector('.p2p-dialog video')};});
console.log(JSON.stringify({...info,expected:SIZE,senderLast:last,seconds:(Date.now()-t0)/1000,storeLeft:m.size}));
// A second receiver with the same (now used) code must be refused.
const third=await (await browser.newContext()).newPage();await third.goto(link.replace(/^https?:\/\/[^/]+/,base));await third.waitForFunction(()=>/انتهى|مستخدم/.test(document.querySelector('.p2p-dialog [role=status]')?.textContent||''),null,{timeout:20000});console.log('reuse:',await third.evaluate(()=>document.querySelector('.p2p-dialog [role=status]').textContent));
await browser.close();server.close();
if(info.size!==SIZE||info.bad||info.name!=='مقطع تجربة.mp4'||m.size)process.exit(1);
