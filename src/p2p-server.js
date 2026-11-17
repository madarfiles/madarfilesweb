// Signaling for direct device-to-device transfer. Only WebRTC session descriptions
// (no file bytes) pass through here; they expire after ten minutes.
const TTL=10*60*1000,MAX_SDP=32768,ID=/^[a-f0-9]{32}$/,SECRET=/^[a-f0-9]{64}$/;
const hex=bytes=>Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
const random=n=>hex(crypto.getRandomValues(new Uint8Array(n)));
const sha=async s=>hex(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))));
const validSDP=(sdp,type)=>typeof sdp==='string'&&sdp.length>20&&sdp.length<=MAX_SDP&&sdp.startsWith('v=0')&&(type==='offer'||type==='answer');
export async function handleP2P(action,body,store,now=Date.now()){
 const live=async key=>{const v=await store.get(key,{type:'json'});if(!v)return null;if(!(v.exp>now)){await store.delete(key);return null;}return v;};
 if(action==='offer'){if(!validSDP(body?.sdp,'offer'))return[400,{error:'عرض اتصال غير صالح'}];const id=random(16),secret=random(32);await store.setJSON('offer/'+id,{sdp:body.sdp,secret:await sha(secret),exp:now+TTL});return[200,{id,secret,expires:now+TTL}];}
 if(!ID.test(body?.id||''))return[400,{error:'رمز إرسال غير صالح'}];
 const offer=await live('offer/'+body.id);
 if(action==='get'){if(!offer)return[404,{error:'انتهى رمز الإرسال أو تم استخدامه؛ اطلب رمزًا جديدًا'}];if(await live('answer/'+body.id))return[409,{error:'هذا الرمز مستخدم من جهاز آخر'}];return[200,{sdp:offer.sdp}];}
 if(action==='answer'){if(!offer)return[404,{error:'انتهى رمز الإرسال؛ اطلب رمزًا جديدًا'}];if(!validSDP(body.sdp,'answer'))return[400,{error:'رد اتصال غير صالح'}];const r=await store.setJSON('answer/'+body.id,{sdp:body.sdp,exp:offer.exp},{onlyIfNew:true});if(r&&r.modified===false)return[409,{error:'هذا الرمز مستخدم من جهاز آخر'}];return[200,{ok:true}];}
 if(action==='poll'||action==='cancel'){if(!SECRET.test(body.secret||'')||!offer||offer.secret!==await sha(body.secret))return[404,{error:'انتهى رمز الإرسال'}];
  if(action==='cancel'){await store.delete('offer/'+body.id);await store.delete('answer/'+body.id);return[200,{cancelled:true}];}
  const answer=await live('answer/'+body.id);if(!answer)return[200,{waiting:true}];await store.delete('offer/'+body.id);await store.delete('answer/'+body.id);return[200,{sdp:answer.sdp}];}
 return[404,{error:'غير موجود'}];
}
