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
    if cfg.get('method') == 'editors':
        patched = root/'result-editors.mp4'
        try:
            frames = ghost_frames(out, patched)
            patched.replace(out)
            report('processing', f'طريقة المحررين: الملف يعلن {frames} إطار (الصورة نفسها ما تغيرت)')
            try:
                extra = json.loads((root/'preview.json').read_text()) if (root/'preview.json').exists() else {}
                extra['method'] = 'editors'; (root/'preview.json').write_text(json.dumps(extra))
            except Exception:
                pass
        except Exception as exc:
            patched.unlink(missing_ok=True)
            report('processing', f'تعذرت طريقة المحررين ({type(exc).__name__})؛ الملف بالطريقة العادية')
    return out


# ---- «طريقة المحررين» (experimental) ---------------------------------------------------------
# Editors' upload tools (TikTok Enhancer, TikQuick, the open-source tiktok-quality) change only the
# MP4 index: they add "ghost" samples to the video track so the file declares many more frames,
# all pointing at one 8-byte H.264 filler NAL (decoders skip it). Not one pixel changes and the
# edit list keeps playback length. TikTok has not documented its rules; whether this still gives
# a higher-quality version is for the visitor's own test to show.
import struct

FILLER = struct.pack('>I', 4) + bytes([0x0C, 0xFF, 0xFF, 0x80])  # length 4 + filler NAL (type 12)
PARENTS = {b'moov', b'trak', b'mdia', b'minf', b'stbl', b'edts', b'udta'}


def _parse(data, start=0, end=None):
    end = len(data) if end is None else end; i = start; out = []
    while i + 8 <= end:
        size, kind = struct.unpack('>I4s', data[i:i+8]); head = 8
        if size == 1:
            size = struct.unpack('>Q', data[i+8:i+16])[0]; head = 16
        elif size == 0:
            size = end - i
        if size < head or i + size > end:
            raise ValueError('MP4 box out of range')
        body = data[i+head:i+size]
        out.append([kind, _parse(body) if kind in PARENTS else body])
        i += size
    return out


def _build(boxes):
    out = bytearray()
    for kind, body in boxes:
        raw = _build(body) if isinstance(body, list) else body
        out += struct.pack('>I4s', 8 + len(raw), kind) + raw
    return bytes(out)


def _child(boxes, kind):
    return next((b for b in boxes if b[0] == kind), None)


def _full(body):
    return body[:4], body[4:]


