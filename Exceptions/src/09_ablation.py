"""
Ablation study for the dual-stream model.

Trains and evaluates three configurations with the same category holdout:
  A. Semantic only  (GraphCodeBERT, no AST)
  B. Structural only (AST, no GraphCodeBERT)
  C. Combined        (both streams fused) — the proposed model

Reports F1 on held-out categories for each configuration.

Output:
  results/ablation.csv
  models/ablation_semantic.pt
  models/ablation_structural.pt
  models/ablation_combined.pt

Run from project root:
    python src/09_ablation.py
"""

from __future__ import annotations

import os
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["SAFETENSORS_FAST_GPU"] = "1"
os.environ["HF_HUB_DISABLE_SAFETENSORS_CONVERSION"] = "1"

import csv
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import f1_score, precision_score, recall_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREPROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessed.json"
AST_VOCAB_PATH = PROJECT_ROOT / "data" / "processed" / "ast_vocab.json"
RESULTS_DIR = PROJECT_ROOT / "results"
MODELS_DIR = PROJECT_ROOT / "models"
OUTPUT_PATH = RESULTS_DIR / "ablation.csv"

GCBERT_MODEL_NAME = "microsoft/graphcodebert-base"

HOLDOUT_CATEGORIES = [
    "swallows_declared_exception",
    "corrupted_state_on_exception",
    "inconsistent_with_precheck",
    "empty_catch",
]

# Model architecture
SEMANTIC_DIM = 768
AST_EMBED_DIM = 128
AST_HIDDEN_DIM = 128
AST_NUM_LAYERS = 2
AST_NUM_HEADS = 4
AST_FF_DIM = 512
FUSION_HIDDEN = 256
NUM_CLASSES = 2

# Training
BATCH_SIZE = 16
EPOCHS = 5
LR_GCBERT = 2e-5
LR_OTHER = 1e-3
WEIGHT_DECAY = 0.01
MAX_GRAD_NORM = 1.0

SEED = 42


# ============================================================
# REPRODUCIBILITY + DEVICE
# ============================================================

def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


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


# ============================================================
# MODEL VARIANTS
# ============================================================

class SemanticOnlyModel(nn.Module):
    """GraphCodeBERT only. No AST stream."""

    def __init__(self):
        super().__init__()
        self.graphcodebert = AutoModel.from_pretrained(GCBERT_MODEL_NAME)
        self.classifier = nn.Sequential(
            nn.Linear(SEMANTIC_DIM, FUSION_HIDDEN),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(FUSION_HIDDEN, NUM_CLASSES),
        )

    def forward(self, input_ids, attention_mask, ast_ids=None):
        gc_out = self.graphcodebert(
            input_ids=input_ids, attention_mask=attention_mask
        )
        semantic_vec = gc_out.pooler_output
        return self.classifier(semantic_vec)


class StructuralOnlyModel(nn.Module):
    """AST only. No GraphCodeBERT."""

    def __init__(self, ast_vocab_size: int):
        super().__init__()
        self.ast_embedding = nn.Embedding(
            num_embeddings=ast_vocab_size,
            embedding_dim=AST_EMBED_DIM,
            padding_idx=0,
        )
        self.ast_position_embedding = nn.Embedding(
            num_embeddings=256, embedding_dim=AST_EMBED_DIM,
        )
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=AST_EMBED_DIM,
            nhead=AST_NUM_HEADS,
            dim_feedforward=AST_FF_DIM,
            dropout=0.1,
            batch_first=True,
        )
        self.ast_transformer = nn.TransformerEncoder(encoder_layer, num_layers=AST_NUM_LAYERS)
        self.ast_projection = nn.Linear(AST_EMBED_DIM, AST_HIDDEN_DIM)

        self.classifier = nn.Sequential(
            nn.Linear(AST_HIDDEN_DIM, FUSION_HIDDEN),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(FUSION_HIDDEN, NUM_CLASSES),
        )

    def forward(self, input_ids=None, attention_mask=None, ast_ids=None):
        ast_mask = (ast_ids == 0)
        B, L = ast_ids.shape
        positions = torch.arange(L, device=ast_ids.device).unsqueeze(0).expand(B, L)
        ast_emb = self.ast_embedding(ast_ids) + self.ast_position_embedding(positions)
        ast_out = self.ast_transformer(ast_emb, src_key_padding_mask=ast_mask)
        mask_float = (~ast_mask).float().unsqueeze(-1)
        pooled = (ast_out * mask_float).sum(dim=1) / mask_float.sum(dim=1).clamp(min=1.0)
        structural_vec = self.ast_projection(pooled)
        return self.classifier(structural_vec)


