"""
src/08b_evaluate_visual.py

Visual evaluation: confusion matrices, bar charts, heatmaps, and ROC curves
for PMD, SpotBugs, and the trained dual-stream model.

Outputs:
  results/figures/confusion_PMD.png
  results/figures/confusion_SpotBugs.png
  results/figures/confusion_Model.png
  results/figures/comparison_bar.png
  results/figures/per_category_heatmap.png
  results/figures/roc_curves.png
  results/figures/summary_metrics.csv

Run from project root:
    python src/08b_evaluate_visual.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, matthews_corrcoef,
    precision_score, recall_score, roc_auc_score, roc_curve,
)
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel

# Match 07_train_model.py architecture
HOLDOUT_CATEGORIES = [
    "swallows_declared_exception",
    "corrupted_state_on_exception",
    "inconsistent_with_precheck",
    "empty_catch",
]

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREPROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessed.json"
STATIC_ANALYSIS_PATH = PROJECT_ROOT / "data" / "processed" / "file_level_results.csv"
CHECKPOINT_PATH = PROJECT_ROOT / "models" / "best_model.pt"
FIGURES_DIR = PROJECT_ROOT / "results" / "figures"
SUMMARY_CSV = PROJECT_ROOT / "results" / "summary_metrics.csv"

# Color palette
COLOR_MODEL = "#2E86DE"      # strong blue
COLOR_PMD = "#F39C12"        # orange
COLOR_SPOTBUGS = "#E74C3C"   # red
COLOR_GREEN = "#27AE60"      # green (correct)
COLOR_RED = "#E74C3C"        # red (wrong)


# ============================================================
# MODEL + DATASET
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
            "label": torch.tensor(r["label"], dtype=torch.long),
        }


def collate_fn(batch):
    return {
        "input_ids": torch.stack([b["input_ids"] for b in batch]),
        "attention_mask": torch.stack([b["attention_mask"] for b in batch]),
        "ast_ids": torch.stack([b["ast_ids"] for b in batch]),
        "label": torch.stack([b["label"] for b in batch]),
    }


class DualStreamModel(nn.Module):
    def __init__(self, ast_vocab_size):
        super().__init__()
        self.graphcodebert = AutoModel.from_pretrained(GCBERT_MODEL_NAME)
        self.ast_embedding = nn.Embedding(ast_vocab_size, AST_EMBED_DIM, padding_idx=0)
        self.ast_position_embedding = nn.Embedding(256, AST_EMBED_DIM)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=AST_EMBED_DIM, nhead=AST_NUM_HEADS,
            dim_feedforward=AST_FF_DIM, dropout=0.1, batch_first=True,
        )
        self.ast_transformer = nn.TransformerEncoder(encoder_layer, num_layers=AST_NUM_LAYERS)
        self.ast_projection = nn.Linear(AST_EMBED_DIM, AST_HIDDEN_DIM)
        fusion_input_dim = SEMANTIC_DIM + AST_HIDDEN_DIM
        self.classifier = nn.Sequential(
            nn.Linear(fusion_input_dim, FUSION_HIDDEN),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(FUSION_HIDDEN, NUM_CLASSES),
        )

    def forward(self, input_ids, attention_mask, ast_ids):
        gc_out = self.graphcodebert(input_ids=input_ids, attention_mask=attention_mask)
        semantic_vec = gc_out.pooler_output
        ast_mask = (ast_ids == 0)
        B, L = ast_ids.shape
        positions = torch.arange(L, device=ast_ids.device).unsqueeze(0).expand(B, L)
        ast_emb = self.ast_embedding(ast_ids) + self.ast_position_embedding(positions)
        ast_out = self.ast_transformer(ast_emb, src_key_padding_mask=ast_mask)
        mask_float = (~ast_mask).float().unsqueeze(-1)
        pooled = (ast_out * mask_float).sum(dim=1) / mask_float.sum(dim=1).clamp(min=1.0)
        structural_vec = self.ast_projection(pooled)
        combined = torch.cat([semantic_vec, structural_vec], dim=-1)
        return self.classifier(combined)


def get_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


@torch.no_grad()
def predict_proba(model, loader, device):
    """
    Return list of dicts with keys:
      label, pred, prob_defective
    """
    model.eval()
    results = []
    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        ast_ids = batch["ast_ids"].to(device)
        labels = batch["label"].cpu().numpy()
        logits = model(input_ids, attention_mask, ast_ids)
        probs = torch.softmax(logits, dim=-1).cpu().numpy()
        preds = logits.argmax(dim=-1).cpu().numpy()
        for i in range(len(labels)):
            results.append({
                "label": int(labels[i]),
                "pred": int(preds[i]),
                "prob_defective": float(probs[i][1]),
            })
    return results


# ============================================================
# METRICS
# ============================================================

def compute_full_metrics(y_true, y_pred, y_prob=None):
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "mcc": matthews_corrcoef(y_true, y_pred) if len(set(y_true)) > 1 else 0.0,
    }
    if y_prob is not None and len(set(y_true)) > 1:
        try:
            metrics["roc_auc"] = roc_auc_score(y_true, y_prob)
        except ValueError:
            metrics["roc_auc"] = 0.0
    else:
        metrics["roc_auc"] = 0.0
    return metrics


# ============================================================
# PLOTS
# ============================================================

def plot_confusion(y_true, y_pred, method_name, cmap, out_path):
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(
        cm, annot=True, fmt="d", cmap=cmap, cbar=False,
        xticklabels=["Predicted Clean", "Predicted Defective"],
        yticklabels=["Actual Clean", "Actual Defective"],
        annot_kws={"size": 18, "weight": "bold"},
        linewidths=1, linecolor="white", ax=ax,
    )
    ax.set_title(f"{method_name}\nConfusion Matrix", fontsize=14, fontweight="bold")
    ax.set_xlabel("Predicted", fontsize=12)
    ax.set_ylabel("Actual", fontsize=12)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_comparison_bar(all_metrics, out_path):
    methods = list(all_metrics.keys())
    metric_keys = ["accuracy", "precision", "recall", "f1", "mcc"]
    metric_labels = ["Accuracy", "Precision", "Recall", "F1", "MCC"]
    colors = [COLOR_PMD, COLOR_SPOTBUGS, COLOR_MODEL]

    x = np.arange(len(metric_keys))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, (method, metrics) in enumerate(all_metrics.items()):
        values = [metrics.get(k, 0.0) for k in metric_keys]
        bars = ax.bar(
            x + i * width - width, values, width,
            label=method, color=colors[i], edgecolor="white", linewidth=1,
        )
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{val:.2f}", ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels, fontsize=11)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title("Method Comparison on Test Set", fontsize=14, fontweight="bold")
    ax.set_ylim(0, 1.1)
    ax.legend(fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_per_category_heatmap(category_recall_map, out_path):
    """category_recall_map: {category: {method: recall}}"""
    categories = sorted(category_recall_map.keys())
    methods = ["PMD", "SpotBugs", "Model"]

    data = np.array([
        [category_recall_map[c].get(m, 0.0) for m in methods]
        for c in categories
    ])

    fig, ax = plt.subplots(figsize=(8, max(6, len(categories) * 0.5)))
    sns.heatmap(
        data, annot=True, fmt=".2f", cmap="RdYlGn", vmin=0, vmax=1,
        xticklabels=methods, yticklabels=categories,
        linewidths=0.5, linecolor="white", ax=ax,
        cbar_kws={"label": "Recall"},
    )
    ax.set_title("Per-Category Recall\n(green = detected, red = missed)",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Method", fontsize=12)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_roc_curves(roc_data, out_path):
    """roc_data: {method: (y_true, y_prob)}"""
    fig, ax = plt.subplots(figsize=(7, 7))
    colors = {"PMD": COLOR_PMD, "SpotBugs": COLOR_SPOTBUGS, "Model": COLOR_MODEL}

    for method, (y_true, y_prob) in roc_data.items():
        if y_prob is None or len(set(y_true)) < 2:
            continue
        fpr, tpr, _ = roc_curve(y_true, y_prob)
        auc = roc_auc_score(y_true, y_prob)
        ax.plot(fpr, tpr, color=colors.get(method, "gray"), lw=2.5,
                label=f"{method} (AUC = {auc:.3f})")

    ax.plot([0, 1], [0, 1], color="gray", lw=1, linestyle="--", label="Random")
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.set_xlabel("False Positive Rate", fontsize=12)
    ax.set_ylabel("True Positive Rate", fontsize=12)
    ax.set_title("ROC Curves", fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", fontsize=11)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


# ============================================================
# MAIN
# ============================================================

def main():
    print("Loading data and model...\n")
    device = get_device()

    with PREPROCESSED_PATH.open(encoding="utf-8") as f:
        records = json.load(f)

    static = {}
    with STATIC_ANALYSIS_PATH.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn = (row.get("filename") or "").strip()
            if fn:
                static[fn] = row

    test_records = [r for r in records if r["split"] == "test"]

    ast_vocab_size = len(json.loads((PROJECT_ROOT / "data" / "processed" / "ast_vocab.json").read_text()))
    model = DualStreamModel(ast_vocab_size).to(device)
    checkpoint = torch.load(CHECKPOINT_PATH, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])

    print(f"Model loaded from {CHECKPOINT_PATH.name}")
    print(f"Test records: {len(test_records)}\n")

    # Predict with model
    loader = DataLoader(ExceptionDataset(test_records), batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn)
    model_preds = predict_proba(model, loader, device)

    # Enrich with static tool predictions
    enriched = []
    for i, r in enumerate(test_records):
        fn = r["id"] + ".java"
        row = static.get(fn, {})
        sa_match = (row.get("candidate_category_match") or "").strip().upper()
        tools = (row.get("candidate_matching_tools") or "").strip()

        enriched.append({
            "label": int(r["label"]),
            "category": r["defect_category"] or "clean",
            "model_pred": model_preds[i]["pred"],
            "model_prob": model_preds[i]["prob_defective"],
            "pmd_pred": 1 if (sa_match == "YES" and "PMD" in tools) else 0,
            "spotbugs_pred": 1 if (sa_match == "YES" and "SpotBugs" in tools) else 0,
        })

    # Metrics per method
    y_true = [e["label"] for e in enriched]
    all_metrics = {}

    for method, key in [("PMD", "pmd_pred"), ("SpotBugs", "spotbugs_pred"), ("Model", "model_pred")]:
        y_pred = [e[key] for e in enriched]
        y_prob = [e["model_prob"] for e in enriched] if method == "Model" else None
        all_metrics[method] = compute_full_metrics(y_true, y_pred, y_prob)

    # Per-category recall
    per_cat = defaultdict(lambda: defaultdict(list))
    for e in enriched:
        per_cat[e["category"]]["PMD"].append((e["label"], e["pmd_pred"]))
        per_cat[e["category"]]["SpotBugs"].append((e["label"], e["spotbugs_pred"]))
        per_cat[e["category"]]["Model"].append((e["label"], e["model_pred"]))

    category_recall_map = {}
    for cat, methods in per_cat.items():
        category_recall_map[cat] = {}
        for method, pairs in methods.items():
            yt = [p[0] for p in pairs]
            yp = [p[1] for p in pairs]
            if sum(yt) > 0:
                category_recall_map[cat][method] = recall_score(yt, yp, zero_division=0)

    # ROC data
    roc_data = {
        "PMD": (y_true, [e["pmd_pred"] for e in enriched]),
        "SpotBugs": (y_true, [e["spotbugs_pred"] for e in enriched]),
        "Model": (y_true, [e["model_prob"] for e in enriched]),
    }

    # ---- Generate plots ----
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    for method, key, cmap in [
        ("PMD", "pmd_pred", "Oranges"),
        ("SpotBugs", "spotbugs_pred", "Reds"),
        ("Model", "model_pred", "Blues"),
    ]:
        y_pred = [e[key] for e in enriched]
        plot_confusion(y_true, y_pred, method, cmap, FIGURES_DIR / f"confusion_{method}.png")

    plot_comparison_bar(all_metrics, FIGURES_DIR / "comparison_bar.png")
    plot_per_category_heatmap(category_recall_map, FIGURES_DIR / "per_category_heatmap.png")
    plot_roc_curves(roc_data, FIGURES_DIR / "roc_curves.png")

    # ---- Save summary CSV ----
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["method", "accuracy", "precision", "recall", "f1", "mcc", "roc_auc"])
        for method, m in all_metrics.items():
            writer.writerow([
                method,
                f"{m['accuracy']:.4f}",
                f"{m['precision']:.4f}",
                f"{m['recall']:.4f}",
                f"{m['f1']:.4f}",
                f"{m['mcc']:.4f}",
                f"{m['roc_auc']:.4f}",
            ])

    # ---- Console summary ----
    print("=" * 70)
    print("SUMMARY — Full test set (150 records)")
    print("=" * 70)
    print(f"{'Method':<12} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'MCC':>10} {'ROC-AUC':>10}")
    print("-" * 70)
    for method, m in all_metrics.items():
        print(f"{method:<12} {m['accuracy']:>10.4f} {m['precision']:>10.4f} {m['recall']:>10.4f} "
              f"{m['f1']:>10.4f} {m['mcc']:>10.4f} {m['roc_auc']:>10.4f}")

    print(f"\nFigures saved to {FIGURES_DIR}")
    print(f"Summary metrics saved to {SUMMARY_CSV}")

    return 0


if __name__ == "__main__":
    sys.exit(main())