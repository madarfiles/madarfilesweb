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
 def test_a_pause_inside_a_sentence_never_cuts_it_and_a_long_one_shows_as_dots(self):
  W=self.W;words=[W('وأنا',4.75,5.29),W('أمك.',5.8,6.2),W('حسنًا',6.4,6.9,1),W('يا',7.8,8.0,1),W('أمي.',8.0,8.4,1)]
  lines=m.group_dub_words(words)
  self.assertEqual([l['say'] for l in lines],['وأنا أمك.','حسنًا يا أمي.'])
  self.assertEqual(lines[1]['text'],'حسنًا … يا أمي.');self.assertEqual(lines[1]['words'][1]['k'],'pause')
 def test_a_new_speaker_starts_a_new_line_even_without_a_pause(self):
  W=self.W;words=[W('بنجو',2.2,2.9),W('وأنا',2.9,3.3),W('أمك',3.3,3.7),W('حسنًا',3.7,4.2),W('يا',4.2,4.4),W('أمي',4.4,4.8)]
  for w in words[:3]:w['spk']=1
  for w in words[3:]:w['spk']=2
  lines=m.group_dub_words(words)
  self.assertEqual([(l['text'],l['spk']) for l in lines],[('بنجو وأنا أمك',1),('حسنًا يا أمي',2)])
  self.assertLessEqual(lines[0]['end'],lines[1]['start'])
 def test_one_speaker_keeps_a_long_sentence_whole_and_only_very_long_speech_is_split_at_a_sentence_end(self):
  W=self.W;words=[W('w%d'%i,i*0.5,i*0.5+0.45) for i in range(30)]
  for w in words:w['spk']=1
  self.assertEqual(len(m.group_dub_words(words)),1,'15 seconds of one speaker stay one line')
  words=[W('w%d'%i,i*0.5,i*0.5+0.45) for i in range(50)];words[17]['w']='end.';words[18]['s']=words[17]['e']+0.05
  for w in words:w['spk']=1
  lines=m.group_dub_words(words)
  self.assertEqual(lines[0]['words'][-1]['w'],'end.');self.assertTrue(all(l['end']-l['start']<=20.3 for l in lines))
 def test_without_speaker_labels_long_runs_are_still_kept_short_enough_to_record(self):
  W=self.W;words=[W('w%d'%i,i*0.4,i*0.4+0.4) for i in range(40)];lines=m.group_dub_words(words)
  self.assertTrue(all(len(l['words'])>=5 for l in lines),[len(l['words']) for l in lines]);self.assertTrue(all(l['end']-l['start']<=8.3 for l in lines))
  self.assertEqual(m.group_dub_words([]),[])
 def test_laughs_join_the_nearest_line_in_time_order_and_far_sounds_get_their_own_line(self):
  W=self.W;words=[W('دي',1.0,1.3),W('ديمز',1.3,1.8),W('أنا',2.6,2.9,1),W('سآخذ',2.9,3.3,1),W('هذا',3.3,3.6,1)]
  lines=m.group_dub_words(words,[{'s':1.9,'e':2.3,'label':'…'},{'s':9.0,'e':9.6,'label':'…'}])
  self.assertEqual([l['text'] for l in lines],['دي ديمز (…)','أنا سآخذ هذا','(…)'])
  self.assertEqual(lines[0]['say'],'دي ديمز');self.assertEqual(lines[0]['words'][-1],{'w':'(…)','s':1.9,'e':2.3,'k':'sound'})
  self.assertGreaterEqual(lines[0]['end'],2.3)
class DubVoices(unittest.TestCase):
 W=lambda self,w,s,e,seg=0:{'w':w,'s':s,'e':e,'seg':seg}
 def test_speaker_embeddings_cluster_into_people_numbered_by_first_appearance(self):
  import numpy as np
  a,b=np.array([1.0,0.1,0]),np.array([0,0.2,1.0])
  self.assertEqual(m.cluster_speakers([b,a*1.1,None,b+0.05,a],0.8),[1,2,None,1,2])
  self.assertEqual(m.cluster_speakers([None]),[None])
 def test_window_labels_reach_words_and_short_flickers_are_smoothed_away(self):
  W=lambda w,s,e:{'w':w,'s':s,'e':e,'seg':0}
  words=[W('a',0.0,0.5),W('b',0.5,1.0),W('c',1.0,1.5),W('d',1.5,2.0),W('e',2.0,2.2),W('f',2.2,3.0),W('g',3.0,3.6)]
  units=[list(range(7))];windows=[(0,0.0,1.2),(0,0.8,2.0),(0,2.0,2.3),(0,2.2,3.6)];labels=[1,1,2,3]
  m.assign_speakers(words,units,windows,labels,min_run=0.6)
  got=[w['spk'] for w in words];self.assertNotIn(2,got,'the 0.2 s blip of speaker 2 joins a neighbour');self.assertEqual(got[:4],[1]*4);self.assertEqual(got[-2:],[3,3])
  wins=m.speech_windows(words,units);self.assertEqual(len(wins),8);self.assertAlmostEqual(wins[-1][2]-wins[-1][1],1.2)
 def test_sounds_made_by_people_get_a_plain_mark_and_music_or_quiet_ones_are_skipped(self):
  for scores in ({'Giggle':0.4},{'Humming':0.2},{'Crying, sobbing':0.3},{'Speech':0.7}):self.assertEqual(m.name_sound(scores,0.8),'…',scores)
  self.assertIsNone(m.name_sound({'Music':0.9,'Laughter':0.05},1.0))
 def test_cut_pieces_rejoin_their_sentence_but_a_full_reply_keeps_its_line(self):
  W=self.W
  words=[W('وانت',7.2,7.6),W('شقيق',7.6,8.0),W('واسمك',8.0,8.6),W('بديدامس',10.0,10.9,1),W('نعم',12.0,12.3,2),W('يا',12.3,12.4,2),W('أمي.',12.4,12.9,2),W('نعم.',13.2,13.5,3)]
  for w,s in zip(words,[1,1,1,1,2,2,2,1]):w['spk']=s
  lines=m.group_dub_words(words)
  self.assertEqual([l['say'] for l in lines],['وانت شقيق واسمك بديدامس','نعم يا أمي.','نعم.'])
  self.assertIn('…',lines[0]['text'])
 def test_a_speaker_blip_inside_one_breath_does_not_cut_the_sentence_without_a_break(self):
  W=self.W;words=[W(x,i*0.5,i*0.5+0.5) for i,x in enumerate('abcdef')]
  for w,s in zip(words,[1,1,1,2,2,2]):w['spk']=s
  self.assertEqual(len(m.group_dub_words(words,pause_turn=0.1)),1)
  self.assertEqual(len(m.group_dub_words(words)),2,'with no pause rule a confident change still cuts')
 def test_sound_regions_are_voice_energy_not_covered_by_any_word(self):
  import numpy as np
  rate=16000;t=np.arange(rate*4)/rate;x=np.zeros_like(t,dtype=np.float32)
  x[int(0.5*rate):int(1.5*rate)]=0.3*np.sin(2*np.pi*200*t[int(0.5*rate):int(1.5*rate)])
  x[int(2.5*rate):int(3.2*rate)]=0.3*np.sin(2*np.pi*300*t[int(2.5*rate):int(3.2*rate)])
  regions=m.sound_regions(x,rate,[{'w':'hi','s':0.5,'e':1.5}])
  self.assertEqual(len(regions),1);self.assertAlmostEqual(regions[0]['s'],2.5,delta=0.05);self.assertAlmostEqual(regions[0]['e'],3.2,delta=0.05)
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
