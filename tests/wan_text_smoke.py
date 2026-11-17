"""Reproduce and repair Wan 0.35.1 text setup using the actual wheel's functions.
Run: PYTHONPATH=<ftfy packages> python tests/wan_text_smoke.py <diffusers wheel>
No model weights, GPU, or network calls are used.
"""
import ast,html,re,sys,zipfile
import ftfy
with zipfile.ZipFile(sys.argv[1]) as wheel:source=wheel.read('diffusers/pipelines/wan/pipeline_wan.py').decode()
functions=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in {'basic_clean','whitespace_clean','prompt_clean'}]
code=compile(ast.Module(body=functions,type_ignores=[]),'real_diffusers_wan_text','exec');old={'html':html,'re':re};exec(code,old)
try:old['prompt_clean']('Madar')
except NameError as e:assert e.name=='ftfy'
else:raise AssertionError('expected to reproduce missing ftfy')
fixed={'html':html,'re':re,'ftfy':ftfy};exec(code,fixed)
assert fixed['prompt_clean']('  Madar &amp; video  ')=='Madar & video'
assert fixed['prompt_clean']('  مشهد   عربي  ')=='مشهد عربي'
print('PASS: actual Wan text path reproduces ftfy NameError and succeeds with explicit dependency')
