"""Reproducible descriptive 29F evaluation: no inferred labels."""
from pathlib import Path
import argparse,csv,json,collections,datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def fig_bar(labels,values,title,xlabel,out):
    fig,ax=plt.subplots(figsize=(10,5.5)); bars=ax.barh(labels,values)
    ax.invert_yaxis();ax.set_title(title,fontweight='bold',pad=14);ax.set_xlabel(xlabel)
    ax.bar_label(bars,padding=4);ax.set_xlim(0,max(values)*1.2 if values else 1)
    fig.tight_layout();fig.savefig(out,dpi=180);plt.close(fig)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--evidence',type=Path,required=True);ap.add_argument('--checks',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    findings=read(args.evidence/'source_backed_findings.csv'); groups=read(args.evidence/'ranking_review_candidates.csv');pairs=read(args.evidence/'grouping_candidate_pairs.csv');checks=read(args.checks/'independent_metric_review.csv');neg=read(args.checks/'missing_concern_candidates.csv')
    concerns=collections.Counter(r['concern'] for r in findings)
    fig_bar(list(concerns),list(concerns.values()),'Analyzer findings by concern','Detected findings (not validated true positives)',out/'01_concern_distribution.png')
    predicted=collections.Counter(r['predicted_same_group'] for r in pairs)
    fig_bar(['Predicted same group','Predicted different group'],[predicted['1'],predicted['0']],'Candidate grouping-pair coverage','Candidate pairs (not ground truth)',out/'02_grouping_candidates.png')
    ranks=collections.Counter(r['concerns'] for r in groups)
    fig_bar(list(ranks),list(ranks.values()),'Ranked groups by concern composition','Groups (not validated relevance)',out/'03_ranked_group_composition.png')
    diffs=collections.Counter(r['proxy_differs_from_reported'].lower() for r in checks if r.get('concern') in ('HIGH_COMPLEXITY','LONG_METHOD'))
    fig_bar(['Lexical proxy differs','Lexical proxy matches'],[diffs['true'],diffs['false']],'AST vs lexical proxy: methodological discrepancy','Compared findings; neither category implies accuracy',out/'04_metric_proxy_agreement.png')
    summary={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_backed_findings':len(findings),'concerns':dict(concerns),'ranked_groups':len(groups),'grouping_candidate_pairs':len(pairs),'predicted_same_group_pairs':predicted['1'],'predicted_different_group_pairs':predicted['0'],'independent_metric_rows':len(checks),'lexical_proxy_differs':diffs['true'],'lexical_proxy_matches':diffs['false'],'non_detection_candidates':len(neg),'ground_truth_label_status':'UNVERIFIED','precision':None,'recall':None,'f1':None,'ndcg':None,'llm_generalization_improvement':None}
    (out/'measured_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    s=f'''# Milestone 29F — Measured results (pre-label stage)\n\nDate (UTC): {summary['generated_utc']}\n\n## Genuine observations\n\n- **{len(findings)}** analyzer findings matched to Java source; **{len(groups)}** ranked groups.\n- **{len(pairs)}** proposed grouping comparison pairs: **{predicted['1']}** predicted related and **{predicted['0']}** predicted unrelated. These are sampling predictions, **not grouping precision/recall**.\n- **{len(checks)}** independent *lexical* comparisons available. **{diffs['true']}** disagree with the analyzer's AST metric and **{diffs['false']}** agree numerically. Different definitions may explain discrepancies, so these cannot be treated as false positives.\n- **{len(neg)}** non-detection candidates available for review. Their truth is unknown.\n\n## Quantitative correctness results\n\n- Detection precision/recall/F1: **not computable** until independent positive and negative labels are verified.\n- Pairwise grouping precision/recall/F1: **not computable** until sampled pairs are labeled.\n- Ranking NDCG: **not computable** until relevance grades are independently assigned.\n- General base-versus-adapted Qwen superiority: **not established** by one Hibernate holdout.\n\n## Generated figures\n\n1. `01_concern_distribution.png` — finding distribution.\n2. `02_grouping_candidates.png` — candidate pair balance.\n3. `03_ranked_group_composition.png` — group compositions.\n4. `04_metric_proxy_agreement.png` — disagreement between different metric implementations.\n\nThese plots are legitimate baseline/evaluation-coverage figures, **not model accuracy graphs**.\n'''
    (out/'MEASURED_RESULTS.md').write_text(s,encoding='utf-8')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
