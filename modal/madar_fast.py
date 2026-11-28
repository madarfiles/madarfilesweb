"""Madar fast lane on Modal: music removal on a dedicated GPU, no Google account needed.

The site (Netlify) hands out one-use tickets with per-visitor and per-day limits; this app
redeems each ticket with the site before doing any GPU work, so nobody can spend the
account's credit by calling it directly. Files live only in the container's temp folder
and are deleted right after the job; nothing is stored.
Deployed by .github/workflows/modal.yml with the account token kept in GitHub Secrets.
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import modal

SITE = 'https://madarfiles.netlify.app'  # server-to-server ticket checks (works under any domain)
ORIGINS = ['https://madarfiles.com', 'https://www.madarfiles.com', 'https://madarfiles.netlify.app']
MODEL = 'UVR-MDX-NET-Voc_FT.onnx'  # same model as the Colab tool, so results match
# The visitor's optional precise model: BS-RoFormer (viperx, SDR 12.97 on vocals). Much better on
# instruments the fast model keeps (wind, flutes, keyboards), slower, so it has a shorter limit.
STRONG = 'model_bs_roformer_ep_317_sdr_12.9755.ckpt'
STRONG_MAX_SECONDS = 15 * 60  # longer clips go to Colab (the site sends them there directly)
# Measured on an L4 with 5 minutes of audio: overlap 2 → 84 s, overlap 4 → 129 s, 1.7 GB of GPU
# memory. Overlap 2 with half precision keeps it about twice the fast model's time.
MDXC_PARAMS = {'segment_size': 256, 'override_model_segment_size': False, 'batch_size': 1, 'overlap': 2, 'pitch_shift': 0}
STRONG_EXTRA = {'use_autocast': True}
MODELS = '/models'
MAX_BYTES = 150 * 1024 * 1024
MAX_SECONDS = 15 * 60  # longer clips go to Colab (the site sends them there directly)
IN_EXTS = {'mkv', 'mka', 'mp4', 'm4a', 'mov', 'webm', 'mp3', 'aac', 'wav', 'flac', 'ogg', 'opus', 'm4b', 'aiff', 'aif', 'wma', 'amr', 'ac3', 'eac3', 'mp2', 'alac'}
OUT = {
    'm4a': (['-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-f', 'mp4'], 'audio/mp4'),
    'mp3': (['-c:a', 'libmp3lame', '-b:a', '192k', '-f', 'mp3'], 'audio/mpeg'),
    'wav': (['-c:a', 'pcm_s16le', '-f', 'wav'], 'audio/wav'),
    'flac': (['-c:a', 'flac', '-f', 'flac'], 'audio/flac'),
    'ogg': (['-c:a', 'libvorbis', '-q:a', '5', '-f', 'ogg'], 'audio/ogg'),
    'opus': (['-c:a', 'libopus', '-b:a', '128k', '-f', 'ogg'], 'audio/ogg'),
    'aac': (['-c:a', 'aac', '-b:a', '192k', '-f', 'adts'], 'audio/aac'),
}

app = modal.App('madar-fast')
# Which calls have actually started on a GPU (a call waiting for a free card is 'queued').
started = modal.Dict.from_name('madar-fast-started', create_if_missing=True)


def _fetch_model():
    """Bakes both model files into the image so a cold container never downloads them."""
    from audio_separator.separator import Separator
    for name in (MODEL, STRONG):
        try:
            Separator(model_file_dir=MODELS, output_dir='/tmp').load_model(model_filename=name)
        except Exception as error:  # no GPU while building; only the downloaded file matters
            print('model load on the build machine:', name, error)
        if not any(Path(MODELS).glob(name)):
            raise RuntimeError('model file was not downloaded: ' + name)


gpu_image = (
    modal.Image.debian_slim(python_version='3.11')
    .apt_install('ffmpeg')
    .pip_install('audio-separator[gpu]==0.48.0', 'onnxruntime-gpu[cuda,cudnn]==1.23.2', 'numpy==2.2.6', 'numba==0.61.2', 'nvidia-cublas-cu12>=12,<13')
    .run_function(_fetch_model)
)
web_image = modal.Image.debian_slim(python_version='3.11').pip_install('fastapi[standard]==0.115.12', 'httpx==0.28.1')


def _ffmpeg(*args):
    run = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', *map(str, args)], capture_output=True, text=True, timeout=900)
    if run.returncode:
        raise RuntimeError('ffmpeg: ' + run.stderr.strip()[-300:])


def _seconds(path):
    run = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)], capture_output=True, text=True, timeout=60)
    try:
        return float(run.stdout.strip())
    except ValueError:
        return 0.0


def _separate(separator, out_dir, data, ext, out, max_seconds):
    if ext not in IN_EXTS or out not in OUT:
        raise ValueError('BAD_FORMAT')
    try:
        started.put(modal.current_function_call_id(), True)
    except Exception:
        pass
    work = Path(tempfile.mkdtemp(prefix='madar-'))
    try:
        source = work / ('in.' + ext)
        source.write_bytes(data)
        seconds = _seconds(source)
        if seconds > max_seconds:
            raise ValueError('TOO_LONG')
        raw = work / 'in.wav'
        _ffmpeg('-i', source, '-map', '0:a:0', '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', raw)
        for old in out_dir.iterdir():
            old.unlink(missing_ok=True)
        names = separator.separate(str(raw), custom_output_names={'Vocals': 'voice'})
        if not names:
            raise RuntimeError('NO_OUTPUT')
        voice = Path(names[0])
        if not voice.is_absolute():
            voice = out_dir / voice
        args, _ = OUT[out]
        result = work / 'result.bin'
        _ffmpeg('-i', voice, '-map_metadata', '-1', *args, result)
        voice.unlink(missing_ok=True)
        return result.read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)


# Cards in order of value for this work (L4, then the cheaper T4, then A10G); an idle card is let
# go after 15 s, since Modal bills the time a card waits for the next job too.
@app.cls(image=gpu_image, gpu=['L4', 'T4', 'A10G'], timeout=1800, scaledown_window=15, max_containers=2)
class MusicRemover:
    @modal.enter()
    def load(self):
        import logging
        import onnxruntime as ort
        if hasattr(ort, 'preload_dlls'):
            ort.preload_dlls(directory='')
        from audio_separator.separator import Separator
        self.out_dir = Path('/tmp/madar-out')
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.separator = Separator(output_dir=str(self.out_dir), model_file_dir=MODELS, output_format='WAV', output_single_stem='Vocals', use_soundfile=True,
                                   log_level=logging.WARNING, mdx_params={'hop_length': 1024, 'segment_size': 256, 'overlap': 0.25, 'batch_size': 1, 'enable_denoise': False})
        self.separator.load_model(model_filename=MODEL)

    @modal.method()
    def run(self, data: bytes, ext: str, out: str) -> bytes:
        return _separate(self.separator, self.out_dir, data, ext, out, MAX_SECONDS)


@app.cls(image=gpu_image, gpu=['L4', 'T4', 'A10G'], timeout=1800, scaledown_window=15, max_containers=2)
class PreciseRemover:
    @modal.enter()
    def load(self):
        import logging
        from audio_separator.separator import Separator
        self.out_dir = Path('/tmp/madar-out-precise')
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.separator = Separator(output_dir=str(self.out_dir), model_file_dir=MODELS, output_format='WAV', output_single_stem='Vocals', use_soundfile=True,
                                   log_level=logging.WARNING, mdxc_params=MDXC_PARAMS, **STRONG_EXTRA)
        self.separator.load_model(model_filename=STRONG)

    @modal.method()
    def run(self, data: bytes, ext: str, out: str) -> bytes:
        return _separate(self.separator, self.out_dir, data, ext, out, STRONG_MAX_SECONDS)


@app.function(image=web_image, timeout=300, max_containers=1)
@modal.concurrent(max_inputs=40)
@modal.asgi_app(label='madar-fast')
def web():
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response

    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    api.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=['GET', 'POST'], allow_headers=['Content-Type', 'X-Madar-Ticket', 'X-Madar-Ext', 'X-Madar-Out', 'X-Madar-Model'], max_age=600)
    not_ready = tuple(e for e in (TimeoutError, getattr(modal.exception, 'TimeoutError', None)) if e)

    def refuse(code, status):
        return JSONResponse({'error': code}, status_code=status)

    @api.get('/health')
    async def health():
        return {'ok': True, 'model': MODEL, 'precise': STRONG}

    @api.post('/submit')
    async def submit(request: Request):
        ticket = request.headers.get('x-madar-ticket', '')
        ext = request.headers.get('x-madar-ext', '').lower()
        out = request.headers.get('x-madar-out', 'm4a').lower()
        model = request.headers.get('x-madar-model', 'fast').lower()
        if not re.fullmatch(r'[a-f0-9]{48}', ticket) or ext not in IN_EXTS or out not in OUT or model not in ('fast', 'precise'):
            return refuse('BAD_REQUEST', 400)
        if int(request.headers.get('content-length') or 0) > MAX_BYTES:
            return refuse('TOO_LARGE', 413)
        body = await request.body()
        if not body or len(body) > MAX_BYTES:
            return refuse('TOO_LARGE' if body else 'EMPTY', 413 if body else 400)
        # The site decides who may use the GPU; an unknown, used or expired ticket stops here.
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                check = await client.post(SITE + '/api/fast/redeem', json={'ticket': ticket})
            allowed = check.status_code == 200 and check.json().get('ok') is True
        except Exception:
            allowed = False
        if not allowed:
            return refuse('TICKET', 403)
        worker = PreciseRemover() if model == 'precise' else MusicRemover()
        call = await worker.run.spawn.aio(body, ext, out)
        return {'id': call.object_id}

    @api.get('/result/{call_id}')
    async def result(call_id: str, out: str = 'm4a'):
        if not re.fullmatch(r'fc-[A-Za-z0-9]{10,40}', call_id) or out not in OUT:
            return refuse('BAD_REQUEST', 400)
        try:
            data = await modal.FunctionCall.from_id(call_id).get.aio(timeout=0)
        except not_ready:
            try:
                on_gpu = await started.get.aio(call_id)
            except Exception:
                on_gpu = True
            return {'state': 'running' if on_gpu else 'queued'}
        except Exception as error:
            text = str(error)
            code = next((c for c in ('TOO_LONG', 'BAD_FORMAT') if c in text), 'FAILED')
            return JSONResponse({'state': 'error', 'error': code}, status_code=500)
        return Response(data, media_type=OUT[out][1], headers={'Cache-Control': 'no-store'})

    @api.post('/cancel/{call_id}')
    async def cancel(call_id: str):
        # The page gives up on a call still waiting for a card; it must not start later and spend credit.
        if not re.fullmatch(r'fc-[A-Za-z0-9]{10,40}', call_id):
            return refuse('BAD_REQUEST', 400)
        try:
            await modal.FunctionCall.from_id(call_id).cancel.aio()
        except Exception:
            pass
        return {'ok': True}

    return api
