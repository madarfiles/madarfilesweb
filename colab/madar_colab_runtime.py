"""Madar GPU separation, run interactively inside the user's own Colab notebook.
No tunnel, web server, remote-control endpoint or account credential is created.
"""
import gc, hashlib, json, logging, math, shutil, subprocess, time
from functools import lru_cache
from pathlib import Path

MODEL = 'UVR-MDX-NET-Voc_FT.onnx'
ROOT = Path('/content/madar_separation')
CACHE = Path('/content/madar_models')
CHUNK_SECONDS = 300


def chunk_plan(total, start=0, duration=0, chunk_seconds=CHUNK_SECONDS):
    total, start, duration = float(total), float(start), float(duration)
    if not all(map(math.isfinite, (total, start, duration))) or total <= 0 or start < 0 or duration < 0 or start >= total or chunk_seconds <= 0:
        raise ValueError('حدّد بداية ومدة صحيحتين داخل المصدر؛ صفر للمدة يعني كامل المتبقي')
    length = min(duration or total-start, total-start)
    return [(start+i*chunk_seconds, min(chunk_seconds, length-i*chunk_seconds)) for i in range(math.ceil(length/chunk_seconds))]


class MediaError(RuntimeError):
    def __init__(self, code, stage, exit_code=None):
        messages={'MEDIA_NO_VIDEO':'المصدر صوت فقط؛ اختر صيغة صوتية بدل الفيديو','MEDIA_NO_AUDIO':'المقطع لا يحتوي على مسار صوت يمكن فصله','MEDIA_DECODER_UNAVAILABLE':'ترميز المصدر غير متاح في محرك هذه الجلسة','MEDIA_INVALID_INPUT':'تعذر قراءة المصدر؛ قد يكون الملف تالفًا أو غير مكتمل','MEDIA_DISK_FULL':'امتلأت مساحة جلسة المعالجة','MEDIA_RESOURCE_BUSY':'موارد فك الترميز مشغولة؛ أعد المحاولة بعد انتهاء المعالجة الأخرى','MEDIA_TIMEOUT':'انتهت مهلة معالجة الوسائط','MEDIA_PROCESS_FAILED':'تعذر فك أو ترميز الوسائط؛ راجع رمز المرحلة في تفاصيل الدعم'}
        super().__init__(messages.get(code,messages['MEDIA_PROCESS_FAILED']))
        self.media_details={'code':code,'stage':stage}
        if isinstance(exit_code,int):self.media_details['exitCode']=exit_code


def media_failure(stderr):
    text=(stderr or '').lower()
    if any(x in text for x in ['no space left','disk quota exceeded']):return 'MEDIA_DISK_FULL'
    if any(x in text for x in ['resource temporarily unavailable','pthread_create','cannot allocate memory','out of memory']):return 'MEDIA_RESOURCE_BUSY'
    if any(x in text for x in ['matches no streams','does not contain any stream','no audio stream']):return 'MEDIA_NO_AUDIO'
    if any(x in text for x in ['unknown decoder','decoder not found','decoding requested, but no decoder found','unsupported codec']):return 'MEDIA_DECODER_UNAVAILABLE'
    if any(x in text for x in ['invalid data found','moov atom not found','error opening input']):return 'MEDIA_INVALID_INPUT'
    return 'MEDIA_PROCESS_FAILED'


def ffmpeg(args):
    args=list(map(str,args));stage='audio_decode' if 'pcm_s16le' in args and '-ss' in args else 'output_encode'
    # Bound decoder/filter threads on shared and small-RAM Colab instances.
    command=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-protocol_whitelist','file,pipe','-threads','2','-filter_threads','1','-filter_complex_threads','1',*args[:-1],'-threads','2',args[-1]]
    for attempt in range(2):
        try:p=subprocess.run(command,capture_output=True,text=True,timeout=1800)
        except subprocess.TimeoutExpired:raise MediaError('MEDIA_TIMEOUT',stage) from None
        if not p.returncode:return
        code=media_failure(p.stderr)
        if code=='MEDIA_RESOURCE_BUSY' and attempt==0:
            
            for at,value in enumerate(command[:-1]):
                if value=='-threads':command[at+1]='1'
            print('تخفيف موارد فك الترميز وإعادة محاولة المرحلة الحالية…',flush=True)
            continue
        # Never expose raw stderr: it can contain source paths or metadata.
        raise MediaError(code,stage,p.returncode)


