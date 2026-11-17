import test from 'node:test';import assert from 'node:assert/strict';
import {renderResultPreview} from '../src/result-preview.js';
class Node {
 constructor(tag='div'){this.tag=tag;this.children=[];}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 querySelectorAll(selector){const names=selector.split(',');return this.children.flatMap(n=>[...(names.includes(n.tag)?[n]:[]),...n.querySelectorAll(selector)]);}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
test('a slow old text preview cannot replace or append to a newer preview',async()=>{
 const before=global.document;global.document={createElement:tag=>new Node(tag)};
 try{
  const root=new Node();let resolve;const oldBlob={type:'text/plain',size:5,slice:()=>({text:()=>new Promise(r=>resolve=r)})};
  const old=renderResultPreview(root,{blob:oldBlob,url:'blob:old',name:'old.txt'});
  const clean=await renderResultPreview(root,{blob:new Blob(['new'],{type:'text/plain'}),url:'blob:new',name:'new.txt'});
  resolve('old');await old;
  assert.deepEqual(root.querySelectorAll('textarea').map(n=>n.value),['new']);
  assert.deepEqual(root.querySelectorAll('a').map(n=>n.href),['blob:new']);clean();
 }finally{global.document=before;}
});
test('cancelled preview does not append late text or download actions',async()=>{
 const before=global.document;global.document={createElement:tag=>new Node(tag)};
 try{
  const root=new Node(),signal=new AbortController();let resolve;
  const promise=renderResultPreview(root,{blob:{type:'text/plain',size:1,slice:()=>({text:()=>new Promise(r=>resolve=r)})},url:'blob:test',name:'test.txt'},{signal:signal.signal});
  signal.abort();resolve('late');await promise;
  assert.equal(root.querySelectorAll('textarea,a').length,0);
 }finally{global.document=before;}
});
