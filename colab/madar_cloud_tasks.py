"""Allowlisted media/document jobs. User inputs are data, never Python or shell."""
import gc, json, re, subprocess, sys, zipfile, ctypes, importlib, importlib.metadata, os, time, threading, queue, shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))

DEPS={
 'ocr':['easyocr==1.7.2','pypdfium2==5.15.2'],
 'cutout':['rembg[gpu]==2.0.67','onnxruntime-gpu[cuda,cudnn]==1.23.2'],
 'word':['pdf2docx==0.5.13','pypdfium2==5.15.2'],
 'asr':['ctranslate2==4.6.0','onnxruntime-gpu[cuda,cudnn]==1.23.2','av==16.0.1','tokenizers==0.21.4','huggingface-hub==0.36.0','nvidia-cublas-cu12>=12,<13','nvidia-cudnn-cu12>=9,<10'],
 'translate':['transformers==4.51.3','sentencepiece==0.2.3','accelerate==1.6.0'],
 'burn':[], 'convert':[], 'resize':[], 'hdr':[],
 'imagegen':['diffusers==0.35.1','transformers==4.51.3','accelerate==1.6.0','sentencepiece==0.2.3'],
 'videogen':['diffusers==0.35.1','transformers==4.51.3','accelerate==1.6.0','sentencepiece==0.2.3','ftfy==6.3.1','imageio[ffmpeg]==2.37.0']}
# Install the full ASR/translation stack before importing any ML package.
DEPS['asr']=[*DEPS['asr'],*DEPS['translate']]

LANG={'ar':'arb_Arab','en':'eng_Latn','ja':'jpn_Jpan','fr':'fra_Latn','es':'spa_Latn','de':'deu_Latn','tr':'tur_Latn'}


def cuda():
 import torch
 if not torch.cuda.is_available(): raise ValueError('هذه الأداة تحتاج GPU فعليًا؛ اختر T4 أو L4 أو A100 ثم أعد المحاولة')
 return torch


_INSTALLED=set()
_MODELS={}

def release_models():
 stop_translator();_MODELS.clear();gc.collect()
 torch=sys.modules.get('torch')
 if torch and torch.cuda.is_available():torch.cuda.empty_cache()

def cached_model(key,loader,report):
 if key not in _MODELS:
  release_models();_MODELS[key]=loader()
 else:report('processing','النموذج جاهز في ذاكرة الجلسة؛ بدء المعالجة مباشرة')
 return _MODELS[key]

def install(task, report):
 if task in _INSTALLED:return
 report('setup','فحص مكتبات الأداة؛ تُجهّز مرة واحدة داخل هذه الجلسة')
 constraints=Path(__file__).parent/'constraints.txt'
 constraints.write_text('numpy==2.2.6\nnumba==0.61.2\nonnxruntime-gpu==1.23.2\nhuggingface-hub==0.36.0\ntokenizers==0.21.4\nopencv-python-headless==4.11.0.86\n')
 deps=DEPS[task]
 if deps:
  try:
   from madar_colab_runtime import install_once
   commands=[['install','--quiet','--disable-pip-version-check','-c',str(constraints),*deps]]
   if task=='asr':commands.append(['install','--quiet','--no-deps','faster-whisper==1.2.1'])
   install_once('task-'+task,commands,report=report)
  except subprocess.TimeoutExpired:raise ValueError('انتهت مهلة تجهيز المكتبات؛ يمكن إعادة المحاولة بنفس الجلسة · DEPENDENCY_TIMEOUT')
  except subprocess.CalledProcessError:raise ValueError('تعذر تثبيت مكتبات الأداة المتوافقة · DEPENDENCY_INSTALL')
 importlib.invalidate_caches();_INSTALLED.add(task)

def load_model(loader,report):
 # Retry only known transfer failures. Hugging Face reuses verified cached files.
 for attempt in range(3):
  try:return loader()
  except Exception as exc:
   code=type(exc).__name__;text=str(exc).lower()
   transient=code in {'ReadTimeout','ConnectTimeout','Timeout','ConnectionError','LocalEntryNotFoundError'} or any(x in text for x in ['timed out','connection reset','temporarily unavailable','502 bad gateway','503 service unavailable','504 gateway'])
   if not transient or attempt==2:raise
   report('processing',f'تأخر تنزيل النموذج؛ استكمال التنزيل المحفوظ · {attempt+1}/2')
   time.sleep(attempt+1)


def transcribe_transformers(source,cfg,root,report):
 install('translate',report)
 torch=cuda()
 from transformers import AutoModelForSpeechSeq2Seq,AutoProcessor,pipeline
 name='openai/whisper-large-v3-turbo'
 report('processing','تشغيل Whisper على PyTorch GPU كمسار توافق بديل')
 def loader():
  model=load_model(lambda:AutoModelForSpeechSeq2Seq.from_pretrained(name,torch_dtype=torch.float16,low_cpu_mem_usage=True,use_safetensors=True,trust_remote_code=False).to('cuda'),report)
  processor=load_model(lambda:AutoProcessor.from_pretrained(name,trust_remote_code=False),report)
  return pipeline('automatic-speech-recognition',model=model,tokenizer=processor.tokenizer,feature_extractor=processor.feature_extractor,chunk_length_s=30,batch_size=1,torch_dtype=torch.float16,device='cuda:0')
 pipe=cached_model('whisper-pytorch',loader,report);kwargs={'task':'transcribe'}
 if cfg['language']!='auto':kwargs['language']=cfg['language']
 out=pipe(str(source),return_timestamps=True,generate_kwargs=kwargs)
 cues=[]
 for i,chunk in enumerate(out.get('chunks',[]),1):
  start,end=chunk.get('timestamp',(None,None));text=chunk.get('text','').strip()
  if not text:continue
  if start is None or end is None or end<=start:raise ValueError('تعذر استنتاج توقيت بعض الجمل؛ أعد التفريغ بلغة محددة · ASR_TIMESTAMPS')
  cues.append(f'{i}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n')
 if not cues:raise ValueError('لم يُكتشف كلام واضح مع توقيت صالح · ASR_NO_SPEECH')
 (root/'original.srt').write_text('\n'.join(cues),encoding='utf-8');(root/'transcript.txt').write_text(out.get('text',''),encoding='utf-8')
 (root/'language.json').write_text(json.dumps({'language':cfg['language']}),encoding='utf-8')
 return zip_outputs(root,[root/'original.srt',root/'transcript.txt'])


