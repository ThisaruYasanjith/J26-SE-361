#!/usr/bin/env python3
"""Create a concise, non-label review packet for the 12 changed-signature cases.

Run from Code Cleanliness/ with Python 3.9+. Read-only except output packet files.
No automatic acceptance, training labels, or claims of refactoring correctness.
"""
import csv
import difflib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'datasets/processed/review_batch_29a/batch_screen'
MANIFEST = ROOT / 'datasets/processed/llm4refactoring_explanation_candidates.jsonl'
OUT = BASE / 'priority_review_packet.md'
TSV = BASE / 'priority_review_decisions.csv'


def path_for(raw):
    p = Path(str(raw).replace('\\', '/'))
    return p if p.is_absolute() else ROOT / p


def safe_str(value):
    return str(value if value is not None else '').replace('|', '\\|').replace('\n', ' ')


def compact_findings(items):
    if not items:
        return 'None detected'
    return '; '.join(f"{x.get('concern', '?')} @ {x.get('symbol', '?')}" for x in items)


def diff_focus(before, after, max_lines=62):
    a = before.splitlines()
    b = after.splitlines()
    lines = list(difflib.unified_diff(a, b, fromfile='before.java', tofile='after.java', n=2, lineterm=''))
    if len(lines) <= max_lines:
        return '\n'.join(lines)
    # Show first change and, if different, last change; clearly identify omissions.
    left = max_lines // 2
    right = max_lines - left
    return '\n'.join(lines[:left] + [f'... [{len(lines)-max_lines} DIFF LINES OMITTED; inspect original sources] ...'] + lines[-right:])


def read_json(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def main():
    if not MANIFEST.is_file() or not (BASE / 'review_queue.csv').is_file():
        raise SystemExit('Missing manifest or screening results. Run batch_screen_refactorings.py first.')
    manifest = {(str(x.get('refactoring_type')), str(x.get('example_id'))): x
                for line in MANIFEST.read_text(encoding='utf-8-sig').splitlines() if line.strip()
                for x in [json.loads(line)]}
    with (BASE / 'review_queue.csv').open(newline='', encoding='utf-8-sig') as f:
        selected = [r for r in csv.DictReader(f) if r.get('review_priority') == 'MATCH_CHANGE_REVIEW']
    doc = ['# Milestone 29B — High-priority source review packet', '',
           'SCREENING EVIDENCE, NOT VERIFIED GROUND TRUTH OR TRAINING LABELS.',
           'Signatures can change because methods were renamed/moved. An unchanged flag can still hide a metric change.',
           'Only isolated Java snapshots were analyzed; whole-project behavior, compilation, and tests remain unverified.', '',
           f'Cases selected: **{len(selected)}**', '']
    decision_rows = []
    for item in selected:
        case = item['case_id']
        typ, eid = item['refactoring_type'], str(item['example_id'])
        rec = manifest.get((typ, eid))
        screen_file = BASE / f'{case}.screen.json'
        if rec is None or not screen_file.is_file():
            raise SystemExit(f'Missing manifest or screen record for {case}')
        screen = read_json(screen_file)
        bef, aft = screen['before'], screen['after']
        comparison = screen.get('comparison', {})
        bp, ap = path_for(rec['before_path']), path_for(rec['after_path'])
        if not bp.is_file() or not ap.is_file():
            raise SystemExit(f'Missing source pair for {case}')
        before, after = bp.read_text(encoding='utf-8-sig'), ap.read_text(encoding='utf-8-sig')
        bf = bef.get('findings', [])
        af = aft.get('findings', [])
        removed = comparison.get('removed_signature_candidates', [])
        added = comparison.get('added_signature_candidates', [])
        doc += [f'## {case} — {safe_str(item["project_name"])} — {typ}', '',
                f'- Commit: `{safe_str(rec.get("commit_sha"))}`',
                f'- Original path: `{safe_str(rec.get("original_file"))}`',
                f'- Snapshot parse statuses: {bef.get("status")} → {aft.get("status")}',
                f'- Counts: {bef.get("finding_count", 0)} → {aft.get("finding_count", 0)}',
                f'- BEFORE findings: {compact_findings(bf)}',
                f'- AFTER findings: {compact_findings(af)}',
                f'- Removed signatures: `{json.dumps(removed, ensure_ascii=False)}`',
                f'- Added signatures: `{json.dumps(added, ensure_ascii=False)}`', '',
                '### Focused source diff (possibly abbreviated)', '', '```diff',
                diff_focus(before, after), '```', '',
                '**Reviewer decision:** PENDING. Compare the actual changed code to the *same* analyzer finding; examine metrics, semantics and developer rationale before approval.', '']
        decision_rows.append({
            'case_id': case, 'project_name': item['project_name'],
            'review_decision': 'NEEDS_REVIEW', 'matched_concern': '',
            'relevant_before_finding_id': '', 'source_evidence_notes': '',
            'metric_comparison': '', 'approved_explanation': '',
            'limitations': '', 'reviewer': '', 'review_date': '',
            'training_eligible': 'false'
        })
    OUT.write_text('\n'.join(doc) + '\n', encoding='utf-8')
    with TSV.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(decision_rows[0].keys())) if decision_rows else None
        if writer:
            writer.writeheader()
            writer.writerows(decision_rows)
    print('Cases:', len(selected))
    print('Review packet:', OUT)
    print('Approval sheet:', TSV)
    print('Automatically approved training records: 0')
    print('Tip: upload priority_review_packet.md for evidence-based review of all cases.')


if __name__ == '__main__':
    main()
