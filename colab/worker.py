"""Madar fixed-code Colab worker. User files and credentials never enter build logs."""
import base64, gc, hashlib, io, json, math, os, re, shutil, subprocess, sys, threading, time, zipfile
from pathlib import Path
BASE=Path(__file__).resolve().parent
PART=2*1024**2
LIMIT=256*1024**2
VERSION=1
AUDIO={'mp3':['-c:a','libmp3lame','-b:a','192k'],'m4a':['-c:a','aac','-b:a','192k','-movflags','+faststart'],'wav':['-c:a','pcm_s16le'],'flac':['-c:a','flac'],'ogg':['-c:a','libvorbis','-q:a','5'],'opus':['-c:a','libopus','-b:a','160k'],'aac':['-c:a','aac','-b:a','192k']}
VIDEO={'mp4','mkv','mov','webm','avi','ts'}
LANG={'ar':'arb_Arab','en':'eng_Latn','ja':'jpn_Jpan','fr':'fra_Latn','es':'spa_Latn','de':'deu_Latn','tr':'tur_Latn','ko':'kor_Hang','zh':'zho_Hans','ur':'urd_Arab'}
class MediaError(RuntimeError):
 def __init__(self,code,stage,exit_code=None):
  self.code=code;self.details={'stage':stage}
  if isinstance(exit_code,int):self.details['exitCode']=exit_code
  messages={'MEDIA_NO_AUDIO':'المصدر لا يحتوي على صوت','MEDIA_NO_VIDEO':'المصدر لا يحتوي على فيديو','MEDIA_INVALID_INPUT':'تعذر قراءة المصدر؛ تحقق من سلامة الملف','MEDIA_DECODER_UNAVAILABLE':'ترميز المصدر غير متاح في محرك الجلسة','MEDIA_RESOURCE_BUSY':'موارد الوسائط مشغولة؛ أعد المحاولة بعد انتهاء العمليات الأخرى','MEDIA_DISK_FULL':'امتلأت مساحة الجلسة','MEDIA_TIMEOUT':'انتهت مهلة معالجة الوسائط','MEDIA_FAILED':'تعذرت مرحلة معالجة الوسائط'}
  super().__init__(messages.get(code,'تعذرت المعالجة'))
def media_code(text):
 text=(text or '').lower()
 for code,terms in [('MEDIA_DISK_FULL',['no space left','disk quota']),('MEDIA_RESOURCE_BUSY',['resource temporarily unavailable','pthread_create','cannot allocate memory','out of memory']),('MEDIA_DECODER_UNAVAILABLE',['unknown decoder','decoder not found','no decoder found']),('MEDIA_INVALID_INPUT',['invalid data found','moov atom not found','error opening input'])]:
  if any(t in text for t in terms):return code
 return 'MEDIA_FAILED'
def ffmpeg(args,stage='output_encode'):
 for attempt in range(2):
  threads='1' if attempt else '2'
  command=['ffmpeg','-v','error','-nostdin','-y','-protocol_whitelist','file,pipe','-threads',threads,'-filter_threads','1','-filter_complex_threads','1',*map(str,args[:-1]),'-threads',threads,str(args[-1])]
  try:p=subprocess.run(command,capture_output=True,text=True,timeout=1800)
  except subprocess.TimeoutExpired:raise MediaError('MEDIA_TIMEOUT',stage) from None
  if not p.returncode:return
  code=media_code(p.stderr)
  if code=='MEDIA_RESOURCE_BUSY' and not attempt:continue
  raise MediaError(code,stage,p.returncode)
def probe(path):
 try:p=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,timeout=30)
 except subprocess.TimeoutExpired:raise MediaError('MEDIA_TIMEOUT','source_probe') from None
 if p.returncode:raise MediaError(media_code(p.stderr),'source_probe',p.returncode)
 try:return json.loads(p.stdout)
 except ValueError:raise MediaError('MEDIA_INVALID_INPUT','source_probe') from None
def has_stream(source,kind):
 return any(s.get('codec_type')==kind for s in probe(source).get('streams',[]))
def audio_source(source):
 if not has_stream(source,'audio'):raise MediaError('MEDIA_NO_AUDIO','source_probe')
def encoder():
 try:
  name=subprocess.run(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],capture_output=True,text=True,timeout=5).stdout
  if any(t in name for t in ['A100','H100']):return ['-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p']
  p=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=256x256:r=30:d=0.1','-c:v','h264_nvenc','-frames:v','1','-f','null','-'],capture_output=True,timeout=15)
  if not p.returncode:return ['-c:v','h264_nvenc','-preset','p4','-cq','23','-pix_fmt','yuv420p']
 except (OSError,subprocess.SubprocessError):pass
 return ['-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p']
