// Return from the full-page Google sign-in (used on iPhone, where Safari blocks the pop-up).
// The token arrives in the address fragment; it is checked against the state saved before
// leaving, kept for this tab only, removed from the address bar, and the tool reopens.
const params=new URLSearchParams(location.hash.slice(1));history.replaceState(null,'',location.pathname);
const show=text=>{document.getElementById('msg').textContent=text;document.getElementById('back').hidden=false;};
let saved=null;try{saved=JSON.parse(sessionStorage.getItem('madar-oauth-state')||'null');sessionStorage.removeItem('madar-oauth-state');}catch{}
const token=params.get('access_token'),scopes=(params.get('scope')||'').split(/\s+/);
if(params.get('error'))show(params.get('error')==='access_denied'?'ما اكتمل الاتصال لأنك ألغيت الموافقة. ارجع وجرّب مرة ثانية.':'ما اكتمل الاتصال بحساب Google. ارجع وجرّب مرة ثانية.');
else if(!saved||saved.state!==params.get('state')||Date.now()-saved.at>15*60000||!token)show('انتهت مهلة الاتصال أو الرابط غير صحيح. ارجع وجرّب مرة ثانية.');
else if(!scopes.includes('https://www.googleapis.com/auth/colaboratory'))show('لازم توافق على صلاحية Colab عشان تشتغل الأدوات السحابية. ارجع وجرّب مرة ثانية.');
else{const expires=Date.now()+Math.max(0,(Number(params.get('expires_in'))||3600)-60)*1000;
 try{sessionStorage.setItem('madar-google-token',JSON.stringify({token,expires,drive:scopes.includes('https://www.googleapis.com/auth/drive.appdata')}));sessionStorage.setItem('madar-oauth-returned','1');try{localStorage.setItem('madar-google-known','1');}catch{}}catch{}
 location.replace('/?resume=1');}
