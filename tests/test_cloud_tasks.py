import importlib.util, json, sys, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=module('cloudtask',ROOT/'colab/madar_cloud_tasks.py');job=module('cloudjob',ROOT/'colab/madar_web_job.py')
class CloudTasks(unittest.TestCase):
 def test_gpu_preflight_rejects_without_cuda(self):
  with patch.dict(sys.modules,{'torch':types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda:False))}):
   with self.assertRaises(ValueError):m.cuda()
 def test_no_file_task_routes_fixed_runner_and_preserves_png_extension(self):
  with tempfile.TemporaryDirectory() as d,patch.object(job,'ROOT',Path(d)):
   p=Path(d);(p/'config.json').write_text(json.dumps({'task':'imagegen','prompt':'garden'}))
   def process(task,source,cfg,root,report):
    self.assertEqual(task,'imagegen');self.assertIsNone(source);out=root/'generated.png';out.write_bytes(b'pngcontent');return out
   with patch.dict(sys.modules,{'madar_cloud_tasks':types.SimpleNamespace(process=process)}):job.main()
   state=json.loads((p/'state.json').read_text());self.assertEqual(state['ext'],'png');self.assertEqual(state['state'],'done');self.assertEqual((p/'output_00000.bin').read_bytes(),b'pngcontent')
 def test_media_calls_ffmpeg_without_shell_and_disallows_network_protocols(self):
  with patch.object(m.subprocess,'run') as run:
   m.run_ffmpeg(['-i','source.mp4','result.mp4']);args=run.call_args.args[0];self.assertEqual(args[args.index('-protocol_whitelist')+1],'file,pipe');self.assertFalse(run.call_args.kwargs.get('shell',False))
 def test_timestamp_carries_milliseconds(self):self.assertEqual(m.timestamp(59.9999),'00:01:00,000')
 def test_cached_model_is_reused_then_evicted_for_another_backend(self):
  m.release_models();loads=[]
  with patch.object(m,'cuda'):
   first=m.cached_model('a',lambda:loads.append('a') or object(),lambda *a:None)
   self.assertIs(first,m.cached_model('a',lambda:loads.append('bad'),lambda *a:None))
   m.cached_model('b',lambda:loads.append('b') or object(),lambda *a:None)
  self.assertEqual(loads,['a','b']);self.assertEqual(list(m._MODELS),['b']);m.release_models()
