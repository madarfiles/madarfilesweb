"""«جودة تيك توك»: one file TikTok keeps sharp, from any phone and any camera mode.

The visitor picks nothing technical. The clip is read first and every decision follows from it:
- size: 1080 on the short side (TikTok never plays above 1080p); 4K/2K is reduced with Lanczos,
  smaller clips are enlarged with Lanczos plus light sharpening;
- light: HDR clips (HDR10/HDR10+ PQ, HLG, Dolby Vision from Samsung, Pixel, Honor, Huawei, iPhone…)
  are tone-mapped here to normal video (SDR, BT.709) with highlight roll-off, the way Meta does it
  on the phone before upload, instead of leaving TikTok's server to convert them (that made clips
  dark and grey); normal clips stay normal and are tagged BT.709 so no app guesses the colours;
- motion: the clip's own frame rate, made constant (phones record variable rates); above 60 → 60;
- encoding: H.264 High, 8-bit 4:2:0, 2-second keyframes, generous bitrate (16 Mbps at 30 fps,
  20 Mbps at 60 fps) so TikTok's own compression starts from a clean picture; AAC 48 kHz;
  index at the front of the file; location and other metadata removed.
"""
import base64, json, shutil, subprocess, time
from pathlib import Path

STANDARD_RATES = ['24000/1001', '24', '25', '30000/1001', '30', '50', '60000/1001', '60']
HDR_TRANSFERS = {'smpte2084': 'HDR10/HDR10+', 'arib-std-b67': 'HLG'}


