from pathlib import Path
import csv,json,subprocess,sys
root=Path(__file__).resolve().parent
repo=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd()
a=repo/'Code Cleanliness'/'analyzer'
src=a/'src'/'main'/'java'
report=a/'evaluation'/'reports'/'analyzer-self-analysis-2026-10-18.json'
if not report.exists():
 matches=list(a.rglob('analyzer-self-analysis-*.json'))
 if matches: report=matches[-1]
if not src.exists() or not report.exists():sys.exit('ERROR: Missing analyzer Java source or self-analysis JSON.')
jar=Path.home()/'.m2'/'repository'/'com'/'github'/'javaparser'/'javaparser-core'/'3.27.1'/'javaparser-core-3.27.1.jar'
if not jar.exists():sys.exit('ERROR: JavaParser jar missing. Run: mvn -f "Code Cleanliness/analyzer/pom.xml" dependency:resolve')
bench=repo/'Code Cleanliness'/'evaluation'/'results'/'29f_method_boundary_benchmark';bench.mkdir(parents=True,exist_ok=True)
java=Path(__file__).with_name('MethodBoundaryReference.java')
if not java.exists():sys.exit('ERROR: MethodBoundaryReference.java must be alongside this Python script')
subprocess.run(['javac','-cp',str(jar),'-d',str(bench),str(java)],check=True)
raw=bench/'all_method_reference_metrics.csv'
with raw.open('w',encoding='utf-8',newline='') as f:
 subprocess.run(['java','-cp',str(bench)+';'+str(jar),'MethodBoundaryReference',str(src)],stdout=f,check=True)
with report.open(encoding='utf-8') as f:d=json.load(f)
findings=[x for g in d['ranked_groups'] for x in g['findings']]
idx={}
for finding in findings:
 if finding['concern'] not in ('LONG_METHOD','HIGH_COMPLEXITY'):continue
 key=(finding['source_file'].replace('\\','/'),str(finding['start_line']),finding['concern'])
 idx[key]=finding
rows=list(csv.DictReader(raw.open(encoding='utf-8',newline='')))
out=[]; seen=set()
for row in rows:
 for concern,metric,bound in [('LONG_METHOD','ncss',30),('HIGH_COMPLEXITY','cyclomatic',10)]:
  key=(row['source_file'],row['start_line'],concern)
  observed=int(row[metric]);ref=int(observed>bound);prediction=int(key in idx);seen.add(key)
  out.append({**row,'concern':concern,'boundary':bound,'reference_metric':observed,'reference_positive':ref,'analyzer_positive':prediction,'agreement':int(ref==prediction),'reference_kind':'SEPARATE_AST_COUNTER_SAME_CONVENTION_NOT_HUMAN_SMELL_LABEL'})
field=list(out[0]) if out else []
with (bench/'all_method_predictions.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=field);w.writeheader();w.writerows(out)
summary={'scope':'same-repository method-level boundary implementation agreement; NOT independently labeled maintainability-smell accuracy','parsed_methods':len(rows),'parse_errors':sum(r['parse_error']=='1' for r in rows),'matched_existing_positive_findings':sum(k in seen for k in idx),'existing_positive_findings':len(idx),'per_concern':{}}
for concern in ['LONG_METHOD','HIGH_COMPLEXITY']:
 rr=[r for r in out if r['concern']==concern]
 tp=sum(r['analyzer_positive']==1 and r['reference_positive']==1 for r in rr)
 fp=sum(r['analyzer_positive']==1 and r['reference_positive']==0 for r in rr)
 fn=sum(r['analyzer_positive']==0 and r['reference_positive']==1 for r in rr)
 tn=sum(r['analyzer_positive']==0 and r['reference_positive']==0 for r in rr)
 precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
 f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None
 summary['per_concern'][concern]={'TP':tp,'FP':fp,'FN':fn,'TN':tn,'boundary_precision':precision,'boundary_recall':recall,'boundary_f1':f1}
(bench/'boundary_results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
try:
 import matplotlib.pyplot as plt
 for concern,values in summary['per_concern'].items():
  fig,ax=plt.subplots(figsize=(6,4));ax.bar(['TP','FP','FN','TN'],[values[k] for k in ('TP','FP','FN','TN')]);ax.set_title(f'{concern}: boundary agreement (NOT smell accuracy)');ax.set_ylabel('Method-concern decisions');fig.tight_layout();fig.savefig(bench/(concern.lower()+'_confusion.png'),dpi=180);plt.close(fig)
except ImportError:print('Matplotlib not installed; CSV and JSON generated.')
print(json.dumps(summary,indent=2));print('RESULTS:',bench)