def preload_cuda():
 # CTranslate2 also needs its libraries loaded before import, not just an ORT provider.
 import site
 for folder in site.getsitepackages():
  for library in ['nvidia/cublas/lib/libcublasLt.so.12','nvidia/cublas/lib/libcublas.so.12','nvidia/cudnn/lib/libcudnn.so.9']:
   p=Path(folder)/library
   if p.exists():ctypes.CDLL(str(p),mode=ctypes.RTLD_GLOBAL)


def run_ffmpeg(args):
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-protocol_whitelist','file,pipe',*map(str,args)],check=True,timeout=1800)


def ensure_image(source):
 from PIL import Image, ImageOps
 Image.MAX_IMAGE_PIXELS=24000000
 image=Image.open(source)
 if image.width*image.height>24000000:raise ValueError('الصورة تتجاوز 24 مليون بكسل')
 return ImageOps.exif_transpose(image).convert('RGB')


def zip_outputs(root, names):
 out=root/'results.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for path in names:z.write(path,Path(path).name)
 return out


def timestamp(seconds):
 ms=max(0,round(float(seconds)*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
 return f'{h:02}:{m:02}:{s:02},{ms:03}'


def load_nllb_weights(name,revision,device='cuda'):
 import torch
 from transformers import AutoConfig,AutoModelForSeq2SeqLM
 from transformers.utils.hub import cached_file
 from safetensors import safe_open
 from safetensors.torch import load_file
 # Restore safetensors alias metadata before tying shared embeddings. Strict
 # loading rejects missing weights; allocating empty tensors is never a fix.
 weights_path=cached_file(name,'model.safetensors',revision=revision)
 state=load_file(weights_path,device='cpu')
 with safe_open(weights_path,framework='pt',device='cpu') as checkpoint:aliases=checkpoint.metadata() or {}
 for alias,target in aliases.items():
  if alias!='format' and alias not in state and target in state:state[alias]=state[target]
 config=AutoConfig.from_pretrained(name,revision=revision,trust_remote_code=False)
 dtype=torch.float16 if device=='cuda' else torch.float32
 with torch.device('cpu'):model=AutoModelForSeq2SeqLM.from_config(config,torch_dtype=dtype,trust_remote_code=False)
 model.load_state_dict(state,strict=True);del state
 model.tie_weights()
 if any(p.is_meta for p in model.parameters()) or any(p.is_meta for p in model.buffers()):raise ValueError('لم تُحمّل أوزان الترجمة كاملة؛ رُفض تشغيل نموذج بأوزان فارغة · MODEL_META_TENSOR')
 return model.eval().to(device)


_TRANSLATOR=None
class TranslationWorkerError(RuntimeError):
 def __init__(self,payload):super().__init__(payload.get('message','تعذر محرك الترجمة'));self.worker_diagnostic=payload


def stop_translator():
 global _TRANSLATOR
 child=_TRANSLATOR;_TRANSLATOR=None
 if not child:return
 p=child['process']
 try:
  p.stdin.close();p.wait(timeout=3)
 except (OSError,subprocess.TimeoutExpired):
  p.terminate()
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
 child['log'].close()


def translation_worker():
 global _TRANSLATOR
 if _TRANSLATOR and _TRANSLATOR['process'].poll() is None:return _TRANSLATOR
 stop_translator();env=os.environ.copy();env.update(USE_TF='0',USE_FLAX='0',TOKENIZERS_PARALLELISM='false')
 log=open(Path(__file__).parent/'translation-worker.log','a')
 try:p=subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),'--translation-worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',bufsize=1,env=env)
 except BaseException:log.close();raise
 events=queue.Queue(maxsize=100)
 def reader():
  try:
   for line in iter(p.stdout.readline,''):
    if len(line)>8*1024**2:events.put({'event':'protocol-error'});return
    try:message=json.loads(line)
    except ValueError:continue
    try:events.put(message,timeout=1)
    except queue.Full:return
  finally:
   try:events.put_nowait({'event':'closed'})
   except queue.Full:pass
 threading.Thread(target=reader,daemon=True).start();_TRANSLATOR={'process':p,'events':events,'log':log};return _TRANSLATOR


def translate_lines(lines,source,target,report,names=None):
 if source not in LANG or target not in LANG:raise ValueError('لغة ترجمة غير مدعومة')
 # A fresh interpreter sees the installed stack, not stale lazy imports from ASR.
 # It remains warm for later translations and is released before other GPU models.
 if _MODELS:release_models()
 child=translation_worker();p=child['process']
 p.stdin.write(json.dumps({'lines':lines,'source':source,'target':target,'names':names or {}},ensure_ascii=False)+'\n');p.stdin.flush();deadline=time.monotonic()+1200
 while time.monotonic()<deadline:
  try:event=child['events'].get(timeout=5)
  except queue.Empty:
   if p.poll() is not None:break
   continue
  if event.get('event')=='progress':report('processing',event.get('message','تشغيل محرك الترجمة'));continue
  if event.get('event')=='result':
   result=event.get('lines')
   if not isinstance(result,list) or len(result)!=len(lines) or any(not isinstance(t,str) for t in result):stop_translator();raise ValueError('رد ترجمة غير مكتمل؛ لم يُعتمد الناتج')
   return result
  if event.get('event')=='error':raise TranslationWorkerError(event)
  if event.get('event') in {'closed','protocol-error'}:break
 stop_translator();raise ValueError('توقف محرك الترجمة المنفصل أو انتهت مهلته؛ المصدر محفوظ · TRANSLATION_WORKER_STOPPED')


