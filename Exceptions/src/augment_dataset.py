"""
Dataset Augmentation Script for Exception Defect Detection.

Expands and balances the training dataset to eliminate out-of-distribution bias
and address severe class imbalance (especially for empty_catch, overly_broad_catch,
print_stacktrace, wrong_propagation, and clean constructs).

Generates diverse, realistic Java source files with varied method signatures,
variable names, parameter types, and realistic exception handling patterns.

Usage:
    python src/augment_dataset.py [--target-per-defect 90] [--clean-target 900]
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path
from typing import Any

import tree_sitter
import tree_sitter_java

# ============================================================
# CONFIG & PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LABELS_PATH = PROJECT_ROOT / "data" / "processed" / "labels.csv"
JAVA_DIR = PROJECT_ROOT / "data" / "processed" / "synthetic_java_files"
BACKUP_DIR = PROJECT_ROOT / "data" / "processed_backup_original"

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
_PARSER = tree_sitter.Parser(JAVA_LANGUAGE)

SEED = 42
random.seed(SEED)

# ============================================================
# DIVERSE VOCABULARY & TEMPLATE BUILDING BLOCKS
# ============================================================

METHOD_NAMES = [
    "validateToken", "fetchUserData", "parseConfigFile", "calculateDiscount",
    "sendNotification", "loadDocument", "executeDatabaseQuery", "transformPayload",
    "convertTimestamp", "processTransaction", "readSystemProperty", "initConnection",
    "updateUserProfile", "downloadResource", "formatDateString", "checkAuthorization",
    "sanitizeInput", "backupDatabase", "serializeState", "authenticateSession",
]

PARAM_OPTIONS = [
    ("String", "token"),
    ("String", "inputPath"),
    ("String", "jsonPayload"),
    ("int", "timeoutMs"),
    ("long", "recordId"),
    ("double", "amount"),
    ("File", "targetFile"),
]

RETURN_TYPES = ["String", "int", "boolean", "void", "double"]

# Diverse realistic bodies for try blocks
TRY_BODIES = [
    # 0: File / Stream
    {
        "imports": ["import java.io.*;", "import java.nio.file.*;"],
        "ret": "String",
        "code": "File f = new File(\"data.txt\");\n            BufferedReader br = new BufferedReader(new FileReader(f));\n            String line = br.readLine();\n            br.close();\n            return line != null ? line : \"\";",
        "exc": "IOException",
    },
    # 1: Number parsing
    {
        "imports": ["import java.text.*;"],
        "ret": "int",
        "code": "if (raw == null || raw.trim().isEmpty()) {\n                return 0;\n            }\n            return Integer.parseInt(raw.trim());",
        "exc": "NumberFormatException",
    },
    # 2: SQL / Database
    {
        "imports": ["import java.sql.*;"],
        "ret": "boolean",
        "code": "Connection conn = DriverManager.getConnection(\"jdbc:mysql://localhost:3306/db\");\n            Statement stmt = conn.createStatement();\n            boolean res = stmt.execute(\"SELECT 1\");\n            conn.close();\n            return res;",
        "exc": "SQLException",
    },
    # 3: Thread / Concurrency
    {
        "imports": ["import java.util.concurrent.*;"],
        "ret": "boolean",
        "code": "Thread.sleep(1000L);\n            return true;",
        "exc": "InterruptedException",
    },
    # 4: Network / URL
    {
        "imports": ["import java.net.*;"],
        "ret": "String",
        "code": "URL url = new URL(\"https://api.example.com/v1/health\");\n            HttpURLConnection c = (HttpURLConnection) url.openConnection();\n            c.setRequestMethod(\"GET\");\n            return String.valueOf(c.getResponseCode());",
        "exc": "IOException",
    },
    # 5: Reflection / Class loading
    {
        "imports": ["import java.lang.reflect.*;"],
        "ret": "Object",
        "code": "Class<?> clazz = Class.forName(\"com.example.ServiceHandler\");\n            return clazz.getDeclaredConstructor().newInstance();",
        "exc": "ReflectiveOperationException",
    },
    # 6: Math / Arithmetic
    {
        "imports": [],
        "ret": "int",
        "code": "int divisor = (int) (Math.random() * 2);\n            return 100 / divisor;",
        "exc": "ArithmeticException",
    },
    # 7: Date parsing
    {
        "imports": ["import java.time.*;", "import java.time.format.*;"],
        "ret": "String",
        "code": "DateTimeFormatter fmt = DateTimeFormatter.ofPattern(\"yyyy-MM-dd\");\n            LocalDate d = LocalDate.parse(\"2026-10-20\", fmt);\n            return d.toString();",
        "exc": "DateTimeParseException",
    },
]


def generate_class_code(
    class_name: str,
    method_name: str,
    defect_category: str | None,
    index: int,
) -> tuple[str, str, str]:
    """
    Generates a compilable Java class containing a try-catch block
    implementing the target defect category (or clean handling).

    Returns:
        (code_content, operation_name, handler_name)
    """
    body_info = TRY_BODIES[index % len(TRY_BODIES)]
    exc_type = body_info["exc"]
    ret_type = body_info["ret"]
    try_code = body_info["code"]
    imports_str = "\n".join(set(body_info["imports"] + ["import java.util.*;", "import java.util.logging.*;"]))

    # Default fallback return statement if method completes
    fallback_ret = ""
    if ret_type == "String":
        fallback_ret = 'return "";'
    elif ret_type in ("int", "double"):
        fallback_ret = "return 0;"
    elif ret_type == "boolean":
        fallback_ret = "return false;"
    elif ret_type == "Object":
        fallback_ret = "return null;"

    # Handlers for specific defect categories
    if defect_category == "empty_catch":
        variations = [
            f"catch ({exc_type} e) {{\n        }}",
            f"catch ({exc_type} ex) {{\n            // intentionally empty\n        }}",
            f"catch ({exc_type} err) {{\n            ; \n        }}",
            f"catch ({exc_type} exception) {{\n        }}",
        ]
        catch_block = variations[index % len(variations)]
        handler_name = "empty_catch"

    elif defect_category == "print_stacktrace":
        variations = [
            f"catch ({exc_type} e) {{\n            e.printStackTrace();\n        }}",
            f"catch ({exc_type} ex) {{\n            System.err.println(\"Failed\");\n            ex.printStackTrace();\n        }}",
            f"catch ({exc_type} err) {{\n            err.printStackTrace(System.err);\n        }}",
        ]
        catch_block = variations[index % len(variations)]
        handler_name = "print_stacktrace"

    elif defect_category == "overly_broad_catch":
        broad_type = "Exception" if index % 2 == 0 else "Throwable"
        variations = [
            f"catch ({broad_type} e) {{\n            System.out.println(\"Error: \" + e.getMessage());\n            {fallback_ret}\n        }}",
            f"catch ({broad_type} ex) {{\n            throw new RuntimeException(\"Failed\", ex);\n        }}",
        ]
        catch_block = variations[index % len(variations)]
        handler_name = "overly_broad_catch"

    elif defect_category == "wrong_propagation":
        wrong_exc = "IllegalArgumentException" if exc_type != "IllegalArgumentException" else "IllegalStateException"
        variations = [
            f"catch ({exc_type} e) {{\n            throw new {wrong_exc}(\"Operation failed due to invalid arguments\", e);\n        }}",
            f"catch ({exc_type} err) {{\n            throw new NullPointerException(\"Unexpected state encountered\");\n        }}",
        ]
        catch_block = variations[index % len(variations)]
        handler_name = "wrong_propagation"

    elif defect_category == "lost_exception_cause":
        variations = [
            f"catch ({exc_type} e) {{\n            throw new RuntimeException(\"Error executing step: \" + e.getMessage());\n        }}",
            f"catch ({exc_type} err) {{\n            throw new IllegalStateException(\"Failed to process operation\");\n        }}",
        ]
        catch_block = variations[index % len(variations)]
        handler_name = "lost_exception_cause"

    elif defect_category == "ambiguous_error_return":
        variations = [
            f"catch ({exc_type} e) {{\n            {fallback_ret}\n        }}",
            f"catch ({exc_type} ex) {{\n            return null;\n        }}",
        ]
        catch_block = variations[index % len(variations)]
        handler_name = "ambiguous_error_return"

    elif defect_category == "wrong_exception_type":
        wrong_catch = "RuntimeException" if exc_type != "RuntimeException" else "IOException"
        catch_block = f"catch ({wrong_catch} e) {{\n            throw new RuntimeException(\"Wrong exception caught\", e);\n        }}"
        handler_name = "wrong_exception_type"

    elif defect_category == "empty_catch_with_context":
        catch_block = f"catch ({exc_type} ignored) {{\n            // Expected condition during initial check; safely suppressed\n        }}"
        handler_name = "empty_catch_with_context"

    elif defect_category == "inconsistent_with_precheck":
        catch_block = f"catch ({exc_type} e) {{\n            // Redundant catch after explicit precondition check\n            {fallback_ret}\n        }}"
        handler_name = "inconsistent_with_precheck"

    elif defect_category == "corrupted_state_on_exception":
        try_code = "this.dirtyState = true;\n            " + try_code
        catch_block = f"catch ({exc_type} e) {{\n            // State mutated before exception but never rolled back\n            {fallback_ret}\n        }}"
        handler_name = "corrupted_state_on_exception"

    elif defect_category == "missing_retry":
        catch_block = f"catch ({exc_type} e) {{\n            // Transient network/IO error caught without retry policy\n            {fallback_ret}\n        }}"
        handler_name = "missing_retry"

    elif defect_category == "exception_swallowing":
        catch_block = f"catch ({exc_type} e) {{\n            // Swallow exception and return normal default\n            {fallback_ret}\n        }}"
        handler_name = "exception_swallowing"

    elif defect_category == "swallows_declared_exception":
        catch_block = f"catch ({exc_type} e) {{\n            // Declared in throws but swallowed internally\n            {fallback_ret}\n        }}"
        handler_name = "swallows_declared_exception"

    else:
        # CLEAN CONSTRUCT (Proper logging, proper rethrowing, or structured cleanup)
        variations = [
            f"catch ({exc_type} e) {{\n            Logger.getLogger(\"{class_name}\").log(Level.SEVERE, \"Encountered failure\", e);\n            throw e;\n        }}",
            f"catch ({exc_type} ex) {{\n            Logger.getLogger(\"{class_name}\").warning(\"Recoverable error: \" + ex.getMessage());\n            throw new RuntimeException(\"Operation failed\", ex);\n        }}",
            f"catch ({exc_type} e) {{\n            Logger.getLogger(\"{class_name}\").severe(\"Failure in operation: \" + e.getMessage());\n            throw e;\n        }}",
        ]
        catch_block = variations[index % len(variations)]
        handler_name = "clean"

    # Assemble complete class code
    throws_clause = f"throws {exc_type}" if "throw e;" in catch_block or defect_category == "swallows_declared_exception" else ""

    class_code = f"""package com.synthetic.augmented;

