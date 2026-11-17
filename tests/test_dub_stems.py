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
 def bluey(self):
  """The opening of the user's clip (Whisper segments, voices as found by TitaNet)."""
  W=self.W
  words=[W('بينجو',1.97,2.49,0),W('أنتِ',2.49,2.67,0),W('طفلة',2.67,3.41,0),W('واسمكِ',3.41,3.95,0),W('ستودروب',3.95,4.59,0),
         W('وأنا',4.59,5.17,1),W('أمك',5.17,5.83,1),W('حسنًا',5.83,6.33,2),W('يا',6.59,6.75,2),W('أمي',6.75,7.41,2),
         W('وأنت',7.41,7.91,3),W('شقيق',7.91,8.55,3),W('ستودروب',8.55,9.23,3),W('واسمك',9.23,10.39,4),W('ديدامز',11.99,12.97,5)]
  units=m.turn_units(words)
  return words,units
 def test_each_line_is_one_speakers_turn_like_the_bluey_opening(self):
  words,units=self.bluey()
  self.assertEqual(len(units),6)
  lines=m.group_dub_words(words,(),units,[1,1,2,1,1,3])
  self.assertEqual([(l['say'],l.get('spk')) for l in lines],[('بينجو أنتِ طفلة واسمكِ ستودروب وأنا أمك',1),('حسنًا يا أمي',2),('وأنت شقيق ستودروب واسمك',1),('ديدامز',3)])
 def test_a_short_turn_of_another_speaker_keeps_its_own_line_however_short(self):
  words,units=self.bluey()
  lines=m.group_dub_words(words,(),units,[1,None,2,1,None,None])
  self.assertEqual([l['say'] for l in lines],['بينجو أنتِ طفلة واسمكِ ستودروب وأنا أمك','حسنًا يا أمي','وأنت شقيق ستودروب واسمك','ديدامز'],'a two-word fragment right after an unfinished sentence is glued back; one after a pause is not')
 def test_the_same_speaker_after_a_real_pause_starts_a_new_line(self):
  W=self.W;words=[W('أنا',0,0.4,0),W('ذاهب.',0.4,1.0,0),W('لماذا؟',1.3,1.9,1),W('لآكل',3.0,3.5,2),W('البروست.',3.5,4.2,2)]
  units=m.turn_units(words);lines=m.group_dub_words(words,(),units,[1,2,1])
  self.assertEqual([l['say'] for l in lines],['أنا ذاهب.','لماذا؟','لآكل البروست.'])
  words=[W('أنا',0,0.4,0),W('ذاهب',0.4,1.0,0),W('إلى',1.3,1.5,1),W('جدتي.',1.5,2.0,1)]
  self.assertEqual(len(m.group_dub_words(words,(),m.turn_units(words),[1,1])),1,'one speaker, short breath: one line')
 def test_without_voices_whisper_segments_and_sentence_ends_make_the_lines(self):
  W=self.W;words=[W('هل',0,0.3,0),W('أنت',0.3,0.6,0),W('مستعد؟',0.6,1.1,0),W('نعم.',1.3,1.6,0),W('هيا',1.7,2.0,1),W('بنا',2.0,2.4,1)]
  self.assertEqual([l['say'] for l in m.group_dub_words(words)],['هل أنت مستعد؟','نعم.','هيا بنا'])
  self.assertEqual(m.group_dub_words([]),[])
 def test_very_long_speech_of_one_speaker_is_split_at_a_sentence_end(self):
  W=self.W;words=[W('w%d'%i,i*0.5,i*0.5+0.45,0) for i in range(50)];words[17]['w']='end.'
  lines=m.group_dub_words(words,(),[list(range(50))],[1])
  self.assertEqual(lines[0]['words'][-1]['w'],'end.');self.assertTrue(all(l['end']-l['start']<=20.3 for l in lines))
 def test_a_long_silence_inside_a_line_shows_as_dots(self):
  W=self.W;words=[W('حسنًا',6.4,6.9,0),W('يا',7.8,8.0,0),W('أمي.',8.0,8.4,0)]
  lines=m.group_dub_words(words,(),[[0,1,2]],[2])
  self.assertEqual(lines[0]['text'],'حسنًا … يا أمي.');self.assertEqual(lines[0]['words'][1]['k'],'pause')
 def test_laughs_join_the_nearest_line_and_far_sounds_get_their_own_line(self):
  W=self.W;words=[W('دي',1.0,1.3,0),W('ديمز',1.3,1.8,0),W('أنا',2.6,2.9,1),W('سآخذ',2.9,3.3,1),W('هذا',3.3,3.6,1)]
  lines=m.group_dub_words(words,[{'s':1.9,'e':2.3,'label':'…'},{'s':9.0,'e':9.6,'label':'…'}],m.turn_units(words),[1,2])
  self.assertEqual([l['text'] for l in lines],['دي ديمز (…)','أنا سآخذ هذا','(…)'])
  self.assertEqual(lines[0]['say'],'دي ديمز');self.assertEqual(lines[0]['words'][-1],{'w':'(…)','s':1.9,'e':2.3,'k':'sound'})
 def test_lines_of_people_talking_together_may_overlap(self):
  W=self.W;words=[W('a',0,1,0),W('b',1,2,0),W('c',1.8,2.5,1)]
  lines=m.group_dub_words(words,(),[[0,1],[2]],[1,2])
  self.assertGreater(lines[0]['end'],lines[1]['start'])
class DubVoices(unittest.TestCase):
 def test_voices_group_into_speakers_and_short_unclear_pieces_stay_unknown(self):
  import numpy as np
  a,b,c=np.array([1.0,0.1,0]),np.array([0,0.2,1.0]),np.array([0.0,1.0,0.0])
  near_a=np.array([0.45,-1.0,0.45])
  labels=m.cluster_speakers([a,b,None,a*1.1,b+0.05,near_a,c],[3,3,0.3,2,2,0.8,0.9])
  self.assertEqual(labels[:5],[1,2,None,1,2])
  self.assertIsNone(labels[5],'short and only half-similar: unknown rather than a guess')
  self.assertEqual(labels[6],3,'short but unlike every known voice: a new speaker')
  self.assertEqual(m.cluster_speakers([None],[1]),[None])
 def test_turn_units_follow_whisper_segments_sentence_ends_and_silences(self):
  W=lambda w,s,e,seg:{'w':w,'s':s,'e':e,'seg':seg}
  words=[W('a',0,0.5,0),W('b.',0.5,1,0),W('c',1.2,1.5,0),W('d',1.5,2,1),W('e',3.2,3.5,1)]
  self.assertEqual(m.turn_units(words),[[0,1],[2],[3],[4]])
 def test_sounds_made_by_people_get_a_plain_mark_and_music_or_quiet_ones_are_skipped(self):
  for scores in ({'Giggle':0.4},{'Humming':0.2},{'Crying, sobbing':0.3},{'Speech':0.7}):self.assertEqual(m.name_sound(scores,0.8),'…',scores)
  self.assertIsNone(m.name_sound({'Music':0.9,'Laughter':0.05},1.0))
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
