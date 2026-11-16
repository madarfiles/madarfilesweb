import base64,hashlib,importlib.util,io,json,shutil,subprocess,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('worker',Path(__file__).parents[1]/'colab/worker.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class WorkerTests(unittest.TestCase):
 def test_chunk_plan_preserves_arbitrary_duration(self):
  self.assertEqual(m.split_plan(1320,600,0),[(600,300),(900,300),(1200,120)])
  self.assertRaises(ValueError,m.split_plan,100,101,0)
 def test_verified_reassembly_reuses_source_and_detects_corruption(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m,'PART',4):
   root=Path(d);blocks=[b'abcd',b'ef'];cfg={'ext':'mp4','size':6,'chunks':2,'sha256':hashlib.sha256(b''.join(hashlib.sha256(b).digest() for b in blocks)).hexdigest()}
   for i,b in enumerate(blocks):(root/('input_%05d.bin'%i)).write_bytes(b)
   out=m.assemble(root,cfg);self.assertEqual(out.read_bytes(),b'abcdef');self.assertEqual(m.assemble(root,cfg),out)
   out.write_bytes(b'wrong!')
   with self.assertRaises(FileNotFoundError):m.assemble(root,cfg)
 def test_ffmpeg_error_is_classified_without_private_stderr(self):
  with patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(returncode=1,stderr='private-file.mp4: moov atom not found')):
   with self.assertRaises(m.MediaError) as result:m.ffmpeg(['-i','private-file.mp4','out.wav'],'audio_decode')
   self.assertEqual(result.exception.code,'MEDIA_INVALID_INPUT');self.assertNotIn('private',str(result.exception))
 def test_resource_error_retries_once_with_one_thread(self):
  seq=[types.SimpleNamespace(returncode=1,stderr='pthread_create: resource temporarily unavailable'),types.SimpleNamespace(returncode=0)]
  with patch.object(m.subprocess,'run',side_effect=seq) as run:
   m.ffmpeg(['-i','in','out.wav']);self.assertEqual(run.call_count,2);args=run.call_args.args[0];self.assertEqual(args[args.index('-threads')+1],'1')
 def test_timeout_is_safe_and_bounded(self):
  with patch.object(m.subprocess,'run',side_effect=subprocess.TimeoutExpired('ffmpeg',1800)):
   with self.assertRaises(m.MediaError) as result:m.ffmpeg(['-i','private','out.wav'])
   self.assertEqual(result.exception.code,'MEDIA_TIMEOUT')
 def test_ass_does_not_accept_override_commands_from_subtitle_text(self):
  style={'x':50,'y':90,'size':4,'color':'#ffffff','font':'sans','weight':700}
  data=m.ass_text('1\n00:00:00,000 --> 00:00:01,000\n{\\p1}سلام',style,720,1280)
  self.assertNotIn('\\p1',data);self.assertIn('سلام',data);self.assertIn('\\pos(360,1152)',data)
 def test_generated_timestamps_preserve_milliseconds(self):
  data=m.srt([{'start':1.234,'end':2.567,'text':'السلام عليكم'}]);self.assertIn('00:00:01,234 --> 00:00:02,567',data)
 def test_fixed_worker_source_compiles_without_gpu_packages(self):
  compile((Path(__file__).parents[1]/'colab/worker.py').read_text(),'runner.py','exec')
 @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg is installed by CI')
 def test_all_thirteen_real_export_formats_have_expected_streams(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.mkv'
   subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x90:r=10','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','0.4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
   with patch.object(m,'encoder',return_value=['-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p']):
    for fmt in list(m.AUDIO)+sorted(m.VIDEO):
     out=m.export(source,root/('result.'+fmt));self.assertGreater(out.stat().st_size,0)
     streams=m.probe(out)['streams'];self.assertTrue(any(s['codec_type']=='audio' for s in streams),fmt)
     if fmt in m.VIDEO:self.assertTrue(any(s['codec_type']=='video' for s in streams),fmt)
   silent=root/'silent.mp4';subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-an','-c:v','copy',str(silent)],check=True)
   with self.assertRaises(m.MediaError) as error:m.audio_source(silent)
   self.assertEqual(error.exception.code,'MEDIA_NO_AUDIO')
   from PIL import Image
   png=io.BytesIO();Image.new('RGBA',(10,10),(255,0,0,255)).save(png,format='PNG')
   cfg={'style':{'x':50,'y':90,'size':4,'color':'#ffffff','font':'sans','weight':700},'logo':'data:image/png;base64,'+base64.b64encode(png.getvalue()).decode(),'logoX':5,'logoY':5,'logoSize':15}
   with patch.object(m,'encoder',return_value=['-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p']):
    out=m.burn(source,'1\n00:00:00,000 --> 00:00:01,000\nسلام',cfg,root)
   self.assertGreaterEqual(float(m.probe(out)['format']['duration']),.3)

 def test_asr_falls_back_to_gpu_transformers_when_first_engine_cannot_load(self):
  fake_cuda=types.SimpleNamespace(is_available=lambda:True,empty_cache=lambda:None)
  fake_torch=types.SimpleNamespace(cuda=fake_cuda,float16='float16')
  def fail(*args,**kw):raise ImportError('synthetic binary mismatch private-source')
  model=types.SimpleNamespace(to=lambda device:types.SimpleNamespace())
  processor=types.SimpleNamespace(tokenizer=object(),feature_extractor=object())
  transformers=types.SimpleNamespace(AutoModelForSpeechSeq2Seq=types.SimpleNamespace(from_pretrained=lambda *a,**k:model),AutoProcessor=types.SimpleNamespace(from_pretrained=lambda *a,**k:processor),pipeline=lambda *a,**k:lambda *x,**kw:{'chunks':[{'timestamp':(0,1),'text':'سلام'}]})
  modules={'torch':fake_torch,'onnxruntime':types.SimpleNamespace(),'faster_whisper':types.SimpleNamespace(WhisperModel=fail),'transformers':transformers}
  with tempfile.TemporaryDirectory() as d,patch.dict(sys.modules,modules),patch.object(m,'audio_source'),patch.object(m,'probe',return_value={'format':{'duration':'1.5'}}):
   root=Path(d);out=m.captions(root/'source.mp4',{'language':'ar','operation':'transcribe','target':'ar'},root,lambda *a,**k:None)
   self.assertTrue(out.is_file());self.assertIn('سلام',(root/'original.srt').read_text())
if __name__=='__main__':unittest.main()
