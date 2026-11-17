import importlib.util,subprocess,tempfile,types,unittest,shutil
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1]
def load(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'colab'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('formats_runtime','madar_colab_runtime.py');job=load('formats_job','madar_web_job.py')
class MediaFormats(unittest.TestCase):
 def test_safe_diagnostics_classify_decode_failure_without_exposing_filename(self):
  p=types.SimpleNamespace(returncode=1,stderr='secret-name.mp4: Invalid data found when processing input')
  with patch.object(m.subprocess,'run',return_value=p):
   try:m.ffmpeg(['-ss',0,'-i','secret-name.mp4','-c:a','pcm_s16le','out.wav'])
   except m.MediaError as e:
    code,msg,d=job.failure_details(e,{'task':'separate'});self.assertEqual(code,'MEDIA_INVALID_INPUT');self.assertEqual(d['media']['stage'],'audio_decode');self.assertNotIn('secret',str((msg,d)))
 def test_transient_resource_failure_retries_once_with_bounded_threads(self):
  results=[types.SimpleNamespace(returncode=1,stderr='pthread_create failed: Resource temporarily unavailable'),types.SimpleNamespace(returncode=0)]
  with patch.object(m.subprocess,'run',side_effect=results) as run:
   m.ffmpeg(['-i','in','out.wav']);self.assertEqual(run.call_count,2);args=run.call_args.args[0];self.assertEqual(args[args.index('-threads')+1],'1');self.assertIn('file,pipe',args)
 def test_invalid_input_is_not_blindly_retried(self):
  with patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(returncode=1,stderr='moov atom not found')) as run:
   with self.assertRaises(m.MediaError):m.ffmpeg(['-i','in','out.wav'])
   self.assertEqual(run.call_count,1)
 @unittest.skipUnless(shutil.which('ffmpeg'),'system ffmpeg required')
 def test_real_media_export_formats_and_decode(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.mkv'
   subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x90:r=10','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','0.4','-c:v','libx264','-pix_fmt','yuv420p','-threads','1','-c:a','aac',str(source)],check=True)
   m.validate_audio_source(source)
   with patch.object(m,'video_encoder',return_value=['-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p']):
    for fmt in [*m.AUDIO_FORMATS,*m.VIDEO_FORMATS]:
     out=root/('result.'+fmt);m.export_media(source,out);self.assertGreater(out.stat().st_size,0,fmt)
     streams=m.media_streams(out);self.assertTrue(any(s['codec_type']=='audio' for s in streams),fmt)
     if fmt in m.VIDEO_FORMATS:self.assertTrue(any(s['codec_type']=='video' for s in streams),fmt)
   silent=root/'silent.mp4';subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-an','-c:v','copy',str(silent)],check=True)
   with self.assertRaises(m.MediaError) as e:m.validate_audio_source(silent)
   self.assertEqual(e.exception.media_details['code'],'MEDIA_NO_AUDIO')
 @unittest.skipUnless(shutil.which('ffmpeg'),'system ffmpeg required')
 def test_real_separation_io_with_cached_mock_stem_exports_mp4_and_mp3(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.webm'
   subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x90:r=10','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','0.4','-c:v','libvpx-vp9','-threads','1','-c:a','libopus',str(source)],check=True)
   calls=[]
   class Separator:
    def __init__(self,work):self.work=work
    def separate(self,path,custom_output_names):
     calls.append(path);out=self.work/'vocals.wav';shutil.copyfile(path,out);return[out.name]
   with patch.object(m,'ROOT',root),patch.object(m,'new_separator',side_effect=Separator),patch.object(m,'video_encoder',return_value=['-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p']):
    for mode,fmt in [('video','mp4'),('audio','mp3'),('audio','wav')]:
     out=m.run_separation(source,mode=mode,output_format=fmt)
     self.assertEqual(out.suffix,'.'+fmt);self.assertGreater(out.stat().st_size,0)
     streams=m.media_streams(out);self.assertTrue(any(s['codec_type']=='audio' for s in streams))
     if fmt=='mp4':self.assertTrue(any(s.get('codec_name')=='h264' for s in streams))
   self.assertEqual(len(calls),2)  # MP3 and WAV share the verified audio stem.
if __name__=='__main__':unittest.main()
