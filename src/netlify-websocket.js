import WebSocket from 'ws';
export function socketFetch(url,options={},fetcher=fetch){
 if(new Headers(options.headers).get('Upgrade')?.toLowerCase()!=='websocket')return fetcher(url,options);
 const endpoint=new URL(url);if(endpoint.protocol!=='https:')return Promise.reject(Error('Secure websocket required'));endpoint.protocol='wss:';
 return new Promise((resolve,reject)=>{if(options.signal?.aborted)return reject(new DOMException('Aborted','AbortError'));const headers=Object.fromEntries(new Headers(options.headers));delete headers.upgrade;
 const ws=new WebSocket(endpoint,{headers,followRedirects:false,handshakeTimeout:12000,maxPayload:1048576,perMessageDeflate:false});ws.binaryType='arraybuffer';const abort=()=>{ws.terminate();reject(new DOMException('Aborted','AbortError'));};options.signal?.addEventListener('abort',abort,{once:true});
 ws.once('open',()=>{ws.accept=()=>{};resolve({status:101,ok:true,webSocket:ws,body:null});});ws.once('close',()=>options.signal?.removeEventListener('abort',abort));ws.once('error',reject);ws.once('unexpected-response',(_request,response)=>{const status=response.statusCode;response.destroy();ws.terminate();resolve({status,ok:false,body:null});});
 });
}