class DualStreamModel(nn.Module):
    """Combined semantic + structural (proposed model)."""

    def __init__(self, ast_vocab_size: int):
        super().__init__()
        self.graphcodebert = AutoModel.from_pretrained(GCBERT_MODEL_NAME)
        self.ast_embedding = nn.Embedding(
            num_embeddings=ast_vocab_size,
            embedding_dim=AST_EMBED_DIM,
            padding_idx=0,
        )
        self.ast_position_embedding = nn.Embedding(
            num_embeddings=256, embedding_dim=AST_EMBED_DIM,
        )
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=AST_EMBED_DIM,
            nhead=AST_NUM_HEADS,
            dim_feedforward=AST_FF_DIM,
            dropout=0.1,
            batch_first=True,
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
        gc_out = self.graphcodebert(
            input_ids=input_ids, attention_mask=attention_mask
        )
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


# ============================================================
# LOADERS
# ============================================================

def load_preprocessed():
    with PREPROCESSED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_ast_vocab_size():
    with AST_VOCAB_PATH.open(encoding="utf-8") as f:
        vocab = json.load(f)
    return len(vocab)


# ============================================================
# METRICS
# ============================================================

def compute_metrics(logits, labels):
    preds = logits.argmax(dim=-1).cpu().numpy()
    labels_np = labels.cpu().numpy()
    return {
        "precision": precision_score(labels_np, preds, zero_division=0),
        "recall": recall_score(labels_np, preds, zero_division=0),
        "f1": f1_score(labels_np, preds, zero_division=0),
    }


# ============================================================
# TRAIN / EVAL
# ============================================================

def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    all_logits, all_labels = [], []
    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        ast_ids = batch["ast_ids"].to(device)
        labels = batch["label"].to(device)

        optimizer.zero_grad()
        logits = model(input_ids, attention_mask, ast_ids)
        loss = criterion(logits, labels)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRAD_NORM)
        optimizer.step()

        total_loss += loss.item() * labels.size(0)
        all_logits.append(logits.detach())
        all_labels.append(labels.detach())

    avg_loss = total_loss / len(loader.dataset)
    return avg_loss, compute_metrics(torch.cat(all_logits), torch.cat(all_labels))


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    all_logits, all_labels = [], []
    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        ast_ids = batch["ast_ids"].to(device)
        labels = batch["label"].to(device)

        logits = model(input_ids, attention_mask, ast_ids)
        loss = criterion(logits, labels)

        total_loss += loss.item() * labels.size(0)
        all_logits.append(logits)
        all_labels.append(labels)

    avg_loss = total_loss / len(loader.dataset)
    return avg_loss, compute_metrics(torch.cat(all_logits), torch.cat(all_labels))


def build_optimizer(model):
    gcbert_params = []
    if hasattr(model, "graphcodebert"):
        gcbert_params = list(model.graphcodebert.parameters())
    gcbert_param_ids = {id(p) for p in gcbert_params}
    other_params = [p for p in model.parameters() if id(p) not in gcbert_param_ids]

    param_groups = [{"params": other_params, "lr": LR_OTHER}]
    if gcbert_params:
        param_groups.insert(0, {"params": gcbert_params, "lr": LR_GCBERT})

    return torch.optim.AdamW(param_groups, weight_decay=WEIGHT_DECAY)


# ============================================================
# RUN ONE CONFIGURATION
# ============================================================

