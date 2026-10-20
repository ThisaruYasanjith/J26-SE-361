#!/usr/bin/env python3
"""29F: use ALL screened refactoring cases without falsely calling them human labels.

Produces project-disjoint, evidence-only weak supervision for experimental training,
plus preserves previously approved training/holdout without contaminating either.
Run from repo root: python "Code Cleanliness/llm/preprocessing/prepare_29f_full_corpus.py" --root "$PWD"
"""
import argparse, csv, hashlib, json, collections
from pathlib import Path

SYSTEM = ("Explain repository-wide Java maintainability findings only from supplied analyzer evidence. "
          "Do not claim behavioral preservation, refactoring correctness, unseen code, or confirmed fixes. "
          "Distinguish observed before/after analyzer results from uncertain real-world quality.")

def records(path):
    if not path.is_file(): return []
    with path.open(encoding='utf-8-sig') as f:
        return [json.loads(line) for line in f if line.strip()]

def dump_jsonl(path, rows):
    with path.open('w', encoding='utf-8') as f:
        for row in rows: f.write(json.dumps(row, ensure_ascii=False)+'\n')

def case_record(row):
    before, after = row.get('before',{}), row.get('after',{})
    cmp = row.get('comparison',{})
    bf, af = before.get('findings',[]), after.get('findings',[])
    if before.get('status') != 'OK' or after.get('status') != 'OK': return None
    project = str(row.get('project_name','unknown'))
    # Limited stable evidence included. Never present detector predictions as human ground truth.
    def show(xs):
        return [{'concern':x.get('concern'), 'symbol':x.get('symbol'), 'rule_id':x.get('rule_id'),
                 'evidence': x.get('evidence',{})} for x in xs[:12]]
    payload = {'source_project':project, 'case_id':row.get('case_id'),
               'historical_refactoring_label':row.get('refactoring_type'),
               'snapshot_scope':'isolated_single_file_snapshot',
               'before_analyzer_findings':show(bf), 'after_analyzer_findings':show(af),
               'before_total':len(bf), 'after_total':len(af),
               'candidate_removed_signatures':cmp.get('removed_signature_candidates',[])[:12],
               'candidate_added_signatures':cmp.get('added_signature_candidates',[])[:12]}
    removed = cmp.get('removed_signature_candidates', [])
    added = cmp.get('added_signature_candidates', [])
    # Objective templated evidence summary; NOT an independently verified improvement label.
    desc = (f"The isolated before snapshot has {len(bf)} analyzer-reported finding(s), "
            f"and the after snapshot has {len(af)}. "
            f"The signature comparison reports {len(removed)} removed and {len(added)} added "
            "finding signature(s). ")
    if removed:
        desc += "Removed detector signature candidates: " + '; '.join(
            f"{str(x[0])} at {str(x[1])} (rule {str(x[2])})" for x in removed[:6] if len(x)>=3) + '. '
    if added:
        desc += "Added detector signature candidates: " + '; '.join(
            f"{str(x[0])} at {str(x[1])} (rule {str(x[2])})" for x in added[:6] if len(x)>=3) + '. '
    desc += ("These are preliminary analyzer observations on isolated file snapshots. "
             "A changed signature does not establish behavior preservation, root-cause resolution, "
             "or a developer's rationale. Review the complete change and tests before claiming success.")
    return {'case_id':row.get('case_id'), 'source_project':project,
            'status':'AUTO_CONSTRUCTED_WEAK_EVIDENCE_ONLY_NOT_HUMAN_APPROVED',
            'provenance':{'generator':'prepare_29f_full_corpus.py','source':'29A screen.json',
                          'input_hashes':row.get('input_hashes',{})},
            'messages':[{'role':'system','content':SYSTEM},
                        {'role':'user','content':json.dumps(payload,ensure_ascii=False)},
                        {'role':'assistant','content':desc}],
            'ground_truth_limitations': 'Weak templated evidence summary, NOT manually approved; NOT detector ground truth.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True); args=p.parse_args()
    root=Path(args.root).resolve()/'Code Cleanliness'
    screens=root/'datasets/processed/review_batch_29a/batch_screen'
    approved=root/'datasets/processed/review_batch_29a/approved_pilot_29c'
    out=root/'datasets/processed/29f_corpus';out.mkdir(parents=True,exist_ok=True)
    files=sorted(screens.glob('*.screen.json'))
    if not files: raise SystemExit(f'ERROR: no screening JSONs at {screens}')
    screened=[json.loads(f.read_text(encoding='utf-8')) for f in files]
    weak=[x for x in (case_record(r) for r in screened) if x]
    # Reserve all previously approved holdout projects, and create deterministic project-level split.
    holdout=records(approved/'holdout_pilot.jsonl')
    train_approved=records(approved/'train_pilot.jsonl')
    held_projects={str(x['source_project']) for x in holdout}
    train_projects={str(x['source_project']) for x in train_approved}
    if held_projects & train_projects:
        raise SystemExit('ERROR: Approved training and holdout share project!')
    held_ids={str(x['case_id']) for x in holdout}
    approved_ids={str(x['case_id']) for x in train_approved}
    # Ensure never expose held-out records as training data.
    candidate=[x for x in weak if x['source_project'] not in held_projects and x['case_id'] not in held_ids]
    projects=sorted({x['source_project'] for x in candidate if x['source_project'] not in train_projects})
    # Deterministic: 20% of remaining projects for a separate weak-only validation (NOT a genuine score set).
    valprojects=set(projects[::5]);
    if len(projects)>1 and len(valprojects)==len(projects): valprojects=set(projects[:1])
    weak_val=[x for x in candidate if x['source_project'] in valprojects]
    weak_train=[x for x in candidate if x['source_project'] not in valprojects and x['case_id'] not in approved_ids]
    assert not ({x['source_project'] for x in weak_train} & ({x['source_project'] for x in weak_val}|held_projects))
    dump_jsonl(out/'weak_train_EXPERIMENTAL.jsonl',weak_train)
    dump_jsonl(out/'weak_validation_NOT_GROUND_TRUTH.jsonl',weak_val)
    dump_jsonl(out/'approved_train.jsonl',train_approved)
    dump_jsonl(out/'approved_holdout.jsonl',holdout)
    report={'screened_total':len(screened), 'parseable_pairs':len(weak),
            'weak_training_records':len(weak_train), 'weak_validation_records':len(weak_val),
            'approved_training_records':len(train_approved),'approved_holdout_records':len(holdout),
            'reserved_heldout_projects':sorted(held_projects),'weak_validation_projects':sorted(valprojects),
            'weak_training_projects':sorted({x['source_project'] for x in weak_train}),
            'restriction':'Weak examples are mechanically templated summaries of analyzer output, not independent quality labels. Evaluate against independently reviewed source/ratings only. Do not call weak validation accuracy.'}
    (out/'corpus_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with (out/'source_review_queue.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['case_id','project','candidate_status','source_review','behavior_verified','approved_explanation','reviewer'])
        w.writeheader()
        for x in weak: w.writerow({'case_id':x['case_id'],'project':x['source_project'],
                                   'candidate_status':'WEAK_ONLY','source_review':'PENDING',
                                   'behavior_verified':'UNKNOWN','approved_explanation':'','reviewer':''})
    print(json.dumps(report,indent=2));print('WROTE:',out)

if __name__=='__main__':main()
