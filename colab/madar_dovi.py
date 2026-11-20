"""Dolby Vision profile 8.4 (HLG base layer) for «جودة تيك توك».

The video is encoded as HLG HEVC 10-bit, dovi_tool writes a generated RPU into every frame, and
this module puts the Dolby Vision configuration box (dvcC) into the MP4 the way phone cameras do,
then moves the index to the front of the file (fast start). ffmpeg cannot write dvcC for a raw
HEVC stream, so the box is written here; any failure leaves the plain HLG file, which is complete
on its own.
"""
import hashlib, io, json, shutil, struct, subprocess, tarfile, urllib.request
from pathlib import Path

DOVI_VERSION = '2.3.3'
DOVI_URL = f'https://github.com/quietvoid/dovi_tool/releases/download/{DOVI_VERSION}/dovi_tool-{DOVI_VERSION}-x86_64-unknown-linux-musl.tar.gz'
DOVI_SHA256 = '5dae82cb2becd3b9fd726127f936a8d32635e60746d16238fdfded12aa05988c'
CONTAINERS = {b'moov', b'trak', b'mdia', b'minf', b'stbl'}


def dovi_tool(cache):
    """The pinned dovi_tool binary, checked by SHA-256 before first use."""
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    tool = cache/'dovi_tool'
    if tool.is_file():
        return tool
    with urllib.request.urlopen(DOVI_URL, timeout=60) as r:
        data = r.read(20_000_001)
    if len(data) > 20_000_000 or hashlib.sha256(data).hexdigest() != DOVI_SHA256:
        raise ValueError('فشل التحقق من أداة Dolby Vision')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        member = next(m for m in tar.getmembers() if Path(m.name).name == 'dovi_tool' and m.isfile())
        tmp = tool.with_suffix('.tmp'); tmp.write_bytes(tar.extractfile(member).read())
    tmp.chmod(0o700); tmp.replace(tool)
    return tool


def dv_level(width, height, fps):
    """Smallest Dolby Vision level whose pixel rate covers the video; frames taller or wider
    than 1920 use the UHD levels."""
    rate = width*height*fps
    table = [(1, 22118400), (2, 27648000), (3, 49766400), (4, 62208000), (5, 124416000), (6, 199065600),
             (7, 248832000), (8, 398131200), (9, 497664000), (10, 995328000), (11, 995328000), (12, 1990656000), (13, 3981312000)]
    level = next((lv for lv, top in table if rate <= top), 13)
    return max(level, 6) if max(width, height) > 1920 else level


def dvcc(level, profile=8, compat=4):
    bits = (profile & 0x7f) << 9 | (level & 0x3f) << 3 | 1 << 2 | 0 << 1 | 1
    return struct.pack('>I4sBBHI16x', 32, b'dvcC', 1, 0, bits, (compat & 0xf) << 28)


def _boxes(data, start, end):
    i = start
    while i + 8 <= end:
        size, kind = struct.unpack('>I4s', data[i:i+8]); head = 8
        if size == 1:
            size = struct.unpack('>Q', data[i+8:i+16])[0]; head = 16
        elif size == 0:
            size = end - i
        if size < head or i + size > end:
            raise ValueError('MP4 box out of range')
        yield i, size, kind, head
        i += size


