import json
from pathlib import Path
root=Path(__file__).resolve().parent
install='''import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "audio-separator[gpu]==0.48.0", "onnxruntime-gpu[cuda,cudnn]==1.22.0", "nvidia-cublas-cu12>=12,<13"])
print("تم تجهيز المكتبات. شغّل الخلية التالية لاختبار GPU.")'''
runtime=(root/'madar_colab_runtime.py').read_text()+'\nGPU_DEVICE = prepare_gpu()\n'
choose='''#@title اختر المصدر من داخل Colab
source_mode = "رفع ملف" #@param ["رفع ملف", "ملف من Google Drive"]
drive_path = "" #@param {type:"string"}
from pathlib import Path
if source_mode == "ملف من Google Drive":
    from google.colab import drive
    drive.mount("/content/drive")
    SOURCE = Path(drive_path).expanduser().resolve()
    if not SOURCE.is_file():
        raise ValueError("أدخل المسار الكامل للملف الموجود في Drive ثم أعد تشغيل هذه الخلية")
else:
    from google.colab import files
    uploaded = files.upload()
    if len(uploaded) != 1:
        raise ValueError("ارفع ملفًا واحدًا ثم أعد تشغيل الخلية")
    SOURCE = Path(next(iter(uploaded))).resolve()
    del uploaded
print("المصدر:", SOURCE.name, "·", round(SOURCE.stat().st_size/1024**2,1), "MB")'''
run='''#@title فصل الموسيقى على GPU — المدة 0 لكامل الملف
start_seconds = 0 #@param {type:"number"}
duration_seconds = 0 #@param {type:"number"}
output_type = "صوت M4A" #@param ["صوت M4A", "فيديو MKV"]
RESULT = run_separation(SOURCE, start=start_seconds, duration=duration_seconds, mode="video" if output_type=="فيديو MKV" else "audio")
from IPython.display import display, FileLink
display(FileLink(str(RESULT)))
print("شغّل خلية التنزيل التالية لحفظ النتيجة على جهازك.")'''
download='''#@title تنزيل النتيجة
from google.colab import files
if "RESULT" not in globals() or not RESULT.is_file():
    raise RuntimeError("شغّل خلية الفصل أولًا وانتظر اكتمالها")
files.download(str(RESULT))'''
intro='''# مدار — إزالة الموسيقى على Colab فقط
هذا الدفتر يُشغَّل داخل حسابك أنت. لا ينشئ نفقًا أو خادمًا عامًا أو رمز ربط أو واجهة تحكم خارجية، ولا يحتاج كلمة مرور Google داخل مدار.

1. اختر **وقت التشغيل ← تغيير نوع وقت التشغيل ← T4 GPU**.
2. شغّل خليتي التثبيت واختبار GPU بالترتيب. إذا فشل CUDA، يتوقف الدفتر بدل الرجوع إلى CPU.
3. ارفع المصدر من خلية اختيار الملف، أو اختر مسار ملف في Google Drive. خيار Drive يحتاج موافقتك داخل Google ويتيح للدفتر الوصول إلى Drive؛ استخدم الرفع المباشر إذا لم ترغب بذلك.
4. شغّل خلية الفصل. **المدة 0 = كامل الملف**، أو حدد البداية والمدة. لا يوجد حد 3 دقائق ولا فحص 5 دقائق ونصف.
5. شغّل خلية التنزيل لحفظ النتيجة. ملفات الجلسة مؤقتة وتضيع عند حذف وقت التشغيل.

الفصل في أجزاء داخلية مدة كل منها 5 دقائق لتقليل الذاكرة؛ هذا لا يحد مدة المصدر. يُحفظ التقدم داخل الجلسة، ويمكن إعادة تشغيل خلية الفصل بنفس الملف والإعدادات لاستكمال الأجزاء السليمة. انتهاء الجلسة يفقد هذا التقدم.

الناتج الافتراضي صوت M4A. خيار فيديو MKV يحتفظ بالصورة والترجمات المضمنة بالنسخ عند فصل الملف كاملًا؛ عند اختيار جزء يُعاد ترميز الصورة لضبط البداية. توافق MKV يعتمد على مشغلك.

النموذج يستهدف إبقاء الصوت البشري، وقد يفقد بعض البيئة أو المؤثرات أو يبقي آثار موسيقى. راجع الناتج قبل اعتماده. توفر GPU والوقت والمساحة يخضع لحدود حساب Colab ولا يُضمن.

لا تشارك نسخة من الدفتر تحتوي على مخرجات أو أسماء ملفات خاصة. لا تتطلب هذه النسخة مفاتيح Groq أو Gemini أو اتصالًا بحساب صاحب مدار.
'''
cells=[{'id':'madar-intro','cell_type':'markdown','metadata':{},'source':intro.splitlines(True)}]
for index,code in enumerate([install,runtime,choose,run,download]):
 cells.append({'id':'madar-code-'+str(index),'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':code.splitlines(True)})
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'Madar_Colab_Separation.ipynb','provenance':[]},'kernelspec':{'name':'python3','display_name':'Python 3'},'accelerator':'GPU'},'cells':cells}
(root/'Madar_Colab_Separation.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=2))