def export(source,target,quality='balanced',audio=None,start=0,duration=0,filters=None):
 target=Path(target);fmt=target.suffix[1:].lower()
 if fmt in AUDIO:
  audio_source(source);ffmpeg(['-i',source,'-map','0:a:0','-vn','-ac','2',*AUDIO[fmt],'-map_metadata','-1',target]);return target
 if fmt not in VIDEO:raise ValueError('صيغة الناتج غير مدعومة')
 info=probe(source);video=next((s for s in info.get('streams',[]) if s.get('codec_type')=='video'),None)
 if not video:raise MediaError('MEDIA_NO_VIDEO','source_probe')
 before=['-ss',start,'-i',source]
 if audio:before+=['-i',audio]
 if duration:before+=['-t',duration]
 before+=['-map','0:v:0','-map','1:a:0' if audio else '0:a:0?']
 q={'high':'20','balanced':'25','small':'30'}[quality]
 if fmt=='webm':codec=['-c:v','libvpx-vp9','-crf',q,'-b:v','0','-deadline','good','-cpu-used','4'];ac=['-c:a','libopus','-b:a','160k']
 elif fmt=='avi':codec=['-c:v','mpeg4','-q:v','4'];ac=['-c:a','libmp3lame','-b:a','192k']
 else:
  compatible=video.get('codec_name')=='h264' and video.get('pix_fmt') in ['yuv420p','yuvj420p','nv12']
  copy=audio and not filters and not start and not duration and (fmt=='mkv' or compatible)
  codec=['-c:v','copy'] if copy else encoder();ac=['-c:a','aac','-b:a','192k']
  if not copy:codec[codec.index('-cq' if 'h264_nvenc' in codec else '-crf')+1]=q
 tail=[*ac,'-map_metadata','-1',*(['-movflags','+faststart'] if fmt in ['mp4','mov'] else []),target]
 try:ffmpeg([*before,*(filters or []),*codec,*tail])
 except MediaError:
  if 'h264_nvenc' not in codec:raise
  ffmpeg([*before,*(filters or []),'-c:v','libx264','-preset','veryfast','-crf',q,'-pix_fmt','yuv420p',*tail])
 return target
def atomic(path,data):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False));temp.replace(path)
def status(root,state,message,**extra):atomic(root/'state.json',dict(state=state,message=message,updated=time.time(),**extra))
def assemble(root,cfg):
 out=root/('source.'+cfg['ext']);digest=hashlib.sha256();total=0
 if out.is_file() and out.stat().st_size==cfg['size']:
  with out.open('rb') as stream:
   while True:
    data=stream.read(PART)
    if not data:break
    digest.update(hashlib.sha256(data).digest())
  if digest.hexdigest()==cfg['sha256']:return out
 digest=hashlib.sha256()
 with out.open('wb') as stream:
  for i in range(cfg['chunks']):
   chunk=root/('input_%05d.bin'%i);data=chunk.read_bytes()
   if len(data)!=min(PART,cfg['size']-i*PART):raise ValueError('حجم جزء الرفع غير صحيح')
   total+=len(data);digest.update(hashlib.sha256(data).digest());stream.write(data)
 if total!=cfg['size'] or digest.hexdigest()!=cfg['sha256']:
  out.unlink(missing_ok=True);raise ValueError('بصمة الملف لا تطابق الرفع؛ أعد رفع المصدر')
 for p in root.glob('input_*.bin'):p.unlink()
 return out
def split_plan(total,start,duration):
 if not all(math.isfinite(float(n)) for n in [total,start,duration]) or total<=0 or start<0 or duration<0 or start>=total:raise ValueError('نطاق المقطع غير صالح')
 length=min(duration or total-start,total-start)
 return [(start+i*300,min(300,length-i*300)) for i in range(math.ceil(length/300))]
