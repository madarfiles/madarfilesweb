"""Fixed-schema ASS text and PNG composition. No user filter expressions."""
import base64,io,json,re,shutil,subprocess
from pathlib import Path

def dimensions(source):
 data=json.loads(subprocess.check_output(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-select_streams','v:0','-show_streams','-of','json',str(source)],timeout=30));stream=data['streams'][0];w,h=int(stream['width']),int(stream['height'])
 rotation=next((x['rotation'] for x in stream.get('side_data_list',[]) if 'rotation' in x),stream.get('tags',{}).get('rotate',0))
 if abs(int(rotation))%180==90:w,h=h,w
 if min(w,h)<1 or w*h>33000000:raise ValueError('أبعاد الفيديو كبيرة')
 return w,h

def number(s,k,a,b,d):
 n=s.get(k,d)
 if isinstance(n,bool) or not isinstance(n,(int,float)) or not a<=n<=b:raise ValueError('قيمة تنسيق غير صالحة')
 return float(n)

def ass_text(text,s,w,h):
 family={'sans':'DejaVu Sans','amiri':'Amiri'}[s.get('fontFamily','sans')];weight={'400':0,'700':-1}[s.get('fontWeight','400')];color=s.get('fontColor','#ffffff')
 if not re.fullmatch('#[a-fA-F0-9]{6}',color):raise ValueError('لون غير صالح')
 color='&H00'+color[5:7]+color[3:5]+color[1:3];size=h*number(s,'fontSizePct',1,12,4)/100;x=w*number(s,'x',0,100,50)/100;y=h*number(s,'y',0,100,90)/100
 if not isinstance(s.get('background',False),bool):raise ValueError('خلفية غير صالحة')
 header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{family},{size:.3f},{color},{color},&H801A211D,&H801A211D,{weight},0,0,0,100,100,0,0,{3 if s.get('background') else 1},{max(1,size*.055):.3f},0,5,{round(w*.05)},{round(w*.05)},0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
 def clock(t):
  a,b,c,d=map(int,re.split('[:,.]',t))
  if b>59 or c>59:raise ValueError('توقيت غير صالح')
  return f'{a}:{b:02}:{c:02}.{d//10:02}'
 out=[]
 for m in re.finditer(r'(\d{1,3}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{1,3}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)',text.replace('\r',''),re.S):
  line=re.sub(r'<[^>]{0,200}>','',m[3]).replace('\\','＼').replace('{','｛').replace('}','｝').strip().replace('\n',r'\N')
  if line:out.append(f'Dialogue: 0,{clock(m[1])},{clock(m[2])},Default,,0,0,0,,{{\\an5\\pos({x:.3f},{y:.3f})}}{line}')
 if not out:raise ValueError('ملف التوقيت لا يحتوي أسطرًا صالحة')
 return header+'\n'.join(out)+'\n'

def fonts(root):
 folder=root/'fonts';folder.mkdir(exist_ok=True)
 try:
  from madar_fonts import FONT_ASSETS
  for name,data in FONT_ASSETS.items():
   if name not in {'DejaVuSans.ttf','DejaVuSans-Bold.ttf','Amiri-Regular.ttf','Amiri-Bold.ttf'}:raise ValueError('خط غير صالح')
   (folder/name).write_bytes(base64.b64decode(data,validate=True))
 except ModuleNotFoundError:
  local=Path(__file__).parents[1]/'src'/'fonts'
  for p in local.glob('*.ttf'):shutil.copyfile(p,folder/p.name)
 return folder

def burn(source,cfg,root,report,codec,run,legacy_style):
 w,h=dimensions(source);fontdir=fonts(root);s=cfg.get('captionStyle');subtitle=root/('captions.ass' if s else 'captions.srt');subtitle.write_text(ass_text(cfg['subtitles'],s,w,h) if s else cfg['subtitles'],encoding='utf-8');vf=f'subtitles={subtitle}:fontsdir={fontdir}'
 if not s:vf+=f":force_style='{legacy_style(cfg)}'"
 inputs=['-i',source];filters=['-vf',vf,'-map','0:v:0','-map','0:a:0?'];logo=cfg.get('logoPng','')
 if logo:
  from PIL import Image
  if not isinstance(logo,str) or len(logo)>480000:raise ValueError('الشعار كبير')
  raw=base64.b64decode(logo,validate=True)
  if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('الشعار ليس PNG')
  image=Image.open(io.BytesIO(raw))
  if min(image.size)<1 or image.width*image.height>1048576:raise ValueError('أبعاد الشعار كبيرة')
  s=s or {};lw=max(1,round(w*number(s,'logoWidth',4,40,15)/100));lh=max(1,round(lw*image.height/image.width))
  if lh>h:raise ValueError('قلّل حجم الشعار')
  x=round((w-lw)*number(s,'logoX',0,100,95)/100);y=round((h-lh)*number(s,'logoY',0,100,5)/100);alpha=number(s,'logoOpacity',10,100,100)/100
  path=root/'logo.png';image.convert('RGBA').resize((lw,lh)).save(path);inputs+=['-loop','1','-i',path];filters=['-filter_complex',f'[0:v]{vf}[text];[1:v]format=rgba,colorchannelmixer=aa={alpha:.4f}[logo];[text][logo]overlay={x}:{y}:shortest=1[v]','-map','[v]','-map','0:a:0?']
 out=root/'result.mp4';tail=['-c:a','aac','-b:a','160k','-map_metadata','-1','-movflags','+faststart',out]
 try:run([*inputs,*filters,*codec,*tail])
 except subprocess.CalledProcessError:
  if 'h264_nvenc' not in codec:raise
  report('processing','استكمال تصدير الفيديو على CPU');run([*inputs,*filters,'-c:v','libx264','-preset','veryfast','-crf','23',*tail])
 return out
