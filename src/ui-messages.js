// Product copy for progress and failures. Technical details remain opt-in.
export function userProgress(value){
 const text=String(value||'').replace(/\s*· عامل الجلسة متصل/g,'').trim();
 if(/NVENC|ترميز CPU|ترميز الفيديو على GPU/.test(text))return 'جارٍ تجهيز الفيديو للحفظ…';
 if(/NLLB|Whisper|PyTorch|CUDA|تهيئة بيئة|مكتبات الأداة|تنزيل النموذج|تحميل النموذج|تجهيز نموذج|تحميل محرك|تثبيت المحرك/.test(text))return 'جارٍ تجهيز الأداة؛ قد يستغرق الاستخدام الأول وقتًا أطول…';
 if(/انتظار تخصيص GPU|إنشاء جلسة|تخصيص (T4|L4|A100)/.test(text))return 'جارٍ تجهيز جلستك السحابية…';
 if(/اكتمل\. نزّل النتيجة/.test(text))return 'النتيجة جاهزة. عاينها ثم احفظها على جهازك.';
 return text.replace(/\s*·\s*[A-Z][A-Z0-9_]{4,}\b/g,'').trim()||'جارٍ المعالجة…';
}
export function userFailure(error){
 const code=error?.code||String(error?.message||error||'').match(/\b(?:CONTENT_REVIEW_REQUIRED|CONTENT_REVIEW_ERROR|[A-Z]+_[A-Z_]+)\b/)?.[0];
 const mediaMessages={MEDIA_NO_VIDEO:'المصدر صوت فقط. اختر صيغة صوتية بدل الفيديو.',MEDIA_NO_AUDIO:'المقطع لا يحتوي على مسار صوت يمكن فصله.',MEDIA_DECODER_UNAVAILABLE:'ترميز المصدر غير متاح في محرك هذه الجلسة.',MEDIA_INVALID_INPUT:'تعذر قراءة الملف. تحقق من سلامته واكتماله.',MEDIA_DISK_FULL:'امتلأت مساحة الجلسة. احفظ نتائجك ثم أنهِ الجلسات غير المستخدمة.',MEDIA_RESOURCE_BUSY:'موارد معالجة الوسائط مشغولة. أعد المحاولة بعد انتهاء العمليات الأخرى.',MEDIA_TIMEOUT:'انتهت مهلة معالجة الوسائط. جرّب جزءًا أقصر أو استرجع العملية.'};if(mediaMessages[code])return mediaMessages[code];
 if(error?.name==='AbortError')return 'توقف الانتظار. يمكنك استرجاع العملية أو إنهاء جلستها.';
 if(error?.status===401)return 'انتهى الاتصال بحسابك. أعد الاتصال ثم استرجع العملية.';
 if(code==='CONTENT_REVIEW_REQUIRED')return 'تعذّر عرض النتيجة بعد فحص المحتوى. يمكنك مراجعة وصف المشهد.';
 if(code==='CONTENT_REVIEW_ERROR')return 'تعذّر إكمال فحص النتيجة. يمكنك إعادة المحاولة لاحقًا.';
 if(/RESOURCE|TOO_MANY_ACTIVE|GPU_UNAVAILABLE/.test(code||''))return 'المورد السحابي غير متاح حاليًا. راجع الجلسات النشطة أو اختر موردًا آخر من الإعدادات المتقدمة.';
 if(code==='GPU_MEMORY')return 'المورد المختار لا يكفي لهذه العملية. قلّل المدة أو اختر موردًا أكبر.';
 if(/TIMEOUT|NETWORK|WORKER_STOPPED/.test(code||''))return 'انقطع الاتصال أو تأخر الرد. يمكنك استرجاع العملية دون بدء رفع جديد.';
 if(/^(TOOL_|MODEL_|PYTHON_|DEPENDENCY_|GPU_LIBRARY)/.test(code||''))return 'تعذّر تجهيز الأداة أو إكمال المعالجة. أعد المحاولة، أو انسخ تفاصيل الدعم إذا تكرر ذلك.';
 const message=String(error?.message||error||'');
 if(error instanceof TypeError||!/[\u0600-\u06ff]/.test(message))return 'تعذّر إكمال الطلب. تحقق من اتصالك ثم أعد المحاولة.';
 return userProgress(message);
}
