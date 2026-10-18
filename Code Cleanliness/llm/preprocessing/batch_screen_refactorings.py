#!/usr/bin/env python3
"""29A.4: screen LLM4Refactoring before/after source with the existing Java CLI.

Runs from Code Cleanliness/ (or any cwd). Never edits raw sources or emits labels.
Single-file snapshots are NOT whole-repository evidence. Multi-unit concatenations
are flagged and excluded from analyzer comparisons (not scored as zero findings).
"""
import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'datasets/processed/llm4refactoring_explanation_candidates.jsonl'
OUT = ROOT / 'datasets/processed/review_batch_29a/batch_screen'
ANALYZER = ROOT / 'analyzer'
MAIN = 'lk.sliit.codecleanliness.analysis.MaintainabilityTriageCli'


def source_path(raw):
    p = Path(str(raw).replace('\\', '/'))
    return p if p.is_absolute() else ROOT / p


def single_unit_warning(source):
    # Conservative signal for dataset files that concatenate two Java compilation units.
    # Never attempt silent AST splitting that could change symbol resolution.
    without_comments = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    if len(re.findall(r'(?m)^\s*package\s+[\w.]+\s*;', without_comments)) > 1:
        return 'MULTIPLE_PACKAGE_DECLARATIONS'
    if len(re.findall(r'(?m)^\s*public\s+(?:(?:final|abstract|sealed|non-sealed)\s+)*(?:class|interface|enum|record)\s+\w+', without_comments)) > 1:
        return 'MULTIPLE_PUBLIC_TOP_LEVEL_TYPES'
    # import after a top-level class declaration is impossible in a single CU
    type_decl = re.search(r'(?m)^\s*(?:(?:public|final|abstract|sealed)\s+)*(?:class|interface|enum|record)\s+\w+', without_comments)
    if type_decl and re.search(r'(?m)^\s*import\s+(?:static\s+)?[\w.*]+\s*;', without_comments[type_decl.end():]):
        return 'IMPORT_AFTER_TYPE_DECLARATION'
    return None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_findings(report):
    # Stable across file renaming and changed line numbers; not an adjudicated match.
    found = []
    for group in report.get('ranked_groups', []):
        for f in group.get('findings', []):
            found.append({'concern': f.get('concern'), 'symbol': f.get('symbol'),
                          'rule_id': f.get('rule_id'), 'scope': f.get('scope'),
                          'evidence': f.get('evidence', {})})
    return found


