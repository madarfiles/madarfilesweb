"""Public media URLs only; runs on the user's Colab session, no account cookies."""
import ipaddress, re, shutil, socket, subprocess, sys, threading, time, hashlib, tarfile, io, urllib.request, json
from pathlib import Path
from urllib.parse import urlsplit

HOSTS = {'youtube.com','youtu.be','tiktok.com','x.com','twitter.com','instagram.com','snapchat.com','facebook.com','fb.watch','fb.com','vimeo.com','reddit.com','redd.it','pinterest.com','pin.it','dailymotion.com','dai.ly','twitch.tv'}
LIMIT = 256*1024**2


def public_url(value):
    u = urlsplit(value)
    if u.scheme != 'https' or not any(u.hostname==h or (u.hostname or '').endswith('.'+h) for h in HOSTS) or u.username or u.password or u.port not in (None,443) or u.path in ('','/') or len(value)>2000:
        raise ValueError('رابط المقطع غير مدعوم؛ استخدم رابطًا عامًا من المنصات المحددة')
    return value


def public_dns(original):
    def resolve(host, port, *args, **kwargs):
        rows = original(host, port, *args, **kwargs)
        if not rows or any(not ipaddress.ip_address(row[4][0].split('%')[0]).is_global for row in rows):
            raise ValueError('رُفض اتصال التحميل بعنوان شبكة غير عام')
        return rows
    return resolve

_READY=False

def javascript_runtime(root,report):
 node=shutil.which('node')
 if node:
  try:
   version=subprocess.check_output([node,'--version'],text=True,timeout=10)
   if int(version.lstrip('v').split('.')[0])>=22:return node
  except Exception:pass
 cache=Path(__file__).parent/'cache/js';cache.mkdir(parents=True,exist_ok=True);node=cache/'node'
 if node.is_file():return str(node)
 report('setup','تجهيز JavaScript المتوافق ليوتيوب؛ مرة واحدة للجلسة')
 name='node-v22.21.1-linux-x64';base='https://nodejs.org/dist/v22.21.1/'
 def fetch(name,limit):
  with urllib.request.urlopen(base+name,timeout=60) as r:data=r.read(limit+1)
  if len(data)>limit:raise ValueError('تجاوز تنزيل محرك JavaScript الحد')
  return data
 archive=name+'.tar.xz';checks=fetch('SHASUMS256.txt',100000).decode();expected=next(line.split()[0] for line in checks.splitlines() if line.split()[-1]==archive);data=fetch(archive,60000000)
 if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('فشل التحقق من محرك JavaScript · JS_CHECKSUM')
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:xz') as tar:
  member=tar.getmember(name+'/bin/node')
  if not member.isfile() or member.size>150000000:raise ValueError('ملف JavaScript غير صالح')
  temp=node.with_suffix('.tmp');temp.write_bytes(tar.extractfile(member).read())
 temp.chmod(0o700);temp.replace(node);return str(node)

def download_error(exc):
 text=str(exc).lower()
 if any(x in text for x in ['not a bot','confirm you’re','confirm you are','sign in to confirm']):return 'المنصة تطلب تحققًا من اتصال Colab؛ المقطع ليس بالضرورة خاصًا. جرّب التحميل من تطبيق مدار على جهازك · PLATFORM_VERIFICATION'
 if any(x in text for x in ['private video','login required','log in','cookies are needed']):return 'هذا الرابط يحتاج تسجيل دخول إلى المنصة · LOGIN_REQUIRED'
 if 'drm' in text:return 'المقطع محمي بـ DRM ولا يمكن تنزيله بهذه الأداة · DRM'
 if any(x in text for x in ['javascript','js runtime','challenge','ejs']):return 'تعذر محرك JavaScript الخاص بالمنصة؛ أعد المحاولة في الجلسة نفسها · JS_CHALLENGE'
 if any(x in text for x in ['403','429','too many requests','forbidden']):return 'رفضت المنصة اتصال الخادم أو حدّت طلباته؛ أعد لاحقًا أو استخدم تطبيق مدار · PLATFORM_NETWORK'
 if any(x in text for x in ['timed out','timeout','network','connection']):return 'تعطل الاتصال بالمنصة؛ أعد المحاولة والجلسة محفوظة · DOWNLOAD_NETWORK'
 if any(x in text for x in ['unsupported','extract','no video formats']):return 'لم يستطع محرك الروابط قراءة هذا المقطع أو صِيغه · EXTRACTOR_FAILED'
 return 'تعذر تنزيل هذا المقطع؛ الجلسة محفوظة ويمكن تجربة رابط آخر · DOWNLOAD_FAILED'


