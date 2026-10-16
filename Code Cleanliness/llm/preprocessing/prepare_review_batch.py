
import argparse
import csv
import difflib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WORKSHEET = (
    ROOT
    / "datasets/processed/llm4refactoring_suitability_review.csv"
)

OUTPUT_DIR = ROOT / "datasets/processed/suitability_batches"


def resolve_source(raw_path):
    """Resolve dataset paths without accepting paths outside ROOT."""
    path = Path(raw_path)

    if not path.is_absolute():
        path = ROOT / path

    path = path.resolve()

    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError(f"Path outside project: {raw_path}")

    return path


def read_code(path):
    if not path.is_file():
        return None

    return path.read_text(
        encoding="utf-8",
        errors="replace"
    ).splitlines()


def compact_json(value):
    try:
        return json.dumps(
            json.loads(value),
            ensure_ascii=False
        )
    except (TypeError, ValueError):
        return value or "[]"


def build_entry(row):
    before_path = resolve_source(row["before_path"])
    after_path = resolve_source(row["after_path"])

    before = read_code(before_path)
    after = read_code(after_path)

    heading = (
        f"## {row['refactoring_type']} "
        f"#{row['example_id']} — {row['project_name']}"
    )

    lines = [
        heading,
        "",
        f"- Commit: `{row['commit_sha']}`",
        f"- Original file: `{row['original_file']}`",
        f"- Before path: `{row['before_path']}`",
        f"- After path: `{row['after_path']}`",
        f"- Quality flags: `{compact_json(row['quality_flags'])}`",
        f"- Related-before records: "
        f"`{compact_json(row['related_before_records'])}`",
        f"- Related-after records: "
        f"`{compact_json(row['related_after_records'])}`",
        f"- Current decision: `{row['review_decision']}`",
        "",
    ]

    if before is None or after is None:
        lines.extend([
            "**Source availability:** Incomplete.",
            "",
            f"- Before exists: `{before is not None}`",
            f"- After exists: `{after is not None}`",
            "",
            "**Review status:** Source inspection required.",
            "",
        ])
        return "\n".join(lines)

    diff = list(difflib.unified_diff(
        before,
        after,
        fromfile="before.java",
        tofile="after.java",
        lineterm="",
        n=3
    ))

    lines.extend([
        f"- Before lines: {len(before)}",
        f"- After lines: {len(after)}",
        f"- Unified diff lines: {len(diff)}",
        "",
        "### Actual code differences",
        "",
        "```diff",
    ])

    lines.extend(diff if diff else ["No textual differences."])

    lines.extend([
        "```",
        "",
        "### Evidence-review checklist",
        "",
        "- [ ] Validate actual transformation",
        "- [ ] Check maintainability metrics and findings",
        "- [ ] Check repository/dependency context",
        "- [ ] Identify supported concern, if any",
        "- [ ] Record evidence and uncertainty",
        "- [ ] Assign justified review decision",
        "",
        "---",
        "",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()

    if args.start < 0 or args.count < 1:
        parser.error("Start must be >= 0 and count must be >= 1")

    if not WORKSHEET.is_file():
        raise FileNotFoundError(WORKSHEET)

    with WORKSHEET.open(
        encoding="utf-8-sig",
        newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))

    selected = [
        row for row in rows
        if row["review_decision"] == "NEEDS_REVIEW"
    ]

    batch = selected[args.start:args.start + args.count]

    if not batch:
        print("No unreviewed examples in this range.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    end = args.start + len(batch)

    output = OUTPUT_DIR / (
        f"review_batch_{args.start + 1:03d}_{end:03d}.md"
    )

    # Never overwrite an existing review report.
    if output.exists():
        raise FileExistsError(
            f"Review batch already exists: {output}"
        )

    sections = [
        "# LLM4Refactoring — Evidence Review Batch",
        "",
        f"Records selected: {len(batch)}",
        "",
        "This report contains source comparisons and",
        "review prompts, not verified concern labels.",
        "",
        "---",
        "",
    ]

    for row in batch:
        sections.append(build_entry(row))

    output.write_text(
        "\n".join(sections),
        encoding="utf-8"
    )

    print("Batch report created:", output)
    print("Records included:", len(batch))
    print("Original dataset: unchanged")
    print("Suitability worksheet: unchanged")
    print("Verified labels automatically assigned: 0")


if __name__ == "__main__":
    main()
