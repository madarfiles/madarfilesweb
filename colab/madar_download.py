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


def renditions(info):
    """The video versions the site offers for this clip (best first), e.g. '1080×1920 h265 7.5Mbps'.
    Shown in the support log so the visitor sees exactly what the platform serves to everyone."""
    seen=[]
    for f in sorted(info.get('formats') or [],key=lambda f:((f.get('height') or 0)*(f.get('width') or 0),f.get('tbr') or 0),reverse=True):
        if (f.get('vcodec') or 'none')=='none' or not f.get('height'):continue
        codec=str(f.get('vcodec')).split('.')[0].replace('avc1','h264').replace('hvc1','h265').replace('hev1','h265').replace('bytevc1','h265')
        rate=f.get('tbr') or f.get('vbr')
        item=f"{f.get('width') or '?'}×{f.get('height')} {codec}"+(f' {rate/1000:.1f}Mbps' if rate else '')
        if item not in seen:seen.append(item)
    return seen[:6]


def download_clip(config, root, report):
    url = public_url(config['url'])
    report('setup', 'تجهيز أداة التحميل في جلسة Colab')
    global _READY
    if not _READY:
        # Platforms change every week; the newest extractor is what keeps links working.
        try:subprocess.run([sys.executable,'-m','pip','install','--quiet','--upgrade','yt-dlp[default]'],check=True,timeout=300)
        except Exception:subprocess.run([sys.executable,'-m','pip','install','--quiet','yt-dlp[default]==2026.10.26'],check=True,timeout=300)
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
        # Same choices as the Madar Android app: H.264 + AAC in .mp4 first (every phone and WhatsApp
        # play it, no re-encode), then anything the site offers.
        format='bv*[vcodec^=avc1]+ba[ext=m4a]/bv*[vcodec^=avc1]+ba/b[ext=mp4]/bv*+ba/b',
        playlistend=1,lazy_playlist=True,merge_output_format='mp4', restrictfilenames=True, quiet=True, no_warnings=True,
        socket_timeout=20, retries=3, fragment_retries=3, concurrent_fragment_downloads=4, http_chunk_size=10*1024*1024,
        source_address='0.0.0.0',
        hls_prefer_native=True, external_downloader={'default':'native'}, proxy='', geo_bypass=False,
        enable_file_urls=False,
        remote_components=[], cachedir=str(Path(__file__).parent/'cache/yt-dlp'), progress_hooks=[progress], match_filter=suitable)
    host=(urlsplit(url).hostname or '').lower()
    youtube=host.endswith('youtube.com') or host=='youtu.be'
    # Only YouTube needs a JavaScript engine; other platforms skip that download entirely.
    if youtube:options['js_runtimes']={'node':{'path':javascript_runtime(root,report)}}
    # Several ways in: when a platform asks this server to prove it is not a bot, another client
    # often isn't asked. Each attempt starts clean.
    attempts=[{}]
    if youtube:attempts+= [{'extractor_args':{'youtube':{'player_client':['tv','web_safari']}}},{'extractor_args':{'youtube':{'player_client':['android_vr','mweb']}}},{'extractor_args':{'youtube':{'player_client':['web_embedded','ios']}}}]
    else:attempts.append({'format':'b/bv*+ba','format_sort':['res:1080']})
    original = socket.getaddrinfo
    socket.getaddrinfo = public_dns(original)
    info=None
    try:
        for n,extra in enumerate(attempts):
            for leftover in out.glob('clip.*'):leftover.unlink(missing_ok=True)
            try:
                with YoutubeDL({**options,**extra}) as downloader:
                    info = downloader.extract_info(url, download=False)
                    if not info or info.get('_type') in ('playlist','multi_video'):
                        raise ValueError('استخدم رابط مقطع واحد، وليس حسابًا أو قائمة تشغيل')
                    if info.get('is_live') or info.get('has_drm'): raise ValueError('البث المباشر والمحتوى المحمي غير مدعومين')
                    offered=renditions(info)
                    if offered:report('downloading','الجودات المتاحة عند المنصة: '+' | '.join(offered))
                    downloader.process_ie_result(info, download=True)
                break
            except ValueError: raise
            except Exception as exc:
                reason=download_error(exc)
                retry=any(code in reason for code in ('PLATFORM_VERIFICATION','PLATFORM_NETWORK','EXTRACTOR_FAILED','JS_CHALLENGE','DOWNLOAD_NETWORK','DOWNLOAD_FAILED'))
                if n+1<len(attempts) and retry:
                    report('setup',f'المنصة ما ردّت من أول مرة؛ نجرب طريقة ثانية ({n+2}/{len(attempts)})…');time.sleep(2);continue
                raise ValueError(reason) from exc
    finally:
        socket.getaddrinfo = original
    title=re.sub(r'[\x00-\x1f<>:"/\\|?*]+',' ',str((info or {}).get('title') or '')).strip()[:90]
    try:(Path(root)/'meta.json').write_text(json.dumps({'title':title},ensure_ascii=False),encoding='utf-8')
    except Exception:pass
    files = [p for p in out.glob('clip.*') if p.suffix.lower() in ('.mp4','.mkv','.webm','.mov') and p.is_file()]
    if not files: raise ValueError('لم تُنتج المنصة ملف فيديو قابلًا للتنزيل')
    source=max(files,key=lambda p:p.stat().st_size)
    from madar_colab_runtime import prepare_mp4
    target=prepare_mp4(source,Path(root)/'downloaded.mp4',report)
    if target.stat().st_size>LIMIT: raise ValueError('الناتج يتجاوز حد تنزيل المتصفح 256 MB')
    return target
