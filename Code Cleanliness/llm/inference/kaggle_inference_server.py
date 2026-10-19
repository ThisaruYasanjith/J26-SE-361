"""Kaggle notebook inference gateway: run AFTER loading `model` and `tokenizer`.
One-shot run: exec(open('/kaggle/working/kaggle_inference_server.py').read())
Port 8766 is bound to notebook loopback. A private bearer token protects a
temporary Cloudflare quick tunnel (subject to Kaggle network policies).
Do not publish tunnel URL or bearer token in source control/screenshots.
"""
import json, os, re, secrets, subprocess, threading, time
from pathlib import Path
from urllib.request import urlretrieve
import torch
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
import uvicorn

assert 'model' in globals() and 'tokenizer' in globals(), 'Run the Kaggle Qwen+adapter loading cell first.'
assert torch.cuda.is_available(), 'GPU unavailable.'
model.eval()
access_token = secrets.token_urlsafe(32)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
model_lock = threading.Lock()
class ExplainPayload(BaseModel):
    task: str
    schema_version: str
    group: dict
    constraints: list[str] = Field(default_factory=list)

@app.get('/health')
def health(authorization: str | None = Header(default=None)):
    if authorization != 'Bearer ' + access_token:
        raise HTTPException(401, 'Unauthorized')
    return {'status':'ready','model':'Qwen2.5-Coder-7B-Instruct + pilot LoRA'}

@app.post('/explain')
def explain(body: ExplainPayload, authorization: str | None = Header(default=None)):
    if authorization != 'Bearer ' + access_token:
        raise HTTPException(401, 'Unauthorized')
    if body.task != 'explain_maintainability_evidence' or body.schema_version != '1.1':
        raise HTTPException(422, 'Incorrect task or schema')
    if len(json.dumps(body.group)) > 15000:
        raise HTTPException(413, 'Evidence too large')
    findings = body.group.get('findings')
    if not isinstance(findings, list) or not (1 <= len(findings) <= 35) or not all(isinstance(f,dict) for f in findings):
        raise HTTPException(422, 'Invalid findings')
    system = ('You explain Java maintainability concerns grounded strictly in supplied analyzer evidence. '
        'Do not invent metrics, unobserved code, runtime bugs, guaranteed improvements, or after-refactoring outcomes. '
        'All rules, thresholds and ranks are preliminary. State the measured evidence first, explain a cautious '
        'refactoring direction only when justified, and note what requires independent verification. '
        'Do not conflate code quality concerns with architecture, requirements drift or runtime issue detection. '
        'Identical normalized fingerprints are screening signals, not proof of semantic equivalence or permission to merge methods. ' 'Do not claim that private helpers can be shared across classes without checking scope and dependencies. ' 'Separate observed evidence, possible maintenance impact, cautious refactoring direction and verification. ' 'Keep the explanation concise and developer-friendly, preferably under 180 words.')
    content = json.dumps({'rank':body.group.get('rank'), 'ranking_explanation':body.group.get('ranking_explanation'),
                          'findings':findings},ensure_ascii=False)
    prompt = tokenizer.apply_chat_template([{'role':'system','content':system},{'role':'user','content':content}],
                                           tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt,return_tensors='pt',add_special_tokens=False).to('cuda')
    n = inputs['input_ids'].shape[1]
    if n > 5500: raise HTTPException(413,'Prompt too large')
    with model_lock, torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=250, do_sample=False,
                                   pad_token_id=tokenizer.eos_token_id, eos_token_id=tokenizer.eos_token_id)
    result = tokenizer.decode(generated[0, n:],skip_special_tokens=True).strip()
    if not result: raise HTTPException(500,'Empty generation')
    return {'explanation':result}

server_thread = threading.Thread(target=lambda: uvicorn.run(app,host='127.0.0.1',port=8766,log_level='warning'),daemon=True)
server_thread.start()
time.sleep(2)
print('Kaggle Qwen local API initialized at 127.0.0.1:8766')
cloudflared = '/kaggle/working/cloudflared'
if not Path(cloudflared).exists():
    urlretrieve('https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64',cloudflared)
    os.chmod(cloudflared,0o755)
process = subprocess.Popen([cloudflared,'tunnel','--url','http://127.0.0.1:8766','--no-autoupdate'],
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
url_result = []
last_lines = []
def capture():
    for line in process.stdout:
        last_lines.append(line.strip())
        if len(last_lines)>30: last_lines.pop(0)
        m=re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com',line)
        if m and not url_result: url_result.append(m.group())
threading.Thread(target=capture,daemon=True).start()
for _ in range(40):
    if url_result or process.poll() is not None: break
    time.sleep(1)
if not url_result:
    print('Tunnel blocked or unavailable. Kaggle may restrict external tunnels.')
    print('Last diagnostic lines:', '\n'.join(last_lines[-8:]))
    raise RuntimeError('Kaggle tunnel did not start; Qwen model remains loaded.')
print('\n=== PRIVATE CONNECTION DETAILS: DO NOT SHARE TOKEN ===')
print('TUNNEL URL:',url_result[0])
print('ACCESS TOKEN:',access_token)
print('======================================================')
print('Start windows_bridge.py on Windows, then click Generate explanation in VS Code.')
print('Keep Kaggle notebook session active; endpoints are temporary.')
