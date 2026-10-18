#!/usr/bin/env python3
"""Verify user-approved 29B records, generate leakage-safe *pilot* SFT examples.
Run from Code Cleanliness repository directory. No third-party Python packages.
"""
import csv, hashlib, json, pathlib, sys
R = pathlib.Path.cwd()
B = R / 'datasets/processed/review_batch_29a'
C = B / '29B_source_review_package/source_review_candidates.json'
E = B / 'batch_screen/evidence'
OUT = B / 'approved_pilot_29c'
CASES = [('Extract_Method_1','checkstyle','HIGH_COMPLEXITY','Checkstyle','1'),
         ('Extract_Method_7','hibernate-orm','LONG_METHOD','Hibernate','7')]

def all_findings(report):
    return [f for g in report.get('ranked_groups',[]) for f in g.get('findings',[])]

def locate_report(case, side):
    # Batch screening format: evidence/Extract_Method_1-before.json or nested paths.
    candidates = [B/'batch_screen/evidence'/f'{case}.{side}.json',
                  B/'batch_screen/evidence'/f'{case}-{side}.json',
                  B/'batch_screen/evidence'/case/f'{side}.json',
                  B/'analyzer_evidence'/('29A-04.json' if side=='before' else '29A-04-after.json') if case=='Extract_Method_1' else B/'nonexistent']
    for p in candidates:
        if p.is_file():return p
    # Per-case screen may embed filenames or reports.
    screen=B/'batch_screen'/f'{case}.screen.json'
    if screen.exists():
        data=json.loads(screen.read_text(encoding='utf8'))
        for k in (f'{side}_report',f'{side}_report_path',f'{side}_evidence_path'):
            if isinstance(data.get(k),str):
                p=pathlib.Path(data[k]);p=p if p.is_absolute() else R/p
                if p.is_file():return p
    return None