def validate_audio_source(source):
    try:streams=media_streams(source)
    except subprocess.TimeoutExpired:raise MediaError('MEDIA_TIMEOUT','source_probe') from None
    except subprocess.CalledProcessError as exc:raise MediaError(media_failure(exc.stderr),'source_probe',exc.returncode) from None
    if not any(item.get('codec_type')=='audio' for item in streams):raise MediaError('MEDIA_NO_AUDIO','source_probe')


AUDIO_FORMATS={'m4a':['-c:a','aac','-b:a','192k','-movflags','+faststart'],'mp3':['-c:a','libmp3lame','-b:a','192k'],'wav':['-c:a','pcm_s16le'],'flac':['-c:a','flac'],'ogg':['-c:a','libvorbis','-q:a','5'],'opus':['-c:a','libopus','-b:a','160k'],'aac':['-c:a','aac','-b:a','192k']}
VIDEO_FORMATS={'mp4','mkv','mov','webm','avi','ts'}


def export_media(source,target,quality='balanced',audio_source=None,start=0,duration=0):
    target=Path(target);fmt=target.suffix[1:].lower()
    if fmt in AUDIO_FORMATS:
        ffmpeg(['-i',source,'-map','0:a:0','-vn','-ac','2',*AUDIO_FORMATS[fmt],'-map_metadata','-1',target]);return target
    if fmt not in VIDEO_FORMATS:raise ValueError('صيغة الناتج غير مدعومة')
    if not any(s.get('codec_type')=='video' for s in media_streams(source)):raise MediaError('MEDIA_NO_VIDEO','source_probe')
    q={'high':'20','balanced':'25','small':'30'}[quality]
    before=['-ss',start,'-i',source]
    if audio_source:before+=['-i',audio_source]
    if duration:before+=['-t',duration]
    before+=['-map','0:v:0','-map','1:a:0' if audio_source else '0:a:0?']
    if fmt=='webm':codec=['-c:v','libvpx-vp9','-crf',q,'-b:v','0','-deadline','good','-cpu-used','4'];audio=['-c:a','libopus','-b:a','160k']
    elif fmt=='avi':codec=['-c:v','mpeg4','-q:v','4'];audio=['-c:a','libmp3lame','-b:a','192k']
    else:
        copy=bool(audio_source) and not start and not duration and (fmt=='mkv' or compatible_mp4(source)[0])
        codec=['-c:v','copy'] if copy else video_encoder()
        if not copy:
            flag='-cq' if 'h264_nvenc' in codec else '-crf';codec=list(codec);codec[codec.index(flag)+1]=q
        audio=['-c:a','aac','-b:a','192k']
    tail=['-map_metadata','-1',*(['-movflags','+faststart'] if fmt in {'mp4','mov'} else []),target]
    try:ffmpeg([*before,*codec,*audio,*tail])
    except RuntimeError:
        if 'h264_nvenc' not in codec:raise
        print('تعذر NVENC؛ استكمال إخراج الفيديو على CPU دون إعادة الفصل',flush=True)
        ffmpeg([*before,'-c:v','libx264','-preset','veryfast','-crf',q,'-pix_fmt','yuv420p',*audio,*tail])
    return target


NVENC_DIAGNOSTIC='NOT_CHECKED'

@lru_cache(maxsize=1)
def gpu_name():
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],capture_output=True,text=True,timeout=5)
        name=getattr(p,'stdout','') or ''
        return name.splitlines()[0].strip()[:100] if name else ''
    except (OSError,subprocess.SubprocessError):return ''


