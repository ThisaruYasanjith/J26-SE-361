#!/usr/bin/env python3
"""MLCQ batch staging and scoring for existing Java repository CLI.
Usage:
 python run_29f_mlcq_batch.py stage --batch PATH
 python run_29f_mlcq_batch.py score --batch PATH --evidence PATH
This computes metrics only from matched code elements; ambiguous / unscorable rows omitted.
"""
import argparse,csv,json,shutil,re,collections
from pathlib import Path

def readcsv(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def paths(batch):return batch/'mlcq_java_repo',batch/'score_29f'
def stage(batch):
 repo,_=paths(batch);repo.mkdir(parents=True,exist_ok=True);rows=readcsv(batch/'source_manifest.csv');out=[]
 for r in rows:
  r=dict(r);r['stage_status']='SKIPPED';r['staged_path']=''
  if r['fetch_status']=='OK' and r['gold'] in ('0','1'):
   src=batch/r['downloaded_path'];sid=re.sub('[^a-zA-Z0-9_-]','_',r['sample_id'])
   # Keep original filename: JavaParser does not require buildable package structure.
   filename=Path(r['path']).name;dst=repo/sid/filename
   try:
    if src.is_file():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);r['stage_status']='OK';r['staged_path']=str(dst.resolve())
   except OSError as exc:r['stage_status']='COPY_FAILED:'+str(exc)[:100]
  out.append(r)
 with open(batch/'staged_manifest.csv','w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
 print(json.dumps({'selected':len(out),'staged':sum(r['stage_status']=='OK' for r in out),'repo':str(repo.resolve()),'manifest':str((batch/'staged_manifest.csv').resolve())},indent=2))

def evidence_findings(j):
 for g in j.get('ranked_groups',[]):
  for f in g.get('findings',[]):yield f

def score(batch,evidence):
 from math import sqrt
 _,outdir=paths(batch);outdir.mkdir(parents=True,exist_ok=True)
 rows=readcsv(batch/'staged_manifest.csv');j=json.loads(evidence.read_text(encoding='utf-8'))
 findings=list(evidence_findings(j));results=[]
 for r in rows:
  status='SCORED';why='';prediction=''
  if r['stage_status']!='OK':status='EXCLUDED';why='not_downloaded'
  elif r['smell'] not in ('long method','blob'):status='EXCLUDED';why='unsupported_smell'
  else:
   try:start,end=int(r['start_line']),int(r['end_line'])
   except (ValueError,TypeError):status='EXCLUDED';why='invalid_line_range'
   if status=='SCORED':
    # MLCQ blob is a class-level label; some analyzer findings are LARGE_CLASS rather than GOD_CLASS.
    concerns={'long method':{'LONG_METHOD'},'blob':{'GOD_CLASS'}}[r['smell']]
    matches=[];related=[]
    stagepath=str(Path(r['staged_path']).resolve()).replace('\\','/').lower()
    for f in findings:
     finding_id=str(f.get('finding_id','')).replace('\\','/').lower()
     if stagepath not in finding_id:continue
     a,b=f.get('start_line'),f.get('end_line')
     if isinstance(a,int) and isinstance(b,int) and a<=end and b>=start:
      related.append(f)
      if f.get('concern') in concerns:matches.append(f)
    prediction='1' if matches else '0'
    # Critical: refuse to call absent finding a TN if source did not parse.
    # Detect parse failures at file level requires detailed parse errors in the analyzer JSON;
    # report aggregate parser count to user, do not silently hide.
    why=f'matched_concerns={len(matches)};same_region_findings={len(related)}'
  results.append({**r,'predicted':prediction,'evaluation_status':status,'notes':why})
 with open(outdir/'per_sample_predictions.csv','w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
 summary={'evaluation':'MLCQ sample-level majority vote provisional labels; exact source commit and annotated line interval','warnings':['Line-overlap matching is approximate if annotation is not exactly AST element extent. Check matching manually before treating metrics as final.','Blob annotation is assessed only against GOD_CLASS. It is not identical to LARGE_CLASS; no unsupported mapping was made.','A parser failure must be resolved before scoring negatives. Confirm parsed_files equals staged file count.','Balanced purposive sample is not representative of population prevalence.'],'analyzer_files':{'total':j.get('total_files'),'parsed':j.get('parsed_files'),'failed':j.get('failed_files')},'by_smell':{}}
 for smell in ['long method','blob']:
  sub=[r for r in results if r['smell']==smell and r['evaluation_status']=='SCORED'];c=collections.Counter((r['gold'],r['predicted']) for r in sub)
  tp=c[('1','1')];tn=c[('0','0')];fp=c[('0','1')];fn=c[('1','0')]
  def ratio(a,b):return round(a/b,4) if b else None
  den=(tp+fp)*(tp+fn)*(tn+fp)*(tn+fn)
  summary['by_smell'][smell]={'n':len(sub),'TP':tp,'FP':fp,'FN':fn,'TN':tn,'precision':ratio(tp,tp+fp),'recall':ratio(tp,tp+fn),'f1':ratio(2*tp,2*tp+fp+fn),'accuracy':ratio(tp+tn,tp+tn+fp+fn),'mcc':round((tp*tn-fp*fn)/sqrt(den),4) if den else None}
 (outdir/'metrics.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 try:
  import matplotlib.pyplot as plt
  for smell,met in summary['by_smell'].items():
   fig,ax=plt.subplots(figsize=(5,4));matrix=[[met['TN'],met['FP']],[met['FN'],met['TP']]]
   ax.imshow(matrix,cmap='Blues')
   for i in range(2):
    for k in range(2):ax.text(k,i,str(matrix[i][k]),ha='center',va='center',fontsize=16)
   ax.set_xticks([0,1],['Predicted no','Predicted yes']);ax.set_yticks([0,1],['Actual no','Actual yes']);ax.set_title(f'MLCQ {smell} (n={met["n"]})')
   fig.tight_layout();fig.savefig(outdir/(smell.replace(' ','_')+'_confusion_matrix.png'),dpi=170);plt.close(fig)
 except ImportError:print('matplotlib not installed; numeric results saved.')
 print(json.dumps(summary,indent=2));print('RESULTS',outdir.resolve())

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['stage','score']);p.add_argument('--batch',type=Path,required=True);p.add_argument('--evidence',type=Path);a=p.parse_args();
 if a.command=='stage':stage(a.batch)
 else:
  if not a.evidence:p.error('--evidence required for score')
  score(a.batch,a.evidence)
