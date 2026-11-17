import importlib.util,json,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1]
def load(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'colab'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
rt=load('warm_runtime','madar_colab_runtime.py')
class InstallOnce(unittest.TestCase):
 def test_early_preparation_and_the_job_share_one_install(self):
  with tempfile.TemporaryDirectory() as d:
   calls=[]
   def run(cmd,**k):calls.append(cmd[3:]);time.sleep(0.2)
   with patch.object(rt,'SETUP_DIR',Path(d)),patch.object(rt.subprocess,'run',side_effect=run):
    results=[]
    threads=[threading.Thread(target=lambda:results.append(rt.install_once('separation',[['install','x==1']]))) for _ in range(2)]
    for t in threads:t.start()
    for t in threads:t.join()
    self.assertEqual(sorted(results),[False,True]);self.assertEqual(calls,[['install','x==1']],'the second waited and skipped')
    self.assertTrue(rt.install_once('separation',[['install','x==2']]),'changed pins install again')
 def test_a_failed_install_leaves_no_marker_so_the_job_tries_again(self):
  with tempfile.TemporaryDirectory() as d:
   with patch.object(rt,'SETUP_DIR',Path(d)),patch.object(rt.subprocess,'run',side_effect=rt.subprocess.CalledProcessError(1,'pip')):
    with self.assertRaises(rt.subprocess.CalledProcessError):rt.install_once('k',[['install','y']])
   self.assertFalse((Path(d)/'k.ok').exists())
class Warm(unittest.TestCase):
 def test_dub_preparation_downloads_every_model_and_survives_failures(self):
  sys.path.insert(0,str(ROOT/'colab'))
  cloud=load('warm_cloud','madar_cloud_tasks.py')
  seen=[]
  fake_rt=type(sys)('madar_colab_runtime');fake_rt.install_once=lambda key,c:seen.append(('pip',key));fake_rt.SEPARATION_PIP=[];fake_rt.MODEL='voc.onnx';fake_rt.DUB_MODEL='inst.onnx';fake_rt.CACHE=Path(tempfile.mkdtemp());fake_rt.VOICEPRINT_PIP=[];fake_rt.voiceprint_model=lambda folder:seen.append(('model',str(folder)))
  hub=type(sys)('huggingface_hub');hub.snapshot_download=lambda repo,revision=None,allow_patterns=None:seen.append(('hub',repo))
  def boom(*a,**k):raise ImportError('no separator here')
  with patch.dict(sys.modules,{'madar_colab_runtime':fake_rt,'huggingface_hub':hub}),patch.object(cloud,'install',side_effect=lambda t,r:seen.append(('task',t))):
   done=cloud.warm('dub')
  self.assertTrue(done[0].startswith('separation'));self.assertTrue(done[1].startswith('whisper'));self.assertTrue(done[2].startswith('voiceprint'),done)
  self.assertIn(('pip','voiceprint'),seen);self.assertIn(('hub','MIT/ast-finetuned-audioset-10-10-0.4593'),seen)
  self.assertEqual(cloud.warm('ocr'),[],'tools without a plan do nothing')
if __name__=='__main__':unittest.main()
