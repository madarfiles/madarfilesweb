// Stand-in for colab-tool.js in qa/dub-e2e.mjs: same interface, no Google.
import {zipSync} from 'fflate';
export function mountColabTool(host,{onResult,onEvent}){let file;const steps={current:'connect'};host.innerHTML='<div class="colab-intro">x</div><button id="fakeConnect" class="button">الاتصال (اختبار)</button>';
 host.querySelector('#fakeConnect').onclick=()=>{steps.current='file';onEvent?.('connected',{});};
 return{steps,load(files){file=files[0];},async run(){window.fakeUploaded={name:file.name,size:file.size,type:file.type};host.innerHTML='<p id="fakeRunning">يعمل (اختبار)</p>';const get=async n=>new Uint8Array(await (await fetch('/fixtures/'+n)).arrayBuffer());const zip=zipSync({'voice.m4a':await get('voice.m4a'),'background.m4a':await get('background.m4a')},{level:0});setTimeout(()=>onResult(new Blob([zip],{type:'application/zip'}),'dub.zip','pdf'),400);},dispose(){}};}