def separate(source,cfg,root,report):
 audio_source(source);info=probe(source);total=float(info['format']['duration']);plan=split_plan(total,cfg['start'],cfg['duration'])
 if shutil.disk_usage(root).free<2*1024**3:raise MediaError('MEDIA_DISK_FULL','source_probe')
 import torch
 if not torch.cuda.is_available():raise RuntimeError('GPU_REQUIRED')
 import onnxruntime as ort
 if hasattr(ort,'preload_dlls'):ort.preload_dlls(directory='')
 if 'CUDAExecutionProvider' not in ort.get_available_providers():raise RuntimeError('CUDA_PROVIDER_UNAVAILABLE')
 from audio_separator.separator import Separator
 obj=Separator(output_dir=str(root),model_file_dir=str(BASE/'cache/models'),output_format='WAV',output_single_stem='Vocals',use_soundfile=True,mdx_params={'hop_length':1024,'segment_size':256,'overlap':.25,'batch_size':1,'enable_denoise':False})
 obj.load_model(model_filename='UVR-MDX-NET-Voc_FT.onnx')
 # Verify that the model session itself uses CUDA, not just the installed package.
 fn=obj.model_instance.model_run
 sessions=[c.cell_contents for c in (getattr(fn,'__closure__',None) or []) if hasattr(c.cell_contents,'get_providers')]
 if not any('CUDAExecutionProvider' in s.get_providers() for s in sessions):raise RuntimeError('CUDA_SESSION_NOT_ACTIVE')
 checkpoint=root/'stems.json'
 try:saved=json.loads(checkpoint.read_text())
 except (ValueError,OSError):saved={}
 voices=[];elapsed=0;measured=0
 for index,(at,seconds) in enumerate(plan):
  item=saved.get(str(index),{});p=root/item.get('name','')
  if item.get('name') and Path(item['name']).name==item['name'] and p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==item.get('sha'):
   voices.append(p);continue
  remaining=round((len(plan)-index)*elapsed/measured) if measured else None
  report('separating','فصل الجزء %d من %d'%(index+1,len(plan)),part=index+1,total=len(plan),remainingSeconds=remaining)
  began=time.monotonic();raw=root/('chunk_%05d.wav'%index)
  try:
   ffmpeg(['-ss',at,'-i',source,'-t',seconds,'-map','0:a:0','-vn','-ac','2','-ar','44100','-c:a','pcm_s16le',raw],'audio_decode')
   names=obj.separate(str(raw),custom_output_names={'Vocals':'voice_%05d'%index})
   if not names:raise RuntimeError('MODEL_NO_OUTPUT')
   p=Path(names[0]);p=p if p.is_absolute() else root/p
   if not p.is_file():raise RuntimeError('MODEL_NO_OUTPUT')
   saved[str(index)]={'name':p.name,'sha':hashlib.sha256(p.read_bytes()).hexdigest()};atomic(checkpoint,saved);voices.append(p)
  finally:raw.unlink(missing_ok=True)
  elapsed+=time.monotonic()-began;measured+=1
 listing=root/'voice-list.txt';listing.write_text(''.join("file '"+str(p)+"'\n" for p in voices))
 report('processing','تجهيز النتيجة للحفظ')
 joined=root/'voice.m4a';ffmpeg(['-f','concat','-safe','0','-i',listing,*AUDIO['m4a'],joined])
 if cfg['mode']=='audio':
  if cfg['format']=='m4a':return joined
  return export(joined,root/('result.'+cfg['format']))
 return export(source,root/('result.'+cfg['format']),audio=joined,start=cfg['start'],duration=sum(n for _,n in plan) if cfg['start'] or cfg['duration'] else 0)
