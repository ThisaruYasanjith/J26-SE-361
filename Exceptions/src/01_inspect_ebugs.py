from pathlib import Path

import pandas as pd


# --------------------------------------------------
# Configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "ebugs.xlsx"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "ebugs_raw.csv"


# --------------------------------------------------
# Load Excel dataset
# --------------------------------------------------

def load_dataset(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {file_path}"
        )

    excel_file = pd.ExcelFile(file_path)

    print("\nAvailable sheets:")
    for sheet in excel_file.sheet_names:
        print(f"  - {sheet}")

    target_sheet = "eBugs-collected-from-JIRA"

    if target_sheet not in excel_file.sheet_names:
        raise ValueError(
            f"Required sheet '{target_sheet}' was not found."
        )

    print(f"\nUsing sheet:")
    print(f"  {target_sheet}")

    df = pd.read_excel(
        file_path,
        sheet_name=target_sheet
    )

    return df


# --------------------------------------------------
# Inspect dataset
# --------------------------------------------------

def inspect_dataset(df: pd.DataFrame) -> None:
    print("\n" + "=" * 60)
    print("DATASET INFORMATION")
    print("=" * 60)

    print(f"Number of rows    : {len(df)}")
    print(f"Number of columns : {len(df.columns)}")

    print("\nColumn names:")
    for index, column in enumerate(df.columns, start=1):
        print(f"  {index}. {column}")

    print("\nFirst 5 records:")
    print(df.head().to_string())

    print("\nMissing values:")
    missing = df.isna().sum()

    for column, count in missing.items():
        print(f"  {column}: {count}")

    print("\nDuplicate rows:")
    print(f"  {df.duplicated().sum()}")

    print("\nData types:")
    print(df.dtypes)


# --------------------------------------------------
# Save raw CSV copy
# --------------------------------------------------

def save_csv(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"\nCSV copy saved to:")
    print(f"  {output_path}")


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    print("=" * 60)
    print("eBugs Dataset Inspection")
    print("=" * 60)

    print(f"\nInput file:")
    print(f"  {INPUT_FILE}")

    df = load_dataset(INPUT_FILE)

    inspect_dataset(df)

    save_csv(df, OUTPUT_FILE)

    print("\nInspection completed successfully.")


if __name__ == "__main__":
    main()