def _patch_moov(moov, box, shift):
    """Returns moov with `box` appended to every HEVC sample entry and all chunk offsets moved by
    `shift`. Parent sizes are rebuilt from the children."""
    def walk(data):
        out = bytearray(); found = False
        for i, size, kind, head in _boxes(data, 0, len(data)):
            body = data[i+head:i+size]
            if kind in CONTAINERS:
                inner, hit = walk(body); found |= hit
                body = inner
            elif kind == b'stsd':
                count = struct.unpack('>I', body[4:8])[0]; entries = bytearray(body[:8]); j = 8
                for _ in range(count):
                    esize, ekind = struct.unpack('>I4s', body[j:j+8]); entry = body[j:j+esize]
                    if ekind in (b'hvc1', b'hev1') and b'dvcC' not in entry:
                        entry = struct.pack('>I', esize + len(box)) + entry[4:] + box; found = True
                    entries += entry; j += esize
                body = bytes(entries)
            elif kind == b'stco':
                n = struct.unpack('>I', body[4:8])[0]
                offsets = [o + shift for o in struct.unpack(f'>{n}I', body[8:8+4*n])]
                if offsets and max(offsets) > 0xffffffff:
                    raise ValueError('offset overflow')
                body = body[:8] + struct.pack(f'>{n}I', *offsets)
            elif kind == b'co64':
                n = struct.unpack('>I', body[4:8])[0]
                body = body[:8] + struct.pack(f'>{n}Q', *[o + shift for o in struct.unpack(f'>{n}Q', body[8:8+8*n])])
            out += struct.pack('>I4s', 8 + len(body), kind) + body
        return bytes(out), found
    patched, found = walk(moov)
    if not found:
        raise ValueError('no HEVC sample entry')
    return patched


def add_dolby_vision(src, dst, level):
    """Writes `dst`: ftyp (with the dby1 brand) + moov (with dvcC, offsets fixed) + the media."""
    src, dst = Path(src), Path(dst)
    with open(src, 'rb') as f:
        layout = []
        pos = 0; total = src.stat().st_size
        while pos + 8 <= total:
            f.seek(pos); size, kind = struct.unpack('>I4s', f.read(8)); head = 8
            if size == 1:
                size = struct.unpack('>Q', f.read(8))[0]; head = 16
            elif size == 0:
                size = total - pos
            if size < head or pos + size > total:
                raise ValueError('MP4 box out of range')
            layout.append((pos, size, kind)); pos += size
        def read(entry):
            f.seek(entry[0]); return f.read(entry[1])
        ftyp = next(e for e in layout if e[2] == b'ftyp'); moov = next(e for e in layout if e[2] == b'moov')
        rest = [e for e in layout if e[2] not in (b'ftyp', b'moov')]
        fdata = read(ftyp)
        if b'dby1' not in fdata[16:]:
            fdata = struct.pack('>I', len(fdata) + 4) + fdata[4:] + b'dby1'
        box = dvcc(level)
        mdata = read(moov)[8:]
        # The new moov's size doesn't depend on the offsets, so measure it once, then shift.
        size = 8 + len(_patch_moov(mdata, box, 0))
        old_media = rest[0][0] if rest else 0
        shift = len(fdata) + size - old_media
        new_moov = _patch_moov(mdata, box, shift)
        with open(dst, 'wb') as out:
            out.write(fdata); out.write(struct.pack('>I4s', 8 + len(new_moov), b'moov')); out.write(new_moov)
            for pos, length, _ in rest:
                f.seek(pos); left = length
                while left:
                    chunk = f.read(min(left, 8 << 20)); out.write(chunk); left -= len(chunk)
    return dst


def generate_rpu(tool, frames, work):
    work = Path(work)
    config = {'cm_version': 'V40', 'profile': '8.4', 'length': int(frames),
              'level6': {'max_display_mastering_luminance': 1000, 'min_display_mastering_luminance': 1,
                         'max_content_light_level': 1000, 'max_frame_average_light_level': 400}}
    (work/'dv.json').write_text(json.dumps(config))
    subprocess.run([str(tool), 'generate', '-j', str(work/'dv.json'), '-o', str(work/'rpu.bin')], check=True, capture_output=True, timeout=300)
    return work/'rpu.bin'


# ---- «جودة تيك توك»: 1440p HLG HEVC 10-bit with Dolby Vision 8.4 -----------------------------
STANDARD_RATES = ['24000/1001', '24', '25', '30000/1001', '30', '50', '60000/1001', '60']
LOOKS = {'natural': 203, 'bright': 320}  # where SDR white lands in HLG: 203 nits is the reference


