import importlib.util, json, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('madar',Path(__file__).parents[1]/'colab'/'madar_colab_runtime.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_long_source_not_subject_to_browser_duration_caps(self):
  plan=m.chunk_plan(1320,0,0)
  self.assertEqual(len(plan),5)
  self.assertEqual(sum(s for _,s in plan),1320)
  self.assertEqual(m.chunk_plan(1320,600,180),[(600,180)])
  self.assertEqual(m.chunk_plan(1320,600,0),[(600,300),(900,300),(1200,120)])
  with self.assertRaises(ValueError):m.chunk_plan(100,101,0)
 def test_cpu_is_not_accepted_as_gpu(self):
  def fake(providers):
   session=types.SimpleNamespace(get_providers=lambda:providers)
   def run(x):return session
   return types.SimpleNamespace(model_instance=types.SimpleNamespace(model_run=run))
  with self.assertRaises(RuntimeError):m.session_from_separator(fake(['CPUExecutionProvider']))
  self.assertIn('CUDAExecutionProvider',m.session_from_separator(fake(['CUDAExecutionProvider','CPUExecutionProvider'])).get_providers())
 def test_interrupted_job_resumes_completed_checked_chunks(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'episode.mkv';source.write_bytes(b'original-private-source')
   calls=[];fail=[True]
   class Separator:
    def __init__(self,work):self.work=work
    def separate(self,path,custom_output_names):
     name=custom_output_names['Vocals'];calls.append(name)
     if name.endswith('00001') and fail[0]:fail[0]=False;raise RuntimeError('interrupted')
     out=self.work/(name+'.wav');out.write_bytes(b'processed-audio');return[out.name]
   def fake_ffmpeg(args):Path(args[-1]).write_bytes(b'encoded-media')
   with patch.object(m,'ROOT',root),patch.object(m,'duration_of',return_value=1320),patch.object(m,'new_separator',side_effect=lambda p:Separator(p)),patch.object(m,'ffmpeg',side_effect=fake_ffmpeg),patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=10*1024**3)):
    with self.assertRaises(RuntimeError):m.run_separation(source)
    output=m.run_separation(source)
    self.assertTrue(output.is_file())
    self.assertEqual(calls.count('voice_00000'),1)
    self.assertEqual(calls.count('voice_00001'),2)
    self.assertEqual(source.read_bytes(),b'original-private-source')
 def test_notebook_cells_compile_and_no_saved_outputs(self):
  nb=json.loads((Path(__file__).parents[1]/'colab'/'Madar_Colab_Separation.ipynb').read_text())
  for cell in nb['cells']:
   if cell['cell_type']=='code':compile(''.join(cell['source']),'notebook','exec');self.assertEqual(cell['outputs'],[])
if __name__=='__main__':unittest.main()
