"""
Preprocessing: tokenize each method with GraphCodeBERT's tokenizer,
and serialize its AST with tree-sitter-java for the structural stream.

Input:  data/processed/dataset.json  (built by 04_build_dataset.py)
Output: data/processed/preprocessed.json
        + data/processed/ast_vocab.json  (AST node type -> integer ID)

Both streams (semantic + structural) are computed from the same `code`
field and saved side by side. The model will consume them in parallel.

Run from project root:
    python src/06_tokenize_and_ast.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import tree_sitter
import tree_sitter_java
from transformers import AutoTokenizer


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "dataset.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessed.json"
AST_VOCAB_PATH = PROJECT_ROOT / "data" / "processed" / "ast_vocab.json"

GCBERT_MODEL_NAME = "microsoft/graphcodebert-base"

MAX_TOKEN_LEN = 512       # GraphCodeBERT input limit
MAX_AST_LEN = 256         # Cap for structural stream


# ============================================================
# PARSER SETUP
# ============================================================

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
_PARSER = tree_sitter.Parser(JAVA_LANGUAGE)


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    print(f"Loading dataset from {DATASET_PATH.relative_to(PROJECT_ROOT)}...")
    records = _load_json(DATASET_PATH)
    print(f"  Loaded {len(records)} records.\n")

    print(f"Loading tokenizer {GCBERT_MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(GCBERT_MODEL_NAME)
    print("  Done.\n")

    # ---------------------------------------------------------
    # Step 1: sanity check token lengths
    # ---------------------------------------------------------
    print(f"Checking token lengths (limit: {MAX_TOKEN_LEN})...")
    over = check_token_lengths(records, tokenizer, max_tokens=MAX_TOKEN_LEN)
    if over:
        print(f"  WARNING: {len(over)} records exceed the limit.")
    print()

    # ---------------------------------------------------------
    # Step 2: build AST vocabulary
    # ---------------------------------------------------------
    print("Building AST vocabulary...")
    ast_vocab = _build_ast_vocab(records)
    print(f"  Vocabulary size: {len(ast_vocab)} node types.\n")
    _save_json(ast_vocab, AST_VOCAB_PATH)
    print(f"  Wrote {AST_VOCAB_PATH.relative_to(PROJECT_ROOT)}\n")

    # ---------------------------------------------------------
    # Step 3: preprocess each record
    # ---------------------------------------------------------
    print("Preprocessing records...")
    preprocessed: list[dict[str, Any]] = []
    skipped = 0

    for i, record in enumerate(records, 1):
        code = record["code"]

        # --- Semantic stream: tokenize with GraphCodeBERT ---
        enc = tokenizer(
            code,
            max_length=MAX_TOKEN_LEN,
            truncation=True,
            padding="max_length",
            return_attention_mask=True,
            return_tensors=None,   # return python lists
        )
        input_ids = enc["input_ids"]
        attention_mask = enc["attention_mask"]

        # --- Structural stream: parse AST and serialize ---
        ast_ids = _serialize_ast(code, ast_vocab)
        if ast_ids is None:
            skipped += 1
            continue

        preprocessed.append({
            "id": record["id"],
            "label": record["label"],
            "split": record["split"],
            "defect_category": record["defect_category"],
            "operation": record["operation"],
            "file_path": record["file_path"],
            "method_name": record["method_name"],
            "construct_type": record["construct_type"],
            "caught_exception_types": record["caught_exception_types"],
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "ast_ids": ast_ids,
        })

        if i % 250 == 0:
            print(f"    Processed {i} / {len(records)}")

    print(f"\n  Preprocessed {len(preprocessed)} records ({skipped} skipped).\n")

    # ---------------------------------------------------------
    # Step 4: write output
    # ---------------------------------------------------------
    print(f"Writing {OUTPUT_PATH.relative_to(PROJECT_ROOT)}...")
    _save_json(preprocessed, OUTPUT_PATH)
    print(f"  Wrote {len(preprocessed)} records.\n")

    # ---------------------------------------------------------
    # Step 5: summary
    # ---------------------------------------------------------
    _print_summary(preprocessed)

    return 0


# ============================================================
# TOKEN LENGTH CHECK
# ============================================================

def check_token_lengths(
    records: list[dict],
    tokenizer,
    max_tokens: int = 512,
) -> list[tuple[str, int]]:
    """
    Return a list of (record_id, token_length) for records that exceed
    the token limit. Prints a summary.
    """
    over: list[tuple[str, int]] = []
    for r in records:
        token_ids = tokenizer(r["code"], truncation=False)["input_ids"]
        if len(token_ids) > max_tokens:
            over.append((r["id"], len(token_ids)))

    if over:
        print(f"  {len(over)} records exceed {max_tokens} tokens:")
        for rid, length in over[:5]:
            print(f"    {rid}: {length} tokens")
        if len(over) > 5:
            print(f"    ... and {len(over) - 5} more.")
    else:
        print(f"  All {len(records)} records fit within {max_tokens} tokens.")
    return over


# ============================================================
# AST VOCABULARY
# ============================================================

def _build_ast_vocab(records: list[dict]) -> dict[str, int]:
    """
    Two-pass: walk all ASTs, count node types, then assign IDs.

    We reserve:
        - ID 0 for PAD
        - ID 1 for UNK
        - IDs 2..N for actual node types (sorted by frequency)
    """
    counts: Counter[str] = Counter()

    for r in records:
        tree = _parse_code(r["code"])
        if tree is None:
            continue
        for node in _walk_nodes(tree.root_node):
            counts[node.type] += 1

    vocab: dict[str, int] = {"<pad>": 0, "<unk>": 1}
    for node_type, _ in counts.most_common():
        vocab[node_type] = len(vocab)
    return vocab


def _serialize_ast(code: str, ast_vocab: dict[str, int]) -> list[int] | None:
    """
    Parse the code with tree-sitter, walk the AST in pre-order, and return
    the sequence of node type IDs (capped at MAX_AST_LEN).
    """
    tree = _parse_code(code)
    if tree is None:
        return None

    ids: list[int] = []
    unk_id = ast_vocab["<unk>"]
    pad_id = ast_vocab["<pad>"]

    for node in _walk_nodes(tree.root_node):
        ids.append(ast_vocab.get(node.type, unk_id))
        if len(ids) >= MAX_AST_LEN:
            break

    # Pad to MAX_AST_LEN
    if len(ids) < MAX_AST_LEN:
        ids = ids + [pad_id] * (MAX_AST_LEN - len(ids))

    return ids


def _parse_code(code: str) -> tree_sitter.Tree | None:
    """Parse a code string. Wrapped in try/except for safety."""
    try:
        # Wrap in a dummy class so a bare method body parses
        wrapped = f"class _Wrap {{ {code} }}"
        return _PARSER.parse(wrapped.encode("utf-8"))
    except Exception:
        return None


def _walk_nodes(node: tree_sitter.Node):
    """Yield node and all descendants in pre-order."""
    yield node
    for child in node.children:
        yield from _walk_nodes(child)


# ============================================================
# JSON HELPERS
# ============================================================

def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _save_json(obj: Any, path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


# ============================================================
# SUMMARY
# ============================================================

def _print_summary(records: list[dict]) -> None:
    labels = Counter(r["label"] for r in records)
    splits = Counter(r["split"] for r in records)

    print("Summary:")
    print(f"  Total records:      {len(records)}")
    print(f"  Clean (label=0):    {labels[0]}")
    print(f"  Defective (label=1):{labels[1]}")
    print()
    print("Split distribution:")
    for split, count in splits.most_common():
        print(f"  {split:8s} {count}")
    print()

    # Show a sample record (first one)
    sample = records[0]
    print("Sample record:")
    print(f"  id:               {sample['id']}")
    print(f"  label:            {sample['label']}")
    print(f"  input_ids length: {len(sample['input_ids'])}")
    print(f"  ast_ids length:   {len(sample['ast_ids'])}")
    print(f"  first 10 input_ids: {sample['input_ids'][:10]}")
    print(f"  first 10 ast_ids:   {sample['ast_ids'][:10]}")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    sys.exit(main())