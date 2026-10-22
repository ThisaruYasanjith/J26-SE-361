"""
src/08b_evaluate_visual.py — Evaluate all 5 methods with binary + multi-class metrics.

Loads:
  models/ablation_semantic_15class.pt
  models/ablation_structural_15class.pt
  models/ablation_combined_15class.pt
  data/processed/file_level_results.csv (for PMD/SpotBugs)

Produces:
  results/figures/comparison_multiclass.png       (3 ML models, multi-class metrics)
  results/summary_metrics.csv                     (binary metrics for all 5)
  results/multiclass_metrics.csv                  (multi-class metrics for 3 ML models)

Run from project root:
    python src/08b_evaluate_visual.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score, f1_score, matthews_corrcoef,
    precision_score, recall_score,
)
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREPROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessed.json"
AST_VOCAB_PATH = PROJECT_ROOT / "data" / "processed" / "ast_vocab.json"
CATEGORY_MAP_PATH = PROJECT_ROOT / "data" / "processed" / "category_map.json"
STATIC_ANALYSIS_PATH = PROJECT_ROOT / "data" / "processed" / "file_level_results.csv"
MODELS_DIR = PROJECT_ROOT / "models"
FIGURES_DIR = PROJECT_ROOT / "results" / "figures"
SUMMARY_CSV = PROJECT_ROOT / "results" / "summary_metrics.csv"
MULTICLASS_CSV = PROJECT_ROOT / "results" / "multiclass_metrics.csv"

GCBERT_MODEL_NAME = "microsoft/graphcodebert-base"

SEMANTIC_DIM = 768
AST_EMBED_DIM = 128
AST_HIDDEN_DIM = 128
AST_NUM_LAYERS = 2
AST_NUM_HEADS = 4
AST_FF_DIM = 512
FUSION_HIDDEN = 256
NUM_CATEGORIES = 15
BATCH_SIZE = 16

# ---- 3 ML models (all 15-class) ----
METHOD_CONFIGS = [
    {"name": "Semantic only",   "checkpoint": "ablation_semantic_15class.pt",   "type": "semantic"},
    {"name": "Structural only", "checkpoint": "ablation_structural_15class.pt", "type": "structural"},
    {"name": "Combined",        "checkpoint": "ablation_combined_15class.pt",   "type": "combined"},
]

# ---- Colors ----
COLORS = {
    "PMD":             "#F39C12",
    "SpotBugs":        "#E74C3C",
    "Semantic only":   "#9B59B6",
    "Structural only": "#16A085",
    "Combined":        "#2E86DE",
}

TITLE_MAP = {
    "PMD":             "PMD (Static Analysis)",
    "SpotBugs":        "SpotBugs (Static Analysis)",
    "Semantic only":   "Semantic-Only Model (GraphCodeBERT)",
    "Structural only": "Structural-Only Model (AST)",
    "Combined":        "Combined Model (GraphCodeBERT + AST)",
}


# ============================================================
# DATASET
# ============================================================

class ExceptionDataset(Dataset):
    def __init__(self, records):
        self.records = records

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        r = self.records[idx]
        return {
            "input_ids": torch.tensor(r["input_ids"], dtype=torch.long),
            "attention_mask": torch.tensor(r["attention_mask"], dtype=torch.long),
            "ast_ids": torch.tensor(r["ast_ids"], dtype=torch.long),
            "category_id": torch.tensor(r["category_id"], dtype=torch.long),
            "label": torch.tensor(r["label"], dtype=torch.long),
        }


def collate_fn(batch):
    return {
        "input_ids": torch.stack([b["input_ids"] for b in batch]),
        "attention_mask": torch.stack([b["attention_mask"] for b in batch]),
        "ast_ids": torch.stack([b["ast_ids"] for b in batch]),
        "category_id": torch.stack([b["category_id"] for b in batch]),
        "label": torch.stack([b["label"] for b in batch]),
    }


# ============================================================
# MODELS (must match 09_ablation.py)
# ============================================================

class SemanticOnlyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.graphcodebert = AutoModel.from_pretrained(GCBERT_MODEL_NAME)
        self.classifier = nn.Sequential(
            nn.Linear(SEMANTIC_DIM, FUSION_HIDDEN),
            nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),
        )

    def forward(self, input_ids, attention_mask, ast_ids=None):
        gc = self.graphcodebert(input_ids=input_ids, attention_mask=attention_mask)
        return self.classifier(gc.pooler_output)


class StructuralOnlyModel(nn.Module):
    def __init__(self, ast_vocab_size):
        super().__init__()
        self.ast_embedding = nn.Embedding(ast_vocab_size, AST_EMBED_DIM, padding_idx=0)
        self.ast_position_embedding = nn.Embedding(256, AST_EMBED_DIM)
        enc = nn.TransformerEncoderLayer(
            d_model=AST_EMBED_DIM, nhead=AST_NUM_HEADS,
            dim_feedforward=AST_FF_DIM, dropout=0.1, batch_first=True,
        )
        self.ast_transformer = nn.TransformerEncoder(enc, num_layers=AST_NUM_LAYERS)
        self.ast_projection = nn.Linear(AST_EMBED_DIM, AST_HIDDEN_DIM)
        self.classifier = nn.Sequential(
            nn.Linear(AST_HIDDEN_DIM, FUSION_HIDDEN),
            nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),
        )

    def forward(self, input_ids=None, attention_mask=None, ast_ids=None):
        m = (ast_ids == 0)
        B, L = ast_ids.shape
        pos = torch.arange(L, device=ast_ids.device).unsqueeze(0).expand(B, L)
        e = self.ast_embedding(ast_ids) + self.ast_position_embedding(pos)
        out = self.ast_transformer(e, src_key_padding_mask=m)
        mf = (~m).float().unsqueeze(-1)
        pooled = (out * mf).sum(1) / mf.sum(1).clamp(min=1.0)
        return self.classifier(self.ast_projection(pooled))


class DualStreamModel(nn.Module):
    def __init__(self, ast_vocab_size):
        super().__init__()
        self.graphcodebert = AutoModel.from_pretrained(GCBERT_MODEL_NAME)
        self.ast_embedding = nn.Embedding(ast_vocab_size, AST_EMBED_DIM, padding_idx=0)
        self.ast_position_embedding = nn.Embedding(256, AST_EMBED_DIM)
        enc = nn.TransformerEncoderLayer(
            d_model=AST_EMBED_DIM, nhead=AST_NUM_HEADS,
            dim_feedforward=AST_FF_DIM, dropout=0.1, batch_first=True,
        )
        self.ast_transformer = nn.TransformerEncoder(enc, num_layers=AST_NUM_LAYERS)
        self.ast_projection = nn.Linear(AST_EMBED_DIM, AST_HIDDEN_DIM)
        self.classifier = nn.Sequential(
            nn.Linear(SEMANTIC_DIM + AST_HIDDEN_DIM, FUSION_HIDDEN),
            nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),
        )

    def forward(self, input_ids, attention_mask, ast_ids):
        gc = self.graphcodebert(input_ids=input_ids, attention_mask=attention_mask)
        sem = gc.pooler_output
        m = (ast_ids == 0)
        B, L = ast_ids.shape
        pos = torch.arange(L, device=ast_ids.device).unsqueeze(0).expand(B, L)
        e = self.ast_embedding(ast_ids) + self.ast_position_embedding(pos)
        out = self.ast_transformer(e, src_key_padding_mask=m)
        mf = (~m).float().unsqueeze(-1)
        pooled = (out * mf).sum(1) / mf.sum(1).clamp(min=1.0)
        st = self.ast_projection(pooled)
        return self.classifier(torch.cat([sem, st], dim=-1))


def build_model(model_type, ast_vocab_size):
    if model_type == "semantic":   return SemanticOnlyModel()
    if model_type == "structural": return StructuralOnlyModel(ast_vocab_size)
    if model_type == "combined":   return DualStreamModel(ast_vocab_size)
    raise ValueError(model_type)


# ============================================================
# DEVICE + PREDICTION
# ============================================================

def get_device():
    if torch.cuda.is_available(): return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available(): return torch.device("mps")
    return torch.device("cpu")


@torch.no_grad()
def predict_all(model, loader, device):
    """Return (category_true, category_pred, binary_true, binary_pred)."""
    model.eval()
    cat_true_all, cat_pred_all = [], []
    for batch in loader:
        ids = batch["input_ids"].to(device)
        mask = batch["attention_mask"].to(device)
        ast = batch["ast_ids"].to(device)
        cat_true = batch["category_id"].cpu().numpy()
        cat_pred = model(ids, mask, ast).argmax(-1).cpu().numpy()
        cat_true_all.extend(cat_true.tolist())
        cat_pred_all.extend(cat_pred.tolist())

    # Aggregate to binary
    bin_true = [1 if c > 0 else 0 for c in cat_true_all]
    bin_pred = [1 if c > 0 else 0 for c in cat_pred_all]

    return cat_true_all, cat_pred_all, bin_true, bin_pred


# ============================================================
# METRICS
# ============================================================

def binary_metrics(y_true, y_pred):
    if not y_true:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0, "mcc": 0.0}
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "mcc": matthews_corrcoef(y_true, y_pred) if len(set(y_true)) > 1 else 0.0,
    }


def multiclass_metrics(cat_true, cat_pred):
    return {
        "accuracy": accuracy_score(cat_true, cat_pred),
        "macro_f1": f1_score(cat_true, cat_pred, average="macro", zero_division=0),
        "weighted_f1": f1_score(cat_true, cat_pred, average="weighted", zero_division=0),
    }


# ============================================================
# PLOTS
# ============================================================

def plot_multiclass_comparison(multiclass_preds, title, filename):
    """
    Bar chart of multi-class metrics for the 3 ML models.

    Metrics shown: Accuracy, Macro-F1, Weighted-F1.
    Static tools (PMD/SpotBugs) are NOT included because they are
    binary detectors and cannot produce a 15-class prediction.
    """
    models = ["Semantic only", "Structural only", "Combined"]
    metric_keys = ["accuracy", "macro_f1", "weighted_f1"]
    metric_labels = ["Accuracy", "Macro-F1", "Weighted-F1"]

    # Compute metrics per model
    data = {}
    for name in models:
        if name not in multiclass_preds:
            continue
        ct, cp = multiclass_preds[name]
        data[name] = multiclass_metrics(ct, cp)

    x = np.arange(len(metric_keys))
    n = len(data)
    w = 0.8 / n

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, name in enumerate(data):
        vals = [data[name][k] for k in metric_keys]
        bars = ax.bar(
            x + i * w - (0.8 - w) / 2, vals, w,
            label=TITLE_MAP.get(name, name),
            color=COLORS[name],
            edgecolor="white", linewidth=1,
        )
        for b, v in zip(bars, vals):
            ax.text(
                b.get_x() + b.get_width() / 2, b.get_height() + 0.01,
                f"{v:.3f}", ha="center", va="bottom", fontsize=9,
            )
    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels, fontsize=12)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(fontsize=10, loc="lower right")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    plt.close()


# ============================================================
# MAIN
# ============================================================

def main():
    device = get_device()
    print(f"Device: {device}\n")

    # ---- Load data ----
    with PREPROCESSED_PATH.open(encoding="utf-8") as f:
        records = json.load(f)
    with AST_VOCAB_PATH.open(encoding="utf-8") as f:
        ast_vocab_size = len(json.load(f))
    with CATEGORY_MAP_PATH.open(encoding="utf-8") as f:
        category_map = json.load(f)
    id_to_cat = {v: k for k, v in category_map.items()}

    test_records = [r for r in records if r["split"] == "test"]
    print(f"Test records: {len(test_records)}")
    print(f"Categories:   {len(category_map)}\n")

    # ---- Load static analysis ----
    static = {}
    with STATIC_ANALYSIS_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            fn = (row.get("filename") or "").strip()
            if fn:
                static[fn] = row

    # ---- Predict with ML models ----
    loader = DataLoader(
        ExceptionDataset(test_records),
        batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn,
    )

    binary_preds = {}
    multiclass_preds = {}

    for cfg in METHOD_CONFIGS:
        ckpt = MODELS_DIR / cfg["checkpoint"]
        if not ckpt.exists():
            print(f"⚠️  {cfg['name']}: {ckpt} not found — skipping\n")
            continue
        print(f"Loading {cfg['name']} from {ckpt.name}...")
        model = build_model(cfg["type"], ast_vocab_size).to(device)
        model.load_state_dict(torch.load(ckpt, map_location=device)["model_state_dict"])

        cat_true, cat_pred, bin_true, bin_pred = predict_all(model, loader, device)
        multiclass_preds[cfg["name"]] = (cat_true, cat_pred)
        binary_preds[cfg["name"]] = (bin_true, bin_pred)
        print(f"  Done.\n")

    # ---- Static tool predictions ----
    pmd_true, pmd_pred = [], []
    sb_true, sb_pred = [], []
    for r in test_records:
        row = static.get(r["id"] + ".java", {})
        m = (row.get("candidate_category_match") or "").strip().upper()
        t = (row.get("candidate_matching_tools") or "").strip()
        lab = int(r["label"])
        pmd_true.append(lab)
        pmd_pred.append(1 if (m == "YES" and "PMD" in t) else 0)
        sb_true.append(lab)
        sb_pred.append(1 if (m == "YES" and "SpotBugs" in t) else 0)

    binary_preds["PMD"] = (pmd_true, pmd_pred)
    binary_preds["SpotBugs"] = (sb_true, sb_pred)

    # ---- Compute binary metrics (written to CSV, not plotted) ----
    binary_metric_map = {}
    for name, (yt, yp) in binary_preds.items():
        binary_metric_map[name] = binary_metrics(yt, yp)

    # ---- Multi-class comparison figure ----
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot_multiclass_comparison(
        multiclass_preds,
        "Multi-Class Performance: Semantic-Only vs Structural-Only vs Combined",
        FIGURES_DIR / "comparison_multiclass.png",
    )

    # ---- Summary CSV (binary, for internal reference / Table 2 source) ----
    SUMMARY_CSV.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["method", "accuracy", "precision", "recall", "f1", "mcc"])
        for name in ["PMD", "SpotBugs", "Semantic only", "Structural only", "Combined"]:
            if name not in binary_metric_map:
                continue
            m = binary_metric_map[name]
            w.writerow([
                TITLE_MAP.get(name, name),
                f"{m['accuracy']:.4f}",
                f"{m['precision']:.4f}",
                f"{m['recall']:.4f}",
                f"{m['f1']:.4f}",
                f"{m['mcc']:.4f}",
            ])

    # ---- Multi-class CSV (3 ML models only) ----
    with MULTICLASS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["method", "accuracy", "macro_f1", "weighted_f1"])
        for name in ["Semantic only", "Structural only", "Combined"]:
            if name not in multiclass_preds:
                continue
            cat_true, cat_pred = multiclass_preds[name]
            m = multiclass_metrics(cat_true, cat_pred)
            w.writerow([
                TITLE_MAP.get(name, name),
                f"{m['accuracy']:.4f}",
                f"{m['macro_f1']:.4f}",
                f"{m['weighted_f1']:.4f}",
            ])

    # ---- Console summary: binary ----
    print("=" * 95)
    print("BINARY METRICS — All 5 methods")
    print("=" * 95)
    print(f"{'Method':<45} {'Acc':>8} {'Prec':>8} {'Rec':>8} {'F1':>8} {'MCC':>8}")
    print("-" * 95)
    for name in ["PMD", "SpotBugs", "Semantic only", "Structural only", "Combined"]:
        if name not in binary_metric_map:
            continue
        m = binary_metric_map[name]
        print(f"{TITLE_MAP.get(name, name):<45} "
              f"{m['accuracy']:>8.4f} {m['precision']:>8.4f} "
              f"{m['recall']:>8.4f} {m['f1']:>8.4f} {m['mcc']:>8.4f}")

    # ---- Console summary: multi-class ----
    print()
    print("=" * 95)
    print("MULTI-CLASS METRICS — 3 ML models (15 classes)")
    print("=" * 95)
    print(f"{'Method':<45} {'Acc':>8} {'MacroF1':>10} {'WeightedF1':>12}")
    print("-" * 95)
    for name in ["Semantic only", "Structural only", "Combined"]:
        if name not in multiclass_preds:
            continue
        cat_true, cat_pred = multiclass_preds[name]
        m = multiclass_metrics(cat_true, cat_pred)
        print(f"{TITLE_MAP.get(name, name):<45} "
              f"{m['accuracy']:>8.4f} {m['macro_f1']:>10.4f} {m['weighted_f1']:>12.4f}")

    print(f"\nFigures saved to {FIGURES_DIR}")
    print(f"Binary metrics:        {SUMMARY_CSV}")
    print(f"Multi-class metrics:   {MULTICLASS_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())