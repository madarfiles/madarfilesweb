"""Madar GPU separation, run interactively inside the user's own Colab notebook.
No tunnel, web server, remote-control endpoint or account credential is created.
"""
import gc, hashlib, json, logging, math, shutil, subprocess, sys, time
from functools import lru_cache
from pathlib import Path

MODEL = 'UVR-MDX-NET-Voc_FT.onnx'
# Dubbing needs a background with no voice left in it. Measured on a speech + music test mix,
# Voc_FT left the voice clearly audible in its instrumental (+12.4 dB during speech) while the
# instrumental-trained Inst_HQ_4 left almost none (+2.3 dB), so dubbing uses Inst_HQ_4.
DUB_MODEL = 'UVR-MDX-NET-Inst_HQ_4.onnx'
ROOT = Path('/content/madar_separation')
CACHE = Path('/content/madar_models')
CHUNK_SECONDS = 300
SEPARATION_PIP = [['install', '--quiet', 'audio-separator[gpu]==0.48.0', 'onnxruntime-gpu[cuda,cudnn]==1.23.2', 'numpy==2.2.6', 'numba==0.61.2', 'nvidia-cublas-cu12>=12,<13']]
SETUP_DIR = Path(__file__).resolve().parent/'setup'


def install_once(key, commands, timeout=600, report=None):
    """Runs the pip commands for `key` once per Colab session. A shared lock lets the early
    preparation (started while the file uploads) and the job itself use the same install:
    whichever comes second waits for the first and then skips it. Returns True if it installed.
    Libraries saved in the visitor's Drive by an earlier session are unpacked instead of pip."""
    import fcntl, threading
    SETUP_DIR.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha256(json.dumps(commands).encode()).hexdigest()[:16]
    marker = SETUP_DIR/(key+'.ok')
    def ready():
        try: return marker.read_text() == tag
        except OSError: return False
    say = report or (lambda *a, **k: None)
    how = SETUP_DIR/(key+'.how')
    def told():
        # The early preparation (no page to report to) may have done the work: tell the page once.
        if report:
            try:
                text = how.read_text(encoding='utf-8'); how.unlink(); say('setup', text)
            except OSError:
                pass
        return False
    if ready(): return told()
    with open(SETUP_DIR/'pip.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if ready(): return told()
        drive = None
        try:
            import madar_drive_cache as drive
            name = drive.lib_name(key, tag)
            got = drive.restore_libs(name, report)
            if got:
                marker.write_text(tag)
                text = f'المكتبات جاهزة من Drive · {got[0]} MB في {got[1]} ث'
                if report: say('setup', text)
                else: how.write_text(text, encoding='utf-8')
                return True
            before = drive.lib_snapshot()
        except Exception:
            drive = None
        began = time.monotonic()
        for command in commands:
            subprocess.run([sys.executable, '-m', 'pip', *command], check=True, timeout=timeout)
        marker.write_text(tag)
        text = f'ثُبتت المكتبات · {time.monotonic()-began:.1f} ث' + (' (تنحفظ في Drive للمرة الجاية)' if drive and drive.token() else ' (ما فيه تصريح Drive لحفظها)')
        if report: say('setup', text)
        else: how.write_text(text, encoding='utf-8')
        if drive:
            try:
                added, removed = drive.lib_changes(before)
                threading.Thread(target=drive.save_libs, args=(name, added, removed, str(SETUP_DIR/'pip.lock')), daemon=False, name='madar-libs-save').start()
            except Exception:
                pass
    return True


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
        codec=(['-c:v','copy']+(['-tag:v','hvc1'] if fmt in {'mp4','mov'} and video_codec(source)=='hevc' else [])) if copy else video_encoder()
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


def video_codec(path):
    try:return next((s for s in media_streams(path) if s.get('codec_type')=='video'),{}).get('codec_name')
    except Exception:return None


def compatible_mp4(path):
    streams = media_streams(path)
    video = next((s for s in streams if s.get('codec_type')=='video'),{})
    audio = next((s for s in streams if s.get('codec_type')=='audio'),None)
    # H.264, and HEVC (phones and TikTok/Instagram play it): keep the original stream, never re-encode.
    return video.get('codec_name') in {'h264','hevc'} and video.get('pix_fmt') in {'yuv420p','yuvj420p','nv12','yuv420p10le'}, audio is None or audio.get('codec_name')=='aac'


def prepare_mp4(source, target, report):
    copy_video, copy_audio = compatible_mp4(source)
    codec = (['-c:v','copy']+(['-tag:v','hvc1'] if video_codec(source)=='hevc' else [])) if copy_video else video_encoder()
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


def new_separator(output_dir, single_stem='Vocals', model=None):
    from audio_separator.separator import Separator
    obj = Separator(output_dir=str(output_dir), model_file_dir=str(CACHE), output_format='WAV', output_single_stem=single_stem, use_soundfile=True,
                    log_level=logging.WARNING, mdx_params={'hop_length':1024, 'segment_size':256, 'overlap':0.25, 'batch_size':1, 'enable_denoise':False})
    obj.load_model(model_filename=model or MODEL)
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


SENTENCE_END = ('.', '?', '!', '؟', '…', '。', '!', '؛')


def _ends_sentence(word):
    return str(word.get('w', '')).rstrip().rstrip('"\'»)').endswith(SENTENCE_END)


def turn_units(words, long_gap=1.0, sentence_gap=0.15):
    """Pieces of speech that belong to one speaker: Whisper's own segments (it starts a new
    one where the speaker changes far more reliably than any pause rule), split further at a
    sentence end followed by a breath, or at a silence. Returns lists of word indexes."""
    units, cur = [], []
    for i, w in enumerate(words):
        if cur:
            prev = words[cur[-1]]; pause = w['s'] - prev['e']
            if w.get('seg') != prev.get('seg') or pause >= long_gap or (_ends_sentence(prev) and pause >= sentence_gap):
                units.append(cur); cur = []
        cur.append(i)
    if cur: units.append(cur)
    return units


def cluster_speakers(vectors, durations, threshold=0.5, assign=0.45, distinct=0.25, reliable=1.5):
    """Speaker number for each piece from its voice print (TitaNet). Pieces long enough to
    trust are grouped first (average similarity ≥ threshold); short ones join the closest
    group only when clearly similar (≥ assign), otherwise stay unknown (None) rather than
    guessing. Numbers follow first appearance."""
    import numpy as np
    labels = [None] * len(vectors)
    have = [i for i, v in enumerate(vectors) if v is not None]
    if not have:
        return labels
    x = {i: np.asarray(vectors[i], dtype=np.float64) for i in have}
    for i in have: x[i] = x[i] / max(np.linalg.norm(x[i]), 1e-9)
    core = [i for i in have if durations[i] >= reliable] or have
    raw = _cluster(np.array([x[i] for i in core]), threshold)
    groups = {}
    for i, g in zip(core, raw): groups.setdefault(g, []).append(i); labels[i] = g
    centre = {}
    for g, members in groups.items():
        c = np.mean([x[i] for i in members], axis=0); centre[g] = c / max(np.linalg.norm(c), 1e-9)
    strangers = []
    for i in have:
        if labels[i] is None:
            g = max(centre, key=lambda k: float(x[i] @ centre[k]))
            best = float(x[i] @ centre[g])
            if best >= assign: labels[i] = g
            elif best < distinct: strangers.append(i)
    # A short piece unlike every known voice (a deep voice among children…) is a new speaker
    # for sure, even if short: group such pieces among themselves.
    if strangers:
        for i, g in zip(strangers, _cluster(np.array([x[i] for i in strangers]), threshold)):
            labels[i] = ('new', g)
    order = {}
    for i, g in enumerate(labels):
        if g is not None: labels[i] = order.setdefault(g, len(order) + 1)
    return labels


def _cluster(x, threshold):
    if len(x) == 1:
        return [0]
    try:
        from scipy.cluster.hierarchy import linkage, fcluster
        return list(fcluster(linkage(x, method='average', metric='cosine'), t=1 - threshold, criterion='distance'))
    except ImportError:
        return _average_linkage(x, threshold)


def _average_linkage(x, threshold):
    import numpy as np
    total = x @ x.T; np.fill_diagonal(total, 0.0)
    groups = {i: [i] for i in range(len(x))}
    while len(groups) > 1:
        keys = list(groups)
        sizes = np.array([len(groups[k]) for k in keys], dtype=np.float64)
        sub = total[np.ix_(keys, keys)] / np.outer(sizes, sizes)
        np.fill_diagonal(sub, -np.inf)
        a, b = np.unravel_index(int(np.argmax(sub)), sub.shape)
        if sub[a, b] < threshold:
            break
        ga, gb = keys[a], keys[b]
        total[ga, :] += total[gb, :]; total[:, ga] += total[:, gb]; total[ga, ga] = 0.0
        groups[ga] += groups.pop(gb)
    raw = [0] * len(x)
    for g, members in groups.items():
        for m in members: raw[m] = g
    return raw


def group_dub_words(words, sounds=(), units=None, labels=None, join_gap=0.6, glue_gap=0.25, max_len=20.0, pause_mark=0.7, attach=0.6, pad_start=0.05, pad_end=0.12):
    """Dubbing lines: one line is one speaker's turn — from when they start until they stop
    or someone else speaks, however short or long. Pieces (turn_units) of the same speaker
    with less than join_gap of silence between them form one turn; a different or unknown
    speaker starts a new line. The only exception is a cut-off fragment (one or two words,
    unknown speaker) right after an unfinished sentence: it is glued back.
    sounds: [{'s','e','label'}] non-word sounds, shown as «(…)» in the nearest line.
    Long silences inside a line show as «…». Lines may overlap when people talk together."""
    ok = lambda w: str(w.get('w', '')).strip() and w.get('e', 0) > w.get('s', 0)
    if units is None:
        words = sorted((w for w in words if ok(w)), key=lambda w: w['s']); units = turn_units(words)
    if labels is None:
        labels = [None] * len(units)
    lines = []
    for unit, lab in zip(units, labels):
        piece = [words[i] for i in unit if ok(words[i])]
        if not piece: continue
        if lines:
            last = lines[-1]; gap = piece[0]['s'] - last['words'][-1]['e']
            same = lab is not None and lab == last['spk'] and gap < join_gap
            glue = lab is None and last['spk'] is not None and len(piece) <= 2 and gap < glue_gap and not _ends_sentence(last['words'][-1])
            if same or glue:
                last['words'].extend(piece); continue
        lines.append({'words': list(piece), 'spk': lab})
    out = []
    def split(chunk, spk):
        if chunk[-1]['e'] - chunk[0]['s'] <= max_len or len(chunk) < 2:
            out.append((chunk, spk)); return
        middle = (chunk[0]['s'] + chunk[-1]['e']) / 2
        k = max(range(1, len(chunk)), key=lambda j: (_ends_sentence(chunk[j-1]), chunk[j-1].get('seg') != chunk[j].get('seg'), round(chunk[j]['s'] - chunk[j-1]['e'], 1), -abs(chunk[j]['s'] - middle)))
        split(chunk[:k], spk); split(chunk[k:], spk)
    for line in lines: split(line['words'], line['spk'])
    extra = []
    for snd in sorted(sounds or [], key=lambda x: x['s']):
        if not (snd.get('e', 0) > snd.get('s', 0) and str(snd.get('label', '')).strip()):
            continue
        item = {'w': '(' + str(snd['label']).strip() + ')', 's': snd['s'], 'e': snd['e'], 'k': 'sound'}
        best, gap = None, attach
        for chunk, _ in out:
            d = max(0.0, chunk[0]['s'] - snd['e'], snd['s'] - chunk[-1]['e'])
            if d <= gap: best, gap = chunk, d
        if best is None: extra.append(([item], None))
        else: best.append(item); best.sort(key=lambda x: x['s'])
    out = sorted(out + extra, key=lambda c: c[0][0]['s'])
    result = []
    for chunk, spk in out:
        items = []
        for w in chunk:
            if items and w.get('k') is None and items[-1].get('k') is None and w['s'] - items[-1]['e'] >= pause_mark:
                items.append({'w': '…', 's': round(items[-1]['e'], 2), 'e': round(w['s'], 2), 'k': 'pause'})
            items.append(w)
        start = max(0.0, chunk[0]['s'] - pad_start); end = chunk[-1]['e'] + pad_end
        line = {'start': round(start, 2), 'end': round(max(end, start + 0.2), 2), 'text': ' '.join(str(w['w']).strip() for w in items),
                'say': ' '.join(str(w['w']).strip() for w in items if w.get('k') is None),
                'words': [{'w': str(w['w']).strip(), 's': round(w['s'], 2), 'e': round(w['e'], 2), **({'k': w['k']} if w.get('k') else {})} for w in items]}
        if spk is not None: line['spk'] = spk
        result.append(line)
    return result


SOUND_LABELS = [
    ('ضحكة', ['Laughter', 'Baby laughter', 'Giggle', 'Snicker', 'Belly laugh', 'Chuckle, chortle']),
    ('همهمة', ['Humming']),
    ('تنهيدة', ['Sigh']),
    ('شهقة', ['Gasp']),
    ('كحة', ['Cough', 'Throat clearing']),
    ('بكاء', ['Crying, sobbing', 'Baby cry, infant cry', 'Whimper', 'Wail, moan']),
    ('صرخة', ['Screaming', 'Yell', 'Shout', 'Children shouting', 'Battle cry']),
    ('تأوه', ['Groan', 'Grunt']),
    ('تنفس', ['Breathing', 'Pant', 'Wheeze']),
    ('همس', ['Whispering']),
    ('عطسة', ['Sneeze']),
]
SPEECH_LABELS = ['Speech', 'Child speech, kid speaking', 'Conversation', 'Narration, monologue', 'Babbling', 'Male speech, man speaking', 'Female speech, woman speaking']


SOUND_MARK = '…'


VOICEPRINT_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/nemo_en_titanet_large.onnx'
VOICEPRINT_SHA256 = 'd51abcf31717ef28162f26acb9d44dd4127c3d44c9b8624f699f3425daca8e77'
VOICEPRINT_PIP = [['install', '--quiet', '--disable-pip-version-check', 'sherpa-onnx==2.0.1']]


def voiceprint_model(folder):
    """NVIDIA TitaNet-large (CC-BY-4.0) as ONNX from sherpa-onnx's GitHub release, checked by hash."""
    import urllib.request
    target = Path(folder)/'titanet_large.onnx'
    if target.is_file() and sha256(target) == VOICEPRINT_SHA256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True); part = target.with_suffix('.part')
    with urllib.request.urlopen(VOICEPRINT_URL, timeout=120) as r, open(part, 'wb') as f:
        shutil.copyfileobj(r, f, 1 << 20)
    if sha256(part) != VOICEPRINT_SHA256:
        part.unlink(missing_ok=True); raise RuntimeError('VOICEPRINT_HASH')
    part.replace(target)
    return target


