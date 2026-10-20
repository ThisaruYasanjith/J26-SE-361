"""Consolidate observed Maintainability Triage results. No synthetic ratings.
Run from anywhere: python 29f_finalize_existing_evidence.py
Place this file in Code Cleanliness/evaluation/ (or specify --evaluation-root).
"""
from __future__ import annotations
import argparse, csv, math, re
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone

P = argparse.ArgumentParser()
P.add_argument('--evaluation-root', type=Path, default=Path(__file__).resolve().parent)
a = P.parse_args()
eval_root = a.evaluation_root.resolve()
base = eval_root/'results'/'final_evaluation'
out = base/'closure'
out.mkdir(parents=True, exist_ok=True)

def read_csv(path):
    if not path.is_file(): return None
    with path.open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))

def num(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError): return None

def csv_write(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

checks=[]; paragraphs=[]
def mark(area,status,detail):
    checks.append({'area':area,'status':status,'evidence':detail})

def fmt(x): return f'{x:.2f}' if x is not None else 'unavailable'

ranking_file=base/'ranking'/'ranking_independent_review.csv'
ranking=read_csv(ranking_file)
if ranking is None:
    mark('Ranking','MISSING_INPUT',str(ranking_file))
else:
    scores=[num(r.get('exceedance_score')) for r in ranking]
    valid=[x for x in scores if x is not None]
    saturated=sum(abs(x-1)<1e-12 for x in valid)
    generated_re=re.compile(r'parser|grammaraccess|\.generated\.|generated/|generated\\|protobuf|antlr',re.I)
    flagged=[r for r in ranking if generated_re.search(str(r.get('group_id','')))]
    reference_col='independent_priority_rank'
    refs=[num(r.get(reference_col)) for r in ranking]
    nref=sum(x is not None for x in refs)
    mark('Ranking','DESCRIPTIVE_ONLY',f'{len(ranking)} top-selected groups; {len(valid)} valid scores; {saturated} scores at 1.0; {len(flagged)} heuristic possible generated-code groups; {nref} independently labeled ranks')
    paragraphs.append(f'Ranking: {len(ranking)} selected rows; {saturated}/{len(valid)} valid score values saturated at 1.0. Identifier-only generated-code heuristic flagged {len(flagged)} rows (not source verified). The independent priority-rank column has {nref} numeric labels. No ranking relevance correlation, NDCG or validated ranking accuracy is claimed.')
    audit=[]
    for r in ranking:
        audit.append({'group_id':r.get('group_id',''),'analyzer_rank':r.get('analyzer_rank',''),'exceedance_score':r.get('exceedance_score',''),'possible_generated_identifier':int(bool(generated_re.search(str(r.get('group_id',''))))),'independent_priority_rank':r.get(reference_col,'')})
    csv_write(out/'ranking_row_audit.csv',audit,['group_id','analyzer_rank','exceedance_score','possible_generated_identifier','independent_priority_rank'])

grouping_file=base/'grouping'/'pilot_pairwise_review.csv'
grouping=read_csv(grouping_file)
if grouping is None:
    mark('Grouping','MISSING_INPUT',str(grouping_file))
else:
    prediction=[num(r.get('system_same_group')) for r in grouping]
    yes=sum(x==1 for x in prediction)
    no=sum(x==0 for x in prediction)
    # Existence and names of independent labels are not standardized; never silently use machine prediction as truth.
    possible=[k for k in grouping[0] if ('independent' in k or 'human' in k or 'reference' in k or 'true_' in k or 'ground_truth' in k) and ('label' in k or 'group' in k or 'related' in k)] if grouping else []
    filled={k:sum(str(r.get(k,'')).strip().lower() not in ('','nan','none') for r in grouping) for k in possible}
    mark('Grouping','DESCRIPTIVE_ONLY',f'{len(grouping)} pairs; system says related {yes}, unrelated {no}; independent label availability {filled}')
    paragraphs.append(f'Grouping: {len(grouping)} candidate pairs, including {yes} system-positive and {no} system-negative assignments. Independent-label fields found: {filled or "none identified"}. Structural consistency is not precision, recall, or F1.')

llm_file=base/'llm'/'base_vs_finetuned_review.csv'
llm=read_csv(llm_file)
if llm is None:
    mark('Qwen','MISSING_INPUT',str(llm_file))
else:
    bymodel=defaultdict(list); screen=[]
    pat=re.compile(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])')
    for r in llm:
        model=str(r.get('model','')); t=num(r.get('generation_seconds'))
        response=str(r.get('response') or ''); evidence=str(r.get('evidence') or '')
        extras=sorted(set(pat.findall(response))-set(pat.findall(evidence)))
        words=len(response.split())
        bymodel[model].append((t,words,len(extras)))
        screen.append({'case_id':r.get('case_id',''),'model':model,'generation_seconds':r.get('generation_seconds',''),'response_words':words,'response_only_numeric_tokens':'|'.join(extras),'numeric_screen_flags':len(extras),'meaning':'Requires examination; not proof of hallucination'})
    csv_write(out/'qwen_response_grounding_screen.csv',screen,['case_id','model','generation_seconds','response_words','response_only_numeric_tokens','numeric_screen_flags','meaning'])
    details=[]
    for model, vals in sorted(bymodel.items()):
        times=[v[0] for v in vals if v[0] is not None]
        average_time=sum(times)/len(times) if times else None
        average_words=sum(v[1] for v in vals)/len(vals)
        flags=sum(v[2] for v in vals)
        details.append(f'{model}: n={len(vals)}, mean latency={fmt(average_time)}s, mean response length={average_words:.2f} words, response-only numeric references={flags}')
    evaluated_quality=sum(any(num(r.get(k)) is not None for k in ['correctness_1_to_5','relevance_1_to_5','actionability_1_to_5','grounding_1_to_5']) for r in llm)
    mark('Qwen','DESCRIPTIVE_ONLY',f'{len(llm)} controlled outputs; {evaluated_quality} quality-rated rows; '+ '; '.join(details))
    paragraphs.append('Qwen: '+ '; '.join(details)+f'. Quality ratings filled in {evaluated_quality}/{len(llm)} rows. Numeric-only screening flags are not hallucination verdicts. Timing and response length cannot establish model quality or LoRA superiority.')

