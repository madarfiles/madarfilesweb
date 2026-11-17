import hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]/'colab'
class PersistentService(unittest.TestCase):
 def test_real_ffmpeg_jobs_reuse_one_worker_and_error_does_not_poison_next_job(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d)
   for name in ['madar_service.py','madar_web_job.py','madar_cloud_tasks.py','madar_colab_runtime.py','madar_download.py']:
    shutil.copy(ROOT/name,base/({'madar_service.py':'service.py','madar_web_job.py':'runner.py'}.get(name,name)))
   source=base/'input.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x120:d=0.2','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
   data=source.read_bytes();manifest=hashlib.sha256(hashlib.sha256(data).digest()).hexdigest();(base/'jobs').mkdir()
   process=subprocess.Popen([sys.executable,str(base/'service.py'),'serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    def submit(index,broken=False):
     root=base/'jobs'/str(index);root.mkdir();payload=b'bad' if broken else data;(root/'input_00000.bin').write_bytes(payload);cfg={'task':'convert','ext':'mp4','size':len(payload),'chunks':1,'sha256':hashlib.sha256(hashlib.sha256(payload).digest()).hexdigest(),'format':'mp4','quality':'balanced'};(root/'config.json').write_text(json.dumps(cfg));(root/'ready').touch()
     deadline=time.time()+35
     while time.time()<deadline:
      if (root/'state.json').exists():
       state=json.loads((root/'state.json').read_text())
       if state['state'] in ['done','error']:return state
      time.sleep(.1)
     self.fail('job did not complete')
    first=submit(1);self.assertEqual(first['state'],'done');self.assertEqual(first['ext'],'mp4');self.assertTrue(first['chunks'])
    health=json.loads((base/'service.json').read_text());self.assertEqual(health['pid'],process.pid)
    bad=submit(2,True);self.assertEqual(bad['state'],'error')
    again=submit(3);self.assertEqual(again['state'],'done');self.assertIsNone(process.poll())
   finally:process.terminate();process.wait(timeout=5)
 def test_bootstrap_works_without_ensurepip_and_reuses_live_service(self):
  import signal
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);shutil.copy(ROOT/'madar_service.py',base/'service.py');(base/'jobs').mkdir();(base/'venv.py').write_text("raise RuntimeError('ensurepip intentionally unavailable')");pid=None
   try:
    subprocess.run([sys.executable,str(base/'service.py')],check=True,timeout=35)
    deadline=time.time()+10
    while not (base/'service.json').exists() and time.time()<deadline:time.sleep(.1)
    health=json.loads((base/'service.json').read_text());pid=health['pid'];self.assertFalse((base/'.environment').exists())
    subprocess.run([sys.executable,str(base/'service.py')],check=True,timeout=5)
    self.assertEqual(json.loads((base/'service.json').read_text())['pid'],pid);self.assertFalse((base/'.environment').exists())
   finally:
    if pid:
     try:os.kill(pid,signal.SIGTERM)
     except ProcessLookupError:pass

 def test_expired_page_lease_stops_worker(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);shutil.copy(ROOT/'madar_service.py',base/'service.py');(base/'jobs').mkdir();(base/'lease.json').write_text(json.dumps({'updated':time.time()-301}))
   child=subprocess.Popen([sys.executable,str(base/'service.py'),'serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    child.wait(timeout=9);self.assertEqual(json.loads((base/'service.json').read_text())['state'],'page-disconnected')
   finally:
    if child.poll() is None:child.terminate();child.wait(timeout=5)