def voiceprints_main(args):
    """Separate process (sherpa-onnx brings its own ONNX Runtime, kept apart from the GPU one):
    voiceprints_main([model, raw float32 16 kHz audio, spans.json, out.npy])."""
    import numpy as np, sherpa_onnx
    model, audio_path, spans_path, out = args
    audio = np.fromfile(audio_path, dtype=np.float32)
    spans = json.loads(Path(spans_path).read_text())
    ex = sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=model, num_threads=4))
    vectors = []
    for a, b in spans:
        clip = audio[max(0, int(a * 16000)):max(0, int(b * 16000))]
        if len(clip) < 0.6 * 16000:
            vectors.append(np.zeros(ex.dim, dtype=np.float32)); continue
        st = ex.create_stream(); st.accept_waveform(16000, clip); st.input_finished()
        vectors.append(np.asarray(ex.compute(st), dtype=np.float32))
    np.save(out, np.array(vectors, dtype=np.float32))


def name_sound(scores, seconds, min_sound=0.1, min_speech=0.3):
    """Mark for a non-word sound made by a person (laugh, hum, sigh, «أمم»…), from AudioSet
    scores {label: probability}. The sound is not named — naming it was often wrong (a squeal
    shown as crying) — the performer only needs to know something other than words is there.
    Music, effects and other leftovers on the voice track get None."""
    vocal = max((scores.get(l, 0.0) for _, labels in SOUND_LABELS for l in labels), default=0.0)
    speech = max((scores.get(l, 0.0) for l in SPEECH_LABELS), default=0.0)
    return SOUND_MARK if vocal >= min_sound or speech >= min_speech else None