def run_configuration(
    name: str,
    model: nn.Module,
    train_loader,
    val_loader,
    test_ood_loader,
    device,
    save_path: Path,
):
    print(f"\n{'='*60}")
    print(f"Training configuration: {name}")
    print(f"{'='*60}\n")

    model = model.to(device)
    optimizer = build_optimizer(model)
    criterion = nn.CrossEntropyLoss()

    best_val_f1 = 0.0
    for epoch in range(1, EPOCHS + 1):
        t0 = time.time()
        train_loss, train_metrics = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_metrics = evaluate(model, val_loader, criterion, device)
        elapsed = time.time() - t0

        print(f"Epoch {epoch}/{EPOCHS}  ({elapsed:.1f}s)")
        print(f"  train  loss={train_loss:.4f}  f1={train_metrics['f1']:.4f}")
        print(f"  val    loss={val_loss:.4f}  f1={val_metrics['f1']:.4f}")

        if val_metrics["f1"] > best_val_f1:
            best_val_f1 = val_metrics["f1"]
            torch.save({
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "val_f1": best_val_f1,
            }, save_path)
            print(f"  -> saved best ({best_val_f1:.4f})")
        print()

    # Load best and evaluate on held-out test
    checkpoint = torch.load(save_path, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])

    test_loss, test_metrics = evaluate(model, test_ood_loader, criterion, device)
    print(f"\n{name} — Final held-out test performance:")
    print(f"  Precision: {test_metrics['precision']:.4f}")
    print(f"  Recall:    {test_metrics['recall']:.4f}")
    print(f"  F1:        {test_metrics['f1']:.4f}\n")

    return {
        "config": name,
        "precision": test_metrics["precision"],
        "recall": test_metrics["recall"],
        "f1": test_metrics["f1"],
    }


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    set_seed(SEED)
    device = get_device()
    print(f"Device: {device}\n")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    records = load_preprocessed()
    ast_vocab_size = load_ast_vocab_size()

    # Split
    train_all = [r for r in records if r["split"] == "train"]
    val_all = [r for r in records if r["split"] == "val"]
    test_all = [r for r in records if r["split"] == "test"]

    # Apply category holdout
    train = [r for r in train_all if r["defect_category"] not in HOLDOUT_CATEGORIES]
    val = [r for r in val_all if r["defect_category"] not in HOLDOUT_CATEGORIES]
    test_ood = [r for r in test_all if r["defect_category"] in HOLDOUT_CATEGORIES]

    print(f"  train (seen categories):  {len(train)}")
    print(f"  val (seen categories):    {len(val)}")
    print(f"  test (held-out only):     {len(test_ood)}\n")

    if not test_ood:
        print("No held-out test records. Aborting.")
        return 1

    # Loaders
    train_loader = DataLoader(ExceptionDataset(train), batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(ExceptionDataset(val), batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn)
    test_ood_loader = DataLoader(ExceptionDataset(test_ood), batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn)

    # Run three configurations
    results = []

    # Config A: Semantic only
    results.append(run_configuration(
        "Semantic only",
        SemanticOnlyModel(),
        train_loader, val_loader, test_ood_loader, device,
        MODELS_DIR / "ablation_semantic.pt",
    ))

    # Config B: Structural only
    results.append(run_configuration(
        "Structural only",
        StructuralOnlyModel(ast_vocab_size=ast_vocab_size),
        train_loader, val_loader, test_ood_loader, device,
        MODELS_DIR / "ablation_structural.pt",
    ))

    # Config C: Combined
    results.append(run_configuration(
        "Combined",
        DualStreamModel(ast_vocab_size=ast_vocab_size),
        train_loader, val_loader, test_ood_loader, device,
        MODELS_DIR / "ablation_combined.pt",
    ))

    # Summary
    print("\n" + "=" * 60)
    print("ABLATION STUDY — Held-out Test F1")
    print("=" * 60 + "\n")
    print(f"{'Configuration':<25} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print("-" * 60)
    for r in results:
        print(f"{r['config']:<25} {r['precision']:>10.4f} {r['recall']:>10.4f} {r['f1']:>10.4f}")

    # Write CSV
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["config", "precision", "recall", "f1"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())