def timestamp(seconds):
 ms=round(float(seconds)*1000);return '%02d:%02d:%02d,%03d'%(ms//3600000,(ms//60000)%60,(ms//1000)%60,ms%1000)
def srt(segments):return '\n\n'.join(str(i+1)+'\n'+timestamp(s['start'])+' --> '+timestamp(s['end'])+'\n'+s['text'].strip() for i,s in enumerate(segments))+'\n'
def translate_lines(lines,source,target):
 import torch
 from transformers import AutoTokenizer,AutoModelForSeq2SeqLM
 name='facebook/nllb-200-distilled-600M';tok=AutoTokenizer.from_pretrained(name,src_lang=LANG[source],trust_remote_code=False)
 model=AutoModelForSeq2SeqLM.from_pretrained(name,torch_dtype=torch.float32,low_cpu_mem_usage=False,use_safetensors=True,trust_remote_code=False)
 device='cuda' if torch.cuda.is_available() else 'cpu';model.to(device);out=[]
 for line in lines:
  if not line.strip() or re.fullmatch(r'\d+',line.strip()) or '-->' in line:out.append(line);continue
  inputs=tok(line,return_tensors='pt',truncation=False)
  if inputs['input_ids'].shape[1]>480:raise ValueError('سطر طويل جدًا للترجمة؛ قسمه إلى أسطر أقصر')
  with torch.inference_mode():tokens=model.generate(**{k:v.to(device) for k,v in inputs.items()},forced_bos_token_id=tok.convert_tokens_to_ids(LANG[target]),max_new_tokens=512)
  out.append(tok.batch_decode(tokens,skip_special_tokens=True)[0])
 del model;gc.collect()
 if torch.cuda.is_available():torch.cuda.empty_cache()
 return out
def translated_srt(text,source,target):return '\n'.join(translate_lines(text.splitlines(),source,target))
def ass_text(text,style,w,h):
 color=style['color'];primary='&H00'+color[5:7]+color[3:5]+color[1:3]
 size=h*style['size']/100;font='DejaVu Sans' if style['font']=='sans' else 'Amiri'
 header='[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 0\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,%s,%.2f,%s,&H000000FF,&H00222222,&H66000000,%d,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'%(w,h,font,size,primary,-1 if style['weight']==700 else 0)
 def clock(v):
  hh,mm,ss=re.split('[:,.]',v)[:3];cent=re.split('[:,.]',v)[3][:2];return '%d:%02d:%02d.%s'%(int(hh),int(mm),int(ss),cent)
 for block in re.split(r'\n\s*\n',text.strip()):
  rows=block.strip().splitlines();idx=next((i for i,r in enumerate(rows) if '-->' in r),None)
  if idx is None:continue
  match=re.search(r'(\d{1,3}:\d\d:\d\d[,.]\d{3})\s*-->\s*(\d{1,3}:\d\d:\d\d[,.]\d{3})',rows[idx])
  if not match:continue
  safe='\\N'.join(rows[idx+1:]).replace('\\','\\').replace('{','').replace('}','')
  # Neutralize ASS override commands while keeping only our explicit line breaks.
  safe='\\N'.join(re.sub(r'\\[A-Za-z][^\s]*','',row).replace('{','').replace('}','') for row in rows[idx+1:])
  pos='{\\pos(%d,%d)}'%(w*style['x']/100,h*style['y']/100)
  header+='Dialogue: 0,%s,%s,Default,,0,0,0,,%s%s\n'%(clock(match[1]),clock(match[2]),pos,safe)
 return header
def burn(source,text,cfg,root):
 info=probe(source);stream=next((s for s in info['streams'] if s.get('codec_type')=='video'),None)
 if not stream:raise MediaError('MEDIA_NO_VIDEO','source_probe')
 w,h=int(stream['width']),int(stream['height']);sub=root/'captions.ass';sub.write_text(ass_text(text,cfg['style'],w,h),encoding='utf-8')
 fonts=BASE/'fonts';fonts.mkdir(exist_ok=True)
 # System DejaVu is the reliable fallback. The build embeds optional Amiri as a sibling file.
 style="subtitles='%s':fontsdir='%s'"%(str(sub).replace("'",r"'\''"),str(fonts).replace("'",r"'\''"))
 args=['-i',source];filters=['-vf',style]
 if cfg.get('logo'):
  from PIL import Image
  raw=base64.b64decode(cfg['logo'].split(',',1)[1],validate=True)
  image=Image.open(io.BytesIO(raw))
  if image.format!='PNG' or image.width*image.height>16000000:raise ValueError('صورة الشعار غير صالحة')
  logo=root/'logo.png';image.save(logo);width=max(2,round(w*cfg['logoSize']/100));args+=['-i',logo]
  x=w*cfg['logoX']/100;y=h*cfg['logoY']/100
  filters=['-filter_complex',"[0:v]%s[v];[1:v]scale=%d:-1[l];[v][l]overlay=%.1f:%.1f:shortest=1[out]"%(style,width,x,y),'-map','[out]','-map','0:a:0?']
 target=root/'result.mp4';codec=encoder()
 try:ffmpeg([*args,*filters,*codec,'-c:a','aac','-movflags','+faststart',target])
 except MediaError:
  if 'h264_nvenc' not in codec:raise
  ffmpeg([*args,*filters,'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',target])
 return target
def zip_files(root,paths):
 out=root/'results.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for p in paths:
   if p.is_file():z.write(p,p.name)
 return out
def captions(source,cfg,root,report):
 audio_source(source);report('processing','تفريغ الكلام وحفظ توقيته')
 import torch
 import onnxruntime as ort
 if hasattr(ort,'preload_dlls'):ort.preload_dlls(directory='')
 from faster_whisper import WhisperModel
 model=WhisperModel('large-v3-turbo',device='cuda',compute_type='float16',download_root=str(BASE/'cache/whisper'))
 try:segments,info=model.transcribe(str(source),language=None if cfg['language']=='auto' else cfg['language'],vad_filter=True)
 except Exception:segments,info=model.transcribe(str(source),language=None if cfg['language']=='auto' else cfg['language'],vad_filter=False)
 rows=[{'start':s.start,'end':s.end,'text':s.text} for s in segments]
 if not rows:raise ValueError('لم يتم العثور على كلام واضح في المصدر')
 original=srt(rows);p=root/'original.srt';p.write_text(original,encoding='utf-8');t=root/'transcript.txt';t.write_text('\n'.join(s['text'] for s in rows),encoding='utf-8')
 rendered=original;files=[p,t];del model;gc.collect()
 import torch
 torch.cuda.empty_cache()
 if 'Translate' in cfg['operation']:
  source_lang=cfg['language'] if cfg['language']!='auto' else info.language
  if source_lang not in LANG:raise ValueError('لغة المصدر المكتشفة غير مدعومة للترجمة')
  report('processing','ترجمة النص مع الحفاظ على توقيت الأسطر')
  rendered=translated_srt(original,source_lang,cfg['target']);p=root/'translated.srt';p.write_text(rendered,encoding='utf-8');files.append(p)
 preview={'srt':rendered[:200000],'truncated':len(rendered)>200000};atomic(root/'preview.json',preview)
 if cfg['operation'].endswith('Burn'):
  report('processing','كتابة النص على الفيديو');out=burn(source,rendered,cfg,root);zip_files(root,files).rename(root/'captions.zip');return out
 return zip_files(root,files)
def review_images(images,root):
 from transformers import pipeline
 checker=pipeline('image-classification',model='Falconsai/nsfw_image_detection',device=-1,model_kwargs={'use_safetensors':True,'trust_remote_code':False})
 for i,image in enumerate(images):
  labels=checker(image);top=max(labels,key=lambda row:row['score'])
  if top['label'].lower()=='nsfw':
   error=RuntimeError('CONTENT_REVIEW_REQUIRED');error.review={'firstFlaggedFrame':i,'checkedFrames':i+1,'generationCompleted':True};raise error
def generate(task,cfg,root,report):
 import torch
 if not torch.cuda.is_available():raise RuntimeError('GPU_REQUIRED')
 prompt=cfg['prompt']
 if re.search('[\u0600-\u06ff]',prompt):prompt=translate_lines([prompt],'ar','en')[0]
 report('processing','تحميل نموذج التوليد؛ أول استخدام قد يستغرق وقتًا أطول')
 if task=='imagegen':
  from diffusers import AutoPipelineForText2Image
  pipe=AutoPipelineForText2Image.from_pretrained('stabilityai/sdxl-turbo',torch_dtype=torch.float16,variant='fp16',use_safetensors=True)
  pipe.enable_model_cpu_offload();image=pipe(prompt=prompt,num_inference_steps=4,guidance_scale=0.0,height=512,width=512).images[0]
  del pipe;gc.collect();torch.cuda.empty_cache();review_images([image],root);out=root/'image.png';image.save(out);return out
 from diffusers import WanPipeline,AutoencoderKLWan
 from diffusers.utils import export_to_video
 name='Wan-AI/Wan2.1-T2V-1.3B-Diffusers';vae=AutoencoderKLWan.from_pretrained(name,subfolder='vae',torch_dtype=torch.float32,use_safetensors=True)
 pipe=WanPipeline.from_pretrained(name,vae=vae,torch_dtype=torch.bfloat16,use_safetensors=True)
 if any(p.is_meta for p in pipe.transformer.parameters()):raise RuntimeError('MODEL_META_TENSOR')
 pipe.enable_model_cpu_offload();pipe.vae.enable_slicing();pipe.vae.enable_tiling()
 count={2:33,5:81,8:129}[cfg['seconds']]
 frames=pipe(prompt=prompt,height=480,width=832,num_frames=count,num_inference_steps=30,guidance_scale=5.0).frames[0]
 del pipe;gc.collect();torch.cuda.empty_cache()
 report('processing','اكتمل التوليد؛ جارٍ فحص الإطارات')
 review_images(frames,root)
 out=root/'video.mp4';export_to_video(frames,str(out),fps=16);return out
def download(source,cfg,root,report):
 import ipaddress,socket
 from urllib.parse import urlsplit
 from yt_dlp import YoutubeDL
 u=urlsplit(cfg['url']);hosts=['youtube.com','youtu.be','tiktok.com','x.com','twitter.com','instagram.com','facebook.com','fb.watch','vimeo.com','snapchat.com','dailymotion.com','twitch.tv','reddit.com','redd.it','pinterest.com','pin.it']
 if u.scheme!='https' or u.username or u.password or u.port or not any(u.hostname==h or (u.hostname or '').endswith('.'+h) for h in hosts):raise ValueError('رابط غير مسموح')
 original=socket.getaddrinfo
 def public_dns(*args,**kwargs):
  rows=original(*args,**kwargs)
  if not rows or any(not ipaddress.ip_address(row[4][0].split('%')[0]).is_global for row in rows):raise ValueError('رُفض عنوان شبكة غير عام')
  return rows
 def progress(data):
  if data.get('downloaded_bytes',0)>LIMIT:raise ValueError('المقطع يتجاوز 256 MB')
  report('processing','تحميل المقطع من المنصة')
 socket.getaddrinfo=public_dns
 try:
  with YoutubeDL({'outtmpl':str(root/'download.%(ext)s'),'noplaylist':True,'playlistend':1,'max_filesize':LIMIT,'format':'bestvideo[height<=1080]+bestaudio/best[height<=1080]','merge_output_format':'mkv','quiet':True,'no_warnings':True,'enable_file_urls':False,'proxy':'','socket_timeout':20,'retries':2,'fragment_retries':2,'hls_prefer_native':True,'external_downloader':{'default':'native'},'remote_components':[],'progress_hooks':[progress]}) as y:
   info=y.extract_info(cfg['url'],download=False)
   if not info or info.get('_type') in ['playlist','multi_video'] or info.get('is_live') or info.get('has_drm'):raise ValueError('استخدم مقطعًا عامًا واحدًا غير محمي')
   y.process_ie_result(info,download=True)
 except Exception as e:
  msg=str(e).lower()
  if any(t in msg for t in ['confirm','not a bot','sign in','login','cookies']):raise RuntimeError('PLATFORM_VERIFICATION') from None
  raise RuntimeError('DOWNLOAD_FAILED') from None
 finally:socket.getaddrinfo=original
 inputs=[p for p in root.glob('download.*') if p.suffix in ['.mp4','.mkv','.webm','.mov']]
 if not inputs:raise RuntimeError('DOWNLOAD_FAILED')
 return export(max(inputs,key=lambda p:p.stat().st_size),root/'result.mp4')
def documents(task,source,cfg,root,report):
 from PIL import Image
 if task=='cutout':
  from rembg import remove,new_session
  session=new_session('u2net',providers=['CUDAExecutionProvider','CPUExecutionProvider']);out=root/'cutout.png'
  image=Image.open(source).convert('RGBA')
  if image.width*image.height>24000000:raise ValueError('أبعاد الصورة كبيرة')
  remove(image,session=session).save(out);return out
 import fitz
 pages=[]
 if cfg['ext']=='pdf':
  doc=fitz.open(source)
  if len(doc)>100:raise ValueError('اختر حتى 100 صفحة للعملية')
  for index,page in enumerate(doc):
   report('processing','قراءة الصفحة %d من %d'%(index+1,len(doc)))
   text=page.get_text().strip()
   if not text:
    image=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5));png=root/('ocr_%04d.png'%index);image.save(png)
    text=subprocess.check_output(['tesseract',str(png),'stdout','-l','ara+eng'],text=True,timeout=180)
   pages.append(text)
 else:
  pages=[subprocess.check_output(['tesseract',str(source),'stdout','-l','ara+eng'],text=True,timeout=180)]
 text='\n\n'.join(pages);out=root/'text.txt';out.write_text(text,encoding='utf-8')
 if task=='ocr':return out
 from docx import Document
 from docx.oxml import OxmlElement
 from docx.oxml.ns import qn
 doc=Document()
 for index,text in enumerate(pages):
  if index:doc.add_page_break()
  for line in text.splitlines():
   p=doc.add_paragraph(line);props=p._p.get_or_add_pPr();bidi=OxmlElement('w:bidi');bidi.set(qn('w:val'),'1');props.append(bidi)
 target=root/'document.docx';doc.save(target);return target