def _translate_lines_local(lines, source, target, report, names=None,device='cuda'):
 if device=='cuda':torch=cuda()
 else:import torch
 from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
 report('processing','تحميل نموذج الترجمة NLLB إلى GPU')
 if tuple(int(v) for v in torch.__version__.split('.')[:2]) < (2,6):raise ValueError('نموذج الترجمة يحتاج PyTorch 2.6 أو أحدث لتحميل الأوزان بأمان')
 name='facebook/nllb-200-distilled-600M';revision='38bd1c6a0f58097b26ef7c7cd73a0dcac034350a'
 def loader():
  tok=load_model(lambda:AutoTokenizer.from_pretrained(name,revision=revision,src_lang=LANG[source],trust_remote_code=False),report)
  model=load_model(lambda:load_nllb_weights(name,revision,device),report)
  return tok,model
 tok,model=cached_model('nllb',loader,report);tok.src_lang=LANG[source]

 try:
  result=[]
  names=names or {}
  pattern='('+'|'.join(re.escape(k) for k in sorted(names,key=len,reverse=True))+')' if names else None
  for i,line in enumerate(lines):
   if not line.strip() or '-->' in line or line.strip().isdigit() or line.strip()=='WEBVTT':result.append(line);continue
   segments=re.split(pattern,line) if pattern else [line]
   blocks=[piece if piece in names else sub for piece in segments for sub in ([piece] if piece in names else [piece[j:j+400] for j in range(0,len(piece),400)])];out=[]
   for block in blocks:
    if block in names:out.append(names[block]);continue
    if not block.strip():continue
    inp=tok(block,return_tensors='pt',truncation=True,max_length=512).to(device)
    with torch.inference_mode():tokens=model.generate(**inp,forced_bos_token_id=tok.convert_tokens_to_ids(LANG[target]),max_new_tokens=512)
    out.append(tok.batch_decode(tokens,skip_special_tokens=True)[0])
   result.append(' '.join(out));report('processing',f'ترجمة النص · {i+1}/{len(lines)} سطرًا؛ التوقيت محفوظ')
  return result
 finally:gc.collect()


def english_prompt(prompt,report):
 if re.search('[\u0600-\u06ff]',prompt):return translate_lines([prompt],'ar','en',report)[0]
 return prompt


def safety_components(device='cuda',dtype=None):
 import torch
 from diffusers.pipelines.stable_diffusion.safety_checker import StableDiffusionSafetyChecker
 from transformers import CLIPImageProcessor
 checker,loading=StableDiffusionSafetyChecker.from_pretrained('CompVis/stable-diffusion-safety-checker',torch_dtype=dtype or torch.float16,output_loading_info=True)
 if loading.get('missing_keys') or loading.get('mismatched_keys') or loading.get('error_msgs'):raise ValueError('لم تُحمّل أوزان فحص المحتوى كاملة؛ لم يُسلّم الناتج · CONTENT_REVIEW_ERROR')
 if any(p.is_meta for p in checker.parameters()) or any(p.is_meta for p in checker.buffers()):raise ValueError('أوزان فحص المحتوى غير جاهزة؛ لم يُسلّم الناتج · CONTENT_REVIEW_ERROR')
 checker=checker.eval().to(device)
 processor=CLIPImageProcessor.from_pretrained('CompVis/stable-diffusion-safety-checker')
 return checker,processor


# Dedicated visual classifier for generated video. CompVis can reject even a
# constant RGB frame; do not use its image-generation concept embeddings here.
VIDEO_REVIEW_MODEL='Falconsai/nsfw_image_detection'
VIDEO_REVIEW_REVISION='96cb0d0342c7afb80cab76ecc58b265fa44da256'

def video_content_flags(logits,labels):
 import torch
 labels={int(k):str(v).lower() for k,v in labels.items()}
 if set(labels)!={0,1} or set(labels.values())!={'normal','nsfw'}:raise ValueError('فئات نموذج فحص الفيديو غير مطابقة؛ لم يُسلّم الناتج · CONTENT_REVIEW_ERROR')
 if logits.ndim!=2 or logits.shape[1]!=2 or not bool(torch.isfinite(logits).all()):raise ValueError('نتيجة مصنّف الفيديو غير صالحة؛ لم يُسلّم الناتج · CONTENT_REVIEW_ERROR')
 nsfw=next(k for k,v in labels.items() if v=='nsfw')
 # Standard binary decision; uncertain ties are blocked too.
 return (logits.float().softmax(dim=-1)[:,nsfw]>=0.5).cpu().tolist()


def video_safety_components(device='cuda'):
 import torch
 from transformers import AutoImageProcessor,AutoModelForImageClassification
 model,loading=AutoModelForImageClassification.from_pretrained(VIDEO_REVIEW_MODEL,revision=VIDEO_REVIEW_REVISION,torch_dtype=torch.float32,use_safetensors=True,trust_remote_code=False,output_loading_info=True)
 if loading.get('missing_keys') or loading.get('mismatched_keys') or loading.get('error_msgs') or any(p.is_meta for p in model.parameters()) or any(p.is_meta for p in model.buffers()):raise ValueError('لم تُحمّل أوزان فحص الفيديو كاملة؛ لم يُسلّم الناتج · CONTENT_REVIEW_ERROR')
 model=model.eval().to(device)
 processor=AutoImageProcessor.from_pretrained(VIDEO_REVIEW_MODEL,revision=VIDEO_REVIEW_REVISION,trust_remote_code=False,use_fast=False)
 def checker(images,clip_input):
  return images,video_content_flags(model(pixel_values=clip_input).logits,model.config.id2label)
 return checker,processor


