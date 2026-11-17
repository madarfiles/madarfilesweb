import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).parents[1]/'colab'
spec=importlib.util.spec_from_file_location('resize19',BASE/'madar_cloud_tasks.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
import madar_colab_runtime as runtime
class Resize19(unittest.TestCase):
 def test_stretch_exports_real_mp4_in_both_directions(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.mp4'
   
   for ratio,expected,size in [('portrait',(720,1280),'320x180'),('landscape',(1280,720),'180x320')]:
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'testsrc2=size={size}:rate=2:duration=0.5','-c:v','libx264','-y',str(source)],check=True)
    for amount in ['0','50','100']:
     with self.subTest(ratio=ratio,amount=amount),patch.object(m,'install'),patch.object(runtime,'video_encoder',return_value=['-c:v','libx264','-preset','ultrafast']),patch.object(runtime,'nvenc_explanation',return_value='test'):
      out=m.process('resize',source,{'ratio':ratio,'fit':'stretch','stretch':amount},root,lambda *a:None)
      info=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,sample_aspect_ratio','-of','json',str(out)]))['streams'][0]
      self.assertEqual((info['width'],info['height']),expected);self.assertEqual(info['sample_aspect_ratio'],'1:1');self.assertGreater(out.stat().st_size,1000)
