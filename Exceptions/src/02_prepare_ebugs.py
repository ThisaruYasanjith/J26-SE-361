from pathlib import Path

import pandas as pd


# --------------------------------------------------
# Configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "ebugs_raw.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "ebugs_normalized.csv"


# --------------------------------------------------
# Column mapping
# --------------------------------------------------

COLUMN_MAPPING = {
    "System": "system",
    "ID": "ebugs_id",
    "Commit #": "commit_url",

    "Triggering Condition\nError Type": "triggering_error_type",
    "Triggering Condition\nScenario": "triggering_scenario",
    "Triggering Condition\nTiming Requirement": "timing_requirement",

    "Root Cause Type": "root_cause_type",
    "Type of Inaccuracy": "type_of_inaccuracy",

    "Root Exception": "root_exception",
    "Missed Exception": "missed_exception",

    "Throwing Distance\nbefore Fix": "throwing_distance_before_fix",
    "Throwing Distance\nafter Fix": "throwing_distance_after_fix",

    "Exceptions Need Further Differentiation on":
        "exception_differentiation",

    "Exceptions Triggered by Same Condition Type Need Different Handling":
        "same_condition_different_handling",

    "Symptom Type": "symptom_type",
    "Issue Priority": "issue_priority",
}


# --------------------------------------------------
# Load dataset
# --------------------------------------------------

def load_dataset(file_path: Path) -> pd.DataFrame:
    """
    Load the raw eBugs CSV dataset.
    """

    if not file_path.exists():
        raise FileNotFoundError(
            f"Input dataset not found: {file_path}"
        )

    return pd.read_csv(file_path)


# --------------------------------------------------
# Normalize columns
# --------------------------------------------------

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename the original eBugs column names to
    stable internal column names.
    """

    missing_columns = [
        column
        for column in COLUMN_MAPPING
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "Expected columns were not found:\n"
            + "\n".join(missing_columns)
        )

    df = df.rename(columns=COLUMN_MAPPING)

    return df


# --------------------------------------------------
# Normalize missing values
# --------------------------------------------------

def normalize_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert empty strings and whitespace-only strings
    into pandas missing values.
    """

    df = df.replace(
        r"^\s*$",
        pd.NA,
        regex=True
    )

    return df


# --------------------------------------------------
# Validate dataset
# --------------------------------------------------

def validate_dataset(df: pd.DataFrame) -> None:
    """
    Validate the normalized eBugs dataset and print
    useful dataset statistics.
    """

    print("\n" + "=" * 60)
    print("NORMALIZED DATASET VALIDATION")
    print("=" * 60)

    # --------------------------------------------------
    # Basic dimensions
    # --------------------------------------------------

    print(f"\nRows    : {len(df)}")
    print(f"Columns : {len(df.columns)}")

    if len(df) != 210:
        print(
            f"\nWARNING: Expected 210 records, "
            f"but found {len(df)}."
        )

    # --------------------------------------------------
    # Column names
    # --------------------------------------------------

    print("\nColumns:")

    for index, column in enumerate(df.columns, start=1):
        print(f"  {index}. {column}")

    # --------------------------------------------------
    # Duplicate validation
    # --------------------------------------------------
    #
    # eBugs IDs are NOT globally unique.
    #
    # Example:
    #   HBase      6649
    #   YARN       6649
    #
    # Therefore, the correct uniqueness key is:
    #
    #   system + ebugs_id
    #
    # --------------------------------------------------

    print("\nDuplicate (System + eBugs ID) pairs:")

    duplicate_mask = df.duplicated(
        subset=["system", "ebugs_id"],
        keep=False
    )

    duplicate_count = df.duplicated(
        subset=["system", "ebugs_id"]
    ).sum()

    print(f"  {duplicate_count}")

    if duplicate_count > 0:

        print(
            "\nWARNING: Duplicate records found "
            "for the same system and eBugs ID:"
        )

        duplicate_rows = df.loc[
            duplicate_mask,
            ["system", "ebugs_id", "commit_url"]
        ]

        print(
            duplicate_rows
            .sort_values(["system", "ebugs_id"])
            .to_string(index=False)
        )

    # --------------------------------------------------
    # Systems
    # --------------------------------------------------

    print("\nSystems:")

    print(
        df["system"]
        .value_counts()
        .to_string()
    )

    # --------------------------------------------------
    # Root cause types
    # --------------------------------------------------

    print("\nRoot Cause Types:")

    print(
        df["root_cause_type"]
        .value_counts()
        .to_string()
    )

    # --------------------------------------------------
    # Issue priorities
    # --------------------------------------------------

    print("\nIssue Priorities:")

    print(
        df["issue_priority"]
        .value_counts()
        .to_string()
    )

    # --------------------------------------------------
    # Missing values
    # --------------------------------------------------

    print("\nMissing Values:")

    missing_values = df.isna().sum()

    missing_values = missing_values[
        missing_values > 0
    ]

    if missing_values.empty:
        print("  None")
    else:
        print(
            missing_values
            .to_string()
        )


# --------------------------------------------------
# Save dataset
# --------------------------------------------------

def save_dataset(
    df: pd.DataFrame,
    file_path: Path
) -> None:
    """
    Save the normalized dataset.
    """

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        file_path,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nNormalized dataset saved to:")
    print(f"  {file_path}")


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    print("=" * 60)
    print("eBugs Dataset Preparation")
    print("=" * 60)

    print("\nInput:")
    print(f"  {INPUT_FILE}")

    # --------------------------------------------------
    # Load
    # --------------------------------------------------

    df = load_dataset(INPUT_FILE)

    # --------------------------------------------------
    # Normalize column names
    # --------------------------------------------------

    df = normalize_columns(df)

    # --------------------------------------------------
    # Normalize missing values
    # --------------------------------------------------

    df = normalize_missing_values(df)

    # --------------------------------------------------
    # Validate
    # --------------------------------------------------

    validate_dataset(df)

    # --------------------------------------------------
    # Save
    # --------------------------------------------------

    save_dataset(
        df,
        OUTPUT_FILE
    )

    print("\nDataset preparation completed successfully.")


# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":
    main()