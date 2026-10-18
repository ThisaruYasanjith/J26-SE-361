#!/usr/bin/env python3
"""Milestone 29A: create a human-review batch, NOT training labels.
Run from Code Cleanliness project root: python llm/preprocessing/prepare_first_training_review.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ROOT / 'datasets/processed/llm4refactoring_explanation_candidates.jsonl'
OUT = ROOT / 'datasets/processed/review_batch_29a'

# Refactoring is only a search hint, not proof of a detected smell.
# Prioritize previously inspected promising cases and then fill from distinct projects.
PRIORITY = [('Extract Method', '4'), ('Extract Method', '18'),
            ('Extract Method', '20'), ('Extract Method', '1'),
            ('Extract Class', '11')]
MAX_CASES = 12
MAX_SOURCE_LINES = 220
MAX_DIFF_CHARS = 10000

def from_manifest_path(raw):
    # Preserve source data; accepts Windows backslashes in manifest on Unix and Windows.
    p = Path(str(raw).replace('\\', '/'))
    return p if p.is_absolute() else ROOT / p

def excerpt(path):
    if not path.is_file():
        return '[SOURCE FILE MISSING]'
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    if len(lines) <= MAX_SOURCE_LINES:
        selected = [(i, line) for i, line in enumerate(lines, 1)]
    else:
        half = MAX_SOURCE_LINES // 2
        selected = list(enumerate(lines[:half], 1)) + [(None, f'... {len(lines)-MAX_SOURCE_LINES} LINES OMITTED ...')] + list(enumerate(lines[-half:], len(lines)-half+1))
    return '\n'.join((f'{i:>5}: {line}' if i is not None else line) for i, line in selected)


def main():
    if not CANDIDATES.is_file():
        raise SystemExit(f'Missing manifest: {CANDIDATES}')
    rows = [json.loads(line) for line in CANDIDATES.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    by_key = {(str(r.get('refactoring_type')), str(r.get('example_id'))): r for r in rows}
    selected, used_keys, used_projects = [], set(), set()

    def add(row):
        key = (str(row.get('refactoring_type')), str(row.get('example_id')))
        if key in used_keys or row.get('source_file_status') != 'PRESENT' or row.get('same_content'):
            return False
        if not all(from_manifest_path(row.get(field, '')).is_file() for field in ('before_path', 'after_path')):
            return False
        selected.append(row)
        used_keys.add(key)
        used_projects.add(row.get('project_name'))
        return True

    for key in PRIORITY:
        if key in by_key:
            add(by_key[key])

    # Prefer a mix of real projects and Extract Method cases without interpreting suitability.
    pool = [r for r in rows if r.get('refactoring_type') in ('Extract Method', 'Extract Class', 'Inline Method')]
    for row in pool:
        if len(selected) >= MAX_CASES: break
        if row.get('project_name') not in used_projects:
            add(row)
    for row in pool:
        if len(selected) >= MAX_CASES: break
        add(row)

    if not selected:
        raise SystemExit('No suitable source pairs could be located; manifest paths or dataset root may differ.')
    OUT.mkdir(parents=True, exist_ok=True)
    fields = ['case_id', 'project_name', 'refactoring_type', 'example_id', 'commit_sha',
              'original_file', 'before_path', 'after_path', 'human_decision',
              'observed_change', 'supported_maintainability_concerns',
              'verified_analyzer_finding_ids', 'developer_rationale_source',
              'approved_explanation', 'limitation_notes', 'reviewer', 'review_date']
    csv_path = OUT / 'review_decisions.csv'
    with csv_path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, row in enumerate(selected, 1):
            record = {k: row.get(k, '') for k in fields}
            record['case_id'] = f'29A-{i:02d}'
            record['human_decision'] = 'NEEDS_REVIEW'
            record['supported_maintainability_concerns'] = ''
            record['approved_explanation'] = ''
            writer.writerow(record)

    bundle = OUT / 'source_review_bundle.md'
    with bundle.open('w', encoding='utf-8') as f:
        f.write('# Milestone 29A — First human review batch\n\n')
        f.write('**NOT training examples.** Case eligibility and explanations must be verified by a reviewer. '
                'Source excerpts may omit middle lines; inspect original files and commits before approving. '
                'A refactoring category does not prove that any analyzer concern exists.\n\n')
        for i, row in enumerate(selected, 1):
            before = from_manifest_path(row['before_path'])
            after = from_manifest_path(row['after_path'])
            f.write(f"\n## 29A-{i:02d} — {row['project_name']} — {row['refactoring_type']} #{row['example_id']}\n\n")
            f.write(f"Commit: `{row.get('commit_sha','')}`  \nOriginal file: `{row.get('original_file','')}`\n\n")
            f.write('### Manifest diff (may be truncated)\n\n```diff\n'+str(row.get('diff_excerpt',''))[:MAX_DIFF_CHARS]+'\n```\n\n')
            f.write('### Before excerpt\n\n```java\n'+excerpt(before)+'\n```\n\n')
            f.write('### After excerpt\n\n```java\n'+excerpt(after)+'\n```\n\n')
    print(f'Manifest records: {len(rows)}')
    print(f'Human-review cases selected: {len(selected)}')
    print(f'Review decisions: {csv_path.relative_to(ROOT)}')
    print(f'Source review bundle: {bundle.relative_to(ROOT)}')
    print('Training-ready examples created: 0 (requires review)')
    print('Priority cases included:', ', '.join(f"{r['refactoring_type']} #{r['example_id']}" for r in selected[:5]))

if __name__ == '__main__':
    main()
