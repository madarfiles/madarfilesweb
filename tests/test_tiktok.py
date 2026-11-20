import importlib.util,json,shutil,subprocess,sys,tempfile,types,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
s=importlib.util.spec_from_file_location('madar_tiktok_test',ROOT/'colab'/'madar_tiktok.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class TikTok(unittest.TestCase):
 def test_size_and_rate_follow_the_clip(self):
  self.assertEqual(m.target_size(2160,3840),(1080,1920));self.assertEqual(m.target_size(720,1280),(1080,1920));self.assertEqual(m.target_size(3840,2160),(1920,1080));self.assertEqual(m.target_size(1080,1080),(1080,1080))
  self.assertEqual(m.output_rate(29.97),'30000/1001');self.assertEqual(m.output_rate(30.3),'30');self.assertEqual(m.output_rate(120),'60');self.assertEqual(m.output_rate(59.94),'60000/1001');self.assertEqual(m.output_rate(41),'30')
 def test_hdr_is_tone_mapped_and_small_clips_sharpened(self):
  base={'w':2160,'h':3840,'bits':10}
  pq=m.video_filter({**base,'transfer':'smpte2084'},1080,1920);self.assertIn('tin=smpte2084',pq);self.assertIn('tonemap=mobius',pq);self.assertNotIn('unsharp',pq)
  self.assertIn('tin=arib-std-b67',m.video_filter({**base,'transfer':'arib-std-b67'},1080,1920))
  sd=m.video_filter({'w':720,'h':1280,'bits':8,'transfer':'bt709'},1080,1920);self.assertNotIn('tonemap',sd);self.assertIn('unsharp',sd)
  self.assertIn('eq=saturation',m.video_filter({'w':720,'h':1280,'bits':8,'transfer':''},1080,1920,'vivid'))
 @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg needed')
 def test_hdr_clip_becomes_clean_1080p_h264(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);src=d/'in.mp4'
   subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','testsrc2=s=1440x2560:r=30:d=1','-f','lavfi','-i','sine=d=1','-vf','format=yuv420p10le','-color_trc','arib-std-b67','-color_primaries','bt2020','-colorspace','bt2020nc','-c:v','libx265','-preset','ultrafast','-x265-params','log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc','-c:a','aac','-shortest',str(src)],check=True)
   sys.modules['madar_colab_runtime']=types.SimpleNamespace(nvenc_ready=lambda:False)
   try:out=m.make_tiktok(src,{},d,lambda *a:None)
   finally:sys.modules.pop('madar_colab_runtime',None)
   v=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out)]))['streams']
   video=next(x for x in v if x['codec_type']=='video')
   self.assertEqual((video['codec_name'],video['width'],video['height'],video['pix_fmt'],video.get('color_transfer')),('h264',1080,1920,'yuv420p','bt709'))
   self.assertTrue(any(x['codec_type']=='audio' for x in v));self.assertTrue((d/'preview.json').exists())
