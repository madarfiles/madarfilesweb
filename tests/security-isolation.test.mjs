import test from 'node:test';
import assert from 'node:assert/strict';
import {createPublicHandler} from '../src/netlify-public-server.js';
const origin='https://madarfiles.netlify.app',runtime='runtimes/madarweb-12345678-1234-4123-8123-123456789abc';
const own='ya29.owner_synthetic_grant_123456',other='ya29.other_synthetic_grant_123456';
const request=(googleToken,body={})=>new Request(origin+'/api/colab/pulse',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json','oai-authenticated-user-id':'same-forged-owner'},body:JSON.stringify({googleToken,runtime,...body})});
test('cached runtime connection cannot cross Google grants even with identical forged account and runtime',async()=>{
 let runtimeCalls=0,proxyCalls=0;
 const handler=createPublicHandler({fetcher:async(url,init)=>{
  if(url.startsWith('https://colaboratory.googleapis.com/')){
   runtimeCalls++;
   if(init.headers.Authorization==='Bearer '+other)return Response.json({error:{}},{status:403});
   assert.equal(init.headers.Authorization,'Bearer '+own);
   return Response.json({name:runtime,connectionInfo:{url:'https://runtime.google.test/base/',token:'synthetic-proxy'}});
  }
  proxyCalls++;assert.equal(init.headers.Authorization,undefined);assert.equal(init.headers['X-Colab-Runtime-Proxy-Token'],'synthetic-proxy');return Response.json({});
 }});
 assert.equal((await handler(request(own))).status,200);
 assert.equal((await handler(request(other))).status,403);
 assert.equal(proxyCalls,1);assert.equal(runtimeCalls,2);
});
test('job path traversal and injected runtime paths fail before contacting any provider',async()=>{
 let calls=0;const handler=createPublicHandler({fetcher:async()=>{calls++;throw Error();}});
 for(const body of [{runtime:runtime+'/../../other'},{jobId:'../../secret'},{jobId:"'); print('injected"}])assert.equal((await handler(request(own,body))).status,400);
 assert.equal(calls,0);
});
test('untrusted runtime URLs cannot redirect the proxy to loopback or plain HTTP',async()=>{
 for(const url of ['http://runtime.example/','https://127.0.0.1/','https://[::1]/','https://metadata.internal/','https://user:pass@runtime.example/']){
  let proxyCalls=0;const handler=createPublicHandler({fetcher:async(endpoint)=>{
   if(endpoint.startsWith('https://colaboratory.googleapis.com/'))return Response.json({name:runtime,connectionInfo:{url,token:'synthetic-proxy'}});
   proxyCalls++;throw Error('unexpected runtime fetch');
  }});
  assert.equal((await handler(request(own))).status,502);assert.equal(proxyCalls,0);
 }
});
