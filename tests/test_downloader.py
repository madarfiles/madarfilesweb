import importlib.util, socket, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('madar_download',Path(__file__).parents[1]/'colab/madar_download.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class DownloadSecurity(unittest.TestCase):
 def test_initial_urls(self):
  self.assertEqual(m.public_url('https://youtu.be/dQw4w9WgXc'),'https://youtu.be/dQw4w9WgXc')
  for u in ['http://youtu.be/x','https://evil.test/x','https://secret@youtube.com/watch?v=x','https://youtube.com:444/watch?v=x','file:///etc/passwd']:
   with self.assertRaises(ValueError):m.public_url(u)
 def test_redirect_dns_cannot_target_local_private_or_metadata_addresses(self):
  for address in ['127.0.0.1','10.0.0.1','169.254.169.254','192.168.1.1','::1','fc00::1']:
   with self.assertRaises(ValueError):m.public_dns(lambda *a:[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))])('cdn.test',443)
  rows=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
  self.assertEqual(m.public_dns(lambda *a:rows)('cdn.test',443),rows)
 def test_verification_is_not_reported_as_private_content_or_gpu_failure(self):
  message=m.download_error(RuntimeError("Sign in to confirm you're not a bot"))
  self.assertIn('PLATFORM_VERIFICATION',message);self.assertNotIn('LOGIN_REQUIRED',message);self.assertNotIn('GPU',message)
  self.assertIn('LOGIN_REQUIRED',m.download_error(RuntimeError('Private video; login required')))
  self.assertIn('JS_CHALLENGE',m.download_error(RuntimeError('JavaScript challenge solver unavailable')))

class DownloadRetries(unittest.TestCase):
 def run_with(self,behaviour,url='https://www.youtube.com/watch?v=abc'):
  import sys,types,tempfile,subprocess
  calls=[]
  class FakeYDL:
   def __init__(self,opts):self.opts=opts;calls.append(opts)
   def __enter__(self):return self
   def __exit__(self,*a):return False
   def extract_info(self,u,download=False):
    outcome=behaviour(len(calls))
    if isinstance(outcome,Exception):raise outcome
    return {'title':'مقطع: تجربة/1','ext':'mp4'}
   def process_ie_result(self,info,download=True):
    Path(self.opts['outtmpl'].replace('%(ext)s','mp4')).write_bytes(b'x'*10)
  sys.modules['yt_dlp']=types.SimpleNamespace(YoutubeDL=FakeYDL)
  runtime=types.ModuleType('madar_colab_runtime');runtime.prepare_mp4=lambda s,t,r:(Path(t).write_bytes(Path(s).read_bytes()),Path(t))[1];sys.modules['madar_colab_runtime']=runtime
  m._READY=True;m.javascript_runtime=lambda root,report:'/usr/bin/node';m.time.sleep=lambda s:None
  root=Path(tempfile.mkdtemp());notes=[]
  try:out=m.download_clip({'url':url},root,lambda s,t:notes.append(t));return out,calls,notes,root
  finally:sys.modules.pop('yt_dlp',None);sys.modules.pop('madar_colab_runtime',None)
 def test_bot_check_retries_with_another_client_and_keeps_title(self):
  out,calls,notes,root=self.run_with(lambda n:RuntimeError("Sign in to confirm you're not a bot") if n==1 else None)
  self.assertTrue(out.is_file());self.assertEqual(len(calls),2)
  self.assertIn('player_client',str(calls[1].get('extractor_args')))
  import json;self.assertEqual(json.loads((root/'meta.json').read_text())['title'],'مقطع  تجربة 1')
 def test_login_required_does_not_retry(self):
  with self.assertRaises(ValueError) as e:self.run_with(lambda n:RuntimeError('Private video; login required'))
  self.assertIn('LOGIN_REQUIRED',str(e.exception))
 def test_gives_up_after_all_ways(self):
  with self.assertRaises(ValueError) as e:self.run_with(lambda n:RuntimeError('HTTP Error 403: Forbidden'),'https://www.tiktok.com/@a/video/1')
  self.assertIn('PLATFORM_NETWORK',str(e.exception))
