"""One-off benchmark (not deployed): speed of the strong separation model on Modal GPUs."""
import modal

STRONG = 'model_bs_roformer_ep_317_sdr_12.9755.ckpt'
app = modal.App('madar-bench')


def _fetch():
    from audio_separator.separator import Separator
    try:
        Separator(model_file_dir='/models', output_dir='/tmp').load_model(model_filename=STRONG)
    except Exception as e:
        print('build load:', e)


image = (modal.Image.debian_slim(python_version='3.11').apt_install('ffmpeg')
         .pip_install('audio-separator[gpu]==0.48.0', 'onnxruntime-gpu[cuda,cudnn]==1.23.2', 'numpy==2.2.6', 'numba==0.61.2', 'nvidia-cublas-cu12>=12,<13')
         .run_function(_fetch))


@app.function(image=image, gpu='L4', timeout=1500)
def bench(data: bytes):
    import inspect, logging, time, subprocess, torch
    from pathlib import Path
    from audio_separator.separator import Separator
    print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))
    print('Separator params:', list(inspect.signature(Separator.__init__).parameters))
    Path('/tmp/in.m4a').write_bytes(data)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', '/tmp/in.m4a', '-ac', '2', '-ar', '44100', '/tmp/in.wav'], check=True)
    out = []
    for overlap in (2, 4):
        kw = dict(output_dir='/tmp/o', model_file_dir='/models', output_format='WAV', output_single_stem='Vocals', use_soundfile=True, log_level=logging.WARNING,
                  mdxc_params={'segment_size': 256, 'override_model_segment_size': False, 'batch_size': 1, 'overlap': overlap, 'pitch_shift': 0})
        if 'use_autocast' in inspect.signature(Separator.__init__).parameters:
            kw['use_autocast'] = True
        t = time.time(); s = Separator(**kw); s.load_model(model_filename=STRONG); load = time.time() - t
        t = time.time(); names = s.separate('/tmp/in.wav'); run = time.time() - t
        print(f'overlap={overlap} load={load:.1f}s run={run:.1f}s names={names} mem={torch.cuda.max_memory_allocated()/1e9:.1f}GB')
        out.append((overlap, load, run))
    return out


@app.local_entrypoint()
def main(path: str):
    print(bench.remote(open(path, 'rb').read()))
