import importlib.util,subprocess,tempfile,unittest,shutil,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1]
s=importlib.util.spec_from_file_location('dub_runtime',ROOT/'colab'/'madar_colab_runtime.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class DubStems(unittest.TestCase):
 @unittest.skipUnless(shutil.which('ffmpeg'),'system ffmpeg required')
 def test_dub_returns_sample_aligned_voice_and_background_in_one_zip(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.m4a'
   subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','7','-c:a','aac',str(source)],check=True)
   created=[]
   class Separator:
    def __init__(self,work,single_stem='Vocals'):self.work=work;created.append(single_stem)
    def separate(self,path,custom_output_names):
     voice=self.work/(custom_output_names['Vocals']+'.wav');bg=self.work/(custom_output_names['Instrumental']+'.wav')
     shutil.copyfile(path,voice);subprocess.run(['ffmpeg','-v','error','-y','-i',path,'-af','volume=0.1',str(bg)],check=True);return[voice.name,bg.name]
   with patch.object(m,'ROOT',root),patch.object(m,'CHUNK_SECONDS',3),patch.object(m,'new_separator',side_effect=Separator):
    bundle=m.run_dub_stems(source)
   self.assertEqual(created,[None],'both stems requested')
   with zipfile.ZipFile(bundle) as z:
    self.assertEqual(sorted(z.namelist()),['background.m4a','voice.m4a'])
    z.extractall(root/'out')
   for name in ['voice.m4a','background.m4a']:
    self.assertAlmostEqual(m.duration_of(root/'out'/name),7,delta=0.15,msg=name)
 def test_dub_refuses_sources_longer_than_30_minutes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'s.m4a';source.write_bytes(b'x')
   with patch.object(m,'ROOT',root),patch.object(m,'duration_of',return_value=31*60):
    with self.assertRaises(ValueError):m.run_dub_stems(source)
if __name__=='__main__':unittest.main()