def nvenc_failure(message):
    message=message.lower()
    if 'unknown encoder' in message:return 'ENCODER_NOT_BUILT'
    if any(t in message for t in ['libnvidia-encode','cannot load libcuda','cannot load libnvcuvid']):return 'DRIVER_LIBRARY_MISSING'
    if any(t in message for t in ['api version','minimum required nvidia driver']):return 'DRIVER_API_MISMATCH'
    if any(t in message for t in ['minimum supported','width is too small','height is too small']):return 'ENCODER_PROBE_DIMENSIONS'
    if 'no nvenc capable devices' in message:return 'GPU_ENCODER_UNAVAILABLE'
    if 'out of memory' in message or 'resource temporarily unavailable' in message:return 'ENCODER_RESOURCE_BUSY'
    return 'GPU_ENCODER_UNAVAILABLE'


def nvenc_explanation():
    descriptions={'HARDWARE_NO_NVENC':'هذه البطاقة لا تحتوي مرمّز NVENC عتاديًا','ENCODER_NOT_BUILT':'نسخة FFmpeg لا تتضمن مرمّز NVENC','DRIVER_LIBRARY_MISSING':'مكتبة ترميز NVIDIA غير متاحة داخل جلسة Colab','DRIVER_API_MISMATCH':'نسخة FFmpeg تتطلب واجهة تعريف NVIDIA مختلفة','ENCODER_PROBE_DIMENSIONS':'رفض المرمّز مقاس اختبار القدرات','ENCODER_RESOURCE_BUSY':'موارد مرمّز NVIDIA مشغولة مؤقتًا','ENCODER_PROBE_FAILED':'تعذر إكمال اختبار ترميز NVIDIA','GPU_ENCODER_UNAVAILABLE':'لم يسمح المورد الحالي بفتح مرمّز NVIDIA'}
    return descriptions.get(NVENC_DIAGNOSTIC,'لم ينجح فحص ترميز NVIDIA')+' · '+NVENC_DIAGNOSTIC


@lru_cache(maxsize=1)
def nvenc_ready():
    global NVENC_DIAGNOSTIC
    """A real encoding probe, not just presence in ffmpeg -encoders."""
    if any(model in gpu_name().upper() for model in ['A100','H100','H200','B200']):
        NVENC_DIAGNOSTIC='HARDWARE_NO_NVENC';return False
    try:
        result = subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-f','lavfi','-i','color=c=black:s=256x256:r=30:d=0.1','-frames:v','2','-pix_fmt','yuv420p','-c:v','h264_nvenc','-preset','p4','-f','null','-'], capture_output=True, timeout=15)
        if result.returncode==0:
            NVENC_DIAGNOSTIC='READY'
            return True
        message=getattr(result,'stderr',b'')
        if isinstance(message,bytes):message=message.decode('utf-8','replace')
        message=message.lower()
        NVENC_DIAGNOSTIC=nvenc_failure(message)
        return False
    except (OSError, subprocess.SubprocessError):
        NVENC_DIAGNOSTIC='ENCODER_PROBE_FAILED'
        return False


def video_encoder():
    if nvenc_ready():
        return ['-c:v','h264_nvenc','-preset','p4','-rc','vbr','-cq','20','-b:v','0','-pix_fmt','yuv420p']
    return ['-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p']


def media_streams(path):
    result = subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_entries','stream=codec_type,codec_name,pix_fmt','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=30)
    return json.loads(result.stdout).get('streams',[])


def compatible_mp4(path):
    streams = media_streams(path)
    video = next((s for s in streams if s.get('codec_type')=='video'),{})
    audio = next((s for s in streams if s.get('codec_type')=='audio'),None)
    return video.get('codec_name')=='h264' and video.get('pix_fmt') in {'yuv420p','yuvj420p','nv12'}, audio is None or audio.get('codec_name')=='aac'


