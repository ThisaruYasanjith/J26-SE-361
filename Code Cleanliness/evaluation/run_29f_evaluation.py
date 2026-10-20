#!/usr/bin/env python3
"""J26-SE-361, Milestone 29F: reproducible evidence inventory (NOT ground-truth accuracy).
Run: python run_29f_evaluation.py --root 'C:/.../J26-SE-361'
"""
import argparse,csv,json,collections,datetime, pathlib, html

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);a=p.parse_args()
    root=pathlib.Path(a.root); comp=root/'Code Cleanliness'
    report=comp/'analyzer/evaluation/reports/analyzer-self-analysis-2026-10-18.json'
    summary=comp/'datasets/processed/review_batch_29a/batch_screen/summary.json'
    queue=comp/'datasets/processed/review_batch_29a/batch_screen/review_queue.csv'
    missing=[str(f) for f in (report,summary,queue) if not f.is_file()]
    if missing: raise SystemExit('Missing inputs:\n'+'\n'.join(missing))
    data=json.loads(report.read_text(encoding='utf-8-sig')); screen=json.loads(summary.read_text(encoding='utf-8-sig'))
    with queue.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    out=comp/'evaluation/results/29f_baseline';out.mkdir(parents=True,exist_ok=True)
    priorities=collections.Counter(r.get('review_priority','UNSPECIFIED') for r in rows)
    concerns=collections.Counter(); rules=collections.Counter(); files=collections.Counter();group_sizes=[]; ranks=[]
    for g in data.get('ranked_groups',[]):
        fs=g.get('findings') or [];group_sizes.append(len(fs));ranks.append(g.get('rank'))
        for finding in fs:
            concerns[str(finding.get('concern','UNKNOWN'))]+=1
            rules[str(finding.get('rule_id','UNKNOWN'))]+=1
            files[str(finding.get('source_file','UNKNOWN'))]+=1
    stats={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'analysis_scope':data.get('analysis_scope'), 'schema_version':data.get('schema_version'),
           'total_files':data.get('total_files'),'parsed_files':data.get('parsed_files'),'failed_files':data.get('failed_files'),
           'finding_count_reported':data.get('finding_count'),'finding_count_recounted':sum(concerns.values()),
           'group_count_reported':data.get('group_count'),'group_count_recounted':len(group_sizes),
           'concern_counts':dict(sorted(concerns.items())), 'rule_counts':dict(sorted(rules.items())),
           'screened_cases':len(rows), 'screening_categories':dict(sorted(priorities.items())),
           'parse_pair_statuses':screen.get('pair_statuses'), 'reviewed_training_data':{'approved_train':1,'approved_holdout':1,'source_projects':['checkstyle','hibernate-orm']},
           'methodology_warning':'Descriptive measurements only. Screening outcomes are not ground-truth labels. No precision, recall, F1 or improvement computed.'}
    assert stats['finding_count_reported']==stats['finding_count_recounted'], 'Finding count mismatch'
    assert stats['group_count_reported']==stats['group_count_recounted'], 'Group count mismatch'
    (out/'descriptive_results.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    try:
        import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
        plots=[('screening_distribution.png','Dataset screening outcomes',priorities),('detected_concerns.png','Analyzer concern distribution',concerns),('findings_per_group.png','Findings per ranked issue group',collections.Counter(map(str,group_sizes)))]
        for filename,title,counts in plots:
            labels=list(counts.keys());values=[counts[k] for k in labels]
            fig,ax=plt.subplots(figsize=(max(8,min(15,len(labels)*1.0)),5))
            ax.bar(range(len(labels)),values);ax.set_xticks(range(len(labels)));ax.set_xticklabels(labels,rotation=38,ha='right',fontsize=8)
            ax.set_title(title);ax.set_ylabel('Count');ax.set_ylim(bottom=0)
            for idx,n in enumerate(values):ax.text(idx,n,str(n),ha='center',va='bottom',fontsize=8)
            fig.tight_layout();fig.savefig(out/filename,dpi=160);plt.close(fig)
    except ImportError:
        print('matplotlib unavailable; charts skipped. Install with: python -m pip install matplotlib')
    labels='\n'.join(f'| {k} | {v} |' for k,v in sorted(priorities.items()))
    detected='\n'.join(f'| {k} | {v} |' for k,v in sorted(concerns.items()))
    md=f'''# Milestone 29F — Reproducible descriptive baseline\n\nGenerated (UTC): {stats['generated_utc']}\n\n**Scope:** One analyzer self-analysis snapshot, plus 180 historical refactoring screening cases.\n\n## Analyzer self-analysis\n\n- Total Java files: {stats['total_files']}\n- Parsed Java files: {stats['parsed_files']}\n- Failed Java files: {stats['failed_files']}\n- Analyzer-reported findings: {stats['finding_count_reported']}\n- Ranked issue groups: {stats['group_count_reported']}\n\n### Concern distribution\n\n| Concern | Count |\n|---|---:|\n{detected}\n\n## Historical refactoring screening\n\n| Screening priority | Cases |\n|---|---:|\n{labels}\n\n**Human-approved explanation records outside initial screening:** one Checkstyle training record; one Hibernate holdout record.\n\n## Research integrity and limitations\n\n- These data show analyzer output and dataset coverage, **NOT detector accuracy**.\n- A detected concern is not necessarily true; a missing concern is not necessarily false.\n- The 180 screening priorities are not ground-truth labels and cannot justify precision, recall, F1, or accuracy.\n- The repository snapshot is not a scalability benchmark; runtime and memory need controlled repeated runs.\n- One QLoRA training example and one holdout cannot support generalized quality-improvement claims.\n- Next required validations: independent concern ground truth, grouped-pair judgments, priority relevance labels, and project-disjoint LLM explanation ratings.\n'''
    (out/'results_summary.md').write_text(md,encoding='utf-8')
    print('PASS: evidence inventory generated.');print('Output:',out);print(f"Parsed {stats['parsed_files']} files, {stats['finding_count_reported']} findings, {stats['group_count_reported']} groups; screened {len(rows)} cases.")
if __name__=='__main__':main()
