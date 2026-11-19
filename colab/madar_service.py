"""Single persistent, fixed-code worker. One job at a time; model/disk cache stays in session."""
import gc, json, os, signal, subprocess, sys, time, threading
from pathlib import Path
BASE=Path(__file__).resolve().parent
VERSION=19

def atomic(path,data):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False));tmp.replace(path)

def bootstrap():
 import fcntl
 setup=open(BASE/'bootstrap.lock','a');fcntl.flock(setup,fcntl.LOCK_EX)
 try:
  health=json.loads((BASE/'service.json').read_text())
  if time.time()-health.get('heartbeat',0)<30:
   pid=int(health['pid']);os.kill(pid,0)
   if health.get('version')==VERSION:return
   if health.get('activeJob'):raise RuntimeError('WORKER_UPGRADE_BUSY')
   os.kill(pid,signal.SIGTERM)
   for _ in range(30):
    try:os.kill(pid,0)
    except ProcessLookupError:break
    time.sleep(.1)
 except (OSError,ValueError,KeyError):pass
 pending=[p.parent for p in (BASE/'jobs').glob('*/ready') if not (p.parent/'started.lock').exists()]
 for root in pending:atomic(root/'state.json',{'state':'setup','message':'بدء عامل الأداة باستخدام Python المثبّت في Colab','updated':time.time()})
 try:
  subprocess.Popen([sys.executable,'-u',str(BASE/'service.py'),'serve'],cwd=BASE,stdout=open(BASE/'service.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
 except Exception as exc:
  code='WORKER_LAUNCH_'+type(exc).__name__.upper()
  for root in pending:atomic(root/'state.json',{'state':'error','message':'تعذر إطلاق عامل الأداة داخل Colab · '+code,'code':code,'updated':time.time()})

def environment():
 os.environ['USE_TF']='0';os.environ['USE_FLAX']='0';os.environ['HF_HUB_ETAG_TIMEOUT']='60';os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='120';os.environ['TOKENIZERS_PARALLELISM']='false'
 os.environ['HF_HOME']=str(BASE/'cache/huggingface');os.environ['U2NET_HOME']=str(BASE/'cache/rembg');os.environ['XDG_CACHE_HOME']=str(BASE/'cache')

def warm(tool):
 """Installs a tool's libraries and downloads its model files while the file uploads.
 One preparation per tool and session; it never touches the GPU or a job."""
 import fcntl
 lock=open(BASE/('warm-'+tool+'.lock'),'a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:return
 if (BASE/('warm-'+tool+'.json')).exists():return
 environment();sys.path.insert(0,str(BASE))
 started=time.time()
 try:
  import madar_cloud_tasks
  done=madar_cloud_tasks.warm(tool)
 except BaseException as exc:done=['failed:'+type(exc).__name__]
 atomic(BASE/('warm-'+tool+'.json'),{'tool':tool,'steps':done,'seconds':round(time.time()-started,1),'finished':time.time()})

def serve():
 import fcntl
 lock=open(BASE/'service.lock','a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:return
 environment()
 idle=time.monotonic();last_task=None;health={'version':VERSION,'pid':os.getpid(),'idleMinutes':40,'activeJob':None}
 done=threading.Event()
 def heartbeat():
  while not done.is_set():
   try:
    lease=json.loads((BASE/'lease.json').read_text())
    if time.time()-float(lease['updated'])>300:
     atomic(BASE/'service.json',{'version':VERSION,'state':'page-disconnected','heartbeat':time.time()})
     cloud=sys.modules.get('madar_cloud_tasks')
     if cloud:cloud.stop_translator()
     os._exit(0)  # worker only; Google allocation deletion is a separate API request.
   except (OSError,ValueError,KeyError):pass
   atomic(BASE/'service.json',{**health,'heartbeat':time.time()});done.wait(5)
 threading.Thread(target=heartbeat,daemon=True).start()

 while time.monotonic()-idle<2400:
  candidates=sorted((BASE/'jobs').glob('*/config.json'),key=lambda p:p.stat().st_mtime)
  for cfgpath in candidates:
   root=cfgpath.parent
   if not (root/'ready').exists() or (root/'started.lock').exists():continue
   idle=time.monotonic();cfg=json.loads(cfgpath.read_text());task=cfg.get('task','separate')
   if last_task and last_task!=task:
    cloud=sys.modules.get('madar_cloud_tasks')
    if cloud:cloud.release_models()
    gc.collect()
   health['activeJob']=root.name
   import runner
   runner.ROOT=root
   try:runner.main()
   except BaseException:
    atomic(root/'state.json',{'state':'error','message':'توقف عامل المعالجة؛ أعد المحاولة في الجلسة نفسها · WORKER_FAILED','code':'WORKER_FAILED','updated':time.time()})
   try:
    if json.loads((root/'state.json').read_text()).get('state')=='error':
     cloud=sys.modules.get('madar_cloud_tasks')
     if cloud:cloud.release_models()
   except (OSError,ValueError):pass
   sys.stdout=sys.__stdout__;health['activeJob']=None;last_task=task;idle=time.monotonic()
  time.sleep(1)
 done.set()
 atomic(BASE/'service.json',{'version':VERSION,'state':'idle-ended','heartbeat':time.time()})

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='serve':serve()
 elif len(sys.argv)>2 and sys.argv[1]=='warm' and sys.argv[2] in {'separate','dub','asr','translate'}:warm(sys.argv[2])
 else:bootstrap()