def prepare_mp4(source, target, report):
    copy_video, copy_audio = compatible_mp4(source)
    codec = ['-c:v','copy'] if copy_video else video_encoder()
    def encode(chosen):
        return subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-protocol_whitelist','file,pipe','-i',str(source),'-map','0:v:0','-map','0:a:0?',*chosen,*(['-c:a','copy'] if copy_audio else ['-c:a','aac','-b:a','160k']),'-map_metadata','-1','-movflags','+faststart',str(target)],check=True,timeout=1200)
    report('downloading','تجهيز MP4 دون إعادة ترميز الفيديو أو تغيير جودته' if copy_video else 'ترميز الفيديو على GPU · NVENC' if 'h264_nvenc' in codec else 'ترميز CPU لهذا الفيديو؛ '+nvenc_explanation())
    try:
        encode(codec)
    except subprocess.CalledProcessError:
        if 'libx264' in codec: raise
        fallback = video_encoder() if copy_video else ['-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p']
        report('downloading','إعادة تجهيز الفيديو بمرمّز متوافق بعد تعذر المسار الأسرع')
        encode(fallback)
    return Path(target)


def duration_of(path):
    p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    value = float(json.loads(p.stdout)['format']['duration'])
    if not math.isfinite(value) or value <= 0:
        raise ValueError('تعذر تحديد مدة المصدر')
    return value


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def session_from_separator(separator):
    fn = separator.model_instance.model_run
    for cell in (getattr(fn, '__closure__', None) or []):
        value = cell.cell_contents
        if hasattr(value, 'get_providers') and 'CUDAExecutionProvider' in value.get_providers():
            return value
    raise RuntimeError('لم يتفعّل CUDA فعليًا؛ لا توجد عودة إلى CPU في هذا الدفتر')


def new_separator(output_dir, single_stem='Vocals'):
    from audio_separator.separator import Separator
    obj = Separator(output_dir=str(output_dir), model_file_dir=str(CACHE), output_format='WAV', output_single_stem=single_stem, use_soundfile=True,
                    log_level=logging.WARNING, mdx_params={'hop_length':1024, 'segment_size':256, 'overlap':0.25, 'batch_size':1, 'enable_denoise':False})
    obj.load_model(model_filename=MODEL)
    session_from_separator(obj)
    return obj


def prepare_gpu():
    import numpy as np
    import onnxruntime as ort
    if hasattr(ort, 'preload_dlls'):
        ort.preload_dlls(directory='')
    import torch
    ROOT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    if not torch.cuda.is_available():
        raise RuntimeError('اختر T4 GPU من إعدادات وقت التشغيل في Colab ثم شغّل الخلية مجددًا')
    probe_dir = ROOT/'probe'
    probe_dir.mkdir(exist_ok=True)
    probe = new_separator(probe_dir)
    session = session_from_separator(probe)
    result = session.run(None, {'input':np.zeros((1,4,3072,256), dtype=np.float32)})[0]
    if not np.isfinite(result).all():
        raise RuntimeError('اختبار GPU لم يُنتج بيانات سليمة')
    device = torch.cuda.get_device_name(0)
    del result, session, probe
    gc.collect()
    print('جاهز: تم اختبار CUDA فعليًا على', device)
    return device


def source_fingerprint(path, start, duration, mode):
    path = Path(path).resolve()
    stat = path.stat()
    digest = hashlib.sha256(str((str(path), stat.st_size, stat.st_mtime_ns, float(start), float(duration), mode)).encode())
    with path.open('rb') as f:
        digest.update(f.read(65536))
        if stat.st_size > 65536:
            f.seek(max(0, stat.st_size-65536))
            digest.update(f.read(65536))
    return digest.hexdigest()[:24]