def ghost_frames(src, dst, factor=10):
    """Writes `dst` with (factor-1)×frames ghost samples added to the video track. Returns the
    declared frame count, or raises ValueError when the file isn't the simple layout this needs
    (ftyp, moov, …, mdat last: what our own encoder writes)."""
    src, dst = Path(src), Path(dst)
    data = src.read_bytes()
    top = []; i = 0
    while i + 8 <= len(data):
        size, kind = struct.unpack('>I4s', data[i:i+8]); head = 8
        if size == 1:
            size = struct.unpack('>Q', data[i+8:i+16])[0]; head = 16
        elif size == 0:
            size = len(data) - i
        top.append((kind, i, size, head)); i += size
    kinds = [t[0] for t in top]
    if b'moov' not in kinds or kinds[-1] != b'mdat' or kinds.index(b'moov') > kinds.index(b'mdat'):
        raise ValueError('layout')
    mo = top[kinds.index(b'moov')]
    moov = _parse(data, mo[1]+mo[3], mo[1]+mo[2])
    mvhd = _child(moov, b'mvhd'); movie_scale = struct.unpack('>I', mvhd[1][12:16] if mvhd[1][0] == 0 else mvhd[1][20:24])[0]
    video = None
    for trak in (b for b in moov if b[0] == b'trak'):
        mdia = _child(trak[1], b'mdia')
        if _child(mdia[1], b'hdlr')[1][8:12] == b'vide':
            video = trak
    if not video:
        raise ValueError('no video')
    mdia = _child(video[1], b'mdia'); stbl = _child(_child(mdia[1], b'minf')[1], b'stbl')[1]
    stsd = _child(stbl, b'stsd')[1]
    if b'avcC' not in stsd or (stsd[stsd.index(b'avcC')+8] & 3) != 3:
        raise ValueError('codec')
    stsz = _child(stbl, b'stsz'); fh, rest = _full(stsz[1]); fixed, count = struct.unpack('>II', rest[:8])
    if fixed:
        raise ValueError('fixed sizes')
    ghosts = count*(factor-1)
    stsz[1] = fh + struct.pack('>II', 0, count+ghosts) + rest[8:8+4*count] + struct.pack('>I', 8)*ghosts
    stts = _child(stbl, b'stts'); fh, rest = _full(stts[1]); n = struct.unpack('>I', rest[:4])[0]
    stts[1] = fh + struct.pack('>I', n+1) + rest[4:4+8*n] + struct.pack('>II', ghosts, 1)
    ctts = _child(stbl, b'ctts')
    if ctts:
        fh, rest = _full(ctts[1]); n = struct.unpack('>I', rest[:4])[0]
        ctts[1] = fh + struct.pack('>I', n+1) + rest[4:4+8*n] + struct.pack('>II', ghosts, 0)
    sdtp = _child(stbl, b'sdtp')
    if sdtp:
        sdtp[1] = sdtp[1] + bytes(ghosts)
    offsets = _child(stbl, b'stco') or _child(stbl, b'co64'); wide = offsets[0] == b'co64'
    fh, rest = _full(offsets[1]); chunks = struct.unpack('>I', rest[:4])[0]
    stsc = _child(stbl, b'stsc'); sfh, srest = _full(stsc[1]); n = struct.unpack('>I', srest[:4])[0]
    sdi = struct.unpack('>I', srest[4+12*(n-1)+8:4+12*n])[0] if n else 1
    stsc[1] = sfh + struct.pack('>I', n+1) + srest[4:4+12*n] + struct.pack('>III', chunks+1, 1, sdi)
    # Media length grows by `ghosts` ticks (a fraction of a second); the edit list keeps what plays.
    mdhd = _child(mdia[1], b'mdhd'); body = bytearray(mdhd[1])
    if body[0] == 0:
        struct.pack_into('>I', body, 16, struct.unpack('>I', body[16:20])[0] + ghosts)
    else:
        struct.pack_into('>Q', body, 24, struct.unpack('>Q', body[24:32])[0] + ghosts)
    mdhd[1] = bytes(body)
    # Offsets: measure the new moov with placeholder offsets, then fill in the real ones.
    def fill(shift, ghost_at):
        # Each call starts from the offsets as they are in the file (the first call shifts by 0).
        for trak in (b for b in moov if b[0] == b'trak'):
            tb = _child(_child(_child(_child(trak[1], b'mdia')[1], b'minf')[1], b'stbl')[1], b'stco') or \
                 _child(_child(_child(_child(trak[1], b'mdia')[1], b'minf')[1], b'stbl')[1], b'co64')
            w = tb[0] == b'co64'; h, r = _full(tb[1])
            k = struct.unpack('>I', r[:4])[0]; fmt = 'Q' if w else 'I'; size = 8 if w else 4
            base = list(struct.unpack(f'>{k}{fmt}', r[4:4+size*k]))
            original = base[:chunks] if trak is video else base
            new = [o + shift for o in original] + ([ghost_at]*ghosts if trak is video else [])
            if not w and max(new) > 0xffffffff:
                raise ValueError('offsets')
            tb[1] = h + struct.pack('>I', len(new)) + struct.pack(f'>{len(new)}{fmt}', *new)
    fill(0, 0)
    new_moov = _build(moov); shift = (8 + len(new_moov)) - mo[2]
    md = top[-1]; ghost_at = md[1] + md[2] + shift
    fill(shift, ghost_at)
    new_moov = _build(moov)
    if 8 + len(new_moov) - mo[2] != shift:
        raise ValueError('size')
    with open(dst, 'wb') as out:
        for kind, start, size, head in top:
            if kind == b'moov':
                out.write(struct.pack('>I4s', 8 + len(new_moov), b'moov')); out.write(new_moov)
            elif kind == b'mdat':
                payload = size - head + len(FILLER)
                if head == 16:
                    out.write(struct.pack('>I4sQ', 1, b'mdat', payload + 16))
                elif payload + 8 <= 0xffffffff:
                    out.write(struct.pack('>I4s', payload + 8, b'mdat'))
                else:
                    raise ValueError('size')
                out.write(data[start+head:start+size]); out.write(FILLER)
            else:
                out.write(data[start:start+size])
    return count + ghosts