def process(cfg,root,report):
 source=assemble(root,cfg) if cfg.get('size') else None;task=cfg['task']
 if task=='separate':return separate(source,cfg,root,report)
 if task=='convert':return export(source,root/('result.'+cfg['format']),cfg['quality'])
 if task=='asr':return captions(source,cfg,root,report)
 if task=='burn':return burn(source,cfg['subtitles'],cfg,root)
 if task=='translate':
  text=source.read_text(encoding='utf-8-sig')
  if len(text)>200000:raise ValueError('النص يتجاوز الحد')
  out=root/('translated.'+cfg['ext']);out.write_text(translated_srt(text,cfg['source'],cfg['target']),encoding='utf-8');return zip_files(root,[source,out])
 if task in ['imagegen','videogen']:return generate(task,cfg,root,report)
 if task=='download':return download(source,cfg,root,report)
 if task in ['cutout','ocr','word']:return documents(task,source,cfg,root,report)
 if task=='resize':
  w,h={'portrait':(720,1280),'landscape':(1280,720),'square':(720,720)}[cfg['ratio']]
  if cfg['fit']=='crop':vf='scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1'%(w,h,w,h)
  elif cfg['fit']=='stretch':
   stream=next(s for s in probe(source)['streams'] if s['codec_type']=='video');sw,sh=stream['width'],stream['height'];amount=cfg['stretch']/100;s=min(w/sw,h/sh)
   rw=max(2,round(sw*(s+(w/sw-s)*amount)/2)*2);rh=max(2,round(sh*(s+(h/sh-s)*amount)/2)*2);vf='scale=%d:%d,pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1'%(rw,rh,w,h)
  else:
   # The background is a blurred copy of this video, never generated content.
   target=root/'result.mp4';codec=encoder();vf='[0:v]split=2[b][f];[b]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=20:2[bg];[f]scale=%d:%d:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]'%(w,h,w,h,w,h)
   try:ffmpeg(['-i',source,'-filter_complex',vf,'-map','[v]','-map','0:a:0?',*codec,'-c:a','aac','-movflags','+faststart',target])
   except MediaError:
    if 'h264_nvenc' not in codec:raise
    ffmpeg(['-i',source,'-filter_complex',vf,'-map','[v]','-map','0:a:0?','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-movflags','+faststart',target])
   return target
  return export(source,root/'result.mp4',filters=['-vf',vf])
 raise ValueError('نوع مهمة غير صالح')