def sound_regions(samples, rate, words, frame=0.03, min_len=0.25, join=0.25, guard=0.08):
    """Stretches where the separated voice track has sound but Whisper wrote no word."""
    import numpy as np
    samples = np.asarray(samples, dtype=np.float32)
    size = max(1, int(round(frame * rate))); count = len(samples) // size
    if not count:
        return []
    rms = np.sqrt(np.mean(samples[:count*size].reshape(count, size) ** 2, axis=1))
    floor, peak = np.quantile(rms, 0.2), np.quantile(rms, 0.95)
    if peak < 0.003:
        return []
    on = rms > max(floor * 3, peak * 0.12, 0.004)
    for w in words:
        a = max(0, int((w['s'] - guard) / frame)); b = min(count, int(np.ceil((w['e'] + guard) / frame)))
        on[a:b] = False
    regions, start = [], None
    for f in range(count + 1):
        active = f < count and on[f]
        if active and start is None: start = f
        if not active and start is not None: regions.append([start * frame, f * frame]); start = None
    merged = []
    for a, b in regions:
        if merged and a - merged[-1][1] < join: merged[-1][1] = b
        else: merged.append([a, b])
    return [{'s': round(a, 2), 'e': round(b, 2)} for a, b in merged if b - a >= min_len]


def run_dub_stems(source, extra=None):
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
    work = ROOT/('dub2-'+source_fingerprint(source, 0, 0, 'audio'))
    work.mkdir(parents=True, exist_ok=True)
    print('تجهيز الدبلجة · عدد الأجزاء:', len(plan), '· المدة:', round(total, 1), 'ثانية', flush=True)
    separator = new_separator(work, single_stem=None, model=DUB_MODEL)
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
        # Free the separation model before anything else uses the GPU (speech-to-text).
        separator = None
        gc.collect()
        if extra:
            outputs += list(extra(outputs[0], work) or [])
        bundle = work/'dub.zip'
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_STORED) as z:
            for path in outputs:
                z.write(path, path.name)
        print('اكتمل تجهيز الدبلجة:', round(bundle.stat().st_size/1024**2, 1), 'MB', flush=True)
        return bundle
    finally:
        del separator
        gc.collect()
