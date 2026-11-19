"""Fixed Colab job launched through the authenticated Jupyter API; no web server."""
import hashlib, json, os, subprocess, sys, time, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PART = 2 * 1024 * 1024
_SEPARATION_READY = False


def status(state, message, **extra):
    tmp = ROOT/'state.tmp'
    tmp.write_text(json.dumps(dict(state=state, message=message, updated=time.time(), **extra), ensure_ascii=False))
    tmp.replace(ROOT/'state.json')


def _manifest(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(PART), b''):
            digest.update(hashlib.sha256(block).digest())
    return digest.hexdigest()


def assemble(config):
    source = ROOT/('source.'+config['ext'])
    if config.get('parentJob'):
        parent_id=config['parentJob']
        if not re.fullmatch(r'[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}',parent_id):raise ValueError('مرجع مصدر غير صالح')
        parent=ROOT.parent/parent_id;old=json.loads((parent/'config.json').read_text())
        if config.get('task')!=old.get('task') or config.get('task') not in {'asr','ocr','cutout','word','translate','burn','convert','resize'} or any(old.get(k)!=config.get(k) for k in ['ext','size','chunks','sha256']):raise ValueError('مرجع المصدر لا يطابق العملية السابقة')
        src=parent/('source.'+config['ext'])
        if not src.is_file():raise ValueError('المصدر المحفوظ غير مكتمل؛ أعد رفع الملف بدل إعادة المحاولة من المصدر')
        digest=hashlib.sha256();size=0
        with src.open('rb') as inp,source.open('wb') as out:
            while True:
                data=inp.read(PART)
                if not data:break
                size+=len(data);digest.update(hashlib.sha256(data).digest());out.write(data)
        if size!=config['size'] or digest.hexdigest()!=config['sha256']:
            source.unlink(missing_ok=True);raise ValueError('لم يطابق المصدر المحفوظ بصمته؛ أعد رفعه')
        return source

    if config.get('driveInput'):
        # The page uploaded the file straight to the visitor's Drive; take it from there.
        from madar_drive_cache import fetch_input
        if not (source.is_file() and source.stat().st_size == config['size'] and _manifest(source) == config['sha256']):
            status('setup', 'نجيب ملفك من Google Drive…')
            size, digest_hex = fetch_input(config['driveInput'], source, PART, config['chunks'])
            if size != config['size'] or digest_hex != config['sha256']:
                source.unlink(missing_ok=True)
                raise ValueError('لم يكتمل نقل الملف بشكل سليم؛ أعد الرفع')
        return source
    digest = hashlib.sha256()
    with source.open('wb') as out:
        for i in range(config['chunks']):
            part = ROOT/f'input_{i:05d}.bin'
            data = part.read_bytes()
            if len(data) != min(PART, config['size']-i*PART):
                raise ValueError('حجم جزء الرفع لا يطابق المصدر؛ أعد الرفع')
            digest.update(hashlib.sha256(data).digest())
            out.write(data)
    if source.stat().st_size != config['size'] or digest.hexdigest() != config['sha256']:
        source.unlink(missing_ok=True)
        raise ValueError('لم يكتمل نقل الملف بشكل سليم؛ أعد الرفع')
    for part in ROOT.glob('input_*.bin'):
        part.unlink()
    return source


