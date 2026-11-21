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
   name=params['q'].split("'")[1];match=(lambda n:name in n) if ' contains ' in params['q'] else (lambda n:n==name)
   return Resp(200,{'files':[{'id':i,'name':f['name'],'size':str(len(f['body'])),'createdTime':'2026-11-%02d'%(1+int(i[1:])%28),'appProperties':f['props']} for i,f in drive.files.items() if match(f['name'])]})
  def post(url,params=None,json=None,headers=None,timeout=None):
   drive.calls.append(('POST',url));key='u%d'%len(drive.uploads);drive.uploads[key]=json;return Resp(200,headers={'Location':'https://www.googleapis.com/upload/drive/v3/files?upload_id='+key})
  def put(url,data=None,headers=None,timeout=None):
   key=url.split('=')[-1];meta=drive.uploads[key];drive.files['f%d'%len(drive.files)]={'name':meta['name'],'props':meta.get('appProperties',{}),'body':data.read()};return Resp(200,{})
  def delete(url,headers=None,timeout=None):drive.calls.append(('DELETE',url));drive.files.pop(url.rsplit('/',1)[1],None);return Resp(204)
  def patch(url,params=None,json=None,headers=None,timeout=None):
   drive.calls.append(('PATCH',url));f=drive.files.get(url.rsplit('/',1)[1])
   if f is not None:f['props']={**f['props'],**(json or {}).get('appProperties',{})}
   return Resp(200,{})
  def put2(url,data=None,headers=None,timeout=None):
   r=put(url,data,headers,timeout);r._data={'id':list(drive.files)[-1]};return r
  return types.SimpleNamespace(get=get,post=post,put=put2,delete=delete,patch=patch,RequestException=Exception)

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

class LibraryCache(unittest.TestCase):
 """What pip added for a tool is packed into Drive once and unpacked on the next machine."""
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
  self.m=load('drive_libs_test','madar_drive_cache.py')
  self.m.BASE=base;self.m.KEY=base/'google.json';self.m.CACHE=base/'models';self.m.LOCKS=base/'locks'
  self.site=base/'site-packages';self.m._package_dirs=lambda:[self.site];self.drive=FakeDrive()
  self.m.KEY.write_text(json.dumps({'token':'tok','expires':time.time()+3000,'drive':True}))
 def tearDown(self):self.tmp.cleanup()
 def dist(self,name,version,files):
  d=self.site/f'{name}-{version}.dist-info';d.mkdir(parents=True)
  rows=[]
  for rel,body in files.items():
   f=self.site/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(body);rows.append(f'{rel},,')
  rows+= [f'{d.name}/RECORD,,','../../../bin/tool,,'];(d/'RECORD').write_text('\n'.join(rows))
 def fresh(self):
  import shutil;shutil.rmtree(self.site,ignore_errors=True);self.dist('pkg','1',{'pkg/__init__.py':b'v1','pkg/old.py':b'old'})
 def test_pip_result_is_restored_on_a_new_machine(self):
  self.fresh();before=self.m.lib_snapshot()
  import shutil;shutil.rmtree(self.site/'pkg');shutil.rmtree(self.site/'pkg-1.dist-info')
  self.dist('pkg','2',{'pkg/__init__.py':b'v2'});self.dist('extra','5',{'extra/lib.so':b'\x7fELF'*100})
  added,removed=self.m.lib_changes(before)
  self.assertEqual(sorted(d.name for d in added),['extra-5.dist-info','pkg-2.dist-info']);self.assertEqual([Path(r).name for r in removed],['pkg-1.dist-info'])
  with patch.dict(sys.modules,{'requests':self.drive.module()}):
   self.assertTrue(self.m.save_libs('lib-sep-abc-img',added,removed))
   self.fresh()
   got=self.m.restore_libs('lib-sep-abc-img')
  self.assertIsNotNone(got)
  self.assertEqual((self.site/'pkg/__init__.py').read_bytes(),b'v2');self.assertFalse((self.site/'pkg/old.py').exists())
  self.assertFalse((self.site/'pkg-1.dist-info').exists());self.assertTrue((self.site/'extra/lib.so').exists())
 def test_missing_or_other_machine_means_plain_pip(self):
  self.fresh()
  with patch.dict(sys.modules,{'requests':self.drive.module()}):
   self.assertIsNone(self.m.restore_libs('lib-none'))
   before=self.m.lib_snapshot();self.dist('extra','5',{'extra/a.py':b'a'});added,removed=self.m.lib_changes(before)
   self.assertTrue(self.m.save_libs('lib-x-1-img',added,removed))
   self.m._package_dirs=lambda:[Path(self.tmp.name)/'other'/'site-packages']
   self.assertIsNone(self.m.restore_libs('lib-x-1-img'))


class DriveCap(unittest.TestCase):
 """Madar never keeps more than the cap in the visitor's Drive: least recently used goes first."""
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
  self.m=load('drive_cap_test','madar_drive_cache.py');self.m.BASE=base;self.m.KEY=base/'google.json';self.m.CACHE=base/'models';self.m.LOCKS=base/'locks'
  self.drive=FakeDrive();self.req=self.drive.module();self.auth={'Authorization':'Bearer tok'}
 def tearDown(self):self.tmp.cleanup()
 def add(self,id,name,size,used):self.drive.files[id]={'name':name,'props':{'used':str(used)},'body':b'x'*size}
 def test_evicts_least_recently_used_until_it_fits(self):
  self.add('f1','madar-1-old',40,100);self.add('f2','madar-1-mid',30,200);self.add('f3','madar-1-new',20,300);self.add('f4','madar-io-in-x',90,1)
  self.assertTrue(self.m.make_room(25,self.auth,self.req,cap=80))
  self.assertNotIn('f1',self.drive.files);self.assertIn('f2',self.drive.files);self.assertIn('f3',self.drive.files);self.assertIn('f4',self.drive.files)
 def test_file_bigger_than_cap_is_not_stored(self):
  self.add('f1','madar-1-a',10,1)
  self.assertFalse(self.m.make_room(100,self.auth,self.req,cap=80));self.assertIn('f1',self.drive.files)
 def test_restore_marks_use(self):
  self.add('f1','madar-1-a',10,1);self.m._touch('f1',self.auth,self.req)
  self.assertGreater(int(self.drive.files['f1']['props']['used']),1000)
 def test_upload_respects_cap(self):
  self.m.CAP=50;self.add('f1','madar-1-a',40,1)
  p=Path(self.tmp.name)/'model.bin';p.write_bytes(b'y'*30)
  self.assertTrue(self.m._upload('b',p,self.auth,self.req))
  self.assertNotIn('f1',self.drive.files);self.assertTrue(any(f['name']=='madar-1-b' and 'used' in f['props'] for f in self.drive.files.values()))
