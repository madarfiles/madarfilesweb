"""Real PyTorch/Transformers regression. Run with the optional model QA Python."""
import importlib.util,os,sys,tempfile,types,json
from pathlib import Path
from unittest.mock import patch
import torch
from safetensors.torch import save_file
from transformers import M2M100Config,M2M100ForConditionalGeneration,AutoModelForSeq2SeqLM
BASE=Path(__file__).parents[1];spec=importlib.util.spec_from_file_location('cloud',BASE/'colab/madar_cloud_tasks.py');cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud)
config=M2M100Config(vocab_size=64,d_model=16,encoder_layers=1,decoder_layers=1,encoder_attention_heads=2,decoder_attention_heads=2,encoder_ffn_dim=32,decoder_ffn_dim=32)
with tempfile.TemporaryDirectory() as d:
 torch.manual_seed(7);reference=M2M100ForConditionalGeneration(config).eval();reference.config.save_pretrained(d)
 aliases={k:'model.decoder.embed_tokens.weight' for k in ['model.shared.weight','model.encoder.embed_tokens.weight','lm_head.weight']}
 weights={k:v.clone().contiguous() for k,v in reference.state_dict().items() if k not in aliases}
 save_file(weights,str(Path(d)/'model.safetensors'),metadata={'format':'pt',**aliases})
 broken=AutoModelForSeq2SeqLM.from_pretrained(d,use_safetensors=True)
 assert any(p.is_meta for p in broken.parameters()),'fixture must reproduce upstream alias failure'
 try:broken.to('cpu')
 except NotImplementedError:pass
 else:raise AssertionError('old path unexpectedly succeeded')
 fixed=cloud.load_nllb_weights(d,None,'cpu');assert not any(p.is_meta for p in fixed.parameters())
 for key,value in reference.state_dict().items():torch.testing.assert_close(fixed.state_dict()[key],value,rtol=0,atol=0)
 x=torch.tensor([[2,4,6,2]])
 with torch.inference_mode():torch.testing.assert_close(reference(input_ids=x,decoder_input_ids=x).logits,fixed(input_ids=x,decoder_input_ids=x).logits)
 print('PASS: reproduced meta alias failure; strict loader restores every weight and logits')