def run_snapshot(src, dest, classpath, timeout):
    if not src.is_file():
        return {'status': 'MISSING_SOURCE'}
    try:
        txt = src.read_text(encoding='utf-8')
    except (UnicodeError, OSError) as exc:
        return {'status': 'SOURCE_READ_ERROR', 'error': str(exc)[:500]}
    warning = single_unit_warning(txt)
    if warning:
        return {'status': 'COMPOSITE_SNAPSHOT_UNSUPPORTED', 'reason': warning}
    with tempfile.TemporaryDirectory(prefix='j26_refactoring_') as tmp:
        workspace = Path(tmp)
        (workspace / 'Snapshot.java').write_text(txt, encoding='utf-8')
        try:
            proc = subprocess.run(['java', '-cp', classpath, MAIN, str(workspace), str(dest)],
                                  capture_output=True, text=True, timeout=timeout,
                                  encoding='utf-8', errors='replace')
        except FileNotFoundError:
            return {'status': 'JAVA_NOT_FOUND'}
        except subprocess.TimeoutExpired:
            return {'status': 'ANALYZER_TIMEOUT'}
    if proc.returncode != 0 or not dest.is_file():
        dest.unlink(missing_ok=True)
        return {'status': 'ANALYZER_ERROR', 'error': (proc.stderr or proc.stdout)[-1500:]}
    try:
        data = json.loads(dest.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        dest.unlink(missing_ok=True)
        return {'status': 'INVALID_REPORT', 'error': str(exc)[:500]}
    if data.get('failed_files') or data.get('parsed_files') != 1:
        return {'status': 'PARSE_INCOMPLETE', 'parsed_files': data.get('parsed_files'),
                'failed_files': data.get('failed_files')}
    return {'status': 'OK', 'findings': stable_findings(data), 'finding_count': data.get('finding_count', 0),
            'group_count': data.get('group_count', 0)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--limit', type=int, default=0, help='First N cases; 0=all 180')
    ap.add_argument('--timeout', type=int, default=75, help='Seconds per Java invocation')
    ap.add_argument('--force', action='store_true', help='Reprocess existing case reports')
    args = ap.parse_args()
    if not MANIFEST.exists():
        sys.exit(f'Missing manifest: {MANIFEST}')
    classes = ANALYZER / 'target/classes'
    runtime = ANALYZER / 'target/runtime-classpath.txt'
    if not classes.is_dir() or not runtime.is_file():
        sys.exit('Build analyzer and runtime classpath first: cd analyzer; mvn package; mvn dependency:build-classpath "-Dmdep.outputFile=target\\runtime-classpath.txt"')
    classpath = str(classes) + (';' if sys.platform == 'win32' else ':') + runtime.read_text(encoding='utf-8-sig').strip()
    rows = [json.loads(line) for line in MANIFEST.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    if args.limit > 0:
        rows = rows[:args.limit]
    OUT.mkdir(parents=True, exist_ok=True)
    reports = OUT / 'evidence'
    reports.mkdir(exist_ok=True)
    summary_rows = []
    for i, rec in enumerate(rows, 1):
        typ = str(rec.get('refactoring_type', 'unknown'))
        eid = str(rec.get('example_id', 'unknown'))
        case = f'{re.sub(r"[^A-Za-z0-9]+", "_", typ)}_{re.sub(r"[^A-Za-z0-9]+", "_", eid)}'
        before = source_path(rec.get('before_path', ''))
        after = source_path(rec.get('after_path', ''))
        summary_file = OUT / (case + '.screen.json')
        if summary_file.exists() and not args.force:
            try:
                result = json.loads(summary_file.read_text(encoding='utf-8'))
                if result.get('input_hashes') == {'before': sha(before), 'after': sha(after)}:
                    summary_rows.append(result)
                    continue
            except (OSError, ValueError):
                pass
        result = {'case_id': case, 'source_dataset': rec.get('source_dataset'),
                  'project_name': rec.get('project_name'), 'refactoring_type': typ,
                  'example_id': eid, 'commit_sha': rec.get('commit_sha'),
                  'training_eligible': False, 'review_status': 'NEEDS_HUMAN_REVIEW',
                  'scope': 'isolated_single_file_snapshot', 'input_hashes': {}}
        if before.is_file() and after.is_file():
            result['input_hashes'] = {'before': sha(before), 'after': sha(after)}
        result['before'] = run_snapshot(before, reports / (case + '.before.json'), classpath, args.timeout)
        result['after'] = run_snapshot(after, reports / (case + '.after.json'), classpath, args.timeout)
        if result['before']['status'] == result['after']['status'] == 'OK':
            b = result['before']['findings']; a = result['after']['findings']
            before_keys = {(x['concern'], x['symbol'], x['rule_id']) for x in b}
            after_keys = {(x['concern'], x['symbol'], x['rule_id']) for x in a}
            result['comparison'] = {
                'before_count': len(b), 'after_count': len(a),
                'removed_signature_candidates': [list(x) for x in sorted(before_keys-after_keys)],
                'added_signature_candidates': [list(x) for x in sorted(after_keys-before_keys)],
                'note': 'Signature change is not proof of fixed smell or behavior preservation.'
            }
            result['review_priority'] = ('MATCH_CHANGE_REVIEW' if before_keys != after_keys
                                         else 'UNCHANGED_FINDINGS_REVIEW' if b else 'NO_DETECTED_FINDINGS')
        else:
            result['review_priority'] = 'INCOMPLETE_OR_COMPOSITE'
        summary_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        summary_rows.append(result)
        if i % 15 == 0 or i == len(rows):
            print(f'Processed {i}/{len(rows)}; latest {case}: {result["review_priority"]}', flush=True)

    priority = {'MATCH_CHANGE_REVIEW': 0, 'UNCHANGED_FINDINGS_REVIEW': 1,
                'NO_DETECTED_FINDINGS': 2, 'INCOMPLETE_OR_COMPOSITE': 3}
    summary_rows.sort(key=lambda x: (priority[x['review_priority']], x['project_name'] or '', x['case_id']))
    columns = ['case_id', 'project_name', 'refactoring_type', 'example_id', 'commit_sha',
               'review_priority', 'before_status', 'after_status', 'before_findings',
               'after_findings', 'removed_signature_count', 'added_signature_count',
               'human_decision', 'training_eligible']
    with (OUT / 'review_queue.csv').open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for x in summary_rows:
            comp = x.get('comparison', {})
            writer.writerow({'case_id': x['case_id'], 'project_name': x['project_name'],
                             'refactoring_type': x['refactoring_type'], 'example_id': x['example_id'],
                             'commit_sha': x['commit_sha'], 'review_priority': x['review_priority'],
                             'before_status': x['before']['status'], 'after_status': x['after']['status'],
                             'before_findings': x['before'].get('finding_count', ''),
                             'after_findings': x['after'].get('finding_count', ''),
                             'removed_signature_count': len(comp.get('removed_signature_candidates', [])),
                             'added_signature_count': len(comp.get('added_signature_candidates', [])),
                             'human_decision': 'NEEDS_REVIEW', 'training_eligible': 'false'})
    counts = Counter(x['review_priority'] for x in summary_rows)
    statuses = Counter((x['before']['status'], x['after']['status']) for x in summary_rows)
    overview = {'screened': len(summary_rows), 'review_priorities': dict(counts),
                'pair_statuses': [{'before': k[0], 'after': k[1], 'count': v} for k, v in sorted(statuses.items())],
                'review_ready_training_records': 0,
                'note': 'Screening outputs are NOT human-verified labels; no training eligibility granted.'}
    (OUT / 'summary.json').write_text(json.dumps(overview, indent=2), encoding='utf-8')
    print('\n=== MILESTONE 29A.4 SCREENING ===')
    print(json.dumps(overview, indent=2))
    print('Review queue:', OUT / 'review_queue.csv')


if __name__ == '__main__':
    main()
