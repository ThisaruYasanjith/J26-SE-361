#!/usr/bin/env python3
"""Select reproducible MLCQ sample batches and retrieve original GitHub Java sources.

No labels are inferred from analyzer output. Retains per-sample vote counts and exact commit.
"""
import argparse,csv,hashlib,json,re,time,urllib.request,urllib.error
from collections import defaultdict,Counter
from pathlib import Path

FIELDS=['sample_id','smell','gold','positive_votes','negative_votes','repository','commit_hash','path','start_line','end_line','link']
def source_url(row):
    repo=row['repository'].strip()
    match=re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$',repo)
    if not match:return None
    owner,project=match.group(1),match.group(2)
    sha=row['commit_hash'].strip(); path=row['path'].strip().lstrip('/')
    if not re.fullmatch(r'[0-9a-f]{7,40}',sha,re.I) or not path.endswith('.java') or '..' in Path(path).parts:return None
    return f'https://raw.githubusercontent.com/{owner}/{project}/{sha}/{path}'

def run(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    with open(args.labels,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    required=set(FIELDS)
    if not rows or not required.issubset(rows[0]):raise ValueError('Missing aggregated_labels.csv fields: '+str(sorted(required-set(rows[0]) if rows else required)))
    chosen=[]
    for smell in ['long method','blob']:
        for gold in ['1','0']:
            pool=[r for r in rows if r['smell'].strip().lower()==smell and r['gold'].strip()==gold and source_url(r)]
            # Prefer stronger consensus; select across distinct repository paths first.
            pool.sort(key=lambda r:(-int(r['positive_votes'])-int(r['negative_votes']),r['repository'],r['sample_id']))
            selected=[];used=set()
            for row in pool:
                repo=row['repository']
                if repo not in used:
                    selected.append(row);used.add(repo)
                    if len(selected)>=args.per_class:break
            for row in pool:
                if len(selected)>=args.per_class:break
                if row not in selected:selected.append(row)
            chosen+=selected
    if not chosen:raise ValueError('No eligible samples; verify CSV and URLs.')
    manifest=[];cache={};failed=Counter()
    for i,r in enumerate(chosen,1):
        url=source_url(r)
        key=(r['repository'],r['commit_hash'],r['path'])
        if key not in cache:
            digest=hashlib.sha256(('|'.join(key)).encode()).hexdigest()[:16]
            local=out/'sources'/(digest+'.java');local.parent.mkdir(parents=True,exist_ok=True)
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'MLCQ-research-reproduction/1.0'})
                with urllib.request.urlopen(req,timeout=args.timeout) as resp:
                    content=resp.read(4*1024*1024+1)
                if len(content)>4*1024*1024:raise ValueError('source file >4MB')
                if not content.strip():raise ValueError('empty source')
                local.write_bytes(content);cache[key]=(str(local.relative_to(out)),hashlib.sha256(content).hexdigest(),'OK')
            except Exception as exc:
                cache[key]=('','','FETCH_FAILED: '+str(exc)[:160]);failed[type(exc).__name__]+=1
            time.sleep(args.delay)
        local,sha256,status=cache[key]
        manifest.append({**{k:r.get(k,'') for k in FIELDS},'source_url':url,'downloaded_path':local,'sha256':sha256,'fetch_status':status})
        if i%20==0:print(f'Processed {i}/{len(chosen)} samples; distinct sources: {len(cache)}',flush=True)
    with open(out/'source_manifest.csv','w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(manifest[0]));writer.writeheader();writer.writerows(manifest)
    stats={'selected_samples':len(chosen),'distinct_sources':len(cache),'fetched_samples':sum(x['fetch_status']=='OK' for x in manifest),'failed_samples':sum(x['fetch_status']!='OK' for x in manifest),'by_smell_gold':dict(Counter(f"{x['smell']}:{x['gold']}" for x in manifest)),'failures':dict(failed),'NOTE':'Human-reviewed MLCQ labels only; this is source preparation, not accuracy evaluation. Original full files may include unrelated methods; match exact sample line intervals.'}
    (out/'retrieval_summary.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    print(json.dumps(stats,indent=2))
    print('RESULTS:',out.resolve())

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--labels',required=True);ap.add_argument('--output',required=True);ap.add_argument('--per-class',type=int,default=20);ap.add_argument('--timeout',type=float,default=12);ap.add_argument('--delay',type=float,default=0.05);run(ap.parse_args())
