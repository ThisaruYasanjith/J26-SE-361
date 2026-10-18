"""Colab T4 QLoRA *smoke test* (NOT scientific model comparison).
Upload train_pilot.jsonl and holdout_pilot.jsonl via the Colab upload prompt.
Runs in one Colab code cell via: exec(open('colab_qlora_pilot.py').read())
Needs GPU and current compatible Transformers/PEFT installed.
"""
import json, torch
from pathlib import Path
from google.colab import files
from transformers import (AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig,
                          TrainingArguments,Trainer,DataCollatorForLanguageModeling)
from peft import LoraConfig,prepare_model_for_kbit_training,get_peft_model
print('Upload: train_pilot.jsonl and holdout_pilot.jsonl')
up=files.upload()
train=json.loads(up['train_pilot.jsonl'].decode('utf-8'))
hold=json.loads(up['holdout_pilot.jsonl'].decode('utf-8'))
assert train['source_project']!=hold['source_project'], 'PROJECT LEAKAGE'
assert train['status']=='USER_APPROVED_SOURCE_REVIEWED_NOT_BEHAVIOR_TESTED'
name='Qwen/Qwen2.5-Coder-7B-Instruct'
# Free GPU memory before loading; reuse loaded Qwen tokenizer but reload a clean model for LoRA
if 'model' in globals():
    del model
    import gc;gc.collect();torch.cuda.empty_cache()
quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
tok=AutoTokenizer.from_pretrained(name)
tok.pad_token=tok.eos_token
model=AutoModelForCausalLM.from_pretrained(name,quantization_config=quant,device_map={'':0},dtype=torch.float16)
model.config.use_cache=False
model=prepare_model_for_kbit_training(model)
model=get_peft_model(model,LoraConfig(r=8,lora_alpha=16,lora_dropout=0.05,bias='none',task_type='CAUSAL_LM',target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj']))
model.print_trainable_parameters()
# Mask user/system tokens: loss is supervised on assistant response only.
def vectorize(item):
    msgs=item['messages']
    prompt=tok.apply_chat_template(msgs[:-1],tokenize=False,add_generation_prompt=True)
    full=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=False)
    prompt_ids=tok(prompt,add_special_tokens=False)['input_ids']
    full_ids=tok(full,add_special_tokens=False)['input_ids']
    assert full_ids[:len(prompt_ids)]==prompt_ids, 'Chat template prefix mismatch: stop and inspect'
    assert len(full_ids)<=4096, f'Sample exceeds 4096 tokens: {len(full_ids)}'
    labels=[-100]*len(prompt_ids)+full_ids[len(prompt_ids):]
    return {'input_ids':full_ids,'attention_mask':[1]*len(full_ids),'labels':labels}
class OneExample(torch.utils.data.Dataset):
    def __init__(self,entry):self.entry=entry
    def __len__(self):return 1
    def __getitem__(self,index):return self.entry
class PadBatch:
    def __call__(self,examples):
        maxlen=max(len(x['input_ids']) for x in examples)
        return {k:torch.tensor([x[k]+([(-100 if k=='labels' else 0)]*(maxlen-len(x[k]))) for x in examples],dtype=torch.long) for k in ('input_ids','attention_mask','labels')}
trainset=OneExample(vectorize(train))
args=TrainingArguments(output_dir='/content/qlora_pilot_output',per_device_train_batch_size=1,gradient_accumulation_steps=1,max_steps=5,learning_rate=1e-4,logging_steps=1,save_strategy='no',report_to='none',fp16=True,gradient_checkpointing=True,remove_unused_columns=False)
trainer=Trainer(model=model,args=args,train_dataset=trainset,data_collator=PadBatch())
trainer.train()
model.save_pretrained('/content/qlora_pilot_adapter')
tok.save_pretrained('/content/qlora_pilot_adapter')
print('PILOT COMPLETE: 5 update steps on ONE training record; NO scientific performance claim')
print('Adapter: /content/qlora_pilot_adapter (download/Drive-copy before session disconnect)')
print('Holdout was NOT used in training:',hold['case_id'])
