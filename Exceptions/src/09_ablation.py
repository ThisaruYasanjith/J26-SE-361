"""
Ablation study for the dual-stream model — 15-class output, no holdout.

Trains and evaluates three configurations on ALL 15 categories:
  A. Semantic only  (GraphCodeBERT, no AST)
  B. Structural only (AST, no GraphCodeBERT)
  C. Combined        (both streams fused) — the proposed model

Uses per-configuration epoch counts so each model gets adequate training time.

Reports accuracy and macro F1 on the full test set for each configuration.

Output:
  results/ablation.csv
  models/ablation_semantic_15class.pt
  models/ablation_structural_15class.pt
  models/ablation_combined_15class.pt

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
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREPROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessed.json"
AST_VOCAB_PATH = PROJECT_ROOT / "data" / "processed" / "ast_vocab.json"
CATEGORY_MAP_PATH = PROJECT_ROOT / "data" / "processed" / "category_map.json"
RESULTS_DIR = PROJECT_ROOT / "results"
MODELS_DIR = PROJECT_ROOT / "models"
OUTPUT_PATH = RESULTS_DIR / "ablation.csv"

GCBERT_MODEL_NAME = "microsoft/graphcodebert-base"

# Model architecture
SEMANTIC_DIM = 768
AST_EMBED_DIM = 128
AST_HIDDEN_DIM = 128
AST_NUM_LAYERS = 2
AST_NUM_HEADS = 4
AST_FF_DIM = 512
FUSION_HIDDEN = 256
NUM_CATEGORIES = 15   # clean + 14 defect categories

# Training — per-configuration epoch counts
# Semantic (GraphCodeBERT) converges fast — 5 epochs is enough
# Structural (AST from scratch) converges slowly — 30 epochs to catch up
# Combined also converges fast — 5 epochs
CONFIG_EPOCHS = {
    "Semantic only": 5,
    "Structural only": 30,
    "Combined": 5,
}

BATCH_SIZE = 16
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
            # Multi-class target: 0-14 instead of binary 0/1
            "label": torch.tensor(r["category_id"], dtype=torch.long),
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
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),   # 15 classes
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
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),   # 15 classes
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
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),   # 15 classes
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


def load_category_map():
    with CATEGORY_MAP_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# METRICS
# ============================================================

def compute_metrics(logits, labels):
    preds = logits.argmax(dim=-1).cpu().numpy()
    labels_np = labels.cpu().numpy()
    return {
        "accuracy": accuracy_score(labels_np, preds),
        "macro_f1": f1_score(labels_np, preds, average="macro", zero_division=0),
        "weighted_f1": f1_score(labels_np, preds, average="weighted", zero_division=0),
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
    test_loader,
    device,
    save_path: Path,
    category_map: dict,
    config_epochs: int,
):
    print(f"\n{'='*60}")
    print(f"Training configuration: {name}  ({config_epochs} epochs)")
    print(f"{'='*60}\n")

    model = model.to(device)
    optimizer = build_optimizer(model)
    criterion = nn.CrossEntropyLoss()

    best_val_f1 = 0.0
    for epoch in range(1, config_epochs + 1):
        t0 = time.time()
        train_loss, train_metrics = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_metrics = evaluate(model, val_loader, criterion, device)
        elapsed = time.time() - t0

        print(f"Epoch {epoch}/{config_epochs}  ({elapsed:.1f}s)")
        print(f"  train  loss={train_loss:.4f}  acc={train_metrics['accuracy']:.4f}  "
              f"macroF1={train_metrics['macro_f1']:.4f}")
        print(f"  val    loss={val_loss:.4f}  acc={val_metrics['accuracy']:.4f}  "
              f"macroF1={val_metrics['macro_f1']:.4f}")

        if val_metrics["macro_f1"] > best_val_f1:
            best_val_f1 = val_metrics["macro_f1"]
            torch.save({
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "val_macro_f1": best_val_f1,
                "num_categories": NUM_CATEGORIES,
                "category_map": category_map,
            }, save_path)
            print(f"  -> saved best (val macro F1={best_val_f1:.4f})")
        print()

    # Load best and evaluate on full test set
    checkpoint = torch.load(save_path, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])

    test_loss, test_metrics = evaluate(model, test_loader, criterion, device)
    print(f"\n{name} — Final test performance:")
    print(f"  Accuracy:    {test_metrics['accuracy']:.4f}")
    print(f"  Macro F1:    {test_metrics['macro_f1']:.4f}")
    print(f"  Weighted F1: {test_metrics['weighted_f1']:.4f}\n")

    return {
        "config": name,
        "accuracy": test_metrics["accuracy"],
        "macro_f1": test_metrics["macro_f1"],
        "weighted_f1": test_metrics["weighted_f1"],
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
    category_map = load_category_map()
    print(f"  {len(records)} records, AST vocab size: {ast_vocab_size}, "
          f"categories: {len(category_map)}\n")

    # Split — no holdout, use all records
    train = [r for r in records if r["split"] == "train"]
    val = [r for r in records if r["split"] == "val"]
    test = [r for r in records if r["split"] == "test"]

    print(f"  train:  {len(train)}")
    print(f"  val:    {len(val)}")
    print(f"  test:   {len(test)}\n")

    if not test:
        print("No test records. Aborting.")
        return 1

    # Loaders
    train_loader = DataLoader(ExceptionDataset(train), batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(ExceptionDataset(val), batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn)
    test_loader = DataLoader(ExceptionDataset(test), batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn)

    # Run three configurations with their own epoch counts
    results = []

    # Config A: Semantic only
    results.append(run_configuration(
        "Semantic only",
        SemanticOnlyModel(),
        train_loader, val_loader, test_loader, device,
        MODELS_DIR / "ablation_semantic_15class.pt",
        category_map,
        CONFIG_EPOCHS["Semantic only"],
    ))

    # Config B: Structural only (30 epochs — was undertrained at 5)
    results.append(run_configuration(
        "Structural only",
        StructuralOnlyModel(ast_vocab_size=ast_vocab_size),
        train_loader, val_loader, test_loader, device,
        MODELS_DIR / "ablation_structural_15class.pt",
        category_map,
        CONFIG_EPOCHS["Structural only"],
    ))

    # Config C: Combined
    results.append(run_configuration(
        "Combined",
        DualStreamModel(ast_vocab_size=ast_vocab_size),
        train_loader, val_loader, test_loader, device,
        MODELS_DIR / "ablation_combined_15class.pt",
        category_map,
        CONFIG_EPOCHS["Combined"],
    ))

    # Summary
    print("\n" + "=" * 70)
    print("ABLATION STUDY — Full Test Set (15-class, no holdout)")
    print("=" * 70 + "\n")
    print(f"{'Configuration':<20} {'Accuracy':>10} {'Macro F1':>10} {'Weighted F1':>12}")
    print("-" * 70)
    for r in results:
        print(f"{r['config']:<20} {r['accuracy']:>10.4f} "
              f"{r['macro_f1']:>10.4f} {r['weighted_f1']:>12.4f}")

    # Write CSV
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["config", "accuracy", "macro_f1", "weighted_f1"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())