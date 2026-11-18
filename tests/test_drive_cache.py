import importlib.util,io,json,sys,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1]
def load(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'colab'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class FakeDrive:
 """Just enough of the Drive v3 API: list by name in appDataFolder, download, resumable upload."""
 def __init__(self):self.files={};self.uploads={};self.calls=[]
 def module(self):
  drive=self
  class Resp:
   def __init__(s,status,data=None,body=b'',headers=None):s.status_code=status;s._data=data;s._body=body;s.headers=headers or {}
   def json(s):return s._data
   def iter_content(s,n):
    for i in range(0,len(s._body),n):yield s._body[i:i+n]
   def __enter__(s):return s
   def __exit__(s,*a):return False
  def get(url,params=None,headers=None,stream=False,timeout=None):
   drive.calls.append(('GET',url));assert headers['Authorization']=='Bearer tok'
   if params and params.get('alt')=='media':return Resp(200,body=drive.files[url.rsplit('/',1)[1]]['body'])
   name=params['q'].split("'")[1];return Resp(200,{'files':[{'id':i,'size':str(len(f['body'])),'appProperties':f['props']} for i,f in drive.files.items() if f['name']==name]})
  def post(url,params=None,json=None,headers=None,timeout=None):
   drive.calls.append(('POST',url));key='u%d'%len(drive.uploads);drive.uploads[key]=json;return Resp(200,headers={'Location':'https://www.googleapis.com/upload/drive/v3/files?upload_id='+key})
  def put(url,data=None,headers=None,timeout=None):
   key=url.split('=')[-1];meta=drive.uploads[key];drive.files['f%d'%len(drive.files)]={'name':meta['name'],'props':meta.get('appProperties',{}),'body':data.read()};return Resp(200,{})
  def delete(url,headers=None,timeout=None):drive.calls.append(('DELETE',url));drive.files.pop(url.rsplit('/',1)[1],None);return Resp(204)
  def put2(url,data=None,headers=None,timeout=None):
   r=put(url,data,headers,timeout);r._data={'id':list(drive.files)[-1]};return r
  return types.SimpleNamespace(get=get,post=post,put=put2,delete=delete,RequestException=Exception)

class DriveCache(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
  sys.path.insert(0,str(ROOT/'colab'))
  self.m=load('drive_cache_test','madar_drive_cache.py')
  self.m.BASE=base;self.m.KEY=base/'google.json';self.m.CACHE=base/'models';self.m.LOCKS=base/'locks'
  self.hub=base/'hf'/'hub';self.parts=[('uvr-x',self.m.CACHE/'x.onnx'),('hf-org--m',self.hub/'models--org--m')]
  self.m.parts=lambda task:self.parts if task=='dub' else []
  self.drive=FakeDrive()
 def tearDown(self):self.tmp.cleanup()
 def key(self,drive=True,expires=None):self.m.KEY.write_text(json.dumps({'token':'tok','expires':expires or time.time()+3000,'drive':drive}))
 def make_models(self):
  self.m.CACHE.mkdir(parents=True);(self.m.CACHE/'x.onnx').write_bytes(b'weights'*1000)
  snap=self.hub/'models--org--m'/'snapshots'/'abc';snap.mkdir(parents=True);(snap/'model.bin').write_bytes(b'w'*5000);(self.hub/'models--org--m'/'refs').mkdir();(self.hub/'models--org--m'/'refs'/'main').write_text('abc')
 def test_models_go_to_drive_once_and_come_back_on_a_new_machine(self):
  self.key();self.make_models()
  with patch.dict(sys.modules,{'requests':self.drive.module()}):
   self.assertEqual(self.m.save('dub'),['uvr-x','hf-org--m'])
   self.assertEqual(self.m.save('dub'),[],'already saved: no second upload')
   import shutil;shutil.rmtree(self.m.CACHE);shutil.rmtree(self.hub);shutil.rmtree(self.m.LOCKS)
   self.assertEqual(self.m.restore('dub'),['uvr-x','hf-org--m'])
  self.assertEqual((self.m.CACHE/'x.onnx').read_bytes(),b'weights'*1000)
  self.assertEqual((self.hub/'models--org--m'/'snapshots'/'abc'/'model.bin').read_bytes(),b'w'*5000)
  with patch.dict(sys.modules,{'requests':self.drive.module()}):self.assertEqual(self.m.save('dub'),[],'models that came from Drive are not uploaded again')
 def test_a_damaged_copy_in_drive_is_ignored_and_nothing_is_written(self):
  self.key();self.make_models()
  with patch.dict(sys.modules,{'requests':self.drive.module()}):
   self.m.save('dub')
   for f in self.drive.files.values():f['body']=f['body'][:-1]+b'!'
   import shutil;shutil.rmtree(self.m.CACHE);shutil.rmtree(self.hub);shutil.rmtree(self.m.LOCKS)
   self.assertEqual(self.m.restore('dub'),[])
  self.assertFalse((self.m.CACHE/'x.onnx').exists());self.assertFalse((self.hub/'models--org--m').exists())
 def test_without_drive_permission_or_with_an_old_token_nothing_is_tried(self):
  self.make_models()
  with patch.dict(sys.modules,{'requests':self.drive.module()}):
   self.assertEqual(self.m.restore('dub'),[]);self.key(drive=False);self.assertEqual(self.m.save('dub'),[]);self.key(expires=time.time()+30);self.assertEqual(self.m.save('dub'),[])
  self.assertEqual(self.drive.calls,[])
 def test_unfinished_downloads_are_never_saved(self):
  self.key();self.make_models();(self.hub/'models--org--m'/'blobs').mkdir();(self.hub/'models--org--m'/'blobs'/'x.incomplete').write_bytes(b'1')
  with patch.dict(sys.modules,{'requests':self.drive.module()}):self.assertEqual(self.m.save('dub'),['uvr-x'])
 def test_every_tool_lists_its_models(self):
  m=load('drive_cache_parts','madar_drive_cache.py')
  names={t:[n for n,_ in m.parts(t)] for t in ['separate','dub','asr','translate','ocr']}
  self.assertEqual(names['separate'],['uvr-UVR-MDX-NET-Voc_FT.onnx']);self.assertIn('hf-mobiuslabsgmbh--faster-whisper-large-v3-turbo',names['dub']);self.assertIn('titanet-large',names['dub']);self.assertEqual(names['ocr'],[])
class DriveTransfer(DriveCache):
 def test_the_uploaded_file_comes_from_drive_with_the_pages_part_hashes_and_is_then_deleted(self):
  import hashlib
  self.key();data=bytes(range(256))*20000;PART=2*1048576
  digest=hashlib.sha256();[digest.update(hashlib.sha256(data[i:i+PART]).digest()) for i in range(0,len(data),PART)]
  self.drive.files['FILEID12345']={'name':'madar-io-in-x','props':{},'body':data}
  dest=Path(self.tmp.name)/'source.mp4'
  with patch.dict(sys.modules,{'requests':self.drive.module()}):size,got=self.m.fetch_input('FILEID12345',dest,PART,3)
  self.assertEqual((size,got),(len(data),digest.hexdigest()));self.assertEqual(dest.read_bytes(),data);self.assertNotIn('FILEID12345',self.drive.files,'deleted from Drive after use')
  with self.assertRaises(ValueError),patch.dict(sys.modules,{'requests':self.drive.module()}):self.m.fetch_input('bad id!',dest,PART,3)
 def test_the_result_goes_to_drive_for_a_direct_download(self):
  self.key();out=Path(self.tmp.name)/'result.m4a';out.write_bytes(b'r'*5000)
  with patch.dict(sys.modules,{'requests':self.drive.module()}):file_id=self.m.put_output(out,'job1')
  self.assertEqual(self.drive.files[file_id]['body'],b'r'*5000);self.assertEqual(self.drive.files[file_id]['name'],'madar-io-out-job1')
  self.m.KEY.unlink()
  with patch.dict(sys.modules,{'requests':self.drive.module()}):self.assertIsNone(self.m.put_output(out,'job2'),'no Drive permission: the site path is used')
if __name__=='__main__':unittest.main()
