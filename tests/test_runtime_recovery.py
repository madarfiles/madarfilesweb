import importlib.util,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1]/'colab'
def module(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=module('recovery_cloud','madar_cloud_tasks.py');job=module('recovery_job','madar_web_job.py')
class RuntimeRecovery(unittest.TestCase):
 def test_only_transient_model_transfer_errors_are_retried(self):
  calls=[]
  def download():
   calls.append(1)
   if len(calls)<3:raise ConnectionError('connection reset https://secret/token')
   return 'cached-model'
  with patch.object(m.time,'sleep'):self.assertEqual(m.load_model(download,lambda *a:None),'cached-model')
  self.assertEqual(len(calls),3)
  with patch.object(m.time,'sleep'),patch.object(m,'cuda'):
   with self.assertRaises(ValueError):m.load_model(lambda:(_ for _ in ()).throw(ValueError('bad weights')),lambda *a:None)
 def test_safe_diagnostic_preserves_failure_class_and_never_inputs(self):
  for exc in [RuntimeError('CUDA out of memory secret-input'),ValueError('failed tokenizer for https://secret/?token=ya29.secret'),OSError('connection reset gsk_secret'),ValueError('خطأ بملف https://secret/private')]:
   try:raise exc
   except Exception as caught:code,msg,diagnostic=job.failure_details(caught,{'task':'asr','prompt':'private prompt'})
   result=json.dumps([code,msg,diagnostic],ensure_ascii=False);self.assertNotIn('secret',result);self.assertNotIn('private prompt',result);self.assertEqual(diagnostic['task'],'asr');self.assertEqual(diagnostic['exception'],type(exc).__name__)
 def test_asr_uses_gpu_transformers_fallback_for_binary_incompatibility(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m,'install'),patch.object(m,'cuda'),patch.object(m,'preload_cuda',side_effect=OSError('libcudnn.so.9 missing')),patch.object(m,'transcribe_transformers',return_value=Path(d)/'results.zip') as alternate:
   out=m.process('asr',Path(d)/'source.mkv',{'_basic_asr':True,'language':'ar'},Path(d),lambda *a:None);self.assertEqual(out.suffix,'.zip');alternate.assert_called_once()
 def test_asr_retries_vad_failure_without_reloading_model(self):
  with tempfile.TemporaryDirectory() as d:
   calls=[]
   class Model:
    def transcribe(self,*args,**kw):
     calls.append(kw['vad_filter'])
     if kw['vad_filter']:raise RuntimeError('onnxruntime silero vad unavailable')
     return iter([types.SimpleNamespace(start=0,end=1,text='عبد المجيد')]),types.SimpleNamespace(language='ar')
   model=Model();ort=types.SimpleNamespace();ctranslate2=types.SimpleNamespace(get_supported_compute_types=lambda device:{'float16'})
   with patch.object(m,'install'),patch.object(m,'cuda'),patch.object(m,'preload_cuda'),patch.object(m,'cached_model',return_value=model),patch.dict(sys.modules,{'faster_whisper':types.SimpleNamespace(WhisperModel=object),'onnxruntime':ort,'ctranslate2':ctranslate2}):
    out=m.process('asr',Path(d)/'source.mkv',{'_basic_asr':True,'language':'ar'},Path(d),lambda *a:None)
   self.assertEqual(calls,[True,False]);self.assertGreater(out.stat().st_size,0);self.assertIn('عبد المجيد',(Path(d)/'original.srt').read_text())