def _probe(source):
    data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=width,height,avg_frame_rate,r_frame_rate,color_transfer,pix_fmt:stream_side_data=rotation:stream_tags=rotate',
        '-show_entries', 'format=duration', '-of', 'json', str(source)], timeout=60))
    s = data['streams'][0]
    w, h = int(s['width']), int(s['height'])
    rot = next((x.get('rotation', 0) for x in s.get('side_data_list', []) if 'rotation' in x), s.get('tags', {}).get('rotate', 0))
    if abs(int(float(rot))) % 180 == 90:
        w, h = h, w
    def rate(v):
        try:
            a, b = str(v).split('/'); return float(a)/float(b) if float(b) else 0.0
        except (ValueError, ZeroDivisionError):
            return 0.0
    fps = rate(s.get('avg_frame_rate')) or rate(s.get('r_frame_rate')) or 30.0
    return w, h, fps, s.get('color_transfer', ''), float(data.get('format', {}).get('duration') or 0)


def output_rate(fps):
    """The standard rate closest to the clip's own (phones record variable rates)."""
    best = min(STANDARD_RATES, key=lambda r: abs(eval_rate(r) - fps))
    return best if abs(eval_rate(best) - fps) <= 1.5 else ('60' if fps > 45 else '30')


def eval_rate(r):
    a, _, b = r.partition('/'); return float(a)/float(b or 1)


def target_size(w, h):
    """Short side 1440 (TikTok's best), long side at most 2560, even numbers."""
    s = min(1440/min(w, h), 2560/max(w, h))
    return max(2, round(w*s/2)*2), max(2, round(h*s/2)*2)


def video_filter(transfer, W, H, npl):
    if transfer == 'arib-std-b67':  # already HLG: size only
        return f'zscale=w={W}:h={H}:f=lanczos,format=yuv420p10le'
    if transfer == 'smpte2084':  # PQ HDR → HLG
        return (f'zscale=tin=smpte2084:min=bt2020nc:pin=bt2020:rin=tv:t=linear:npl=1000,format=gbrpf32le,'
                f'zscale=w={W}:h={H}:f=lanczos,zscale=t=arib-std-b67:m=bt2020nc:r=tv:npl=1000,format=yuv420p10le')
    return ('unsharp=5:5:0.45:5:5:0,'
            'zscale=tin=bt709:min=bt709:pin=bt709:rin=tv:t=linear:p=bt709,format=gbrpf32le,'
            f'zscale=p=bt2020:w={W}:h={H}:f=lanczos,zscale=t=arib-std-b67:m=bt2020nc:r=tv:npl={npl},format=yuv420p10le')


COLOR_TAGS = ['-color_primaries', 'bt2020', '-color_trc', 'arib-std-b67', '-colorspace', 'bt2020nc', '-color_range', 'tv']


def encoders():
    gpu = ['-c:v', 'hevc_nvenc', '-preset', 'p6', '-tune', 'hq', '-profile:v', 'main10', '-pix_fmt', 'p010le', '-rc', 'vbr',
           '-b:v', '25M', '-maxrate', '35M', '-bufsize', '50M', '-bf', '0', *COLOR_TAGS]
    cpu = ['-c:v', 'libx265', '-preset', 'faster', '-pix_fmt', 'yuv420p10le', '-b:v', '25M', '-x265-params',
           'bframes=0:vbv-maxrate=35000:vbv-bufsize=50000:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:repeat-headers=1:log-level=error', *COLOR_TAGS]
    return gpu, cpu


def _ffmpeg(args, timeout=3600):
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', *map(str, args)], check=True, timeout=timeout)


