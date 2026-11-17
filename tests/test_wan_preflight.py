import importlib.util,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1]/'colab'
spec=importlib.util.spec_from_file_location('wan_cloud',ROOT/'madar_cloud_tasks.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
spec=importlib.util.spec_from_file_location('wan_job',ROOT/'madar_web_job.py');job=importlib.util.module_from_spec(spec);spec.loader.exec_module(job)
class WanPreflight(unittest.TestCase):
 def test_missing_text_dependency_stops_before_cuda_and_model_download(self):
  self.assertIn('ftfy==6.3.1',m.DEPS['videogen'])
  with tempfile.TemporaryDirectory() as d,patch.object(m,'install'),patch.object(m,'check_video_text_dependencies',side_effect=ValueError('text setup failed')),patch.object(m,'cuda') as cuda,patch.object(m,'load_model') as download:
   with self.assertRaises(ValueError):m.process('videogen',None,{'prompt':'garden','length':'short'},Path(d),lambda *a:None)
   cuda.assert_not_called();download.assert_not_called()
 def test_real_pipeline_preprocessor_is_exercised(self):
  calls=[]
  modules={'ftfy':types.SimpleNamespace(),'diffusers.pipelines.wan.pipeline_wan':types.SimpleNamespace(prompt_clean=lambda text:calls.append(text) or 'Madar & video')}
  with patch.dict(sys.modules,modules):m.check_video_text_dependencies()
  self.assertEqual(calls,['  Madar &amp; video  '])
 def test_safe_nameerror_diagnostics_preserve_undefined_symbol(self):
  try:eval('ftfy_missing_symbol')
  except NameError as exc:code,message,diagnostic=job.failure_details(exc,{'task':'videogen'})
  self.assertEqual(diagnostic['undefinedName'],'ftfy_missing_symbol');self.assertEqual(code,'TOOL_NAMEERROR')