def failure_details(exc,cfg):
 import traceback
 text=str(exc).lower();kind=type(exc).__name__;module=type(exc).__module__
 known=['CONTENT_REVIEW_REQUIRED','CONTENT_REVIEW_ERROR','VIDEOGEN_TEXT_SETUP','MODEL_META_TENSOR','TRANSLATION_WORKER_STOPPED','DEPENDENCY_TIMEOUT','DEPENDENCY_INSTALL','PYTHON_ENV_SETUP','JS_CHECKSUM','PLATFORM_VERIFICATION','LOGIN_REQUIRED','DRM','JS_CHALLENGE','PLATFORM_NETWORK','DOWNLOAD_NETWORK','EXTRACTOR_FAILED','DOWNLOAD_FAILED','ASR_TIMESTAMPS','ASR_NO_SPEECH']
 code=next((c for c in known if '· '+c in str(exc)),None)
 if not code:
  if isinstance(exc,ImportError):code='MODEL_IMPORT_INCOMPATIBLE'
  elif 'meta tensor' in text:code='MODEL_META_TENSOR'
  elif 'out of memory' in text:code='GPU_MEMORY'
  elif isinstance(exc,subprocess.TimeoutExpired):code='PROCESS_TIMEOUT'
  elif isinstance(exc,subprocess.CalledProcessError):code='MEDIA_PROCESS_FAILED'
  elif isinstance(exc,ModuleNotFoundError):code='MODULE_MISSING'
  elif any(x in text for x in ['cudnn','cublas','cuda','undefined symbol']):code='GPU_LIBRARY'
  elif kind in {'GatedRepoError','RepositoryNotFoundError','EntryNotFoundError'}:code='MODEL_NOT_ACCESSIBLE'
  elif any(x in (module+' '+kind).lower() for x in ['huggingface','httpx','requests','urllib3']) or any(x in text for x in ['timed out','connection reset','connection aborted']):code='MODEL_DOWNLOAD_FAILED'
  elif any(x in text for x in ['safetensor','weights_only','state_dict','tokenizer','from_pretrained']):code='MODEL_LOAD_FAILED'
  else:code='TOOL_'+re.sub('[^A-Z0-9_]','',kind.upper())[:60]
 friendly={'MODEL_IMPORT_INCOMPATIBLE':'تعذر توافق استيراد مكتبات النموذج؛ التشخيص يتضمن الرمز أو المكتبة الناقصة','MODEL_META_TENSOR':'أوزان النموذج غير محمّلة فعليًا؛ رُفض نقل أوزان فارغة إلى GPU','GPU_MEMORY':'نفدت ذاكرة GPU؛ قلّل مدة اللقطة أو اختر ذاكرة أكبر','MODULE_MISSING':'لم تكتمل إحدى مكتبات الأداة؛ أعد المحاولة في الجلسة نفسها','GPU_LIBRARY':'تعذر توافق مكتبة GPU؛ جرّب مسار التوافق أو جلسة جديدة','DEPENDENCY_TIMEOUT':'انتهت مهلة تجهيز المكتبات؛ أعد المحاولة في الجلسة نفسها','PROCESS_TIMEOUT':'انتهت مهلة مرحلة المعالجة؛ المصدر محفوظ للمحاولة التالية','DEPENDENCY_INSTALL':'تعذر تثبيت مكتبات الأداة المتوافقة','MEDIA_PROCESS_FAILED':'تعذر فك أو ترميز الملف؛ تحقق من وجود صوت أو فيديو صالح','MODEL_NOT_ACCESSIBLE':'ملف النموذج المطلوب غير متاح من مزوده','MODEL_DOWNLOAD_FAILED':'تعذر تنزيل ملفات النموذج؛ الملفات المكتملة محفوظة ويمكن استكمالها','MODEL_LOAD_FAILED':'تعذر تحميل النموذج أو توافق أوزانه؛ تفاصيل التشخيص مرفقة'}
 frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__) if Path(f.filename).name in {'madar_cloud_tasks.py','runner.py','madar_web_job.py','madar_colab_runtime.py','madar_download.py','pipeline_wan.py','transformer_wan.py','autoencoder_kl_wan.py','modeling_utils.py','modeling_m2m_100.py','import_utils.py'}][-8:]
 versions={}
 task=cfg.get('task','separate') if isinstance(cfg,dict) else 'unknown'
 packages=['yt-dlp','yt-dlp-ejs'] if task=='download' else ['torch','ctranslate2','faster-whisper','transformers','diffusers','onnxruntime-gpu','huggingface-hub','tokenizers','safetensors','accelerate','ftfy']
 for name in packages:
  try:
   import importlib.metadata
   versions[name]=importlib.metadata.version(name)
  except importlib.metadata.PackageNotFoundError:pass
 task=cfg.get('task','separate') if isinstance(cfg,dict) else 'unknown'
 loaded_versions={n:getattr(sys.modules.get(n),'__version__',None) for n in ['torch','transformers','accelerate','tokenizers','safetensors','huggingface_hub'] if sys.modules.get(n) is not None}
 signature=re.search(r"cannot import name ['\"]([A-Za-z_][A-Za-z0-9_]{0,79})['\"] from ['\"]([A-Za-z_][A-Za-z0-9_.]{0,159})['\"]",str(exc))
 undefined=getattr(exc,'name',None) if isinstance(exc,NameError) else None
 diagnostic={'task':task,'exception':kind if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',kind) else 'Unknown','frames':frames,'versions':versions,'loadedVersions':loaded_versions}
 if code in {'CONTENT_REVIEW_REQUIRED','CONTENT_REVIEW_ERROR'}:diagnostic.update(stage='content_review',generationCompleted=code=='CONTENT_REVIEW_REQUIRED')
 if code=='CONTENT_REVIEW_REQUIRED':
  details=getattr(exc,'review_details',{})
  review={k:details[k] for k in ['firstFlaggedFrame','timestampMs','checkedFrames','totalFrames','fps'] if isinstance(details.get(k),int) and not isinstance(details[k],bool) and 0<=details[k]<=1000000}
  review.update(precision='float32',decision='flagged_frame')
  if details.get('checker')=='Falconsai/nsfw_image_detection' and details.get('revision')=='96cb0d0342c7afb80cab76ecc58b265fa44da256':review.update(checker=details['checker'],revision=details['revision'],policy='binary_classifier_default')
  diagnostic['review']=review
 if isinstance(undefined,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',undefined):diagnostic['undefinedName']=undefined
 if signature:diagnostic['missingImport']={'symbol':signature[1],'module':signature[2]}
 media=getattr(exc,'media_details',None)
 if isinstance(media,dict) and media.get('code') in {'MEDIA_NO_VIDEO','MEDIA_NO_AUDIO','MEDIA_DECODER_UNAVAILABLE','MEDIA_INVALID_INPUT','MEDIA_DISK_FULL','MEDIA_RESOURCE_BUSY','MEDIA_TIMEOUT','MEDIA_PROCESS_FAILED'}:
  safe={'code':media['code'],'stage':media.get('stage') if media.get('stage') in {'source_probe','audio_decode','output_encode'} else 'unknown'}
  if isinstance(media.get('exitCode'),int):safe['exitCode']=media['exitCode']
  diagnostic['media']=safe
  return media['code'],str(exc)[:300],diagnostic
 if getattr(exc,'worker_diagnostic',None):return exc.worker_diagnostic['code'],exc.worker_diagnostic['message'].split(' · ')[0],exc.worker_diagnostic['diagnostic']
 # Only our explicit Arabic ValueErrors can be shown, without URLs or source paths.
 msg=str(exc).split(' · ')[0] if isinstance(exc,ValueError) and re.search('[\u0600-\u06ff]',str(exc)) and not re.search(r'https?://|[/\\]|ya29\.|gsk_',str(exc)) else friendly.get(code,'فشلت مرحلة في الأداة؛ التشخيص مرفق دون محتوى ملفك')
 return code,msg[:400],diagnostic


def main():
    global _SEPARATION_READY
    ROOT.mkdir(exist_ok=True)
    # Atomic lock prevents an uncertain websocket reply from starting a second job.
    try:
        lock = os.open(str(ROOT/'started.lock'), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(lock)
    except FileExistsError:
        return
    cfg={}
    try:
        cfg = json.loads((ROOT/'config.json').read_text())
        drive_task = cfg.get('task', 'separate')
        try:
            # Models kept in the visitor's Drive come back in seconds instead of a fresh download.
            from madar_drive_cache import restore
            restore(drive_task, status)
        except Exception:
            pass
        if cfg.get('task') == 'download':
            from madar_download import download_clip
            output = download_clip(cfg, ROOT, status)
        elif cfg.get('task') in {'ocr','cutout','word','asr','translate','burn','convert','resize','imagegen','videogen'}:
            from madar_cloud_tasks import process
            source=assemble(cfg) if cfg.get('size') else None
            output=process(cfg['task'],source,cfg,ROOT,status)
        else:
            status('setup', 'تثبيت مكتبات الفصل على Colab؛ أول تشغيل قد يستغرق عدة دقائق')
            if not _SEPARATION_READY:
                from madar_colab_runtime import install_once, SEPARATION_PIP
                install_once('separation', SEPARATION_PIP)
                _SEPARATION_READY = True
            status('gpu', 'تحميل النموذج واختبار CUDA فعليًا')
            import madar_colab_runtime as runtime
            source = assemble(cfg)
            runtime.validate_audio_source(source)
            runtime.prepare_gpu()
            # Progress is emitted by the existing tested chunk engine, with measured ETA.
            class ProgressLog:
                def __init__(self): self.pending = ''
                def write(self, text):
                    sys.__stdout__.write(text)
                    self.pending += text
                    if '\n' in self.pending:
                        lines = self.pending.split('\n')
                        self.pending = lines.pop()
                        for line in lines:
                            if line.strip(): status('separating', line.strip()[:500])
                def flush(self): sys.__stdout__.flush()
            sys.stdout = ProgressLog()
            if cfg.get('task') == 'dub':
                def dub_lines(voice, work):
                    # Text is a helper: if it fails the visitor still gets the stems and can dub.
                    if cfg.get('textLang', 'none') == 'none':
                        return []
                    try:
                        from madar_cloud_tasks import dub_text
                        data = dub_text(voice, cfg['textLang'], status)
                    except Exception as exc:
                        data = {'error': (str(exc) or type(exc).__name__)[:300], 'lines': []}
                    target = work/'lines.json'
                    target.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                    return [target]
                output = runtime.run_dub_stems(source, extra=dub_lines)
            else:
                output = runtime.run_separation(source, cfg['start'], cfg['duration'], cfg['mode'], **({'output_format':cfg['outputFormat']} if cfg.get('outputFormat') else {}))
            sys.stdout = sys.__stdout__
        if output.stat().st_size<1:raise ValueError('لم تنتج الأداة ملفًا صالحًا')
        if output.stat().st_size > 256*1024**2:
            raise ValueError('الناتج يتجاوز حد التنزيل الآمن للمتصفح 256 MB؛ اختر MP3 أو M4A للصوت، أو جزءًا أقصر')
        chunks = []
        with output.open('rb') as f:
            while True:
                block = f.read(PART)
                if not block: break
                index = len(chunks)
                (ROOT/f'output_{index:05d}.bin').write_bytes(block)
                chunks.append(hashlib.sha256(block).hexdigest())
        captions={}
        if cfg.get('task')=='asr' and output.suffix=='.mp4':
            import zipfile
            sidecar=ROOT/'caption-files.zip'
            with zipfile.ZipFile(sidecar,'w',zipfile.ZIP_DEFLATED) as z:
                for name in ['original.srt','transcript.txt','translated.srt','rendered.srt']:
                    if (ROOT/name).is_file():z.write(ROOT/name,name)
            hashes=[]
            with sidecar.open('rb') as f:
                while True:
                    block=f.read(PART)
                    if not block:break
                    (ROOT/f'captions_{len(hashes):05d}.bin').write_bytes(block);hashes.append(hashlib.sha256(block).hexdigest())
            captions={'size':sidecar.stat().st_size,'chunks':hashes,'ext':'zip'}
        preview={}
        if (ROOT/'preview.json').exists():preview=json.loads((ROOT/'preview.json').read_text())
        drive_out = None
        try:
            from madar_drive_cache import put_output, save_later, token as drive_token
            if drive_token():
                status('downloading', 'نجهز النتيجة للتنزيل السريع عبر Google Drive…')
                drive_out = put_output(output, ROOT.name)
            save_later(cfg.get('task', 'separate'))
        except Exception:
            pass
        meta={}
        try:meta=json.loads((ROOT/'meta.json').read_text(encoding='utf-8')) if (ROOT/'meta.json').exists() else {}
        except Exception:meta={}
        status('done', 'اكتملت المعالجة؛ النتيجة جاهزة للتنزيل', **({'driveOutput': drive_out} if drive_out else {}), title=str(meta.get('title',''))[:90], size=output.stat().st_size, chunks=chunks, ext=output.suffix.lower().lstrip('.'), task=cfg.get('task','separate'), designName=cfg.get('name',''),sourceName=cfg.get('sourceName',''),preview=preview,captions=captions)
    except Exception as exc:
        # Detailed traceback remains in the user's runtime, never in the page response.
        import traceback
        traceback.print_exc()
        code,msg,diagnostic=failure_details(exc,cfg)
        status('error',msg+' · '+code,code=code,diagnostic=diagnostic)


if __name__ == '__main__':
    main()
