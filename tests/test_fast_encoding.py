import importlib.util, json, subprocess, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('fast_runtime',Path(__file__).parents[1]/'colab/madar_colab_runtime.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class FastEncoding(unittest.TestCase):
 def test_nvenc_requires_successful_real_probe(self):
  m.nvenc_ready.cache_clear()
  with patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(returncode=1)):
   self.assertFalse(m.nvenc_ready());self.assertIn('libx264',m.video_encoder())
  m.nvenc_ready.cache_clear()
  with patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(returncode=0)) as run:
   self.assertTrue(m.nvenc_ready());self.assertIn('h264_nvenc',m.video_encoder());self.assertIn('-frames:v',run.call_args.args[0])
  m.nvenc_ready.cache_clear()
 def test_compatible_video_skips_gpu_probe_and_preserves_bitstream(self):
  with patch.object(m,'compatible_mp4',return_value=(True,True)),patch.object(m,'nvenc_ready') as probe,patch.object(m.subprocess,'run') as run:
   m.prepare_mp4('in.mp4','out.mp4',lambda *a:None)
   args=run.call_args.args[0];self.assertEqual(args[args.index('-c:v')+1],'copy');self.assertEqual(args[args.index('-c:a')+1],'copy');probe.assert_not_called()
 def test_incompatible_video_uses_verified_nvenc(self):
  with patch.object(m,'compatible_mp4',return_value=(False,False)),patch.object(m,'nvenc_ready',return_value=True),patch.object(m.subprocess,'run') as run:
   m.prepare_mp4('in.webm','out.mp4',lambda *a:None)
   self.assertIn('h264_nvenc',run.call_args.args[0]);self.assertIn('aac',run.call_args.args[0])
 def test_gpu_failure_has_safe_cpu_fallback(self):
  calls=[]
  def run(args,**kw):
   calls.append(args)
   if 'h264_nvenc' in args:raise subprocess.CalledProcessError(1,args)
  with patch.object(m,'compatible_mp4',return_value=(False,False)),patch.object(m,'nvenc_ready',return_value=True),patch.object(m.subprocess,'run',side_effect=run):
   m.prepare_mp4('in.webm','out.mp4',lambda *a:None)
  self.assertEqual(len(calls),2);self.assertIn('libx264',calls[1])
 def test_partial_video_gpu_failure_reuses_audio_without_reseparating(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.mkv';source.write_bytes(b'original');separations=[];encoders=[]
   class Separator:
    def __init__(self,work):self.work=work
    def separate(self,path,custom_output_names):
     separations.append(path);p=self.work/'voice.wav';p.write_bytes(b'audio');return [str(p)]
   def ffmpeg(args):
    if str(args[-1]).endswith('result.mkv'):
     encoders.append(args)
     if 'h264_nvenc' in args:raise RuntimeError('GPU failed')
    Path(args[-1]).write_bytes(b'encoded')
   with patch.object(m,'ROOT',root),patch.object(m,'duration_of',return_value=100),patch.object(m,'new_separator',side_effect=lambda work:Separator(work)),patch.object(m,'video_encoder',return_value=['-c:v','h264_nvenc']),patch.object(m,'ffmpeg',side_effect=ffmpeg),patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=10*1024**3)):
    out=m.run_separation(source,start=2,duration=10,mode='video')
   self.assertTrue(out.is_file());self.assertEqual(len(separations),1);self.assertEqual(len(encoders),2);self.assertIn('libx264',encoders[1])
 def test_nvenc_probe_uses_supported_frame_dimensions(self):
  m.nvenc_ready.cache_clear()
  with patch.object(m,'gpu_name',return_value='Tesla T4'),patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(returncode=0)) as run:
   self.assertTrue(m.nvenc_ready());args=run.call_args.args[0];self.assertIn('color=c=black:s=256x256:r=30:d=0.1',args);self.assertNotIn('color=c=black:s=64x64:r=1:d=1',args)
  m.nvenc_ready.cache_clear()
 def test_a100_has_no_hardware_encoder_and_missing_driver_is_distinct(self):
  m.nvenc_ready.cache_clear()
  with patch.object(m,'gpu_name',return_value='NVIDIA A100-SXM4-40GB'),patch.object(m.subprocess,'run') as run:
   self.assertFalse(m.nvenc_ready());self.assertEqual(m.NVENC_DIAGNOSTIC,'HARDWARE_NO_NVENC');run.assert_not_called()
  self.assertEqual(m.nvenc_failure('Cannot load libnvidia-encode.so.1'),'DRIVER_LIBRARY_MISSING');self.assertEqual(m.nvenc_failure('Frame Dimension less than the minimum supported value'),'ENCODER_PROBE_DIMENSIONS');self.assertEqual(m.nvenc_failure('Driver does not support the required nvenc API version'),'DRIVER_API_MISMATCH');m.nvenc_ready.cache_clear()