def video_scene_conditioning(original,translated):
 # Preserve the requested action/place; make clothing explicit for child scenes.
 child_en=re.search(r'\b(?:boy|girl|child|children|kid|kids|toddler|baby|teenager)\b',translated,re.I)
 child_ar=re.search(r'(?<!\w)(?:ال)?(?:ولد|طفل|طفلة|[أا]طفال|صبي|بنت|فتى|فتاة صغيرة)(?!\w)',original)
 prompt=translated.strip()
 if child_en or child_ar:
  beach=re.search(r'\b(?:beach|shore|seaside|coast)\b',translated,re.I) or re.search(r'شاط|ساحل',original)
  if beach:prompt+=' The child is wearing a loose long-sleeved shirt, long trousers and sneakers throughout the scene. Wide camera framing keeps the complete outfit visible.'
  else:prompt+=' The child is fully clothed in clothing appropriate to the described setting and time period.'
 negative='nudity, naked, shirtless, bare chest, underwear, sexual content'
 return prompt,negative


class ContentReviewRequired(ValueError):
 def __init__(self,message,review_details=None):
  super().__init__(message);self.review_details=review_details or {}


def review_video_frames(frames,report):
 import numpy as np
 torch=cuda()
 if not frames:raise ValueError('لم ينتج النموذج إطارات صالحة للفحص · CONTENT_REVIEW_ERROR')
 report('processing','اكتمل توليد اللقطة؛ جارٍ فحص المحتوى قبل التصدير')
 # Use the pinned dedicated classifier in full precision for every frame.
 checker,processor=video_safety_components()
 for start in range(0,len(frames),4):
  batch=[frame.convert('RGB') for frame in frames[start:start+4]]
  pixels=processor(images=batch,return_tensors='pt').pixel_values.to('cuda',dtype=torch.float32)
  with torch.inference_mode():_,flags=checker(images=np.stack([np.asarray(frame,dtype=np.float32)/255.0 for frame in batch]),clip_input=pixels)
  if not isinstance(flags,(list,tuple)) or len(flags)!=len(batch) or not all(isinstance(flag,(bool,np.bool_)) for flag in flags):raise ValueError('لم يكتمل فحص جميع إطارات اللقطة؛ لم يُسلّم ناتج غير مفحوص · CONTENT_REVIEW_ERROR')
  if any(flags):
   first=start+next(i for i,flag in enumerate(flags) if flag)
   details={'firstFlaggedFrame':first+1,'timestampMs':round(first*1000/16),'checkedFrames':start+len(batch),'totalFrames':len(frames),'fps':16,'checker':VIDEO_REVIEW_MODEL,'revision':VIDEO_REVIEW_REVISION}
   raise ContentReviewRequired('اكتمل التوليد؛ أوقف مصنّف المحتوى تسليم اللقطة. هذا القرار يخص الإطارات الناتجة ولا يثبت وجود مشكلة في وصفك · CONTENT_REVIEW_REQUIRED',details)
  report('processing',f'فحص اللقطة قبل التصدير · {min(start+4,len(frames))}/{len(frames)} إطارًا')
 return True


def check_video_text_dependencies():
 # Exercise the real installed pipeline text path before downloading weights.
 try:
  import ftfy
  from diffusers.pipelines.wan.pipeline_wan import prompt_clean
  cleaned=prompt_clean('  Madar &amp; video  ')
  if cleaned!='Madar & video':raise ValueError('unexpected text preprocessing result')
 except (ImportError,NameError,AttributeError,ValueError) as exc:
  raise ValueError('تعذر تجهيز مكتبة تهيئة وصف الفيديو؛ أعد المحاولة لتجهيز المتطلبات · VIDEOGEN_TEXT_SETUP') from exc


