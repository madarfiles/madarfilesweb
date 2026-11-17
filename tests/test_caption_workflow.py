import hashlib,importlib.util,json,shutil,subprocess,sys,tempfile,types,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).parents[1]/'colab'
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,BASE/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load('captiontask','madar_cloud_tasks.py');job=load('captionjob','madar_web_job.py')
class CaptionWorkflow(unittest.TestCase):
 def test_followup_source_is_reused_and_verified_without_upload(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);parent=base/'12345678-1234-4123-8123-123456789abc';parent.mkdir();child=base/'child';child.mkdir();data=b'abcdefg';cfg=dict(task='asr',ext='mp4',size=7,chunks=2,sha256=hashlib.sha256(b''.join(hashlib.sha256(b).digest() for b in [b'abcd',b'efg'])).hexdigest());(parent/'config.json').write_text(json.dumps(cfg));(parent/'source.mp4').write_bytes(data)
   with patch.object(job,'ROOT',child),patch.object(job,'PART',4):
    self.assertEqual(job.assemble({**cfg,'parentJob':parent.name}).read_bytes(),data)
    (parent/'source.mp4').write_bytes(b'bad')
    with self.assertRaises(ValueError):job.assemble({**cfg,'parentJob':parent.name})
    self.assertFalse((child/'source.mp4').exists())
 def test_translation_followup_preserves_timing_and_preview(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);srt='1\n00:00:00,000 --> 00:00:01,000\nHello';cfg=dict(operation='translate',subtitles=srt,source='en',target='ar',names='',ext='mp4')
   with patch.object(m,'install'),patch.object(m,'translate_lines',side_effect=lambda lines,*a:['شموخ' if x=='Hello' else x for x in lines]):out=m.caption_workflow(root/'source.mp4',cfg,root,lambda *a:None)
   with zipfile.ZipFile(out) as z:self.assertIn('00:00:00,000 --> 00:00:01,000',z.read('translated.srt').decode());self.assertIn('شموخ',z.read('translated.srt').decode())
   preview=json.loads((root/'preview.json').read_text());self.assertEqual(preview['language'],'ar');self.assertFalse(preview['truncated'])
 @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg unavailable')
 def test_real_ffmpeg_burn_accepts_all_positions_and_colors(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=320x240:d=0.3','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
   runtime=types.SimpleNamespace(video_encoder=lambda:['-c:v','libx264','-preset','ultrafast'],nvenc_ready=lambda:False)
   for pos,color in [('top','ivory'),('middle','white'),('bottom','gold')]:
    cfg=dict(subtitles='1\n00:00:00,000 --> 00:00:01,000\nشموخ',position=pos,fontColor=color,fontSize='24')
    with patch.object(m,'install'),patch.dict(sys.modules,{'madar_colab_runtime':runtime}):out=m.process('burn',source,cfg,root,lambda *a:None)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out)]));self.assertEqual(probe['streams'][0]['codec_name'],'h264');self.assertGreater(out.stat().st_size,100)
 def test_retry_source_is_bound_to_original_tool(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);parent=base/'12345678-1234-4123-8123-123456789abc';parent.mkdir();child=base/'child';child.mkdir();data=b'abcdefg';cfg=dict(task='resize',ext='mp4',size=7,chunks=2,sha256=hashlib.sha256(b''.join(hashlib.sha256(b).digest() for b in [b'abcd',b'efg'])).hexdigest());(parent/'config.json').write_text(json.dumps(cfg));(parent/'source.mp4').write_bytes(data)
   with patch.object(job,'ROOT',child),patch.object(job,'PART',4):
    self.assertEqual(job.assemble({**cfg,'parentJob':parent.name}).read_bytes(),data)
    with self.assertRaises(ValueError):job.assemble({**cfg,'task':'burn','parentJob':parent.name})
 @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg unavailable')
 def test_real_resize_preserves_video_stream_and_requested_canvas(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x180:d=0.2','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
   runtime=types.SimpleNamespace(video_encoder=lambda:['-c:v','libx264','-preset','ultrafast'],nvenc_ready=lambda:False)
   with patch.object(m,'install'),patch.dict(sys.modules,{'madar_colab_runtime':runtime}):out=m.process('resize',source,{'ratio':'portrait','fit':'blur'},root,lambda *a:None)
   probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out)]));stream=probe['streams'][0];self.assertEqual((stream['width'],stream['height']),(720,1280));self.assertEqual(stream['codec_name'],'h264');self.assertGreater(out.stat().st_size,1000)
 def test_failed_translation_retry_reuses_completed_transcription(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);parent=base/'12345678-1234-4123-8123-123456789abc';parent.mkdir();root=base/'new';root.mkdir();srt='1\n00:00:00,000 --> 00:00:01,000\nHello'
   (parent/'config.json').write_text(json.dumps({'language':'en'}));(parent/'original.srt').write_text(srt);(parent/'language.json').write_text(json.dumps({'language':'en'}));(parent/'transcript.txt').write_text('Hello')
   with patch.object(m,'process') as asr,patch.object(m,'install'),patch.object(m,'translate_lines',side_effect=lambda lines,*args:lines):
    out=m.caption_workflow(root/'source.mp4',{'operation':'transcribeTranslate','parentJob':parent.name,'language':'en','source':'en','target':'ar','ext':'mp4'},root,lambda *a:None)
   asr.assert_not_called();self.assertGreater(out.stat().st_size,0);self.assertEqual((root/'original.srt').read_text(),srt)
