// The page behind an open tool must not scroll: node qa/scroll-check.mjs "$PWD"
import http from 'node:http';import {readFile} from 'node:fs/promises';
const root=process.argv[2];const {chromium}=await import('/opt/npm-tools/node_modules/playwright/index.mjs');
const server=http.createServer(async(req,res)=>{let p=new URL(req.url,'http://x').pathname;if(p==='/')p='/index.html';try{const b=await readFile(root+'/netlify-public'+p);res.writeHead(200,{'content-type':p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':p.endsWith('.html')?'text/html':'application/octet-stream'});res.end(b);}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const page=await (await browser.newContext({viewport:{width:400,height:700},hasTouch:true,isMobile:true})).newPage();await page.goto('http://127.0.0.1:'+server.address().port+'/#remove-music');await page.waitForTimeout(800);
const y0=await page.evaluate(()=>scrollY);for(let i=0;i<8;i++){await page.mouse.move(200,400);await page.mouse.wheel(0,600);await page.waitForTimeout(80);}for(let i=0;i<8;i++){await page.mouse.wheel(0,-600);await page.waitForTimeout(80);}
console.log('page behind moved by:',(await page.evaluate(()=>scrollY))-y0,'px | page scroll locked:',await page.evaluate(()=>getComputedStyle(document.documentElement).overflow));
await page.keyboard.press('Escape');await page.waitForTimeout(300);console.log('after closing, page scroll:',await page.evaluate(()=>getComputedStyle(document.documentElement).overflow));
await browser.close();server.close();