def _preview(source, result, W, H, at, root):
    """Two small JPEGs of the same zoomed-in spot: the source simply enlarged, and the result
    (shown in normal colors so any screen can compare the detail)."""
    import base64
    side = min(480, W, H); x = (W-side)//2; y = (H-side)//2
    before, after = Path(root)/'before.jpg', Path(root)/'after.jpg'
    _ffmpeg(['-ss', f'{at:.2f}', '-i', source, '-frames:v', '1', '-vf', f'scale={W}:{H}:flags=bilinear,crop={side}:{side}:{x}:{y}', '-q:v', '4', before], 120)
    _ffmpeg(['-ss', f'{at:.2f}', '-i', result, '-frames:v', '1', '-vf',
             f'zscale=tin=arib-std-b67:min=bt2020nc:pin=bt2020:rin=tv:t=bt709:m=bt709:p=bt709:r=tv:npl=203,format=yuv420p,crop={side}:{side}:{x}:{y}', '-q:v', '4', after], 120)
    data = {k: 'data:image/jpeg;base64,' + base64.b64encode(p.read_bytes()).decode() for k, p in (('before', before), ('after', after)) if p.is_file() and p.stat().st_size < 400000}
    if len(data) == 2:
        (Path(root)/'preview.json').write_text(json.dumps(data))


def make_tiktok(source, cfg, root, report):
    import time
    from madar_colab_runtime import nvenc_ready
    root = Path(root); work = root/'hdr'; work.mkdir(exist_ok=True)
    w, h, fps, transfer, duration = _probe(source)
    W, H = target_size(w, h); rate = output_rate(fps); npl = LOOKS.get(cfg.get('look'), 203)
    report('processing', f'نكبّر إلى {W}×{H} ونحوّل لـ HDR (HLG 10-bit) · {eval_rate(rate):.0f} إطار')
    vf = video_filter(transfer, W, H, npl)
    gpu, cpu = encoders(); base = work/'bl.hevc'
    began = time.monotonic()
    common = ['-i', source, '-map', '0:v:0', '-vf', vf, '-vsync', 'cfr', '-r', rate, '-an', '-sn', '-dn', '-map_metadata', '-1']
    try:
        if not nvenc_ready():
            raise RuntimeError('no nvenc')
        _ffmpeg([*common, *gpu, '-f', 'hevc', base])
        how = 'GPU · NVENC'
    except (RuntimeError, subprocess.CalledProcessError):
        report('processing', 'ترميز HEVC على المعالج (CPU)؛ أبطأ من GPU')
        _ffmpeg([*common, *cpu, '-f', 'hevc', base])
        how = 'CPU · x265'
    report('processing', f'خلص الترميز ({how}) في {time.monotonic()-began:.0f} ث؛ نضيف Dolby Vision')
    mux = work/'mux.mp4'; out = root/'result.mp4'
    def mux_from(video):
        _ffmpeg(['-r', rate, '-i', video, '-i', source, '-map', '0:v:0', '-map', '1:a:0?', '-c:v', 'copy', '-tag:v', 'hvc1',
                 '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-map_metadata', '-1', mux], 900)
    try:
        tool = dovi_tool(Path(__file__).parent/'cache/dovi')
        frames = int(subprocess.check_output(['ffprobe', '-v', 'error', '-count_packets', '-select_streams', 'v:0',
                     '-show_entries', 'stream=nb_read_packets', '-of', 'csv=p=0', str(base)], timeout=600).decode().strip())
        rpu = generate_rpu(tool, frames, work)
        injected = work/'dv.hevc'
        subprocess.run([str(tool), 'inject-rpu', '-i', str(base), '--rpu-in', str(rpu), '-o', str(injected)], check=True, capture_output=True, timeout=900)
        mux_from(injected)
        add_dolby_vision(mux, out, dv_level(W, H, eval_rate(rate)))
        report('processing', 'جاهز: HEVC 10-bit · HLG · Dolby Vision 8.4')
    except Exception as exc:
        report('processing', f'تعذر Dolby Vision ({type(exc).__name__})؛ الناتج HDR HLG بدونه')
        mux_from(base)
        _ffmpeg(['-i', mux, '-c', 'copy', '-movflags', '+faststart', out], 600)
    try:
        _preview(source, out, W, H, min(max(duration/2, 0), max(duration-0.5, 0)), root)
    except Exception:
        pass
    shutil.rmtree(work, ignore_errors=True)
    return out