def process(task, source, cfg, root, report):
 if task=='asr' and not cfg.get('_basic_asr'):return caption_workflow(source,cfg,root,report)
 install(task,report)
 if task=='ocr':
  import easyocr,torch;import numpy as np
  report('processing','تحميل نموذج OCR واستخراج النص')
  reader=cached_model('ocr-'+cfg['language'],lambda:easyocr.Reader({'ar':['ar','en'],'en':['en'],'ja':['ja','en']}[cfg['language']],gpu=torch.cuda.is_available()),report)
  def text(image):return '\n'.join(reader.readtext(np.asarray(image.convert('RGB')),detail=0,paragraph=True))
  if cfg['ext']=='pdf':
   import pypdfium2 as pdfium
   doc=pdfium.PdfDocument(str(source))
   if len(doc)>20:raise ValueError('اختر PDF حتى 20 صفحة؛ قسّم الملف من أداة ترتيب PDF')
   pages=[]
   try:
    for i in range(len(doc)):
     page=doc[i]
     width,height=page.get_size()
     if width*height*1.8**2>24000000:raise ValueError('صفحة PDF تتجاوز حد الصورة الآمن؛ قلّل مقاسها أولًا')
     bitmap=page.render(scale=1.8);image=bitmap.to_pil();pages.append(f'— الصفحة {i+1} —\n'+text(image));bitmap.close();page.close();report('processing',f'OCR · الصفحة {i+1}/{len(doc)}')
   finally:doc.close()
   content='\n\n'.join(pages)
  else:content=text(ensure_image(source))
  if not content.strip():raise ValueError('لم يُكتشف نص واضح؛ جرّب صورة أوضح')
  out=root/'ocr.txt';out.write_text(content,encoding='utf-8');return out
 if task=='cutout':
  import torch;gpu=torch.cuda.is_available()
  if gpu:preload_cuda()
  import onnxruntime as ort
  if gpu and hasattr(ort,'preload_dlls'):ort.preload_dlls(directory='')
  from rembg import new_session, remove
  report('processing','تحميل نموذج العزل'+(' على GPU' if gpu else ' على المعالج'))
  session=cached_model('cutout-'+('gpu' if gpu else 'cpu'),lambda:new_session('isnet-general-use',providers=['CUDAExecutionProvider','CPUExecutionProvider'] if gpu else ['CPUExecutionProvider']),report)
  image=ensure_image(source);result=remove(image,session=session);out=root/'cutout.png';result.save(out);return out
 if task=='word':
  import pypdfium2 as pdfium
  doc=pdfium.PdfDocument(str(source));count=len(doc);doc.close()
  if count>20:raise ValueError('تحويل Word حتى 20 صفحة للعملية؛ قسّم المستند أولًا')
  from pdf2docx import Converter
  report('processing','إعادة بناء النصوص والصور والجداول في Word')
  out=root/'converted.docx';converter=Converter(str(source))
  try:converter.convert(str(out),start=0,end=count,multi_processing=False)
  finally:converter.close()
  return out
 if task=='asr':
  cuda();report('processing','تجهيز الصوت واختبار محرك Whisper على CUDA')
  try:
   preload_cuda();import onnxruntime as ort
   if hasattr(ort,'preload_dlls'):ort.preload_dlls(directory='')
   from faster_whisper import WhisperModel
   import ctranslate2
   supported=ctranslate2.get_supported_compute_types('cuda');compute=next((v for v in ['float16','int8_float16','float32'] if v in supported),None)
   if not compute:raise RuntimeError('CUDA_COMPUTE_UNSUPPORTED')
   model=cached_model('whisper-'+compute,lambda:load_model(lambda:WhisperModel('large-v3-turbo',device='cuda',compute_type=compute),report),report)
   def decode(vad):
    segments,info=model.transcribe(str(source),language=None if cfg['language']=='auto' else cfg['language'],vad_filter=vad,beam_size=5)
    text=[];srt=[]
    for i,seg in enumerate(segments,1):
     text.append(seg.text.strip());srt.append(f'{i}\n{timestamp(seg.start)} --> {timestamp(seg.end)}\n{seg.text.strip()}\n');report('processing',f'تفريغ الكلام · وصلنا إلى {round(seg.end/60,1)} دقيقة')
    return text,srt,info
   try:text,srt,info=decode(True)
   except Exception as exc:
    if not any(x in (type(exc).__module__+' '+str(exc)).lower() for x in ['onnxruntime','silero','vad']):raise
    report('processing','تعذر مرشح الصمت؛ استكمال التفريغ بنفس النموذج دون المرشح');text,srt,info=decode(False)
  except (RuntimeError,OSError,ImportError,ValueError) as exc:
   if not any(x in str(exc).lower() for x in ['cuda','cudnn','cublas','ctranslate','onnxruntime','undefined symbol','compute type']):raise
   if 'out of memory' in str(exc).lower():raise
   model=None;release_models();return transcribe_transformers(source,cfg,root,report)
  if not text:raise ValueError('لم يُكتشف كلام واضح في الملف · ASR_NO_SPEECH')
  (root/'language.json').write_text(json.dumps({'language':info.language}),encoding='utf-8')
  txt=root/'transcript.txt';sub=root/'original.srt';txt.write_text('\n'.join(text),encoding='utf-8');sub.write_text('\n'.join(srt),encoding='utf-8');return zip_outputs(root,[txt,sub])
 if task=='translate':
  text=source.read_text(encoding='utf-8-sig')
  if len(text)>200000:raise ValueError('النص أطول من الحد 200 ألف حرف')
  names={}
  for row in cfg.get('names','').splitlines()[:30]:
   key,_,value=row.partition('=');key=key.strip();value=value.strip() or key
   if key:names[key]=value
  translated='\n'.join(translate_lines(text.splitlines(),cfg['source'],cfg['target'],report,names))
  out=root/('translated.'+cfg['ext']);original=root/('original.'+cfg['ext']);out.write_text(translated,encoding='utf-8');original.write_text(text,encoding='utf-8');return zip_outputs(root,[original,out])
 if task=='hdr':
  from madar_dovi import make_tiktok
  return make_tiktok(source,cfg,root,report)
 if task in {'burn','convert','resize'}:
  from madar_colab_runtime import video_encoder, nvenc_ready
  import madar_colab_runtime as media_runtime
  out=root/('result.'+(cfg.get('format','mp4')));report('processing','فحص قدرات الفيديو وتجهيز الناتج')
  if task=='convert':
   media_runtime.export_media(source,out,quality=cfg['quality']);return out
  codec=video_encoder();report('processing','ترميز الفيديو على GPU · NVENC' if 'h264_nvenc' in codec else 'ترميز CPU لهذا الفيديو؛ '+(media_runtime.nvenc_explanation() if hasattr(media_runtime,'nvenc_explanation') else 'لم ينجح اختبار NVENC'))
  filters=[]
  if task=='burn':
   from madar_captions import burn
   return burn(source,cfg,root,report,codec,run_ffmpeg,subtitle_style)
  if task=='resize':
   w,h={'portrait':(720,1280),'landscape':(1280,720),'square':(720,720)}[cfg['ratio']]
   if cfg['fit']=='stretch':
    from madar_captions import dimensions
    sw,sh=dimensions(source);amount=float(cfg.get('stretch','100'))/100
    if not 0<=amount<=1:raise ValueError('نسبة التمديد غير صالحة')
    scale=min(w/sw,h/sh);rw=max(2,min(w,round(sw*(scale+(w/sw-scale)*amount)/2)*2));rh=max(2,min(h,round(sh*(scale+(h/sh-scale)*amount)/2)*2))
    filters=['-vf',f'scale={rw}:{rh},pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1']
   elif cfg['fit']=='crop':filters=['-vf',f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1']
   else:filters=['-filter_complex',f'[0:v]split=2[bg][fg];[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=20:2[blur];[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[front];[blur][front]overlay=(W-w)/2:(H-h)/2,setsar=1[v]','-map','[v]','-map','0:a:0?']
  if task=='convert':
   q={'high':'20','balanced':'25','small':'30'}[cfg['quality']]
   codec=[*codec];flag='-cq' if 'h264_nvenc' in codec else '-crf';codec[codec.index(flag)+1]=q
  args=['-i',source,*filters,*codec,'-c:a','aac','-b:a','160k','-map_metadata','-1','-movflags','+faststart',out]
  try:run_ffmpeg(args)
  except subprocess.CalledProcessError:
   if 'h264_nvenc' not in codec:raise
   report('processing','تعذر NVENC لهذا الملف؛ استكمال التصدير على CPU')
   run_ffmpeg(['-i',source,*filters,'-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-b:a','160k','-map_metadata','-1','-movflags','+faststart',out])
  return out
 if task=='imagegen':
  torch=cuda();prompt=english_prompt(cfg['prompt'],report)
  from diffusers import AutoPipelineForText2Image
  report('processing','تجهيز نموذج الصورة من ذاكرة الجلسة أو تنزيله عند أول استخدام')
  def load_image():
   checker,processor=safety_components()
   return AutoPipelineForText2Image.from_pretrained('stabilityai/sd-turbo',torch_dtype=torch.float16,variant='fp16',use_safetensors=True,safety_checker=checker,feature_extractor=processor).to('cuda')
  pipe=cached_model('sd-turbo',load_image,report)
  result=pipe(prompt=prompt,num_inference_steps=4,guidance_scale=0.0,width=512,height=512)
  if result.nsfw_content_detected and any(result.nsfw_content_detected):raise ValueError('تعذر تسليم الصورة وفق فحص سلامة المحتوى؛ عدّل الوصف')
  out=root/'generated.png';result.images[0].save(out);return out
 if task=='videogen':
  report('setup','فحص مكتبات تهيئة وصف الفيديو قبل تحميل النموذج');check_video_text_dependencies()
  torch=cuda()
  if torch.cuda.get_device_capability()[0]<8:raise ValueError('توليد الفيديو يحتاج L4 أو A100؛ T4 غير مناسب لهذا المسار')
  prompt=english_prompt(cfg['prompt'],report);prompt,negative_prompt=video_scene_conditioning(cfg['prompt'],prompt);release_models()
  from diffusers import WanPipeline, AutoencoderKLWan
  from diffusers.utils import export_to_video
  release_models();name='Wan-AI/Wan2.1-T2V-1.3B-Diffusers';report('processing','تجهيز نموذج الفيديو؛ الأوزان تُنزّل عند أول استخدام وتبقى في قرص الجلسة')
  vae=load_model(lambda:AutoencoderKLWan.from_pretrained(name,subfolder='vae',torch_dtype=torch.float32,use_safetensors=True),report)
  pipe=load_model(lambda:WanPipeline.from_pretrained(name,vae=vae,torch_dtype=torch.bfloat16,use_safetensors=True,low_cpu_mem_usage=True),report);pipe.enable_model_cpu_offload();pipe.vae.enable_tiling()
  def step(p,i,t,kwargs):report('processing',f'توليد اللقطة · الخطوة {i+1}/25');return kwargs
  frames=pipe(prompt=prompt,negative_prompt=negative_prompt,width=512,height=288,num_frames={'short':33,'five':81,'eight':129}[cfg['length']],output_type='pil',num_inference_steps=25,guidance_scale=5.0,callback_on_step_end=step).frames[0]
  del pipe,vae;gc.collect();torch.cuda.empty_cache()
  review_video_frames(frames,report)
  report('processing','اكتمل الفحص؛ جارٍ تصدير فيديو MP4')
  out=root/'generated.mp4';export_to_video(frames,str(out),fps=16);return out
 raise ValueError('نوع أداة غير مدعوم')

# Timed text is always data; style values are mapped to a fixed ASS palette.
def subtitle_style(cfg):
 color={'ivory':'&H00C9E7F2','white':'&H00FFFFFF','gold':'&H0078BDD8','black':'&H00223324','mint':'&H00C0E0B0'}[cfg.get('fontColor','ivory')]
 align={'bottom':2,'middle':5,'top':8}[cfg.get('position','bottom')]
 size=int(cfg.get('fontSize','24'))
 if size not in {20,24,32}:raise ValueError('حجم خط غير صالح')
 return f'FontName=DejaVu Sans,FontSize={size},PrimaryColour={color},OutlineColour=&H001A211D,BorderStyle=1,Outline=1.5,Shadow=0,Alignment={align},MarginV=28'


def write_caption_preview(root,srt,language='',original=''):
 data={'srt':srt[:200000],'language':language,'original':original[:200000],'truncated':len(srt)>200000}
 (root/'preview.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')


def caption_workflow(source,cfg,root,report):
 op=cfg.get('operation','transcribe');original='';language=cfg.get('source','auto')
 if op in {'transcribe','transcribeTranslate','transcribeBurn','transcribeTranslateBurn'}:
  # Invoke the ordinary fixed ASR path once; follow-up operations reuse its source.
  reused=False
  if op in {'transcribeTranslate','transcribeBurn','transcribeTranslateBurn'} and cfg.get('parentJob'):
   parent=root.parent/cfg['parentJob']
   try:
    previous=json.loads((parent/'config.json').read_text())
    if previous.get('language')==cfg.get('language') and (parent/'language.json').is_file() and '-->' in (parent/'original.srt').read_text(encoding='utf-8'):
     for filename in ['original.srt','language.json','transcript.txt']:
      if (parent/filename).is_file():shutil.copyfile(parent/filename,root/filename)
     reused=True;report('processing','استكمال الترجمة من التفريغ المكتمل؛ لا يُعاد تفريغ المصدر')
   except (OSError,ValueError):pass
  if not reused:
   basic={**cfg,'_basic_asr':True};process('asr',source,basic,root,report)
  original=(root/'original.srt').read_text(encoding='utf-8');srt=original
  info=json.loads((root/'language.json').read_text());language=info['language']
 else:srt=cfg['subtitles'];original=srt
 if op in {'transcribeTranslate','transcribeTranslateBurn','translate','translateburn'}:
  install('translate',report)
  selected=cfg.get('source','auto');source_language=language if selected=='auto' else selected
  if selected=='auto' and cfg.get('parentJob'):
   parent=root.parent/cfg['parentJob'];meta=parent/'language.json'
   if meta.exists():source_language=json.loads(meta.read_text())['language']
  if source_language not in LANG:raise ValueError('اختر لغة المصدر صراحة؛ اللغة المكتشفة غير مدعومة للترجمة')
  if source_language==cfg['target']:raise ValueError('لغة المصدر والهدف متطابقتان؛ اختر لغة أخرى أو احرق التفريغ الأصلي')
  names={}
  for row in cfg.get('names','').splitlines()[:30]:
   key,_,value=row.partition('=');key=key.strip()
   if key:names[key]=value.strip() or key
  srt='\n'.join(translate_lines(srt.splitlines(),source_language,cfg['target'],report,names));language=cfg['target'];(root/'translated.srt').write_text(srt,encoding='utf-8')
 if not (root/'original.srt').exists():(root/'original.srt').write_text(original,encoding='utf-8')
 (root/'rendered.srt').write_text(srt,encoding='utf-8')
 write_caption_preview(root,srt,language,original)
 if op in {'burn','translateburn','transcribeBurn','transcribeTranslateBurn'}:
  if cfg['ext'] not in {'mp4','mkv','mov','webm','avi','mpeg'}:raise ValueError('دمج الترجمة يحتاج ملف فيديو؛ يمكنك حفظ SRT مع ملف الصوت')
  return process('burn',source,{**cfg,'subtitles':srt},root,report)
 if not (root/'original.srt').exists():(root/'original.srt').write_text(original,encoding='utf-8')
 outputs=[root/'original.srt'];txt=root/'transcript.txt'
 if txt.exists():outputs.append(txt)
 if (root/'translated.srt').exists():outputs.append(root/'translated.srt')
 return zip_outputs(root,outputs)


def serve_translation_worker(device='cuda'):
 # The Colab allocation outlives Python processes. Exit if the owning worker dies.
 parent=os.getppid()
 def watch_parent():
  while os.getppid()==parent:time.sleep(2)
  os._exit(0)
 threading.Thread(target=watch_parent,daemon=True).start()
 def emit(data):print(json.dumps(data,ensure_ascii=False),flush=True)
 for raw in sys.stdin:
  try:
   if len(raw)>3*1024**2:raise ValueError('طلب الترجمة أطول من الحد')
   cfg=json.loads(raw);result=_translate_lines_local(cfg['lines'],cfg['source'],cfg['target'],lambda state,message:emit({'event':'progress','message':message}),cfg.get('names'),device=device)
   emit({'event':'result','lines':result})
  except Exception as exc:
   try:from runner import failure_details
   except ModuleNotFoundError:from madar_web_job import failure_details
   code,message,diagnostic=failure_details(exc,{'task':'translate'})
   emit({'event':'error','code':code,'message':message+' · '+code,'diagnostic':diagnostic})


if __name__=='__main__' and sys.argv[1:]==['--translation-worker']:serve_translation_worker()


# Helper models for «دبلج»: who is speaking (TitaNet voiceprints) and which non-word sounds
# the performer should make (AST). Both are optional: if either fails the lines are still made.
SOUND_MODEL='MIT/ast-finetuned-audioset-10-10-0.4593'
# Tuned on a dubbed cartoon (Bluey, Arabic): long pieces of one voice agree at 0.7–0.85, other
# voices stay under ~0.55; a short piece joins a voice from 0.45, and one under 0.25 to every
# known voice (a deep voice among children) is a new speaker.
SPEAKER_SIMILARITY=0.5
SPEAKER_ASSIGN=0.45


def mono16k(path):
 import numpy as np
 raw=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(path),'-ac','1','-ar','16000','-f','f32le','-'],check=True,capture_output=True,timeout=900).stdout
 return np.frombuffer(raw,dtype=np.float32)


