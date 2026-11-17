// Our previews need small classic ZIP files, never multipart archives or ZIP64.
// Validate the central directory before giving untrusted bytes to a decompressor.
export function validatePreviewArchive(bytes){
 const fail=()=>{throw Error('ملف مضغوط غير صالح أو غير مناسب للمعاينة');};
 if(!(bytes instanceof Uint8Array)||bytes.length<22||bytes.length>256*1048576)fail();
 const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
 let end=-1;
 for(let p=bytes.length-22;p>=Math.max(0,bytes.length-65557);p--){if(view.getUint32(p,true)===0x06054b50&&p+22+view.getUint16(p+20,true)===bytes.length){end=p;break;}}
 if(end<0)fail();
 const count=view.getUint16(end+10,true),size=view.getUint32(end+12,true),start=view.getUint32(end+16,true);
 if(view.getUint16(end+4,true)||view.getUint16(end+6,true)||view.getUint16(end+8,true)!==count||count>256||start===0xffffffff||size===0xffffffff||start+size!==end)fail();
 let p=start;
 for(let n=0;n<count;n++){
  if(p+46>end||view.getUint32(p,true)!==0x02014b50)fail();
  const compressed=view.getUint32(p+20,true),original=view.getUint32(p+24,true),name=view.getUint16(p+28,true),extra=view.getUint16(p+30,true),comment=view.getUint16(p+32,true),offset=view.getUint32(p+42,true);
  if(view.getUint16(p+8,true)&1||compressed===0xffffffff||original===0xffffffff||offset===0xffffffff||view.getUint16(p+34,true)||p+46+name+extra+comment>end||offset+30>start)fail();
  if(view.getUint32(offset,true)!==0x04034b50)fail();
  const dataStart=offset+30+view.getUint16(offset+26,true)+view.getUint16(offset+28,true);
  if(dataStart>start||dataStart+compressed>start)fail();
  const extraEnd=p+46+name+extra;
  for(let at=p+46+name;at<extraEnd;){if(at+4>extraEnd)fail();const id=view.getUint16(at,true),length=view.getUint16(at+2,true);if(id===1||at+4+length>extraEnd)fail();at+=4+length;}
  p+=46+name+extra+comment;
 }
 if(p!==end)fail();
}
