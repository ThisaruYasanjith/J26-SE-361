"""
Builds data/processed/dataset.json by running the extractor over all
synthetic Java files and joining with labels from labels.csv.

Run from project root:
    python src/04_build_dataset.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

# Import the extractor by path (numeric prefix prevents normal import)
sys.path.insert(0, str(Path(__file__).parent))
import importlib
_extractor = importlib.import_module("03_extractor")
extract_from_file = _extractor.extract_from_file


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LABELS_PATH = PROJECT_ROOT / "data" / "processed" / "labels.csv"
JAVA_DIR = PROJECT_ROOT / "data" / "processed" / "synthetic_java_files"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "dataset.json"


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    print(f"Loading labels from {LABELS_PATH.relative_to(PROJECT_ROOT)}...")
    labels = _load_labels(LABELS_PATH)
    print(f"  Found {len(labels)} label rows.\n")

    print(f"Running extractor on {JAVA_DIR.relative_to(PROJECT_ROOT)}...")
    records = _extract_all(labels)
    print(f"  Extracted {len(records)} records from {len(labels)} files.\n")

    if not records:
        print("No records extracted. Aborting.")
        return 1

    unmatched = [r for r in records if r["label"] is None]
    if unmatched:
        print(f"  WARNING: {len(unmatched)} records have no matching label.")
        for r in unmatched[:5]:
            print(f"    {r['file_path']}")
        print()

    matched = [r for r in records if r["label"] is not None]

    print(f"Writing {OUTPUT_PATH.relative_to(PROJECT_ROOT)}...")
    _write_json(matched, OUTPUT_PATH)
    print(f"  Wrote {len(matched)} records.\n")

    _print_summary(matched)
    _print_preview(matched[0])

    return 0


# ============================================================
# LABELS
# ============================================================

def _load_labels(path: Path) -> dict[str, dict]:
    """Return a dict keyed by filename → label metadata."""
    result: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = row["filename"]
            result[filename] = {
                "label": int(row["label"]),
                "group": int(row["group"]),
                "defect_category": row["defect_category"] or None,
                "split": row["split"],
                "operation": row["operation"],
                "handler": row["handler"],
            }
    return result


# ============================================================
# EXTRACTION
# ============================================================

def _extract_all(labels: dict[str, dict]) -> list[dict]:
    """Run extractor over all files; join with labels."""
    result: list[dict] = []

    for i, (filename, meta) in enumerate(labels.items(), 1):
        file_path = JAVA_DIR / filename
        if not file_path.is_file():
            print(f"  Missing file: {filename}")
            continue

        try:
            file_records = extract_from_file(file_path)
        except Exception as e:
            print(f"  Extraction failed for {filename}: {e}")
            continue

        if not file_records:
            print(f"  No records for {filename}")
            continue

        for j, record in enumerate(file_records, 1):
            # Build a unique id
            base = filename.replace(".java", "")
            if len(file_records) == 1:
                record_id = base
            else:
                record_id = f"{base}__try_{j}"

            # Merge label metadata into the record
            full_record = {
                "id": record_id,
                "code": record["code"],
                "label": meta["label"],
                "defect_category": meta["defect_category"],
                "split": meta["split"],
                "group": meta["group"],
                "operation": meta["operation"],
                "handler": meta["handler"],
                "file_path": record["file_path"],
                "method_name": record["method_name"],
                "class_name": record["class_name"],
                "method_start_line": record["method_start_line"],
                "method_end_line": record["method_end_line"],
                "try_start_line": record["try_start_line"],
                "try_end_line": record["try_end_line"],
                "construct_type": record["construct_type"],
                "caught_exception_types": record["caught_exception_types"],
                "has_finally": record["has_finally"],
            }
            result.append(full_record)

        if i % 250 == 0:
            print(f"    Processed {i} / {len(labels)}")

    return result


# ============================================================
# OUTPUT
# ============================================================

def _write_json(records: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


# ============================================================
# SUMMARY
# ============================================================

def _print_summary(records: list[dict]) -> None:
    labels = Counter(r["label"] for r in records)
    splits = Counter(r["split"] for r in records)
    categories = Counter(r["defect_category"] for r in records if r["defect_category"])
    operations = Counter(r["operation"] for r in records)

    print("Summary:")
    print(f"  Total records:      {len(records)}")
    print(f"  Clean (label=0):    {labels[0]}")
    print(f"  Defective (label=1):{labels[1]}")
    print()

    print("Split distribution:")
    for split, count in splits.most_common():
        print(f"  {split:8s} {count}")
    print()

    print("Top operations:")
    for op, count in operations.most_common(12):
        print(f"  {op:25s} {count}")
    print()

    print("Defect category distribution:")
    for cat, count in categories.most_common():
        print(f"  {cat:32s} {count}")
    print()


def _print_preview(record: dict) -> None:
    print("Preview of first record:")
    preview = dict(record)
    code = preview["code"]
    if len(code) > 120:
        preview["code"] = code[:120] + "..."
    for key in ("id", "label", "defect_category", "split", "operation",
                "method_name", "construct_type", "caught_exception_types"):
        print(f"  {key}: {preview[key]}")
    print(f"  code: {preview['code']}")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    sys.exit(main())