def dub_speakers(audio,words,report):
 """Speaker turns for «دبلج»: Whisper's segments are cut into pieces, every piece gets a TitaNet
 voiceprint (in its own process), and pieces are grouped into speakers. Returns (units, labels)."""
 import numpy as np,tempfile
 from madar_colab_runtime import turn_units,cluster_speakers,install_once,voiceprint_model,VOICEPRINT_PIP,CACHE
 report('processing','تمييز صوت كل شخصية')
 install_once('voiceprint',VOICEPRINT_PIP);model=voiceprint_model(CACHE)
 units=turn_units(words);spans=[(words[u[0]]['s']-0.1,words[u[-1]]['e']+0.1) for u in units]
 with tempfile.TemporaryDirectory() as tmp:
  raw=Path(tmp)/'voice.f32';audio.astype(np.float32).tofile(raw);(Path(tmp)/'spans.json').write_text(json.dumps(spans))
  code='import sys;sys.path.insert(0,sys.argv[1]);import madar_colab_runtime as r;r.voiceprints_main(sys.argv[2:])'
  subprocess.run([sys.executable,'-c',code,str(Path(__file__).resolve().parent),str(model),str(raw),str(Path(tmp)/'spans.json'),str(Path(tmp)/'v.npy')],check=True,timeout=1800,capture_output=True)
  vectors=np.load(Path(tmp)/'v.npy')
 durations=[b-a-0.2 for a,b in spans]
 labels=cluster_speakers([v if np.any(v) else None for v in vectors],durations,SPEAKER_SIMILARITY,SPEAKER_ASSIGN)
 return units,labels