def read_source(refactoring_id,side):
    p=R/'datasets/raw/LLM4Refactoring/data/dataset/Extract Method'/refactoring_id/f'{side}.java'
    if not p.exists():raise FileNotFoundError(p)
    return p,hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    if not C.is_file():raise FileNotFoundError(f'Missing {C}. Extract the 29B review ZIP first.')
    byid={x['case_id']:x for x in json.loads(C.read_text(encoding='utf-8'))['candidates']}
    verified=[]; report_rows=[]
    for case,project,concern,folder,number in CASES:
        candidate=byid[case]
        verified_hashes={}
        for side in ('before','after'):
            path,sha=read_source(number,side)
            expected=candidate.get(f'{side}_sha256')
            if sha!=expected:raise RuntimeError(f'SOURCE HASH MISMATCH {case} {side}: {sha} != {expected}')
            verified_hashes[side]=sha
        before_path=locate_report(case,'before'); after_path=locate_report(case,'after')
        if not before_path or not after_path:
            raise RuntimeError(f'Cannot locate both analyzer evidence JSONs for {case}. Available batch evidence folder: {E}. Please share directory names; no labels created.')
        before=json.loads(before_path.read_text(encoding='utf8'));after=json.loads(after_path.read_text(encoding='utf8'))
        if before.get('failed_files') or after.get('failed_files') or before.get('parsed_files')!=1 or after.get('parsed_files')!=1:
            raise RuntimeError(f'Invalid parsed snapshot for {case}')
        target=next((f for f in all_findings(before) if f.get('concern')==concern and
                     ('findMatch(' in f.get('symbol','') if case=='Extract_Method_1' else 'refresh(' in f.get('symbol',''))),None)
        if not target:raise RuntimeError(f'Missing expected BEFORE finding for {case}')
        after_same=[f for f in all_findings(after) if f.get('concern')==concern and
                    (('findMatch(' in f.get('symbol','')) if case=='Extract_Method_1' else ('refresh(' in f.get('symbol','') and 'RefreshEvent, RefreshContext, Object' in f.get('symbol','')))]
        if after_same:raise RuntimeError(f'Expected finding still present AFTER for {case}')
        ev=target.get('evidence',{})
        if case=='Extract_Method_1':
            if int(ev.get('cyclomaticComplexity',-1))!=12 or int(ev.get('configuredMaxComplexity',-1))!=10:
                raise RuntimeError('Checkstyle recorded complexity or configured boundary disagrees')
        else:
            if 'ncss' not in '|'.join(ev).lower() and 'ncss' not in target.get('rule_id','').lower():
                raise RuntimeError('Hibernate before evidence is not NCSS-based')
        ctx=target.get('code_context') or {}
        if not ctx.get('text'):raise RuntimeError(f'No source excerpt for {case}')
        explanation=candidate['proposed_explanation']
        if case=='Extract_Method_7':
            # Include exact values only when the evidence identifies the correct keys.
            measured=next((v for k,v in ev.items() if k.lower() in ('ncss','methodncss')),None)
            limit=next((v for k,v in ev.items() if k.lower() in ('configuredmaxncss','maxncss')),None)
            if measured is None or limit is None:
                raise RuntimeError(f'Hibernate NCSS values are not unambiguously present: {ev}')
            explanation=explanation.replace('under the configured NCSS boundary',f'with NCSS {measured} against the preliminary configured boundary {limit}')
            explanation=explanation.replace('Verify metric values directly from the corresponding evidence report and ','')
        prompt={'source_project':project,'concern':concern,'symbol':target['symbol'],
                'rule_id':target['rule_id'],'recorded_evidence':ev,
                'code_context':ctx.get('text'),
                'code_context_truncated':ctx.get('truncated',True),
                'scope_limit':'isolated single-file snapshot, preliminary analyzer findings'}
        entry={'case_id':case,'source_project':project,'status':'USER_APPROVED_SOURCE_REVIEWED_NOT_BEHAVIOR_TESTED',
               'messages':[{'role':'system','content':'Explain Java maintainability findings strictly from supplied analyzer evidence. Do not invent metrics, behavior equivalence, developer intent, or ranking. Distinguish observed code from possible improvements; state limitations.'},
                           {'role':'user','content':json.dumps(prompt,ensure_ascii=False)},
                           {'role':'assistant','content':explanation}],
               'provenance':{'before_sha256':verified_hashes['before'],'after_sha256':verified_hashes['after'],
                             'before_evidence':str(before_path.relative_to(R)),'after_evidence':str(after_path.relative_to(R))},
               'ground_truth_limitations':['User approved explanation with stated limitations','Source and analyzer comparison only','No verified developer rationale','No whole-project compilation or behavioral proof']}
        verified.append(entry)
        report_rows.append({'case_id':case,'project':project,'metric_evidence':json.dumps(ev), 'after_matching_findings':len(after_same),'source_hash_verified':True})
    OUT.mkdir(parents=True,exist_ok=True)
    # Explicit fixed project-disjoint PILOT. Not a research evaluation dataset.
    (OUT/'train_pilot.jsonl').write_text(json.dumps(verified[0],ensure_ascii=False)+'\n',encoding='utf8')
    (OUT/'holdout_pilot.jsonl').write_text(json.dumps(verified[1],ensure_ascii=False)+'\n',encoding='utf8')
    (OUT/'verification.json').write_text(json.dumps({'status':'PILOT_ONLY_NOT_RESEARCH_EVALUATION',
          'verified_cases':report_rows,'split':{'train_projects':['checkstyle'],'holdout_projects':['hibernate-orm']},
          'mockito':'PENDING_EXCLUDED','training_examples':1,'holdout_examples':1,
          'warning':'Insufficient supervised examples for claims of generalization or adaptation quality.'},indent=2),encoding='utf8')
    print('PASS: source hashes, parse status, recorded metrics and finding disappearance verified')
    print('Created:',OUT)
    print('Training: 1 Checkstyle case; holdout: 1 Hibernate case; Mockito excluded')
    print('This is a QLoRA pipeline smoke-test dataset, not a scientifically sufficient training set.')
if __name__=='__main__':
    try: main()
    except Exception as exc: print(f'VERIFICATION STOPPED: {exc}',file=sys.stderr);sys.exit(1)
