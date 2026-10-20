#!/usr/bin/env python3
"""Reproducible, deliberately conservative independent lexical audit.
Java syntax proxies are NOT human-verified ground truth and NOT AST-equivalent.
"""
import argparse,csv,json,re,zipfile,collections,datetime,pathlib

def mask_java(source):
    # Replace comments and string/char/text-block literals with whitespace, preserving newlines and indices.
    out=list(source); n=len(source); i=0
    while i<n:
        c=source[i]; nxt=source[i+1] if i+1<n else ''
        if c=='/' and nxt=='/':
            j=source.find('\n',i);j=n if j<0 else j
        elif c=='/' and nxt=='*':
            e=source.find('*/',i+2);j=n if e<0 else e+2
        elif source.startswith('"""',i):
            j=i+3
            while j<n and not source.startswith('"""',j):j+=1
            j=min(n,j+3)
        elif c in ('"',"'"):
            quote=c;j=i+1
            while j<n:
                if source[j]=='\\':j+=2;continue
                if source[j]==quote:j+=1;break
                j+=1
        else:
            i+=1;continue
        for k in range(i,j):
            if out[k]!='\n':out[k]=' '
        i=j
    return ''.join(out)

def signals(chunk):
    masked=mask_java(chunk)
    tok=re.findall(r'&&|\|\||\b(?:if|for|while|catch|case|default|do|switch)\b|\?|;|\{|\}|->',masked)
    counts=collections.Counter(tok)
    # JavaParser cyclomatic calculator may use different semantics for switch, foreach, lambda, etc.
    complexity_proxy=1+sum(counts.get(k,0) for k in ['if','for','while','catch','case','?','&&','||'])
    return {'lexical_complexity_proxy':complexity_proxy,'semicolon_ncss_proxy':counts[';'],
            'decision_counts':{k:counts[k] for k in ['if','for','while','catch','case','?','&&','||']},
            'method_lines_examined':chunk.count('\n')+1}

def main():
    p=argparse.ArgumentParser();p.add_argument('--zip',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    dest=pathlib.Path(a.output);dest.mkdir(parents=True,exist_ok=True)
    z=zipfile.ZipFile(a.zip)
    payload=json.loads(z.read('analyzer/evaluation/reports/analyzer-self-analysis-2026-10-18.json'))
    finding_rows=[];seen={}
    for group in payload['ranked_groups']:
      for f in group['findings']:
        src=f['source_file'].replace('\\','/'); name='analyzer/src/main/java/'+src
        if name not in z.namelist():continue
        content=z.read(name).decode('utf-8-sig',errors='replace')
        lines=content.splitlines(keepends=True)
        start=int(f.get('start_line') or 1);end=int(f.get('end_line') or start)
        excerpt=''.join(lines[max(start-1,0):min(end,len(lines))]); sig=signals(excerpt)
        evidence=f.get('evidence',{}); con=f['concern']
        reported=evidence.get('cyclomaticComplexity','') if con=='HIGH_COMPLEXITY' else evidence.get('ncss','') if con=='LONG_METHOD' else ''
        threshold=evidence.get('configuredMaxComplexity','') if con=='HIGH_COMPLEXITY' else evidence.get('configuredMaxNcss','') if con=='LONG_METHOD' else ''
        proxy=sig['lexical_complexity_proxy'] if con=='HIGH_COMPLEXITY' else sig['semicolon_ncss_proxy'] if con=='LONG_METHOD' else ''
        numeric=lambda s: int(s) if str(s).isdigit() else None
        discrepancy= numeric(reported) is not None and proxy!='' and numeric(reported)!=proxy
        row={'finding_id':f['finding_id'],'source_file':src,'symbol':f['symbol'],'concern':con,'start_line':start,'end_line':end,'reported_metric':reported,'configured_threshold':threshold,'independent_lexical_proxy':proxy,'proxy_differs_from_reported':discrepancy if proxy!='' else '', 'proxy_limitations':'Token-based proxy; not equivalent to JavaParser AST complexity or NCSS. Includes method signature/for-loop semicolons and switch handling differences. Do NOT auto-label correctness.', 'human_gold':'','review_status':'UNREVIEWED','reviewer':'','review_note':'','decision_counts':json.dumps(sig['decision_counts'])}
        finding_rows.append(row)
        if con in ('HIGH_COMPLEXITY','LONG_METHOD'):seen[(src,start,end,con)]=True
    with (dest/'independent_metric_review.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=finding_rows[0]);w.writeheader();w.writerows(finding_rows)
    # Candidate negatives are methods named in ranked groups where the OTHER threshold finding is absent.
    # These are NOT true negatives until independently source-reviewed.
    candidates=[]
    grouped=collections.defaultdict(set)
    for r in finding_rows:grouped[(r['source_file'],r['start_line'],r['end_line'],r['symbol'])].add(r['concern'])
    for (src,start,end,symbol),present in grouped.items():
      if '(' not in symbol: continue # exclude field/class findings
      for con in ('HIGH_COMPLEXITY','LONG_METHOD'):
        if con not in present:
          candidates.append({'source_file':src,'symbol':symbol,'start_line':start,'end_line':end,'concern':con,'analyzer_predicted':0,'human_gold':'','review_status':'UNREVIEWED','review_note':'Candidate non-detection; selected from already flagged methods, not a representative random sample.'})
    with (dest/'missing_concern_candidates.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['source_file','symbol','start_line','end_line','concern','analyzer_predicted','human_gold','review_status','review_note']);w.writeheader();w.writerows(candidates)
    summaries={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_zip':pathlib.Path(a.zip).name,'findings_processed':len(finding_rows),'method_metric_predictions':sum(r['concern'] in ('HIGH_COMPLEXITY','LONG_METHOD') for r in finding_rows),'lexical_proxy_disagreements':sum(r['proxy_differs_from_reported'] is True for r in finding_rows),'candidate_missing_concerns':len(candidates),'research_limitation':'ALL labels remain UNREVIEWED. Lexical proxies are screening signals, NOT independent gold labels. No precision, recall or F1 claimed.'}
    (dest/'independent_checks_summary.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8')
    print(json.dumps(summaries,indent=2));print('Files in:',dest)
if __name__=='__main__':main()
