import importlib.util,shutil,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
s=importlib.util.spec_from_file_location('madar_dovi_test',ROOT/'colab'/'madar_dovi.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Dovi(unittest.TestCase):
 def test_sizes_rates_levels(self):
  self.assertEqual(m.target_size(1080,1920),(1440,2560));self.assertEqual(m.target_size(1920,1080),(2560,1440));self.assertEqual(m.target_size(3840,2160),(2560,1440))
  self.assertEqual(m.target_size(720,720),(1440,1440))
  self.assertEqual(m.output_rate(29.97),'30000/1001');self.assertEqual(m.output_rate(30.2),'30');self.assertEqual(m.output_rate(59.94),'60000/1001');self.assertEqual(m.output_rate(41),'30')
  self.assertEqual(m.dv_level(1440,2560,30),6);self.assertEqual(m.dv_level(1440,2560,60),7);self.assertEqual(m.dv_level(1080,1920,30),4)
 def test_dvcc_bits(self):
  box=m.dvcc(6);self.assertEqual(len(box),32);self.assertEqual(box[4:8],b'dvcC');self.assertEqual(box[8:10],b'\x01\x00')
  bits=struct.unpack('>H',box[10:12])[0];self.assertEqual(bits>>9,8);self.assertEqual((bits>>3)&0x3f,6);self.assertEqual(bits&7,0b101);self.assertEqual(box[12]>>4,4)
 def test_filter_keeps_hdr_sources(self):
  self.assertNotIn('arib-std-b67:m',m.video_filter('arib-std-b67',1440,2560,203));self.assertIn('npl=320',m.video_filter('bt709',1440,2560,320))
 @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg needed')
 def test_box_lands_in_mp4_and_media_still_plays(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);src=d/'a.mp4';out=d/'b.mp4'
   subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=1','-f','lavfi','-i','sine=d=1','-c:v','libx265','-x265-params','log-level=error','-tag:v','hvc1','-c:a','aac','-shortest',str(src)],check=True)
   m.add_dolby_vision(src,out,4)
   probe=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format',str(out)],capture_output=True,text=True).stdout
   self.assertIn('dv_profile=8',probe);self.assertIn('dv_bl_signal_compatibility_id=4',probe);self.assertIn('dby1',probe)
   self.assertEqual(out.read_bytes()[4:8],b'ftyp');self.assertEqual(out.read_bytes()[out.read_bytes().index(b'moov')-4:][4:8],b'moov')
   r=subprocess.run(['ffmpeg','-v','error','-i',str(out),'-f','null','-'],capture_output=True,text=True);self.assertEqual(r.returncode,0);self.assertEqual(r.stderr.strip(),'')