def run_job(root):
 cfg={};report=lambda state,message,**extra:status(root,state,message,**extra)
 try:
  fd=os.open(root/'started.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
 except FileExistsError:return
 try:
  cfg=json.loads((root/'config.json').read_text());report('setup','تجهيز الأداة')
  out=process(cfg,root,report)
  if not out.is_file() or not 0<out.stat().st_size<=LIMIT:raise ValueError('الناتج يتجاوز 256 MB أو لم يكتمل؛ اختر صيغة مضغوطة أو جزءًا أقصر')
  def parts(path,prefix):
   hashes=[]
   with path.open('rb') as stream:
    while True:
     chunk=stream.read(PART)
     if not chunk:break
     (root/('%s_%05d.bin'%(prefix,len(hashes)))).write_bytes(chunk);hashes.append(hashlib.sha256(chunk).hexdigest())
   return {'size':path.stat().st_size,'chunks':hashes,'ext':path.suffix[1:]}
  data=parts(out,'output')
  if (root/'captions.zip').is_file():data['captions']=parts(root/'captions.zip','captions')
  if (root/'preview.json').is_file():data['preview']=json.loads((root/'preview.json').read_text())
  report('done','النتيجة جاهزة للمعاينة',**data)
 except Exception as e:
  import traceback
  code=e.code if isinstance(e,MediaError) else str(e) if str(e) in ['CONTENT_REVIEW_REQUIRED','PLATFORM_VERIFICATION','DOWNLOAD_FAILED','MODEL_META_TENSOR','GPU_REQUIRED','CUDA_PROVIDER_UNAVAILABLE','CUDA_SESSION_NOT_ACTIVE'] else 'TOOL_'+type(e).__name__.upper()
  frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(e.__traceback__)][-8:]
  diagnostic={'task':cfg.get('task'),'exception':type(e).__name__,'frames':frames}
  if isinstance(e,MediaError):diagnostic['media']=e.details
  if hasattr(e,'review'):diagnostic.update(stage='content_review',review=e.review)
  friendly={'CONTENT_REVIEW_REQUIRED':'اكتمل التوليد؛ أوقف فحص المحتوى تسليم النتيجة. القرار يخص الإطارات الناتجة ولا يثبت مشكلة في وصفك.','PLATFORM_VERIFICATION':'المنصة تطلب تحققًا لا يمكن إكماله داخل الخادم','MODEL_META_TENSOR':'أوزان النموذج لم تُحمّل بالكامل','GPU_REQUIRED':'هذه العملية تحتاج GPU فعليًا'}
  message=str(e) if isinstance(e,MediaError) else str(e) if isinstance(e,ValueError) and re.search('[\u0600-\u06ff]',str(e)) and not re.search(r'https?://|[/\\]',str(e)) else friendly.get(code,'تعذرت مرحلة المعالجة؛ تفاصيل الدعم مرفقة دون محتوى الملف')
  report('error',message,code=code,diagnostic=diagnostic)
