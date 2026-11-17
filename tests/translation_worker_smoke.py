"""Real isolated-worker QA with cached official NLLB weights; CPU only for this QA."""
import importlib.util,os,sys,types
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).parents[1];spec=importlib.util.spec_from_file_location('cloud',BASE/'colab/madar_cloud_tasks.py');cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud)
original=cloud.subprocess.Popen
code='import sys;sys.path.insert(0,'+repr(str(BASE/'colab'))+');from madar_cloud_tasks import serve_translation_worker;serve_translation_worker(device="cpu")'
def launch(args,**kwargs):return original([sys.executable,'-u','-c',code],**kwargs)
logs=[]
try:
 with patch.object(cloud.subprocess,'Popen',side_effect=launch),patch.dict(sys.modules,{'transformers':types.SimpleNamespace(__version__='stale-broken-parent')}):
  first=cloud.translate_lines(['1','00:00:00,000 --> 00:00:02,000','Hello, how are you?'],'en','ar',lambda *a:logs.append(a))
  pid=cloud._TRANSLATOR['process'].pid
  second=cloud.translate_lines(['Shin says hello.'],'en','ar',lambda *a:logs.append(a),{'Shin':'شين'})
  assert cloud._TRANSLATOR['process'].pid==pid
  assert first[:2]==['1','00:00:00,000 --> 00:00:02,000']
  assert first[2].strip() and 'شين' in second[0]
  assert any('النموذج جاهز' in message for _,message in logs)
  print('PASS: isolated from stale parent imports; timestamps retained; protected name retained; warm PID reused')
  print('REAL_TRANSLATION',first[2],second[0])
finally:cloud.stop_translator()