def dub_sounds(audio,words,report):
 """Finds laughs, hums, sighs… on the voice track where Whisper wrote no word, and names them."""
 from madar_colab_runtime import sound_regions,name_sound
 regions=sound_regions(audio,16000,words)[:400]
 if not regions:return []
 torch=cuda()
 from transformers import AutoFeatureExtractor,ASTForAudioClassification
 report('processing','البحث عن الضحك والأصوات اللي مو كلام')
 extractor=load_model(lambda:AutoFeatureExtractor.from_pretrained(SOUND_MODEL,trust_remote_code=False),report)
 model=load_model(lambda:ASTForAudioClassification.from_pretrained(SOUND_MODEL,trust_remote_code=False),report).to('cuda').eval()
 try:
  names=model.config.id2label;found=[]
  for r in regions:
   clip=audio[int(r['s']*16000):int(r['e']*16000)]
   inputs=extractor(clip,sampling_rate=16000,return_tensors='pt')
   with torch.no_grad():probs=torch.sigmoid(model(**{k:v.to('cuda') for k,v in inputs.items()}).logits[0]).float().cpu().tolist()
   label=name_sound({names[i]:p for i,p in enumerate(probs)},r['e']-r['s'])
   if label:found.append({**r,'label':label})
  return found
 finally:
  del model;gc.collect();torch.cuda.empty_cache()