{imports_str}

public class {class_name} {{
    private boolean dirtyState = false;

    public {ret_type} {method_name}(String raw) {throws_clause} {{
        try {{
            {try_code}
        }} {catch_block}
        {fallback_ret}
    }}
}}
"""
    return class_code, f"op_{index % 8}", handler_name


def validate_java_syntax(code: str) -> bool:
    """Check that the generated code parses with tree-sitter without syntax errors."""
    try:
        tree = _PARSER.parse(code.encode("utf-8"))
        if tree is None:
            return False
        # Ensure root node is program and contains no ERROR node
        has_error = any(node.type == "ERROR" for node in _walk_nodes(tree.root_node))
        return not has_error
    except Exception:
        return False


def _walk_nodes(node: tree_sitter.Node):
    yield node
    for child in node.children:
        yield from _walk_nodes(child)


def main():
    parser = argparse.ArgumentParser(description="Augment exception defect dataset")
    parser.add_argument("--target-per-defect", type=int, default=90, help="Target count per defect category")
    parser.add_argument("--clean-target", type=int, default=850, help="Target count for clean samples")
    args = parser.parse_args()

    print("=" * 65)
    print("DATASET AUGMENTATION & BALANCING")
    print("=" * 65)

    if not LABELS_PATH.exists():
        print(f"Error: {LABELS_PATH} not found.")
        return 1

    # Load existing labels
    existing_rows = []
    with LABELS_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or [
            "filename", "class_name", "label", "group",
            "defect_category", "split", "operation", "handler"
        ]
        for row in reader:
            existing_rows.append(row)

    print(f"Loaded {len(existing_rows)} existing records from labels.csv")

    # Count existing categories
    counts: dict[str, int] = {}
    for r in existing_rows:
        cat = r["defect_category"] or "clean"
        counts[cat] = counts.get(cat, 0) + 1

    print("\nCurrent class distribution:")
    for cat, count in sorted(counts.items(), key=lambda x: x[1]):
        print(f"  {cat:<30}: {count}")

    # Determine needed augmentation
    all_defect_categories = [
        "empty_catch", "wrong_propagation", "overly_broad_catch",
        "print_stacktrace", "wrong_exception_type", "ambiguous_error_return",
        "empty_catch_with_context", "inconsistent_with_precheck",
        "lost_exception_cause", "corrupted_state_on_exception",
        "missing_retry", "inappropriate_handling",
        "swallows_declared_exception", "exception_swallowing",
    ]

    needed_per_category: dict[str, int] = {}
    for cat in all_defect_categories:
        current = counts.get(cat, 0)
        needed = max(0, args.target_per_defect - current)
        if needed > 0:
            needed_per_category[cat] = needed

    clean_current = counts.get("clean", 0)
    clean_needed = max(0, args.clean_target - clean_current)
    if clean_needed > 0:
        needed_per_category["clean"] = clean_needed

    print("\nSamples to generate per category:")
    total_to_generate = sum(needed_per_category.values())
    for cat, n in needed_per_category.items():
        print(f"  + {cat:<30}: {n}")
    print(f"Total new samples to generate: {total_to_generate}\n")

    if total_to_generate == 0:
        print("Dataset is already balanced. No new samples needed.")
        return 0

    # Ensure output java directory exists
    JAVA_DIR.mkdir(parents=True, exist_ok=True)

    new_rows = []
    current_index = len(existing_rows)
    group_id = 11

    splits = ["train"] * 7 + ["val"] * 2 + ["test"] * 1  # 70% train, 20% val, 10% test

    for cat, needed in needed_per_category.items():
        defect_label = 0 if cat == "clean" else 1
        cat_value = "" if cat == "clean" else cat

        for i in range(needed):
            current_index += 1
            class_name = f"Augmented_{cat}_{current_index:04d}"
            filename = f"{class_name}.java"
            method_name = random.choice(METHOD_NAMES)
            split = random.choice(splits)

            code, op, handler = generate_class_code(
                class_name=class_name,
                method_name=method_name,
                defect_category=cat if cat != "clean" else None,
                index=current_index,
            )

            # Validate Java syntax with tree-sitter
            if not validate_java_syntax(code):
                print(f"Warning: Syntax validation failed for {filename}, skipping.")
                continue

            file_path = JAVA_DIR / filename
            file_path.write_text(code, encoding="utf-8")

            new_rows.append({
                "filename": filename,
                "class_name": class_name,
                "label": defect_label,
                "group": group_id,
                "defect_category": cat_value,
                "split": split,
                "operation": op,
                "handler": handler,
            })

    print(f"Successfully generated and wrote {len(new_rows)} Java source files.")

    # Write combined rows to labels.csv
    combined_rows = existing_rows + new_rows
    with LABELS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(combined_rows)

    print(f"Updated {LABELS_PATH.relative_to(PROJECT_ROOT)} (now {len(combined_rows)} total rows).")

    # Print final summary
    final_counts: dict[str, int] = {}
    for r in combined_rows:
        c = r["defect_category"] or "clean"
        final_counts[c] = final_counts.get(c, 0) + 1

    print("\n" + "=" * 65)
    print("FINAL BALANCED CLASS DISTRIBUTION")
    print("=" * 65)
    for cat, count in sorted(final_counts.items(), key=lambda x: x[1]):
        print(f"  {cat:<30}: {count}")

    print("\nNext step: Run 'python src/04_build_dataset.py' to rebuild dataset.json.")
    return 0


if __name__ == "__main__":
    main()
