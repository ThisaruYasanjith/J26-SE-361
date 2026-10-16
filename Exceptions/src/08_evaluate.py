"""
Evaluate the trained dual-stream model on the test set.
Compare with PMD and SpotBugs baselines.

Loads:
  models/best_model.pt
  data/processed/preprocessed.json
  data/processed/file_level_results.csv

Writes:
  results/evaluation.csv

Run from project root:
    python src/08_evaluate.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import f1_score, matthews_corrcoef, precision_score, recall_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREPROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessed.json"
STATIC_ANALYSIS_PATH = PROJECT_ROOT / "data" / "processed" / "file_level_results.csv"
CHECKPOINT_PATH = PROJECT_ROOT / "models" / "best_model.pt"
OUTPUT_PATH = PROJECT_ROOT / "results" / "evaluation.csv"

GCBERT_MODEL_NAME = "microsoft/graphcodebert-base"

SEMANTIC_DIM = 768
AST_EMBED_DIM = 128
AST_HIDDEN_DIM = 128
AST_NUM_LAYERS = 2
AST_NUM_HEADS = 4
AST_FF_DIM = 512
FUSION_HIDDEN = 256
NUM_CLASSES = 2

BATCH_SIZE = 16


# ============================================================
# DEVICE
# ============================================================

def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


# ============================================================
# DATASET
# ============================================================

class ExceptionDataset(Dataset):
    def __init__(self, records: list[dict]):
        self.records = records

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int):
        r = self.records[idx]
        return {
            "input_ids": torch.tensor(r["input_ids"], dtype=torch.long),
            "attention_mask": torch.tensor(r["attention_mask"], dtype=torch.long),
            "ast_ids": torch.tensor(r["ast_ids"], dtype=torch.long),
            "label": torch.tensor(r["label"], dtype=torch.long),
        }


def collate_fn(batch):
    return {
        "input_ids": torch.stack([b["input_ids"] for b in batch]),
        "attention_mask": torch.stack([b["attention_mask"] for b in batch]),
        "ast_ids": torch.stack([b["ast_ids"] for b in batch]),
        "label": torch.stack([b["label"] for b in batch]),
    }


# ============================================================
# MODEL (must match 07_train_model.py)
# ============================================================

class DualStreamModel(nn.Module):
    def __init__(self, ast_vocab_size: int):
        super().__init__()

        self.graphcodebert = AutoModel.from_pretrained(GCBERT_MODEL_NAME)

        self.ast_embedding = nn.Embedding(
            num_embeddings=ast_vocab_size,
            embedding_dim=AST_EMBED_DIM,
            padding_idx=0,
        )
        self.ast_position_embedding = nn.Embedding(
            num_embeddings=256,
            embedding_dim=AST_EMBED_DIM,
        )
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=AST_EMBED_DIM,
            nhead=AST_NUM_HEADS,
            dim_feedforward=AST_FF_DIM,
            dropout=0.1,
            batch_first=True,
        )
        self.ast_transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers=AST_NUM_LAYERS,
        )
        self.ast_projection = nn.Linear(AST_EMBED_DIM, AST_HIDDEN_DIM)

        fusion_input_dim = SEMANTIC_DIM + AST_HIDDEN_DIM
        self.classifier = nn.Sequential(
            nn.Linear(fusion_input_dim, FUSION_HIDDEN),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(FUSION_HIDDEN, NUM_CLASSES),
        )

    def forward(self, input_ids, attention_mask, ast_ids):
        gc_outputs = self.graphcodebert(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )
        semantic_vec = gc_outputs.pooler_output

        ast_mask = (ast_ids == 0)
        B, L = ast_ids.shape
        positions = torch.arange(L, device=ast_ids.device).unsqueeze(0).expand(B, L)
        ast_emb = self.ast_embedding(ast_ids) + self.ast_position_embedding(positions)
        ast_out = self.ast_transformer(ast_emb, src_key_padding_mask=ast_mask)
        mask_float = (~ast_mask).float().unsqueeze(-1)
        pooled = (ast_out * mask_float).sum(dim=1) / mask_float.sum(dim=1).clamp(min=1.0)
        structural_vec = self.ast_projection(pooled)

        combined = torch.cat([semantic_vec, structural_vec], dim=-1)
        logits = self.classifier(combined)
        return logits


# ============================================================
# LOADERS
# ============================================================

def load_preprocessed() -> list[dict]:
    with PREPROCESSED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_ast_vocab_size() -> int:
    with (PROJECT_ROOT / "data" / "processed" / "ast_vocab.json").open(encoding="utf-8") as f:
        vocab = json.load(f)
    return len(vocab)


def load_static_analysis() -> dict[str, dict]:
    """Return a dict: filename → row (candidate_category_match, tools)."""
    result = {}
    with STATIC_ANALYSIS_PATH.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn = row.get("filename", "").strip()
            if fn:
                result[fn] = row
    return result


# ============================================================
# PREDICTION
# ============================================================

@torch.no_grad()
def predict(model, loader, device):
    """
    Return a dict: record_id → predicted_label (0 or 1)
    """
    model.eval()
    predictions = {}
    current_idx = 0
    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        ast_ids = batch["ast_ids"].to(device)
        logits = model(input_ids, attention_mask, ast_ids)
        preds = logits.argmax(dim=-1).cpu().numpy()
        batch_size = preds.shape[0]
        for i in range(batch_size):
            predictions[current_idx] = int(preds[i])
            current_idx += 1
    return predictions


# ============================================================
# METRICS
# ============================================================

def compute_metrics(y_true: list[int], y_pred: list[int]) -> dict:
    if not y_true:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "mcc": 0.0, "n": 0}
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    return {
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "mcc": matthews_corrcoef(y_true, y_pred) if len(set(y_true)) > 1 else 0.0,
        "n": len(y_true),
    }


def mcnemar_test(y_true, y_pred_a, y_pred_b):
    """
    McNemar's test comparing two classifiers on the same data.
    y_true: ground truth labels
    y_pred_a, y_pred_b: predictions from two methods
    """
    from scipy.stats import chi2

    # n01: A wrong, B correct
    # n10: A correct, B wrong
    n01 = 0
    n10 = 0
    for t, a, b in zip(y_true, y_pred_a, y_pred_b):
        a_correct = (a == t)
        b_correct = (b == t)
        if not a_correct and b_correct:
            n01 += 1
        elif a_correct and not b_correct:
            n10 += 1

    if n01 + n10 == 0:
        return {"statistic": 0.0, "p_value": 1.0, "n01": n01, "n10": n10}

    statistic = ((abs(n01 - n10) - 1) ** 2) / (n01 + n10)
    p_value = 1 - chi2.cdf(statistic, df=1)
    return {
        "statistic": float(statistic),
        "p_value": float(p_value),
        "n01": n01,
        "n10": n10,
    }


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    device = get_device()
    print(f"Device: {device}\n")

    # ---- Load data ----
    print("Loading preprocessed data...")
    records = load_preprocessed()
    ast_vocab_size = load_ast_vocab_size()

    # ---- Load static analysis ----
    print("Loading static analysis results...")
    static = load_static_analysis()

    # ---- Filter to test ----
    test_records = [r for r in records if r["split"] == "test"]
    print(f"  Test records: {len(test_records)}\n")

    if not test_records:
        print("No test records found. Aborting.")
        return 1

    # ---- Load model ----
    print("Loading model...")
    model = DualStreamModel(ast_vocab_size=ast_vocab_size).to(device)
    checkpoint = torch.load(CHECKPOINT_PATH, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    print(f"  Loaded checkpoint from epoch {checkpoint.get('epoch', '?')}\n")

    # ---- Load held-out categories ----
    HOLDOUT_CATEGORIES = checkpoint.get(
        "holdout_categories",
        [
            "swallows_declared_exception",
            "corrupted_state_on_exception",
            "inconsistent_with_precheck",
            "empty_catch",
        ],
    )
    print(f"Held-out categories: {HOLDOUT_CATEGORIES}\n")

    # ---- Predict on test ----
    print("Running predictions on test set...")
    test_loader = DataLoader(
        ExceptionDataset(test_records),
        batch_size=BATCH_SIZE,
        shuffle=False,
        collate_fn=collate_fn,
    )
    model_preds = predict(model, test_loader, device)

    # ---- Attach predictions and static results to each record ----
    enriched = []
    for i, r in enumerate(test_records):
        fn = r["id"] + ".java"
        sa_row = static.get(fn, {})
        sa_match = (sa_row.get("candidate_category_match", "") or "").strip().upper()
        sa_tool = sa_row.get("candidate_matching_tools", "") or ""

        enriched.append({
            "record": r,
            "model_pred": model_preds.get(i, 0),
            "pmd_pred": 1 if sa_match == "YES" and "PMD" in sa_tool else 0,
            "spotbugs_pred": 1 if sa_match == "YES" and "SpotBugs" in sa_tool else 0,
            "any_sa_pred": 1 if sa_match == "YES" else 0,
        })

    # ---- Compute metrics ----
    print("\n" + "=" * 60)
    print("Test set evaluation")
    print("=" * 60 + "\n")

    # In-distribution: seen categories
    id_records = [e for e in enriched if e["record"]["defect_category"] not in HOLDOUT_CATEGORIES]
    ood_records = [e for e in enriched if e["record"]["defect_category"] in HOLDOUT_CATEGORIES]

    print(f"Test split by category visibility:")
    print(f"  In-distribution (seen categories):  {len(id_records)}")
    print(f"  Out-of-distribution (held-out):     {len(ood_records)}")
    print()

    methods = [
        ("PMD", "pmd_pred"),
        ("SpotBugs", "spotbugs_pred"),
        ("Any static tool", "any_sa_pred"),
        ("Model (ID)", "model_pred"),
        ("Model (OOD)", "model_pred"),
    ]

    results = {}

    for method_name, pred_key in methods:
        if method_name == "Model (ID)":
            subset = id_records
        elif method_name == "Model (OOD)":
            subset = ood_records
        else:
            subset = enriched  # static tools evaluated on the full test set

        y_true = [e["record"]["label"] for e in subset]
        y_pred = [e[pred_key] for e in subset]

        m = compute_metrics(y_true, y_pred)
        results[method_name] = m

    # Print table
    print(f"{'Method':<20} {'Prec':>7} {'Rec':>7} {'F1':>7} {'MCC':>7} {'N':>5}")
    print("-" * 60)
    for method_name, _ in methods:
        m = results[method_name]
        print(f"{method_name:<20} {m['precision']:>7.4f} {m['recall']:>7.4f} "
              f"{m['f1']:>7.4f} {m['mcc']:>7.4f} {m['n']:>5}")

    # ---- McNemar's test ----
    print("\n" + "=" * 60)
    print("McNemar's test (Model ID vs static tools)")
    print("=" * 60 + "\n")

    id_only = id_records
    y_true = [e["record"]["label"] for e in id_only]
    model_preds_list = [e["model_pred"] for e in id_only]
    pmd_preds_list = [e["pmd_pred"] for e in id_only]
    sa_preds_list = [e["any_sa_pred"] for e in id_only]

    mc = mcnemar_test(y_true, model_preds_list, pmd_preds_list)
    print(f"Model (ID) vs PMD:")
    print(f"  n01 (only model correct):    {mc['n01']}")
    print(f"  n10 (only PMD correct):      {mc['n10']}")
    print(f"  statistic:                   {mc['statistic']:.4f}")
    print(f"  p-value:                     {mc['p_value']:.4f}")
    print(f"  significant at α=0.05:       {'YES' if mc['p_value'] < 0.05 else 'NO'}")
    print()

    mc_sa = mcnemar_test(y_true, model_preds_list, sa_preds_list)
    print(f"Model (ID) vs any static tool:")
    print(f"  n01 (only model correct):    {mc_sa['n01']}")
    print(f"  n10 (only static correct):   {mc_sa['n10']}")
    print(f"  statistic:                   {mc_sa['statistic']:.4f}")
    print(f"  p-value:                     {mc_sa['p_value']:.4f}")
    print(f"  significant at α=0.05:       {'YES' if mc_sa['p_value'] < 0.05 else 'NO'}")
    print()

    # ---- Per-category breakdown ----
    print("=" * 60)
    print("Per-category breakdown (all test records, by defect_category)")
    print("=" * 60 + "\n")

    by_cat = defaultdict(list)
    for e in enriched:
        cat = e["record"]["defect_category"] or "clean"
        by_cat[cat].append(e)

    print(f"{'Category':<35} {'N':>4} {'Model F1':>10} {'PMD F1':>10}")
    print("-" * 60)
    for cat in sorted(by_cat.keys()):
        entries = by_cat[cat]
        y_true = [e["record"]["label"] for e in entries]
        y_m = [e["model_pred"] for e in entries]
        y_p = [e["pmd_pred"] for e in entries]
        f1_m = f1_score(y_true, y_m, zero_division=0)
        f1_p = f1_score(y_true, y_p, zero_division=0)
        print(f"{cat:<35} {len(entries):>4} {f1_m:>10.4f} {f1_p:>10.4f}")

    # ---- Write results ----
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["method", "precision", "recall", "f1", "mcc", "n"])
        for method_name, _ in methods:
            m = results[method_name]
            writer.writerow([method_name, m["precision"], m["recall"], m["f1"], m["mcc"], m["n"]])
        writer.writerow([])
        writer.writerow(["mcnemar_against", "n01", "n10", "statistic", "p_value"])
        writer.writerow(["PMD", mc["n01"], mc["n10"], mc["statistic"], mc["p_value"]])
        writer.writerow(["Any static tool", mc_sa["n01"], mc_sa["n10"], mc_sa["statistic"], mc_sa["p_value"]])

    print(f"\nWrote results to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")

    return 0


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    sys.exit(main())