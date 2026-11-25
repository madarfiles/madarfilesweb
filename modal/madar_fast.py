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

SITE = 'https://madarfiles.netlify.app'
MODEL = 'UVR-MDX-NET-Voc_FT.onnx'  # same model as the Colab tool, so results match
MODELS = '/models'
MAX_BYTES = 150 * 1024 * 1024
MAX_SECONDS = 60 * 60
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
    """Bakes the model file into the image so a cold container never downloads it."""
    from audio_separator.separator import Separator
    try:
        Separator(model_file_dir=MODELS, output_dir='/tmp').load_model(model_filename=MODEL)
    except Exception as error:  # no GPU while building; only the downloaded file matters
        print('model load on the build machine:', error)
    if not any(Path(MODELS).glob(MODEL)):
        raise RuntimeError('model file was not downloaded')


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


@app.cls(image=gpu_image, gpu=['L4', 'A10G', 'T4'], timeout=1800, scaledown_window=60, max_containers=2)
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
            if seconds > MAX_SECONDS:
                raise ValueError('TOO_LONG')
            raw = work / 'in.wav'
            _ffmpeg('-i', source, '-map', '0:a:0', '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', raw)
            for old in self.out_dir.iterdir():
                old.unlink(missing_ok=True)
            names = self.separator.separate(str(raw), custom_output_names={'Vocals': 'voice'})
            if not names:
                raise RuntimeError('NO_OUTPUT')
            voice = Path(names[0])
            if not voice.is_absolute():
                voice = self.out_dir / voice
            args, _ = OUT[out]
            result = work / 'result.bin'
            _ffmpeg('-i', voice, '-map_metadata', '-1', *args, result)
            voice.unlink(missing_ok=True)
            return result.read_bytes()
        finally:
            shutil.rmtree(work, ignore_errors=True)


@app.function(image=web_image, timeout=300, max_containers=1)
@modal.concurrent(max_inputs=40)
@modal.asgi_app(label='madar-fast')
def web():
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response

    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    api.add_middleware(CORSMiddleware, allow_origins=[SITE], allow_methods=['GET', 'POST'], allow_headers=['Content-Type', 'X-Madar-Ticket', 'X-Madar-Ext', 'X-Madar-Out'], max_age=600)
    not_ready = tuple(e for e in (TimeoutError, getattr(modal.exception, 'TimeoutError', None)) if e)

    def refuse(code, status):
        return JSONResponse({'error': code}, status_code=status)

    @api.get('/health')
    async def health():
        return {'ok': True, 'model': MODEL}

    @api.post('/submit')
    async def submit(request: Request):
        ticket = request.headers.get('x-madar-ticket', '')
        ext = request.headers.get('x-madar-ext', '').lower()
        out = request.headers.get('x-madar-out', 'm4a').lower()
        if not re.fullmatch(r'[a-f0-9]{48}', ticket) or ext not in IN_EXTS or out not in OUT:
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
        call = await MusicRemover().run.spawn.aio(body, ext, out)
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
