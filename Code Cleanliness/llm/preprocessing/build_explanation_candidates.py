"""Prepare audit-only refactoring candidates; never creates training labels.
Run from the Code Cleanliness repository directory:
    python llm/preprocessing/build_explanation_candidates.py
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / 'datasets/processed/llm4refactoring_suitability_review.csv'
OUTPUT = ROOT / 'datasets/processed/llm4refactoring_explanation_candidates.jsonl'
SUMMARY = ROOT / 'datasets/processed/llm4refactoring_explanation_candidates_summary.json'


def source_path(raw: str) -> Path:
    path = Path(raw.replace('\\', '/'))
    return path if path.is_absolute() else ROOT / path


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def make_record(row: dict[str, str]) -> dict:
    before_file = source_path(row['before_path'])
    after_file = source_path(row['after_path'])
    missing = [label for label, path in [('before', before_file), ('after', after_file)] if not path.is_file()]
    result = {
        'source_dataset': 'LLM4Refactoring',
        'refactoring_type': row['refactoring_type'],
        'example_id': row['example_id'],
        'project_name': row['project_name'],
        'commit_sha': row['commit_sha'],
        'original_file': row['original_file'],
        'before_path': row['before_path'],
        'after_path': row['after_path'],
        'source_file_status': 'MISSING' if missing else 'PRESENT',
        'missing_files': missing,
        'review_decision': row['review_decision'],
        'review_reason': row['review_reason'],
        'verified_concerns': row['verified_concerns'],
        'evidence_reference': row['evidence_reference'],
        'context_availability': row['context_availability'],
        'requires_human_review': row['review_decision'] != 'INCLUDE',
        'analyzer_evidence_verified': False,
        'fine_tuning_eligible': False,
    }
    if missing:
        return result

    before = before_file.read_text(encoding='utf-8-sig', errors='replace')
    after = after_file.read_text(encoding='utf-8-sig', errors='replace')
    before_lines, after_lines = before.splitlines(), after.splitlines()
    diff = list(difflib.unified_diff(before_lines, after_lines, fromfile='before.java', tofile='after.java', lineterm=''))
    result.update({
        'before_sha256': sha256(before),
        'after_sha256': sha256(after),
        'same_content': before == after,
        'before_lines': len(before_lines),
        'after_lines': len(after_lines),
        'diff_lines': len(diff),
        'diff_excerpt': '\n'.join(diff[:120]),
        'diff_truncated': len(diff) > 120,
        'review_note': 'Inspect source context and the real analyzer results; a named refactoring is not proof of a smell or rationale.',
    })
    return result


def main() -> None:
    if not CSV.is_file():
        raise FileNotFoundError(f'Expected source CSV: {CSV}')
    with CSV.open(newline='', encoding='utf-8-sig') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError('Suitability CSV is empty')
    records = [make_record(row) for row in rows]
    # Refuse to replace previous review results silently.
    if OUTPUT.exists() or SUMMARY.exists():
        raise FileExistsError('Candidate output already exists. Move or review it before rerunning.')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    summary = {
        'total_candidates': len(records),
        'projects': len({r['project_name'] for r in records}),
        'refactoring_types': dict(sorted(Counter(r['refactoring_type'] for r in records).items())),
        'missing_source_pairs': sum(r['source_file_status'] == 'MISSING' for r in records),
        'unchanged_source_pairs': sum(r.get('same_content', False) for r in records),
        'human_review_pending': sum(r['review_decision'] == 'NEEDS_REVIEW' for r in records),
        'verified_llm_training_records': 0,
        'note': 'Audit manifest only. No model training examples or ground truth created.'
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print(f'Candidate manifest: {OUTPUT}')
    print(f'Summary: {SUMMARY}')


if __name__ == '__main__':
    main()
