import importlib.util,subprocess,tempfile,unittest,shutil,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1]
s=importlib.util.spec_from_file_location('dub_runtime',ROOT/'colab'/'madar_colab_runtime.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class DubStems(unittest.TestCase):
 @unittest.skipUnless(shutil.which('ffmpeg'),'system ffmpeg required')
 def test_dub_returns_sample_aligned_voice_and_background_in_one_zip(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.m4a'
   subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','7','-c:a','aac',str(source)],check=True)
   created=[]
   class Separator:
    def __init__(self,work,single_stem='Vocals',model=None):self.work=work;created.append((single_stem,model))
    def separate(self,path,custom_output_names):
     voice=self.work/(custom_output_names['Vocals']+'.wav');bg=self.work/(custom_output_names['Instrumental']+'.wav')
     shutil.copyfile(path,voice);subprocess.run(['ffmpeg','-v','error','-y','-i',path,'-af','volume=0.1',str(bg)],check=True);return[voice.name,bg.name]
   with patch.object(m,'ROOT',root),patch.object(m,'CHUNK_SECONDS',3),patch.object(m,'new_separator',side_effect=Separator):
    bundle=m.run_dub_stems(source)
   self.assertEqual(created,[(None,'UVR-MDX-NET-Inst_HQ_4.onnx')],'both stems from the instrumental model')
   with zipfile.ZipFile(bundle) as z:
    self.assertEqual(sorted(z.namelist()),['background.m4a','voice.m4a'])
    z.extractall(root/'out')
   for name in ['voice.m4a','background.m4a']:
    self.assertAlmostEqual(m.duration_of(root/'out'/name),7,delta=0.15,msg=name)
 def test_dub_refuses_sources_longer_than_30_minutes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'s.m4a';source.write_bytes(b'x')
   with patch.object(m,'ROOT',root),patch.object(m,'duration_of',return_value=31*60):
    with self.assertRaises(ValueError):m.run_dub_stems(source)
class DubLines(unittest.TestCase):
 W=lambda self,w,s,e,seg=0:{'w':w,'s':s,'e':e,'seg':seg}
 def test_fast_back_to_back_dialogue_is_cut_between_words_at_each_turn(self):
  W=self.W
  words=[W('Can',0.5,0.7),W('we',0.7,0.8),W('go?',0.8,1.1),W('No.',1.2,1.5,1),W('Why',1.62,1.8,2),W('not?',1.8,2.1,2),W('Because',2.5,2.9,3),W('it',2.9,3.0,3),W('rains',3.0,3.4,3)]
  lines=m.group_dub_words(words)
  self.assertEqual([l['text'] for l in lines],['Can we go?','No.','Why not?','Because it rains'])
  for a,b in zip(lines,lines[1:]):self.assertLessEqual(a['end'],b['start'],'no overlap')
  for l in lines:self.assertLessEqual(l['start'],l['words'][0]['s']);self.assertGreaterEqual(l['end'],l['words'][-1]['e'])
  self.assertEqual(lines[1]['words'],[{'w':'No.','s':1.2,'e':1.5}])
 def test_long_speech_is_split_at_its_widest_pause_and_empty_words_are_ignored(self):
  W=self.W;words=[W('w%d'%i,i*0.5,i*0.5+0.4) for i in range(20)];words[9]['e']=4.55;words[10]['s']=5.3
  words.insert(3,W('  ',1.5,1.6));lines=m.group_dub_words(words)
  self.assertTrue(all(l['end']-l['start']<=6.3 for l in lines));self.assertEqual(lines[0]['words'][-1]['w'],'w9')
  self.assertEqual(m.group_dub_words([]),[])
 def test_fluent_speech_without_pauses_is_split_near_the_middle_not_word_by_word(self):
  W=self.W;words=[W('w%d'%i,i*0.4,i*0.4+0.4) for i in range(40)];lines=m.group_dub_words(words)
  self.assertTrue(all(len(l['words'])>=5 for l in lines),[len(l['words']) for l in lines]);self.assertTrue(all(l['end']-l['start']<=6.3 for l in lines))
 @unittest.skipUnless(shutil.which('ffmpeg'),'system ffmpeg required')
 def test_text_file_from_the_extra_step_goes_into_the_zip_after_the_model_is_released(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.m4a'
   subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','2','-c:a','aac',str(source)],check=True)
   class Separator:
    def __init__(self,work,single_stem='Vocals',model=None):self.work=work
    def separate(self,path,custom_output_names):
     out=[]
     for k in ('Vocals','Instrumental'):t=self.work/(custom_output_names[k]+'.wav');shutil.copyfile(path,t);out.append(t.name)
     return out
   seen=[]
   def extra(voice,work):seen.append(voice.name);t=work/'lines.json';t.write_text('{"lines":[]}');return[t]
   with patch.object(m,'ROOT',root),patch.object(m,'new_separator',side_effect=Separator):bundle=m.run_dub_stems(source,extra=extra)
   self.assertEqual(seen,['voice.m4a'])
   with zipfile.ZipFile(bundle) as z:self.assertEqual(sorted(z.namelist()),['background.m4a','lines.json','voice.m4a'])
if __name__=='__main__':unittest.main()
