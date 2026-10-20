#!/usr/bin/env python3
"""Milestone 29F: create audit forms and score ONLY independently reviewed judgments.
Usage: python run_29f_validated_evaluation.py --root "C:/path/J26-SE-361"
Re-run after filling audit CSVs. Does not run, train, or claim model accuracy on its own.
"""
import argparse, csv, json, pathlib, collections, datetime, math

def write_csv(path, headers, rows):
    if path.exists(): return False
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)
    return True

def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def div(a,b):return a/b if b else None

def numeric(x):
    try:return float(x)
    except (ValueError,TypeError):return None

def scores_binary(tp,fp,fn,tn):
    p=div(tp,tp+fp);r=div(tp,tp+fn)
    return dict(tp=tp,fp=fp,fn=fn,tn=tn,precision=p,recall=r,f1=div(2*tp,2*tp+fp+fn),accuracy=div(tp+tn,tp+fp+fn+tn))

def flatten(obj):
    out=[]
    for g in obj.get('ranked_groups',[]):
        for f in g.get('findings',[]) or []:out.append((g,f))
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);a=ap.parse_args()
    root=pathlib.Path(a.root)/'Code Cleanliness';out=root/'evaluation'/'results'/'29f_validated';out.mkdir(parents=True,exist_ok=True)
    report=root/'analyzer'/'evaluation'/'reports'/'analyzer-self-analysis-2026-10-18.json'
    if not report.exists():raise SystemExit('Missing analyzer report: '+str(report))
    data=json.loads(report.read_text(encoding='utf-8-sig'));pairs=flatten(data)
    detection=out/'detector_audit.csv'; grouping=out/'grouping_audit.csv'; ranking=out/'ranking_audit.csv'; llm=out/'llm_blind_review.csv'
    drows=[]
    for i,(g,f) in enumerate(pairs,1):
        drows.append(dict(case_id='SELF_%03d'%i,source_project='maintainability-analyzer',source_file=str(f.get('source_file','')),
          symbol=str(f.get('symbol',f.get('symbol_name',f.get('location','')))),concern=str(f.get('concern','')),
          predicted='1',gold='',review_status='UNREVIEWED',reviewer='',evidence_note=''))
    made=[]
    if write_csv(detection,['case_id','source_project','source_file','symbol','concern','predicted','gold','review_status','reviewer','evidence_note'],drows):made.append(detection.name)
    # Grouping pairs MUST be sampled and labeled independently; placeholder means no fabricated judgments.
    if write_csv(grouping,['pair_id','source_project','finding_id_a','finding_id_b','predicted_same_group','gold_same_group','review_status','reviewer','evidence_note'],[]):made.append(grouping.name)
    if write_csv(ranking,['case_id','source_project','group_id','predicted_rank','gold_relevance_0_to_3','review_status','reviewer','evidence_note'],[]):made.append(ranking.name)
    if write_csv(llm,['case_id','source_project','model','evidence_accuracy_0_to_4','concern_coverage_0_to_4','refactoring_relevance_0_to_4','unsupported_claims_count','review_status','reviewer','notes'],[]):made.append(llm.name)
    dr=read_csv(detection);gr=read_csv(grouping);rr=read_csv(ranking);lr=read_csv(llm)
    accepted=lambda r:r.get('review_status','').strip().upper()=='VERIFIED'
    by_concern=collections.defaultdict(lambda:collections.Counter())
    invalid=[];valid_d=0
    for r in dr:
        if not accepted(r):continue
        pr=r['predicted'].strip();gold=r['gold'].strip()
        if pr not in ('0','1') or gold not in ('0','1'):
            invalid.append('Invalid detector labels at '+r['case_id']);continue
        valid_d+=1;by_concern[r['concern']][('TP' if pr=='1' and gold=='1' else 'FP' if pr=='1' else 'FN' if gold=='1' else 'TN')]+=1
    det={name:scores_binary(*(cnt[k] for k in ('TP','FP','FN','TN'))) for name,cnt in sorted(by_concern.items())}
    pooled=collections.Counter()
    for counts in by_concern.values():pooled.update(counts)
    if valid_d:det['MICRO']=scores_binary(*(pooled[k] for k in ('TP','FP','FN','TN')))
    group_counter=collections.Counter();valid_g=0
    for r in gr:
        if not accepted(r):continue
        p=r['predicted_same_group'].strip();g=r['gold_same_group'].strip()
        if p not in ('0','1') or g not in ('0','1'):invalid.append('Invalid grouping pair '+r['pair_id']);continue
        valid_g+=1;group_counter['TP' if p=='1' and g=='1' else 'FP' if p=='1' else 'FN' if g=='1' else 'TN']+=1
    group_metrics=scores_binary(*(group_counter[k] for k in ('TP','FP','FN','TN'))) if valid_g else None
    # NDCG ranks: relevance labels on independently rated group ids; per project, 2+ groups.
    ranking_groups=collections.defaultdict(list)
    for r in rr:
        if not accepted(r):continue
        rank=numeric(r.get('predicted_rank'));rel=numeric(r.get('gold_relevance_0_to_3'))
        if rank is None or rank<1 or rel not in (0,1,2,3):invalid.append('Invalid ranking '+r['case_id']);continue
        ranking_groups[r['source_project']].append((rank,rel))
    ndcg={}
    for project,items in ranking_groups.items():
        if len(items)<2:continue
        ordered=sorted(items);ideal=sorted((rel for _,rel in items),reverse=True)
        dcg=sum((2**rel-1)/math.log2(i+2) for i,(_,rel) in enumerate(ordered))
        idcg=sum((2**rel-1)/math.log2(i+2) for i,rel in enumerate(ideal))
        ndcg[project]=div(dcg,idcg)
    # LLM: paired cases ONLY, across distinct heldout projects if provided. Do not infer split validity.
    ratings=collections.defaultdict(dict)
    for r in lr:
        if not accepted(r):continue
        key=(r['source_project'].strip(),r['case_id'].strip());model=r['model'].strip().lower()
        if model not in ('base','adapted'):invalid.append('Invalid model '+r['case_id']);continue
        metric_keys=('evidence_accuracy_0_to_4','concern_coverage_0_to_4','refactoring_relevance_0_to_4')
        vals=[numeric(r.get(k)) for k in metric_keys];claims=numeric(r.get('unsupported_claims_count'))
        if any(v is None or v<0 or v>4 or v%1 for v in vals) or claims is None or claims<0 or claims%1:
            invalid.append('Invalid LLM ratings '+r['case_id']);continue
        ratings[key][model]=dict(zip(metric_keys,vals));ratings[key][model]['unsupported_claims_count']=claims
    paired=[(key,models) for key,models in ratings.items() if set(models)=={'base','adapted'}]
    fields=['evidence_accuracy_0_to_4','concern_coverage_0_to_4','refactoring_relevance_0_to_4','unsupported_claims_count']
    comparison={field:{'base_mean':sum(m['base'][field] for _,m in paired)/len(paired),
            'adapted_mean':sum(m['adapted'][field] for _,m in paired)/len(paired),
            'mean_delta_adapted_minus_base':sum(m['adapted'][field]-m['base'][field] for _,m in paired)/len(paired)} for field in fields} if paired else {}
    result=dict(generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      detector={'audited_rows':valid_d,'by_concern':det,'limitations':'Without reviewed negatives, recall and accuracy are not estimable for the detection task; F1 from positives alone is not a representative benchmark.'},
      grouping={'audited_pairs':valid_g,'pairwise_metrics':group_metrics},ranking={'verified_projects_ndcg':ndcg,'reviewed_groups':sum(map(len,ranking_groups.values()))},
      llm={'paired_cases':len(paired),'paired_projects':sorted(set(key[0] for key,_ in paired)),'comparison':comparison,
           'limitations':'Verify that test projects were excluded from fine-tuning; blinded ratings preferred. One held-out example is only a pilot.'},errors=invalid,
      warning='UNREVIEWED rows were excluded. Gold labels and model scores must be independently established, not inferred from analyzer outputs.')
    (out/'validated_metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    try:
        import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
        if det:
            names=[k for k in det if k!='MICRO'];xs=list(range(len(names)));values=[det[k]['f1'] for k in names]
            fig,ax=plt.subplots(figsize=(max(7,1.7*len(names)),4));ax.bar(xs,[v if v is not None else 0 for v in values]);ax.set_xticks(xs,names,rotation=25,ha='right');ax.set_ylim(0,1);ax.set_ylabel('F1 on VERIFIED records');ax.set_title('Reviewed detector F1 — audit subset only');fig.tight_layout();fig.savefig(out/'verified_detector_f1.png',dpi=160);plt.close(fig)
        if comparison:
            names=fields[:3];fig,ax=plt.subplots(figsize=(9,4));xs=range(len(names));ax.bar([x-.18 for x in xs],[comparison[k]['base_mean'] for k in names],width=.36,label='Base');ax.bar([x+.18 for x in xs],[comparison[k]['adapted_mean'] for k in names],width=.36,label='Adapted');ax.set_xticks(list(xs),['Evidence','Coverage','Relevance']);ax.set_ylim(0,4);ax.set_title(f'Paired human ratings (n={len(paired)}; verify project independence)');ax.legend();fig.tight_layout();fig.savefig(out/'verified_llm_comparison.png',dpi=160);plt.close(fig)
    except ImportError:pass
    def fmt(x):return 'N/A' if x is None else f'{x:.3f}'
    lines=['# Milestone 29F — Validated evaluation','',f'Generated: {result["generated_utc"]}','',
    '**Important:** UNREVIEWED records are not scored. Missing values are not zero.','',
    f'- Detector verified judgments: **{valid_d}** (seeded predictions: {len(dr)}; not ground truth)','- Detector metrics:',
    '|Concern|TP|FP|FN|TN|Precision|Recall|F1|','|---|---:|---:|---:|---:|---:|---:|---:|']
    for k,v in det.items():lines.append('|'+ '|'.join([k]+[str(v[x]) for x in ('tp','fp','fn','tn')]+[fmt(v[x]) for x in ('precision','recall','f1')])+'|')
    lines+=['',f'- Reviewed grouping pairs: **{valid_g}**; pairwise F1: **{fmt(group_metrics["f1"]) if group_metrics else "N/A"}**',
      f'- Ranking projects with NDCG: **{len(ndcg)}**',f'- Paired Qwen comparison cases: **{len(paired)}**','']
    for field,v in comparison.items():lines.append(f'- {field}: base {v["base_mean"]:.2f}, adapted {v["adapted_mean"]:.2f}, delta {v["mean_delta_adapted_minus_base"]:+.2f}')
    lines+=['','## Required evaluation controls','',
      '- Detector: include **verified negative** Java examples for each evaluated concern and audit detection misses; do not use analyzer output as gold.',
      '- Grouping: evaluate independently rated same/different concern pairs, including cross-file pairs.',
      '- Ranking: collect independent relevance judgments on all groups in each compared repository.',
      '- LLM: one base and one adapted output per held-out case, score blind using the same evidence, audit project-level split.',
      '- Any metric above describes only the verified audit sample, not generalized system accuracy.',
      '',f'Invalid verified entries: {len(invalid)}']
    lines.extend('- '+e for e in invalid)
    (out/'validated_results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('PASS: evaluation forms/results generated:',out)
    if made:print('New CSV audit forms:',', '.join(made))
    print('Reviewed detector rows:',valid_d,'/ seeded',len(dr),'| grouping pairs:',valid_g,'| LLM paired cases:',len(paired))
    if invalid:print('WARNING:',len(invalid),'invalid verified records; see validated_metrics.json')
    if not(valid_d or valid_g or paired):print('No independent labels entered yet: no accuracy or model improvement has been claimed.')
if __name__=='__main__':main()