def download_clip(config, root, report):
    url = public_url(config['url'])
    report('setup', 'تجهيز أداة التحميل في جلسة Colab')
    global _READY
    if not _READY:
        subprocess.run([sys.executable,'-m','pip','install','--quiet','yt-dlp[default]==2026.10.26'],check=True,timeout=300)
        _READY=True
    from yt_dlp import YoutubeDL
    out = Path(root)/'download'
    out.mkdir(exist_ok=True)
    progress_lock=threading.Lock()
    last_update=[0.0]
    def progress(data):
        if data.get('status') == 'downloading':
            done = data.get('downloaded_bytes') or 0
            if done > LIMIT: raise ValueError('المقطع يتجاوز حد 256 MB؛ اختر رابط مقطع أقصر')
            total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            with progress_lock:
                now=time.monotonic()
                if now-last_update[0]>=1:
                    last_update[0]=now
                    report('downloading', 'تحميل المقطع من المنصة'+(f' · {min(99,round(done/total*100))}٪' if total else '…'))
    def suitable(info, *, incomplete):
        if info.get('is_live'): return 'البث المباشر غير مدعوم؛ استخدم مقطعًا مكتملًا'
    options = dict(outtmpl=str(out/'clip.%(ext)s'), noplaylist=True, max_filesize=LIMIT,
        format='bestvideo[ext=mp4][vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][vcodec^=avc1][height<=1080]/bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best[height<=1080]',
        playlistend=1,lazy_playlist=True,merge_output_format='mp4', restrictfilenames=True, quiet=True, no_warnings=True,
        socket_timeout=20, retries=2, fragment_retries=2, concurrent_fragment_downloads=4,
        hls_prefer_native=True, external_downloader={'default':'native'}, proxy='', geo_bypass=False,
        enable_file_urls=False,
        remote_components=[], cachedir=False, progress_hooks=[progress], match_filter=suitable)
    options['js_runtimes']={'node':{'path':javascript_runtime(root,report)}}
    original = socket.getaddrinfo
    socket.getaddrinfo = public_dns(original)
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False)
            if not info or info.get('_type') in ('playlist','multi_video'):
                raise ValueError('استخدم رابط مقطع واحد، وليس حسابًا أو قائمة تشغيل')
            if info.get('is_live') or info.get('has_drm'): raise ValueError('البث المباشر والمحتوى المحمي غير مدعومين')
            downloader.process_ie_result(info, download=True)
    except ValueError: raise
    except Exception as exc:
        raise ValueError(download_error(exc)) from exc
    finally:
        socket.getaddrinfo = original
    files = [p for p in out.glob('clip.*') if p.suffix.lower() in ('.mp4','.mkv','.webm','.mov') and p.is_file()]
    if not files: raise ValueError('لم تُنتج المنصة ملف فيديو قابلًا للتنزيل')
    source=max(files,key=lambda p:p.stat().st_size)
    from madar_colab_runtime import prepare_mp4
    target=prepare_mp4(source,Path(root)/'downloaded.mp4',report)
    if target.stat().st_size>LIMIT: raise ValueError('الناتج يتجاوز حد تنزيل المتصفح 256 MB')
    return target
