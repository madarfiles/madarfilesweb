"""Optional real-weight CPU regression. No downloads and no unsafe fixtures.

python tests/video_review_smoke.py --video-model /path/to/local/Falconsai \
  --legacy-model /path/to/local/CompVis --reference-image /path/to/known-safe.jpg
Requires torch, transformers, diffusers, numpy and Pillow. Never changes weights.
"""
import argparse,importlib.util,json
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch
from PIL import Image

parser=argparse.ArgumentParser()
parser.add_argument('--video-model',required=True)
parser.add_argument('--legacy-model')
parser.add_argument('--reference-image',action='append',default=[])
args=parser.parse_args()
torch.set_num_threads(2)
spec=importlib.util.spec_from_file_location('video_review_cloud',Path(__file__).parents[1]/'colab/madar_cloud_tasks.py')
cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud)
fixtures=[(name,Image.new('RGB',(512,288),color)) for name,color in [('solid-blue',(40,80,120)),('black',(0,0,0)),('white',(255,255,255)),('red',(255,0,0))]]
fixtures += [(Path(p).name,Image.open(p).convert('RGB')) for p in args.reference_image]
# Exercise the production loader, preprocessing and numerical decision code.
with patch.object(cloud,'VIDEO_REVIEW_MODEL',str(Path(args.video_model).resolve())):
 checker,processor=cloud.video_safety_components(device='cpu')
for name,image in fixtures:
 decisions=[]
 for batch in [[image],[image]*4]:
  pixels=processor(images=batch,return_tensors='pt').pixel_values.to('cpu',dtype=torch.float32)
  with torch.inference_mode():_,flags=checker(images=np.zeros((len(batch),1,1,3)),clip_input=pixels)
  assert flags==[False]*len(batch),(name,flags)
  decisions.append(flags)
 print(json.dumps({'fixture':name,'newClassifierFlags':decisions}),flush=True)
# Numerical policy tests do not require explicit/unsafe pictures.
assert cloud.video_content_flags(torch.tensor([[10.,-10.],[-10.,10.],[0.,0.]]),{0:'normal',1:'nsfw'})==[False,True,True]
assert cloud.video_content_flags(torch.tensor([[10.,-10.],[-10.,10.]]),{0:'nsfw',1:'normal'})==[True,False]
for logits,labels in [(torch.tensor([[float('nan'),0.]]),{0:'normal',1:'nsfw'}),(torch.zeros((1,3)),{0:'normal',1:'nsfw'}),(torch.zeros((1,2)),{0:'safe',1:'unknown'})]:
 try:cloud.video_content_flags(logits,labels)
 except ValueError:pass
 else:raise AssertionError('malformed review must fail closed')
if args.legacy_model:
 from diffusers.pipelines.stable_diffusion.safety_checker import StableDiffusionSafetyChecker
 from transformers import CLIPImageProcessor
 old=StableDiffusionSafetyChecker.from_pretrained(args.legacy_model,torch_dtype=torch.float32,local_files_only=True).eval()
 pre=CLIPImageProcessor.from_pretrained(args.legacy_model,local_files_only=True)
 blue=fixtures[0][1]
 with torch.inference_mode():_,flags=old(images=np.asarray(blue,dtype=np.float32)[None]/255,clip_input=pre(images=[blue],return_tensors='pt').pixel_values)
 assert flags==[True],flags
 print('Reproduced legacy false positive on constant blue; new classifier passed.',flush=True)
print('PASS: real-weight safe references, batching, label mapping, blocking and invalid-output decisions.',flush=True)
