import test from 'node:test';import assert from 'node:assert/strict';
import {userProgress,userFailure} from '../src/ui-messages.js';
test('product progress preserves transfer progress but hides engine internals',()=>{
 assert.equal(userProgress('تنزيل النتيجة · 42٪ · المتبقي نحو 8 ثانية'),'تنزيل النتيجة · 42٪ · المتبقي نحو 8 ثانية');
 assert.doesNotMatch(userProgress('NVENC غير متاح؛ تجهيز الفيديو على CPU · عامل الجلسة متصل'),/NVENC|CPU|عامل/);
 assert.doesNotMatch(userProgress('تحميل نموذج الترجمة NLLB إلى GPU'),/NLLB|GPU/);
});
test('review, resource and connection failures give distinct actionable messages',()=>{
 assert.match(userFailure({code:'CONTENT_REVIEW_REQUIRED',message:'internal'}),/فحص المحتوى/);
 assert.match(userFailure({code:'RESOURCE_LIMIT_OR_UNAVAILABLE'}),/غير متاح/);
 assert.match(userFailure({status:401}),/أعد الاتصال/);
 assert.match(userFailure({code:'COLAB_TIMEOUT'}),/استرجاع العملية/);
 assert.doesNotMatch(userFailure(Error('تعذر التنفيذ · TOOL_IMPORTERROR')),/TOOL_|IMPORT/);
 assert.equal(userFailure(Error('اختر الملف أولًا')),'اختر الملف أولًا');
});