# Other existing evidence: preserve provenance, not claims invented here.
known=[eval_root/'notebooks'/'29f_reproducible_evaluation.ipynb',eval_root/'notebooks'/'29f_grouping_validation.ipynb',eval_root/'notebooks'/'29f_ranking_validation.ipynb',eval_root/'notebooks'/'29f_llm_quality_validation.ipynb',eval_root/'FINAL_EVALUATION_SUMMARY.md',eval_root/'29F_FINAL_EVALUATION_COMPLETION_REPORT.md']
mark('Reproducibility files','CHECKED', '; '.join(f'{p.name}={"present" if p.is_file() else "absent"}' for p in known))
csv_write(out/'completion_evidence_inventory.csv',checks,['area','status','evidence'])
report=['# Final Evaluation Evidence Reconciliation','',f'Generated: {datetime.now(timezone.utc).isoformat()}','', '## Scope and interpretation', 'This report is computed exclusively from locally stored CSV inputs. It does not create human judgments, independent labels, external ground truth, or new model inference. The tested implementation may be complete even where empirical quality remains uncertain.','', '## Available computed observations','']
report += [f'- {p}' for p in paragraphs]
report+=['','## Completion boundaries', '- **Detection comparison:** use the existing PMD/MLCQ experiment as reported; this script does not recalculate its sample-level ground truth.', '- **Grouping:** pair predictions and transitivity checks alone do not establish grouping accuracy.', '- **Ranking:** selected top-ranked groups and source-unverified generated-code flags cannot establish priority utility or unbiased retrieval performance.', '- **LLM:** a six-output controlled demonstration cannot establish statistically representative generalization or quality superiority.', '- **Scalability:** previously recorded 5/10/20/40-file timings are preliminary and do not establish performance at 100–1,000 files.', '- **External human reviews:** not performed. No review scores are imputed.', '', '## Evidence files', '- `completion_evidence_inventory.csv`: source/status inventory.', '- `ranking_row_audit.csv`: per-group score and possible-generated heuristic (when available).', '- `qwen_response_grounding_screen.csv`: per-output numeric-reference checks (when available).', '', '## Status', 'This closes the descriptive evidence-reconciliation step, NOT every scientific evaluation requirement. Remaining effectiveness gaps require independent, credible benchmarks or explicitly bounded claims.','']
(out/'FINAL_EVALUATION_RECONCILIATION.md').write_text('\n'.join(report),encoding='utf-8')
print('Wrote results to:',out)
for r in checks: print(f"[{r['status']}] {r['area']}: {r['evidence']}")
print('Created:',*[p.name for p in sorted(out.iterdir()) if p.is_file()],sep='\n - ')
