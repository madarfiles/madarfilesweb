// Run with the real Workers engine, not Node's Fetch implementation.
import {colabAPI,execute} from '../src/colab-server.js';
export default {async fetch(){
 const check={};
 try{new Request('https://colaboratory.googleapis.com/v1beta/subscription',{redirect:'error'});check.unsupportedErrorModeRejected=false;}catch(e){check.unsupportedErrorModeRejected=e.name==='TypeError';}
 let calls=0;
 const upstream=async(url,init)=>{new Request(url,init);calls++;if(url.endsWith('subscription'))return Response.json({tier:'SUBSCRIPTION_TIER_PRO'});if(url.endsWith('runtimespecs'))return Response.json({runtimeSpecs:[]});return Response.json({runtimes:[]});};
 const request=()=>new Request('https://madar.test/api/colab/check',{method:'POST',headers:{Origin:'https://madar.test','Content-Type':'application/json','oai-authenticated-user-id':'runtime-test'},body:JSON.stringify({googleToken:'ya29.synthetic_runtime_test_not_a_real_credential'})});
 const out=await colabAPI(request(),{},upstream);check.eligibilityStatus=out.status;check.calls=calls;
 let redirects=0;const blocked=await colabAPI(request(),{},async(url,init)=>{new Request(url,init);redirects++;return new Response(null,{status:302,headers:{Location:'https://untrusted.invalid/'}});});check.redirectStatus=blocked.status;check.redirectCalls=redirects;
 const frame=message=>{const bytes=new TextEncoder().encode(JSON.stringify(message)),out=new Uint8Array(bytes.length+8),view=new DataView(out.buffer);view.setUint32(0,1,false);view.setUint32(4,8,false);out.set(bytes,8);return out.buffer;};
 const runtime='runtimes/madarweb-12345678-1234-4123-8123-123456789abc';
 for(const mode of ['binary','closed']){
  let started=false,opens=0;
  const fake=async(url,init)=>{new Request(url,init);
   if(url==='https://colaboratory.googleapis.com/v1beta/'+runtime)return Response.json({name:runtime,connectionInfo:{url:'https://runtime.google.test/base/',token:'synthetic-proxy'}});
   if(url.includes('/state.json'))return started?Response.json({format:'text',content:JSON.stringify({state:'setup',message:'test'})}):Response.json({}, {status:404});
   if(url.endsWith('/api/kernels'))return Response.json([{id:'python-123',name:'python3',execution_state:'idle'}]);
   if(url.includes('/channels?')){
    if(init.headers.Origin!=='https://runtime.google.test'||init.headers.Authorization)throw new Error('Invalid runtime credentials/origin');
    opens++;const pair=new WebSocketPair();pair[1].accept();
    pair[1].addEventListener('message',ev=>{const m=JSON.parse(ev.data);started=true;if(mode==='binary')pair[1].send(frame({parent_header:{msg_id:m.header.msg_id},header:{msg_type:'execute_reply'},content:{status:'ok'}}));pair[1].close(1000,'test');});
    return {webSocket:pair[0]};
   }
   if(url.includes('/api/contents/'))return Response.json({});
   throw Error('Unexpected test request');
  };
  const body={googleToken:'ya29.synthetic_runtime_test_not_a_real_credential',runtime,kernel:'python-123',ext:'mp4',size:1,chunks:1,sha256:'a'.repeat(64),start:0,duration:400,mode:'video'};
  const r=await colabAPI(new Request('https://madar.test/api/colab/run',{method:'POST',headers:{Origin:'https://madar.test','Content-Type':'application/json','oai-authenticated-user-id':'runtime-test'},body:JSON.stringify(body)}),{},fake);
  check[mode+'StartupStatus']=r.status;check[mode+'StartupConnections']=opens;
 }
 check.ok=check.unsupportedErrorModeRejected&&check.eligibilityStatus===200&&check.calls===3&&check.redirectStatus===502&&redirects===1&&check.binaryStartupStatus===200&&check.closedStartupStatus===200&&check.binaryStartupConnections===1&&check.closedStartupConnections===1;
 return Response.json(check,{status:check.ok?200:500});
}};
