
import json
from collections import Counter, defaultdict
from pathlib import Path

COMPONENT_ROOT = Path(__file__).resolve().parents[2]

INVENTORY_PATH = (
    COMPONENT_ROOT
    / "datasets/processed/llm4refactoring_inventory.jsonl"
)

OUTPUT_PATH = (
    COMPONENT_ROOT
    / "datasets/processed/llm4refactoring_quality_review.jsonl"
)

REQUIRED_METADATA = (
    "project_name",
    "commit_sha",
    "original_file",
    "refactoring_metadata",
)


def load_inventory(path):
    if not path.is_file():
        raise FileNotFoundError(f"Inventory not found: {path}")

    records = []

    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue

            record = json.loads(line)

            if not isinstance(record, dict):
                raise ValueError(
                    f"Expected JSON object on line {line_number}"
                )

            records.append(record)

    return records


def build_hash_groups(records, field):
    groups = defaultdict(list)

    for record in records:
        digest = record.get(field)

        if digest:
            identifier = (
                str(record.get("refactoring_type", "")),
                str(record.get("example_id", "")),
            )
            groups[digest].append(identifier)

    return groups


def review_records(records):
    before_groups = build_hash_groups(
        records, "before_sha256"
    )

    after_groups = build_hash_groups(
        records, "after_sha256"
    )

    results = []

    for record in records:
        category = str(
            record.get("refactoring_type", "")
        )
        example_id = str(
            record.get("example_id", "")
        )

        identifier = (category, example_id)
        flags = []

        if record.get("status") != "valid_pair":
            flags.append("INVALID_FILE_PAIR")

        if any(
            not record.get(field)
            for field in REQUIRED_METADATA
        ):
            flags.append("MISSING_METADATA")

        before_hash = record.get("before_sha256")
        after_hash = record.get("after_sha256")

        before_related = [
            {"refactoring_type": kind, "example_id": eid}
            for kind, eid in before_groups.get(
                before_hash, []
            )
            if (kind, eid) != identifier
        ]

        after_related = [
            {"refactoring_type": kind, "example_id": eid}
            for kind, eid in after_groups.get(
                after_hash, []
            )
            if (kind, eid) != identifier
        ]

        if before_related:
            flags.append("REPEATED_BEFORE_CODE")

        if after_related:
            flags.append("REPEATED_AFTER_CODE")

        if (
            before_hash
            and after_hash
            and before_hash == after_hash
        ):
            flags.append("UNCHANGED_BEFORE_AFTER_CODE")

        if (
            record.get("before_bytes", 0) <= 0
            or record.get("after_bytes", 0) <= 0
        ):
            flags.append("EMPTY_CODE_FILE")

        # These flags only describe data quality.
        # They are not maintainability-smell labels.
        #
        # Every record still requires suitability review.

        results.append({
            "source": record.get("source"),
            "refactoring_type": category,
            "example_id": example_id,
            "project_name": record.get("project_name"),
            "commit_sha": record.get("commit_sha"),
            "original_file": record.get("original_file"),
            "before_path": record.get("before_path"),
            "after_path": record.get("after_path"),
            "quality_flags": flags,
            "related_before_records": before_related,
            "related_after_records": after_related,
            "suitability_status": "NOT_REVIEWED",
            "suitability_reason": None,
            "verified_maintainability_concerns": [],
            "explanation_label_status": "NOT_STARTED",
        })

    return results


def write_jsonl(records, path):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(
                json.dumps(record, ensure_ascii=False)
                + "\n"
            )


def main():
    inventory = load_inventory(INVENTORY_PATH)

    keys = [
        (
            str(record.get("refactoring_type", "")),
            str(record.get("example_id", "")),
        )
        for record in inventory
    ]

    if len(keys) != len(set(keys)):
        raise ValueError(
            "Duplicate category/ID combinations found"
        )

    reviews = review_records(inventory)
    write_jsonl(reviews, OUTPUT_PATH)

    flag_counts = Counter(
        flag
        for review in reviews
        for flag in review["quality_flags"]
    )

    print("LLM4Refactoring Quality Review")
    print("--------------------------------")
    print("Records reviewed:", len(reviews))
    print("Suitability status: NOT_REVIEWED")

    print("\nQuality flags:")
    if flag_counts:
        for flag, count in sorted(flag_counts.items()):
            print(f"  {flag}: {count}")
    else:
        print("  No quality flags")

    flagged_records = sum(
        bool(review["quality_flags"])
        for review in reviews
    )

    print("\nRecords with quality flags:", flagged_records)
    print("Records without quality flags:",
          len(reviews) - flagged_records)

    print("\nReview manifest saved to:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
