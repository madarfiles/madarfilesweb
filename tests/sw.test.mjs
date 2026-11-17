import test from'node:test';import assert from'node:assert/strict';import{readFile}from'node:fs/promises';import vm from'node:vm';import{renderServiceWorker,staticHeaders}from'../src/security.mjs';
const SHELL=['/','/app.js'],ORIGIN='https://madar.test';
async function worker(network){const stores=new Map(),listeners={};const open=async name=>{if(!stores.has(name))stores.set(name,new Map());const m=stores.get(name),key=r=>typeof r==='string'?new URL(r,ORIGIN).pathname:new URL(r.url).pathname;return{addAll:async list=>{for(const p of list)m.set(key(p),new Response('shell '+p));},put:async(r,res)=>{m.set(key(r),res);},match:async r=>m.get(key(r))?.clone()};};
const caches={open,keys:async()=>[...stores.keys()],delete:async k=>stores.delete(k)};
const self={location:new URL(ORIGIN),clients:{claim:async()=>{}},skipWaiting:async()=>{},addEventListener:(t,f)=>listeners[t]=f};
vm.runInNewContext(renderServiceWorker(await readFile(new URL('../src/sw.js',import.meta.url),'utf8'),'0123456789abcdef',SHELL,'0.12.10'),{self,caches,fetch:network,URL,Response,Promise,JSON});
const run=async(type,extra={})=>{let p;const e={...extra,waitUntil:x=>p=x,respondWith:x=>p=x};listeners[type](e);return{handled:!!p,value:await p};};
return{stores,run};}
const get=(path,mode='cors')=>({method:'GET',url:ORIGIN+path,mode});
test('service worker leaves the API alone, keeps the engine offline and falls back to the cached page',async()=>{let online=true,calls=0;const w=await worker(async r=>{calls++;if(!online)throw TypeError('offline');return new Response('net '+new URL(r.url).pathname);});
w.stores.set('madar-shell-old',new Map());await w.run('install');await w.run('activate');assert(!w.stores.has('madar-shell-old'));
assert.equal((await w.run('fetch',{request:get('/api/colab/status')})).handled,false);assert.equal((await w.run('fetch',{request:{...get('/api/x'),method:'POST'}})).handled,false);
assert.equal(await (await w.run('fetch',{request:get('/runtime/0.12.10/ffmpeg-core.wasm')})).value.text(),'net /runtime/0.12.10/ffmpeg-core.wasm');
online=false;const before=calls;assert.equal(await (await w.run('fetch',{request:get('/runtime/0.12.10/ffmpeg-core.wasm')})).value.text(),'net /runtime/0.12.10/ffmpeg-core.wasm');assert.equal(calls,before+1-1);
assert.equal(await (await w.run('fetch',{request:get('/some/page','navigate')})).value.text(),'shell /');
assert.equal(await (await w.run('fetch',{request:get('/app.js')})).value.text(),'shell /app.js');});
test('service worker script revalidates and the version is validated',()=>{assert.match(staticHeaders(),/\/sw\.js\n  Cache-Control: no-cache/);assert.throws(()=>renderServiceWorker('x','bad',[],'0.12.10'));});
