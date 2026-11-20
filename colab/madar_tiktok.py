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


def target_size(w, h):
    """Short side 1080, keeping the shape; never more than 1920 on the long side."""
    s = min(1080/min(w, h), 1920/max(w, h))
    return max(2, round(w*s/2)*2), max(2, round(h*s/2)*2)


def video_filter(info, W, H, colors='natural'):
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
    if grow:
        chain += ',unsharp=5:5:0.5:5:5:0'
    if colors == 'vivid':
        chain += ',eq=saturation=1.12:contrast=1.04'
    return chain + ',setsar=1'


def bitrate(rate):
    return (20, 28) if rate_value(rate) > 31 else (16, 22)


COLOR = ['-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv']


def encoder_args(rate, gpu):
    b, peak = bitrate(rate); gop = str(max(1, round(rate_value(rate)*2)))
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
    W, H = target_size(info['w'], info['h']); rate = output_rate(info['fps'])
    steps = []
    if min(info['w'], info['h']) > 1080:
        steps.append('تصغير ذكي لـ1080')
    elif min(info['w'], info['h']) < 1080:
        steps.append('تكبير لـ1080 مع تحسين الحدة')
    if info['transfer'] in HDR_TRANSFERS:
        steps.append('تحويل HDR لألوان عادية مضبوطة')
    report('processing', f"المقطع: {describe(info)} → {W}×{H} · {round(rate_value(rate))} إطار" + (' · ' + '، '.join(steps) if steps else ''))
    vf = video_filter(info, W, H, cfg.get('colors', 'natural'))
    out = root/'result.mp4'
    began = time.monotonic()
    def encode(gpu):
        args = (['-hwaccel', 'cuda'] if gpu else []) + ['-i', source, '-map', '0:v:0', '-map', '0:a:0?', '-vf', vf, '-fps_mode', 'cfr', '-r', rate,
                *encoder_args(rate, gpu), '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-ac', '2', '-sn', '-dn',
                '-map_metadata', '-1', '-map_chapters', '-1', '-movflags', '+faststart', '-tag:v', 'avc1', out]
        _ffmpeg(args)
    how = 'GPU'
    try:
        if not nvenc_ready():
            raise RuntimeError('no nvenc')
        encode(True)
    except (RuntimeError, subprocess.CalledProcessError):
        how = 'CPU'
        report('processing', 'الترميز على المعالج (CPU)؛ أبطأ شوي من GPU')
        encode(False)
    b, _ = bitrate(rate)
    report('processing', f'جاهز: H.264 · {W}×{H} · {round(rate_value(rate))} إطار · {b} Mbps · {how} في {time.monotonic()-began:.0f} ث')
    try:
        preview(source, out, info, W, H, root)
    except Exception:
        pass
    return out