def run_separation(source, start=0, duration=0, mode='audio', output_format=None):
    source = Path(source).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError('المصدر غير موجود أو فارغ')
    if mode not in {'audio','video'}:
        raise ValueError('نوع الناتج غير صالح')
    if output_format is not None and output_format not in (VIDEO_FORMATS if mode=='video' else AUDIO_FORMATS):
        raise ValueError('صيغة الناتج لا تطابق نوع الملف')
    plan = chunk_plan(duration_of(source), start, duration)
    length = sum(seconds for _,seconds in plan)
    if shutil.disk_usage(ROOT).free < 2*1024**3:
        raise RuntimeError('مساحة Colab المتبقية أقل من 2 GB')
    work = ROOT/source_fingerprint(source,start,duration,mode)
    work.mkdir(exist_ok=True)
    manifest = work/'checkpoint.json'
    try:
        completed = json.loads(manifest.read_text())
    except (ValueError, OSError):
        completed = {}
    print('عدد الأجزاء:',len(plan),'· مدة المصدر المختارة:',round(length,1),'ثانية')
    print('الأجزاء المكتملة تُحفظ داخل هذه الجلسة لاستكمالها إذا أعدت تشغيل خلية الفصل بنفس المصدر والإعدادات.')
    separator = new_separator(work)
    voices = []
    measured = 0.0
    measured_count = 0
    try:
        for index,(at,seconds) in enumerate(plan):
            saved = completed.get(str(index),{})
            name = saved.get('name','')
            cached = work/name
            if name and Path(name).name == name and cached.is_file() and sha256(cached) == saved.get('sha256'):
                voices.append(cached)
                print(f'{index+1}/{len(plan)} · استكمال الجزء المحفوظ')
                continue
            if shutil.disk_usage(ROOT).free < 512*1024**2:
                raise RuntimeError('المساحة لا تكفي للجزء التالي؛ الأجزاء المكتملة محفوظة في الجلسة')
            began = time.monotonic()
            remaining = f' · المتبقي تقريبًا {math.ceil((len(plan)-index)*measured/measured_count)} ثانية' if measured_count else ' · قياس سرعة أول جزء'
            print(f'{index+1}/{len(plan)} · فصل على GPU'+remaining,flush=True)
            raw = work/f'chunk_{index:05d}.wav'
            try:
                ffmpeg(['-ss',at,'-i',source,'-t',seconds,'-map','0:a:0','-vn','-ac','2','-ar','44100','-c:a','pcm_s16le',raw])
                names = separator.separate(str(raw), custom_output_names={'Vocals':f'voice_{index:05d}'})
                if not names:
                    raise RuntimeError('لم يُنتج نموذج الفصل ملفًا')
                result = Path(names[0])
                if not result.is_absolute():
                    result = work/result
                if not result.is_file():
                    raise RuntimeError('ملف الجزء المفصول غير موجود')
                voices.append(result)
                completed[str(index)] = {'name':result.name,'sha256':sha256(result)}
                temp = work/'checkpoint.tmp'
                temp.write_text(json.dumps(completed))
                temp.replace(manifest)
            finally:
                raw.unlink(missing_ok=True)
            measured += time.monotonic()-began
            measured_count += 1
        listing = work/'voice_list.txt'
        listing.write_text(''.join("file '"+str(p)+"'\n" for p in voices))
        audio = work/'voice.m4a'
        print('جمع الأجزاء وحفظ M4A…',flush=True)
        ffmpeg(['-f','concat','-safe','0','-i',listing,'-c:a','aac','-b:a','192k','-movflags','+faststart',audio])
        if output_format is not None:
            if mode=='video':
                output=export_media(source,work/('result.'+output_format),audio_source=audio,start=start,duration=length if (start or duration) else 0)
            elif output_format=='m4a':output=audio
            else:output=export_media(audio,work/('voice.'+output_format))
        elif mode == 'video':
            output = work/'result.mkv'
            codec = ['-c:v','copy'] if float(start)==0 and float(duration)==0 else video_encoder()
            print('تجهيز الفيديو: '+('نسخ الصورة الأصلية دون إعادة ترميز' if 'copy' in codec else 'GPU · NVENC' if 'h264_nvenc' in codec else 'CPU؛ NVENC غير متاح في هذه الجلسة'),flush=True)
            before=['-ss',start,'-i',source,'-i',audio,'-t',length,'-map','0:v:0','-map','1:a:0','-map','0:s?']
            after=['-c:a','copy','-c:s','copy','-map_metadata','-1',output]
            try:
                ffmpeg([*before,*codec,*after])
            except RuntimeError:
                if 'h264_nvenc' not in codec: raise
                print('تعذر ترميز هذا الفيديو عبر NVENC؛ استكمال الإخراج على CPU دون إعادة الفصل',flush=True)
                ffmpeg([*before,'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p',*after])
        else:
            output = audio
        print('اكتمل:',output,'·',round(output.stat().st_size/1024**2,1),'MB')
        return output
    finally:
        del separator
        gc.collect()