def dependencies(task):
 packages={'separate':['audio-separator[gpu]==0.48.0','onnxruntime-gpu[cuda,cudnn]==1.23.2','numpy==2.2.6','numba==0.61.2'],'asr':['faster-whisper==1.2.1','ctranslate2==4.6.0','transformers==4.51.3','huggingface-hub==0.36.0','sentencepiece==0.2.0','safetensors==0.8.0'],'translate':['transformers==4.51.3','huggingface-hub==0.36.0','sentencepiece==0.2.0','safetensors==0.8.0'],'imagegen':['diffusers==0.35.1','transformers==4.51.3','huggingface-hub==0.36.0','accelerate==1.6.0','safetensors==0.8.0','sentencepiece==0.2.0','ftfy==6.3.1'],'videogen':['diffusers==0.35.1','transformers==4.51.3','huggingface-hub==0.36.0','accelerate==1.6.0','safetensors==0.8.0','sentencepiece==0.2.0','ftfy==6.3.1','imageio[ffmpeg]==2.37.0'],'cutout':['rembg[gpu]==2.0.67'],'word':['PyMuPDF==1.26.6','python-docx==1.2.0'],'ocr':['PyMuPDF==1.26.6'],'download':['yt-dlp[default]==2026.10.26']}
 return packages.get(task,[])+['Pillow==11.3.0'] if task in ['burn','asr','imagegen','videogen','cutout'] else packages.get(task,[])
