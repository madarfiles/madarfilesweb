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
