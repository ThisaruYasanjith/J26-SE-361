
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

INPUT = ROOT / (
    "datasets/processed/"
    "llm4refactoring_quality_review.jsonl"
)

OUTPUT = ROOT / (
    "datasets/processed/"
    "llm4refactoring_suitability_review.csv"
)

COLUMNS = [
    "refactoring_type",
    "example_id",
    "project_name",
    "commit_sha",
    "original_file",
    "before_path",
    "after_path",
    "quality_flags",
    "related_before_records",
    "related_after_records",
    "review_decision",
    "review_reason",
    "verified_concerns",
    "evidence_reference",
    "context_availability",
    "reviewer",
]

VALID_DECISIONS = {
    "INCLUDE",
    "EXCLUDE",
    "NEEDS_CONTEXT",
    "NEEDS_REVIEW",
}


def main():
    if not INPUT.is_file():
        raise FileNotFoundError(INPUT)

    # Protect previous human review decisions.
    if OUTPUT.exists():
        raise FileExistsError(
            f"Review worksheet already exists: {OUTPUT}"
        )

    records = [
        json.loads(line)
        for line in INPUT.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    if len(records) != 180:
        raise ValueError(
            f"Expected 180 records, found {len(records)}"
        )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as stream:

        writer = csv.DictWriter(
            stream,
            fieldnames=COLUMNS
        )
        writer.writeheader()

        for record in records:
            row = {
                column: record.get(column, "")
                for column in COLUMNS
            }

            for field in (
                "quality_flags",
                "related_before_records",
                "related_after_records",
            ):
                row[field] = json.dumps(
                    record.get(field, []),
                    ensure_ascii=False
                )

            row["review_decision"] = "NEEDS_REVIEW"
            row["review_reason"] = ""
            row["verified_concerns"] = ""
            row["evidence_reference"] = ""
            row["context_availability"] = "NOT_CHECKED"
            row["reviewer"] = ""

            writer.writerow(row)

    print("Suitability Review Worksheet")
    print("----------------------------")
    print("Records prepared:", len(records))
    print("Initial decisions: NEEDS_REVIEW")
    print("Verified concern labels: 0")
    print("Original dataset: unchanged")
    print("Worksheet:", OUTPUT)


if __name__ == "__main__":
    main()