def dub_text(voice, target, report):
 """Speech-to-text for «دبلج» on the separated voice track, with the time of every word,
 grouped into whole sentences of one speaker; non-word sounds are marked; optionally
 translated to Arabic so the visitor reads while recording."""
 from madar_colab_runtime import group_dub_words
 install('asr',report);cuda();report('processing','تفريغ الكلام وتوقيت كل كلمة')
 preload_cuda();import onnxruntime as ort
 if hasattr(ort,'preload_dlls'):ort.preload_dlls(directory='')
 from faster_whisper import WhisperModel
 import ctranslate2
 supported=ctranslate2.get_supported_compute_types('cuda');compute=next((v for v in ['float16','int8_float16','float32'] if v in supported),None)
 if not compute:raise RuntimeError('CUDA_COMPUTE_UNSUPPORTED')
 model=cached_model('whisper-'+compute,lambda:load_model(lambda:WhisperModel('large-v3-turbo',device='cuda',compute_type=compute),report),report)
 segments,info=model.transcribe(str(voice),language=None,vad_filter=True,beam_size=5,word_timestamps=True)
 words=[]
 for i,seg in enumerate(segments):
  for w in seg.words or []:words.append({'w':w.word,'s':float(w.start),'e':float(w.end),'seg':i})
  report('processing',f'تفريغ الكلام · وصلنا إلى {round(seg.end/60,1)} دقيقة')
 release_models()
 sounds=[];speakers=0;skipped=[];units=labels=None
 if words:
  try:audio=mono16k(voice)
  except Exception:audio=None;skipped.append('audio')
  if audio is not None:
   try:units,labels=dub_speakers(audio,words,report);speakers=len({l for l in labels if l is not None})
   except Exception as exc:skipped.append('speakers:'+type(exc).__name__)
   try:sounds=dub_sounds(audio,words,report)
   except Exception as exc:skipped.append('sounds:'+type(exc).__name__)
 lines=group_dub_words(words,sounds,units,labels);lang=info.language;note=''
 if target=='ar' and lines and lang!='ar':
  if lang in LANG:
   report('processing','ترجمة الجمل إلى العربية')
   try:
    spoken=[l for l in lines if l['say'].strip()]
    for line,text in zip(spoken,translate_lines([l['say'] for l in spoken],lang,'ar',report)):
     # Sound marks stay in place: before the sentence if they open it, otherwise after it.
     marks=[w for w in line['words'] if w.get('k')=='sound'];first=next((w for w in line['words'] if not w.get('k')),None)
     before=[m['w'] for m in marks if first and m['s']<first['s']];after=[m['w'] for m in marks if not first or m['s']>=first['s']]
     line['tr']=' '.join([*before,text,*after])
   finally:stop_translator()
  else:note='الترجمة للعربي غير متاحة لهذه اللغة؛ يظهر النص بلغته الأصلية'
 release_models()
 if any(x.startswith(('audio','speakers')) for x in skipped):note=(note+' · ' if note else '')+'تمييز الشخصيات ما اشتغل هالمرة؛ الجمل مقسّمة حسب نهايتها'
 return {'language':lang,'target':target,'lines':lines,'note':note,'speakers':speakers,**({'skipped':skipped} if skipped else {})}


# Early preparation: started when the Colab session is prepared, while the file is still
# uploading, so each tool's libraries and model files are ready before the job needs them.
# It only installs and downloads (no GPU); the job runs exactly as before and simply finds
# everything in place. Any failure here is ignored: the job then does the same step itself.
WARM_TOOLS={'separate','dub','asr','translate'}

def warm(tool):
 if tool not in WARM_TOOLS:return []
 from madar_colab_runtime import install_once,SEPARATION_PIP,MODEL,DUB_MODEL,CACHE
 quiet=lambda *a,**k:None;done=[]
 try:
  from madar_drive_cache import restore
  done+=['drive:'+n for n in restore(tool)]
 except Exception as exc:done.append('drive:'+type(exc).__name__)
 def step(name,fn):
  try:fn();done.append(name)
  except Exception as exc:done.append(name+':'+type(exc).__name__)
 def uvr(model):
  install_once('separation',SEPARATION_PIP)
  from audio_separator.separator import Separator
  CACHE.mkdir(parents=True,exist_ok=True)
  Separator(model_file_dir=str(CACHE),output_dir=str(CACHE),log_level=40).download_model_files(model)
 def whisper():
  install('asr',quiet)
  from faster_whisper.utils import download_model
  download_model('large-v3-turbo')
 def hub(repo,revision=None,patterns=None):
  from huggingface_hub import snapshot_download
  snapshot_download(repo,revision=revision,allow_patterns=patterns)
 if tool in {'separate','dub'}:step('separation',lambda:uvr(DUB_MODEL if tool=='dub' else MODEL))
 if tool in {'dub','asr'}:step('whisper',whisper)
 if tool=='dub':
  def voiceprint():
   from madar_colab_runtime import VOICEPRINT_PIP,voiceprint_model
   install_once('voiceprint',VOICEPRINT_PIP);voiceprint_model(CACHE)
  step('voiceprint',voiceprint)
  step(SOUND_MODEL,lambda:hub(SOUND_MODEL,patterns=['*.json','*.safetensors','*.bin','*.txt']))
 if tool=='translate':
  def nllb():
   install('translate',quiet);hub('facebook/nllb-200-distilled-600M','38bd1c6a0f58097b26ef7c7cd73a0dcac034350a',['*.json','model.safetensors','*.model'])
  step('nllb',nllb)
 try:
  from madar_drive_cache import save
  done+=['saved:'+n for n in save(tool)]
 except Exception as exc:done.append('save:'+type(exc).__name__)
 return done