def environment(task,root):
 deps=dependencies(task)
 if not deps:return sys.executable
 digest=hashlib.sha256(json.dumps(deps).encode()).hexdigest()[:16];folder=BASE/'cache/envs'/digest;python=folder/'bin/python';ready=folder/'ready'
 if not ready.exists():
  status(root,'setup','تجهيز مكتبات الأداة المعزولة؛ مرة واحدة للجلسة')
  subprocess.run([sys.executable,'-m','venv','--system-site-packages',str(folder)],check=True,timeout=120)
  if task in ['ocr','word']:
   subprocess.run(['apt-get','update','-qq'],check=True,timeout=180)
   subprocess.run(['apt-get','install','-y','-qq','tesseract-ocr','tesseract-ocr-ara','tesseract-ocr-eng'],check=True,timeout=300)
  subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','--quiet',*deps],check=True,timeout=900)
  ready.write_text('1')
 return str(python)
def serve():
 import fcntl
 BASE.mkdir(exist_ok=True);(BASE/'cache/envs').mkdir(parents=True,exist_ok=True)
 lock=open(BASE/'service.lock','a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:return
 idle=time.monotonic()
 health={'activeJob':None,'heartbeat':time.time(),'version':VERSION}
 done=threading.Event()
 def beat():
  while not done.is_set():
   try:atomic(BASE/'service.json',{**health,'heartbeat':time.time()})
   except OSError:pass
   done.wait(5)
 threading.Thread(target=beat,daemon=True).start()
 while time.monotonic()-idle<2400:
  for path in sorted((BASE/'jobs').glob('*/ready'),key=lambda p:p.stat().st_mtime):
   root=path.parent
   if (root/'started.lock').exists():continue
   cfg=json.loads((root/'config.json').read_text());idle=time.monotonic();health['activeJob']=root.name
   try:
    python=environment(cfg['task'],root)
    subprocess.run([python,str(Path(__file__).resolve()),'--job',root.name],cwd=BASE,timeout=14400,check=True)
   except (subprocess.SubprocessError,OSError):
    status(root,'error','تعذر تجهيز أو تشغيل عامل الأداة؛ أعد المحاولة في مهمة جديدة',code='WORKER_SETUP_FAILED')
   finally:health['activeJob']=None;idle=time.monotonic()
  try:
   lease=json.loads((BASE/'lease.json').read_text())
   if time.time()-float(lease['updated'])>300:return
  except (OSError,ValueError,KeyError):pass
  time.sleep(1)
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='--serve':serve()
 elif len(sys.argv)>2 and sys.argv[1]=='--job' and re.fullmatch(r'[a-f0-9-]{36}',sys.argv[2]):run_job(BASE/'jobs'/sys.argv[2])
