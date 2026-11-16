import test from'node:test';import assert from'node:assert/strict';import{readFile}from'node:fs/promises';import{JSDOM}from'jsdom';
test('all 24 tool panels mount and close, use appropriate file pickers and keep safe settings',async()=>{
const dom=new JSDOM(await readFile('src/index.html','utf8'),{url:'https://madar.test',pretendToBeVisual:true});const w=dom.window,restore={};const set=(key,value)=>{restore[key]=Object.getOwnPropertyDescriptor(globalThis,key);Object.defineProperty(globalThis,key,{value,configurable:true,writable:true});};
const context=new Proxy({measureText:text=>({width:String(text).length*20})},{get:(target,key)=>key in target?target[key]:(()=>{}),set:(target,key,value)=>{target[key]=value;return true;}});
w.HTMLCanvasElement.prototype.getContext=()=>context;w.HTMLCanvasElement.prototype.toBlob=function(callback){callback(new Blob(['png'],{type:'image/png'}));};
w.HTMLElement.prototype.showModal=function(){this.setAttribute('open','');};w.HTMLElement.prototype.close=function(){this.removeAttribute('open');};w.HTMLInputElement.prototype.showPicker=function(){};
w.google={accounts:{oauth2:{initTokenClient:()=>({requestAccessToken(){}})}}};
for(const[key,value]of Object.entries({window:w,document:w.document,localStorage:w.localStorage,sessionStorage:w.sessionStorage,google:w.google,requestAnimationFrame:()=>1,matchMedia:()=>({matches:true}),confirm:()=>true,fetch:async url=>{if(String(url)==='/api/config')return Response.json({clientId:'public-client-id'});throw Error('No network in UI test');}}))set(key,value);
try{
 await import('../src/app.mjs');await new Promise(r=>setImmediate(r));
 const cards=[...w.document.querySelectorAll('.tool-card')];assert.equal(cards.length,24);
 for(const card of cards){
  const title=card.querySelector('b').textContent;card.click();await new Promise(r=>setImmediate(r));
  assert(w.document.querySelector('#toolDialog').hasAttribute('open'),title);
  assert.equal(w.document.querySelector('#toolTitle').textContent,title);
  assert(w.document.querySelector('#toolBody button.primary.full'),title);
  if(title==='التفريغ والترجمة')assert.equal(w.document.querySelector('#asr-operation').options.length,4);
  if(title==='إزالة الموسيقى'){assert.equal(w.document.querySelector('#separate-format').value,'mp4');const mode=w.document.querySelector('#separate-mode');mode.value='audio';mode.dispatchEvent(new w.Event('change'));assert.equal(w.document.querySelector('#separate-format').value,'mp3');}
  if(title==='تصميم اسم عربي')assert.equal(w.document.querySelectorAll('.designs button').length,20);
  if(title==='دمج وترتيب PDF')assert.equal(w.document.querySelector('#toolBody input[type=file]').accept,'application/pdf');
  if(title==='إزالة خلفية الصورة')assert.equal(w.document.querySelector('#toolBody input[type=file]').accept,'image/*');
  w.document.querySelector('#toolClose').click();assert(!w.document.querySelector('#toolDialog').hasAttribute('open'),title);
 }
 const stored=w.localStorage.getItem('madar-preferences-v2');assert(!stored.includes('access_token'));assert(!stored.includes('googleToken'));assert(!stored.includes('gsk_'));
}finally{dom.window.close();for(const[key,descriptor]of Object.entries(restore)){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}}
});
