import http from 'node:http';
import {readFile} from 'node:fs/promises';
const portIndex=process.argv.indexOf('--port');
const port=Number(portIndex>=0?process.argv[portIndex+1]:(process.env.PORT||3000));
const {default:worker}=await import('../worker/index.js');
http.createServer(async(req,res)=>{try{const request=new Request('http://localhost:'+port+req.url,{method:req.method});const response=await worker.fetch(request);res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));}catch{res.writeHead(500);res.end('Preview error');}}).listen(port,'0.0.0.0',()=>console.log('Madar preview ready on '+port));
