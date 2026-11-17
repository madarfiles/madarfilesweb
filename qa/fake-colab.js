import {zipSync} from 'fflate';
export function mountColabTool(host,{onResult}){let file;host.innerHTML='<p id="fakeInfo">Colab (اختبار)</p><button id="fakeRun" class="button">تشغيل الفصل (اختبار)</button>';
 host.querySelector('#fakeRun').onclick=async()=>{const get=async n=>new Uint8Array(await (await fetch('/fixtures/'+n)).arrayBuffer());window.fakeUploaded=file?{name:file.name,size:file.size,type:file.type}:null;const zip=zipSync({'voice.m4a':await get('voice.m4a'),'background.m4a':await get('background.m4a')},{level:0});onResult(new Blob([zip],{type:'application/zip'}),'dub.zip','pdf');};
 return{load(files){file=files[0];},dispose(){}};}