def rate_value(r):
    a, _, b = str(r).partition('/')
    try:
        return float(a)/float(b or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(source):
    data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(source)], timeout=60))
    video = next(s for s in data['streams'] if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic'))
    audio = any(s.get('codec_type') == 'audio' for s in data['streams'])
    w, h = int(video['width']), int(video['height'])
    rot = 0
    for side in video.get('side_data_list', []) or []:
        if 'rotation' in side:
            rot = side['rotation']
    rot = rot or video.get('tags', {}).get('rotate', 0)
    try:
        if abs(int(float(rot))) % 180 == 90:
            w, h = h, w
    except ValueError:
        pass
    fps = rate_value(video.get('avg_frame_rate')) or rate_value(video.get('r_frame_rate')) or 30.0
    dovi = any('dv_profile' in s for s in video.get('side_data_list', []) or [])
    tags = {k.lower(): v for k, v in (data.get('format', {}).get('tags') or {}).items()}
    return {'w': w, 'h': h, 'fps': fps, 'transfer': video.get('color_transfer', ''), 'primaries': video.get('color_primaries', ''),
            'bits': 10 if '10' in video.get('pix_fmt', '') else 8, 'codec': video.get('codec_name', ''), 'audio': audio, 'dovi': dovi,
            'apple': 'apple' in str(tags.get('com.apple.quicktime.make', '')).lower() or 'com.apple.quicktime.make' in tags,
            'duration': float(data.get('format', {}).get('duration') or 0)}


def output_rate(fps):
    """The clip's own rate as a standard one (phones record 29.6…30.4); above 60 becomes 60."""
    if fps > 61:
        return '60'
    best = min(STANDARD_RATES, key=lambda r: abs(rate_value(r) - fps))
    return best if abs(rate_value(best) - fps) <= 1.5 else ('60' if fps > 45 else '30')


def target_size(w, h, short=1080):
    """Short side 1080 (up to `short` when the clip has it), keeping the shape."""
    s = min(max(1080, min(short, min(w, h)))/min(w, h), max(1920, min(short*16//9, max(w, h)))/max(w, h))
    return max(2, round(w*s/2)*2), max(2, round(h*s/2)*2)


DENOISE = {'light': 'hqdn3d=2:1.5:6:4.5',
           'strong': 'atadenoise=0a=0.04:0b=0.08:1a=0.04:1b=0.08:2a=0.04:2b=0.08:s=9,hqdn3d=3:2:8:6'}


def video_filter(info, W, H, colors='natural', denoise='off'):
    grow = min(info['w'], info['h']) < 1080
    size = f'scale={W}:{H}:flags=lanczos'
    if info['transfer'] in HDR_TRANSFERS:
        # Size first (cheap, at 10-bit), then light: linear → BT.709 primaries → Möbius roll-off
        # (keeps the brightness of normal areas and the detail in lamps and sky) → BT.709, dithered.
        tin = 'smpte2084' if info['transfer'] == 'smpte2084' else 'arib-std-b67'
        chain = (f'{size},format=yuv420p10le,zscale=tin={tin}:min=bt2020nc:pin=bt2020:rin=tv:t=linear:npl=203,format=gbrpf32le,'
                 'zscale=p=bt709,tonemap=mobius:param=0.5:desat=0,zscale=t=bt709:m=bt709:r=tv:d=error_diffusion,format=yuv420p')
    else:
        chain = f'{size},format=yuv420p'
        if info['bits'] > 8:
            chain = f'{size},zscale=d=error_diffusion,format=yuv420p'
    if denoise in DENOISE:
        # Night and indoor phone clips carry grain that TikTok's encoder turns into blocks; cleaning
        # it (in time, across frames, and lightly in space) keeps detail and compresses cleaner.
        chain += ',' + DENOISE[denoise]
    if grow:
        chain += ',unsharp=5:5:0.5:5:5:0'
    if colors == 'vivid':
        chain += ',eq=saturation=1.12:contrast=1.04'
    return chain + ',setsar=1'


def bitrate(rate, W=1080, H=1920):
    """Mbps (target, peak): 16/20 at 1080p 30/60 fps, scaled with the picture up to 4K."""
    fast = rate_value(rate) > 31; scale = max(1.0, (W*H)/(1080*1920))
    b = round((20 if fast else 16) * scale**0.75)
    return b, round(b*1.4)


COLOR = ['-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv']


def encoder_args(rate, gpu, W=1080, H=1920):
    b, peak = bitrate(rate, W, H); gop = str(max(1, round(rate_value(rate)*2)))
    if gpu:
        return ['-c:v', 'h264_nvenc', '-preset', 'p6', '-tune', 'hq', '-profile:v', 'high', '-rc', 'vbr', '-b:v', f'{b}M', '-maxrate', f'{peak}M',
                '-bufsize', f'{peak*2}M', '-bf', '3', '-spatial-aq', '1', '-temporal-aq', '1', '-rc-lookahead', '32', '-g', gop, '-pix_fmt', 'yuv420p', *COLOR]
    return ['-c:v', 'libx264', '-preset', 'fast', '-profile:v', 'high', '-b:v', f'{b}M', '-maxrate', f'{peak}M', '-bufsize', f'{peak*2}M',
            '-g', gop, '-keyint_min', gop, '-pix_fmt', 'yuv420p', '-x264-params', 'aq-mode=3', *COLOR]


def describe(info):
    light = HDR_TRANSFERS.get(info['transfer'], 'عادي')
    if info['dovi']:
        light += ' + Dolby Vision'
    return f"{info['w']}×{info['h']} · {round(info['fps'])} إطار · {light}"


def _ffmpeg_progress(args, duration, report, timeout=5400):
    """ffmpeg with a live percentage and time left in the page (long clips took minutes in silence)."""
    import threading
    began = time.monotonic(); last = [0.0]
    proc = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-progress', 'pipe:1', '-nostats', *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    err = []
    threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True).start()
    for line in proc.stdout:
        if not line.startswith('out_time_us=') or duration <= 0:
            continue
        try:
            done = max(0.0, int(line.split('=', 1)[1]) / 1e6)
        except ValueError:
            continue
        now = time.monotonic()
        if now - last[0] < 3:
            continue
        last[0] = now; part = min(0.99, done/duration); spent = now - began
        left = spent/part - spent if part > 0.02 else 0
        report('processing', f'المعالجة {round(part*100)}٪' + (f' · باقي تقريبًا {round(left)} ث' if left else ''))
        if now - began > timeout:
            proc.kill()
    if proc.wait() != 0:
        raise subprocess.CalledProcessError(proc.returncode, 'ffmpeg', stderr=''.join(err))


def _ffmpeg(args, timeout=5400):
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', *map(str, args)], check=True, timeout=timeout)


def _jpeg(path):
    if path.is_file() and path.stat().st_size < 400000:
        return 'data:image/jpeg;base64,' + base64.b64encode(path.read_bytes()).decode()


def preview(source, result, info, W, H, root):
    """Before: the clip as a normal screen shows it with no care (HDR simply clipped). After: ours."""
    at = max(0.0, min(info['duration']/2, info['duration']-0.5))
    pw = 480 if W <= H else 640; ph = max(2, round(pw*H/W/2)*2)
    root = Path(root); before, after = root/'before.jpg', root/'after.jpg'
    plain = f'scale={pw}:{ph}'
    if info['transfer'] in HDR_TRANSFERS:
        plain += ',zscale=m=bt709:t=bt709:p=bt709:r=tv,format=yuv420p'
    _ffmpeg(['-ss', f'{at:.2f}', '-i', source, '-frames:v', '1', '-vf', plain, '-q:v', '4', before], 180)
    _ffmpeg(['-ss', f'{at:.2f}', '-i', result, '-frames:v', '1', '-vf', f'scale={pw}:{ph}', '-q:v', '4', after], 180)
    data = {'before': _jpeg(before), 'after': _jpeg(after)}
    if all(data.values()):
        (root/'preview.json').write_text(json.dumps(data))


def make_tiktok(source, cfg, root, report):
    from madar_colab_runtime import nvenc_ready
    root = Path(root)
    info = probe(source)
    editors = cfg.get('method') in ('editors', 'editors4k')
    try:
        gpu_ok = bool(nvenc_ready())
    except Exception:
        gpu_ok = False
    # The editors' method aims at TikTok keeping the file as uploaded, so the clip keeps up to 4K
    # (1440 without a GPU: 4K on two CPU cores would take many minutes).
    # 4K only for normal clips on a GPU: tone-mapping HDR at 4K on Colab's two CPU cores took over
    # seven minutes for a 36-second clip, so HDR (and anything without a GPU) stops at 1440.
    hdr = info['transfer'] in HDR_TRANSFERS
    # TikTok's phone app refuses anything above 1080p ("غير مدعومة الآن"), so the app route stays at
    # 1080; above it only for upload from a computer (tiktok.com/tiktokstudio).
    short = (2160 if gpu_ok and not hdr else 1440) if cfg.get('method') == 'editors4k' else 1080
    W, H = target_size(info['w'], info['h'], short); rate = output_rate(info['fps'])
    steps = []
    if min(info['w'], info['h']) > min(W, H):
        steps.append(f'تصغير ذكي لـ{min(W, H)}')
    elif min(info['w'], info['h']) == min(W, H) and min(W, H) > 1080:
        steps.append(f'نحافظ على دقة {min(W, H)}')
    elif min(info['w'], info['h']) < 1080:
        steps.append('تكبير لـ1080 مع تحسين الحدة')
    if info['transfer'] in HDR_TRANSFERS:
        steps.append('تحويل HDR لألوان عادية مضبوطة')
    if cfg.get('denoise', 'light') in DENOISE:
        steps.append('إزالة التشويش' + (' القوية' if cfg.get('denoise') == 'strong' else ''))
    report('processing', f"المقطع: {describe(info)} → {W}×{H} · {round(rate_value(rate))} إطار" + (' · ' + '، '.join(steps) if steps else ''))
    vf = video_filter(info, W, H, cfg.get('colors', 'natural'), cfg.get('denoise', 'light'))
    out = root/'result.mp4'
    began = time.monotonic()
    def encode(gpu):
        args = (['-hwaccel', 'cuda'] if gpu else []) + ['-i', source, '-map', '0:v:0', '-map', '0:a:0?', '-vf', vf, '-fps_mode', 'cfr', '-r', rate,
                *encoder_args(rate, gpu, W, H), '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-ac', '2', '-sn', '-dn',
                '-map_metadata', '-1', '-map_chapters', '-1', '-movflags', '+faststart', '-tag:v', 'avc1', out]
        _ffmpeg_progress(args, info['duration'], report)
    how = 'GPU'
    try:
        if not gpu_ok:
            raise RuntimeError('no nvenc')
        encode(True)
    except (RuntimeError, subprocess.CalledProcessError):
        how = 'CPU'
        report('processing', 'الترميز على المعالج (CPU)؛ أبطأ شوي من GPU')
        encode(False)
    b, _ = bitrate(rate, W, H)
    report('processing', f'جاهز: H.264 · {W}×{H} · {round(rate_value(rate))} إطار · {b} Mbps · {how} في {time.monotonic()-began:.0f} ث')
    try:
        preview(source, out, info, W, H, root)
    except Exception:
        pass
    if editors:
        from madar_upload_method import transform
        patched = root/'result-editors.mp4'
        try:
            stats = transform(str(out), str(patched))
            patched.replace(out)
            report('processing', f"طريقة المحررين: الملف يعلن {stats['declared_frames']} إطار (الصورة نفسها ما تغيرت)")
            try:
                extra = json.loads((root/'preview.json').read_text()) if (root/'preview.json').exists() else {}
                extra['method'] = cfg.get('method'); (root/'preview.json').write_text(json.dumps(extra))
            except Exception:
                pass
        except Exception as exc:
            patched.unlink(missing_ok=True)
            report('processing', f'تعذرت طريقة المحررين ({type(exc).__name__})؛ الملف بالطريقة العادية')
    return out
