import base64,importlib.util,io,json,shutil,subprocess,sys,tempfile,types,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
BASE=Path(__file__).parents[1]/'colab';sys.path.insert(0,str(BASE))
import madar_captions as cap
spec=importlib.util.spec_from_file_location('studio_cloud',BASE/'madar_cloud_tasks.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SRT='1\n00:00:00,000 --> 00:00:01,000\nHello world\n';STYLE=dict(fontFamily='sans',fontWeight='700',fontColor='#ffffff',fontSizePct=8,x=25,y=75,background=False,logoX=95,logoY=5,logoWidth=10,logoOpacity=100)
def video(p):subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=0x294645:s=640x360:d=1.1','-c:v','libx264','-pix_fmt','yuv420p',str(p)],check=True)
@unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
class Studio(unittest.TestCase):
 def test_four_workflows_translate_only_when_requested_and_keep_text(self):
  process=m.process
  for operation in ['transcribe','transcribeTranslate','transcribeBurn','transcribeTranslateBurn']:
   with self.subTest(operation=operation),tempfile.TemporaryDirectory() as d:
    root=Path(d);source=root/'source.mp4';video(source)
    def route(task,source,cfg,path,report):
     if task=='asr' and cfg.get('_basic_asr'):
      (path/'original.srt').write_text(SRT);(path/'transcript.txt').write_text('Hello world');(path/'language.json').write_text(json.dumps({'language':'en'}));return path/'original.srt'
     return process(task,source,cfg,path,report)
    runtime=types.SimpleNamespace(video_encoder=lambda:['-c:v','libx264','-preset','ultrafast'],nvenc_ready=lambda:False)
    with patch.object(m,'process',side_effect=route),patch.object(m,'install'),patch.object(m,'translate_lines',side_effect=lambda lines,*a:['مرحبا بكم' if x=='Hello world' else x for x in lines]) as translate,patch.dict(sys.modules,{'madar_colab_runtime':runtime}):
     out=m.caption_workflow(source,dict(operation=operation,language='auto',source='auto',target='ar',names='',ext='mp4',captionStyle=STYLE),root,lambda *a:None)
    self.assertEqual(translate.call_count,int('Translate' in operation));self.assertEqual(out.suffix,'.mp4' if operation.endswith('Burn') else '.zip');self.assertEqual((root/'original.srt').read_text(),SRT);self.assertIn('-->',(root/'rendered.srt').read_text());self.assertGreater(out.stat().st_size,100)
 def test_real_ffmpeg_places_arabic_and_logo_at_selected_coordinates(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.mp4';video(source);im=Image.new('RGBA',(32,32),(255,0,0,255));raw=io.BytesIO();im.save(raw,'PNG')
   out=cap.burn(source,dict(subtitles=SRT.replace('Hello world','مرحبا بكم'),captionStyle=STYLE,logoPng=base64.b64encode(raw.getvalue()).decode()),root,lambda *a:None,['-c:v','libx264','-preset','ultrafast'],m.run_ffmpeg,m.subtitle_style)
   data=subprocess.check_output(['ffmpeg','-v','error','-ss','0.4','-i',str(out),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']);frame=np.frombuffer(data,np.uint8).reshape(360,640,3);self.assertGreater(frame[25,560,0],230);self.assertLess(frame[25,560,1],30);yy,xx=np.where(np.all(frame>200,axis=2));self.assertGreater(len(xx),10);self.assertLess(abs(xx.mean()-160),40);self.assertLess(abs(yy.mean()-270),35)
 def test_ass_escapes_user_tags_and_rejects_style_injection(self):
  ass=cap.ass_text(SRT.replace('Hello world',r'{\pos(1,1)} مرحبا'),STYLE,1920,1080);self.assertIn('\\pos(480.000,810.000)',ass);self.assertNotIn('{\\pos(1,1)}',ass)
  for change in [{'fontFamily':'evil,path'},{'fontColor':'red,Size=999'},{'x':float('nan')}]:
   with self.assertRaises((ValueError,KeyError)):cap.ass_text(SRT,{**STYLE,**change},1920,1080)
 def test_runner_writes_full_caption_sidecar_with_chunk_integrity(self):
  spec=importlib.util.spec_from_file_location('studio_job',BASE/'madar_web_job.py');job=importlib.util.module_from_spec(spec);spec.loader.exec_module(job)
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'config.json').write_text(json.dumps({'task':'asr','operation':'transcribeBurn'}))
   def fake(task,source,cfg,path,report):
    (path/'original.srt').write_text(SRT);(path/'transcript.txt').write_text('Hello world');(path/'rendered.srt').write_text(SRT);out=path/'result.mp4';out.write_bytes(b'video');return out
   with patch.object(job,'ROOT',root),patch.dict(sys.modules,{'madar_cloud_tasks':types.SimpleNamespace(process=fake)}):job.main()
   state=json.loads((root/'state.json').read_text());self.assertEqual(state['state'],'done');self.assertEqual(hashlib.sha256((root/'captions_00000.bin').read_bytes()).hexdigest(),state['captions']['chunks'][0])