def run_dub_stems(source):
    """Dubbing preparation: split the whole source into the human voice and everything else
    (ambient sound, effects, music). Both stems come back sample-aligned in one ZIP so the
    browser can find speech timings from voice.m4a and mix new recordings over background.m4a."""
    import zipfile
    source = Path(source).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError('المصدر غير موجود أو فارغ')
    total = duration_of(source)
    if total > 30*60:
        raise ValueError('حد الدبلجة 30 دقيقة للمقطع؛ اختر مقطعًا أقصر')
    plan = chunk_plan(total, chunk_seconds=CHUNK_SECONDS)
    if shutil.disk_usage(ROOT).free < 2*1024**3:
        raise RuntimeError('مساحة Colab المتبقية أقل من 2 GB')
    work = ROOT/('dub-'+source_fingerprint(source, 0, 0, 'audio'))
    work.mkdir(parents=True, exist_ok=True)
    print('تجهيز الدبلجة · عدد الأجزاء:', len(plan), '· المدة:', round(total, 1), 'ثانية', flush=True)
    separator = new_separator(work, single_stem=None)
    voices, backgrounds = [], []
    try:
        for index, (at, seconds) in enumerate(plan):
            print(f'{index+1}/{len(plan)} · فصل الأصوات البشرية عن المحيط على GPU', flush=True)
            raw = work/f'chunk_{index:05d}.wav'
            try:
                ffmpeg(['-ss', at, '-i', source, '-t', seconds, '-map', '0:a:0', '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', raw])
                names = separator.separate(str(raw), custom_output_names={'Vocals': f'voice_{index:05d}', 'Instrumental': f'bg_{index:05d}'})
                found = {}
                for name in names or []:
                    path = Path(name)
                    path = path if path.is_absolute() else work/path
                    if path.name.startswith('voice_'): found['voice'] = path
                    elif path.name.startswith('bg_'): found['bg'] = path
                if set(found) != {'voice', 'bg'} or not all(p.is_file() for p in found.values()):
                    raise RuntimeError('لم يُنتج نموذج الفصل مساري الصوت والمحيط')
                voices.append(found['voice']); backgrounds.append(found['bg'])
            finally:
                raw.unlink(missing_ok=True)
        outputs = []
        for label, parts in (('voice', voices), ('background', backgrounds)):
            listing = work/f'{label}_list.txt'
            listing.write_text(''.join("file '"+str(p)+"'\n" for p in parts))
            target = work/f'{label}.m4a'
            print('جمع ' + ('مسار الكلام' if label == 'voice' else 'مسار المحيط') + '…', flush=True)
            ffmpeg(['-f', 'concat', '-safe', '0', '-i', listing, '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', target])
            outputs.append(target)
        bundle = work/'dub.zip'
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_STORED) as z:
            for path in outputs:
                z.write(path, path.name)
        print('اكتمل تجهيز الدبلجة:', round(bundle.stat().st_size/1024**2, 1), 'MB', flush=True)
        return bundle
    finally:
        del separator
        gc.collect()
