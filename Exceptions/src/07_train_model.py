"""
Dual-stream model for Java exception-handling defect classification.

Semantic stream: GraphCodeBERT -> 768-dim
Structural stream: AST embedding + transformer -> 128-dim
Fusion: concatenate -> MLP classifier -> 15 classes
        (clean + 14 defect categories)

Trains on ALL 15 categories (no holdout).

Trains on data/processed/preprocessed.json and saves the best model
to models/best_model_categorizer.pt.

Works on CPU, CUDA (Colab), or Apple Silicon MPS.

Run from project root:
    python src/07_train_model.py
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
CHECKPOINT_PATH = PROJECT_ROOT / "models" / "best_model_categorizer.pt"
HISTORY_PATH = PROJECT_ROOT / "results" / "training_history_categorizer.csv"

GCBERT_MODEL_NAME = "microsoft/graphcodebert-base"

# Model hyperparameters
SEMANTIC_DIM = 768
AST_EMBED_DIM = 128
AST_HIDDEN_DIM = 128
AST_NUM_LAYERS = 2
AST_NUM_HEADS = 4
AST_FF_DIM = 512
FUSION_HIDDEN = 256
NUM_CATEGORIES = 15   # clean + 14 defect categories

# Training hyperparameters
BATCH_SIZE = 16
EPOCHS = 10
LEARNING_RATE_GCBERT = 2e-5
LEARNING_RATE_OTHER = 1e-3
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.1
MAX_GRAD_NORM = 1.0
EARLY_STOP_PATIENCE = 3

# Reproducibility
SEED = 42


# ============================================================
# REPRODUCIBILITY
# ============================================================

def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


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
# MODEL
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
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),   # 15 classes
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
# DATA LOADING
# ============================================================

def load_preprocessed() -> list[dict]:
    with PREPROCESSED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_ast_vocab_size() -> int:
    with AST_VOCAB_PATH.open(encoding="utf-8") as f:
        vocab = json.load(f)
    return len(vocab)


def load_category_map() -> dict:
    with CATEGORY_MAP_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def split_by_field(records: list[dict]):
    train = [r for r in records if r["split"] == "train"]
    val = [r for r in records if r["split"] == "val"]
    test = [r for r in records if r["split"] == "test"]
    return train, val, test


# ============================================================
# METRICS
# ============================================================

def compute_metrics(logits: torch.Tensor, labels: torch.Tensor) -> dict:
    preds = logits.argmax(dim=-1).cpu().numpy()
    labels_np = labels.cpu().numpy()
    return {
        "accuracy": accuracy_score(labels_np, preds),
        "macro_f1": f1_score(labels_np, preds, average="macro", zero_division=0),
        "weighted_f1": f1_score(labels_np, preds, average="weighted", zero_division=0),
    }


# ============================================================
# TRAIN / VALIDATE
# ============================================================

def train_one_epoch(model, loader, optimizer, criterion, device, scheduler=None):
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
        if scheduler is not None:
            scheduler.step()

        total_loss += loss.item() * labels.size(0)
        all_logits.append(logits.detach())
        all_labels.append(labels.detach())

    avg_loss = total_loss / len(loader.dataset)
    all_logits = torch.cat(all_logits, dim=0)
    all_labels = torch.cat(all_labels, dim=0)
    metrics = compute_metrics(all_logits, all_labels)
    return avg_loss, metrics


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
    all_logits = torch.cat(all_logits, dim=0)
    all_labels = torch.cat(all_labels, dim=0)
    metrics = compute_metrics(all_logits, all_labels)
    return avg_loss, metrics


# ============================================================
# OPTIMIZER
# ============================================================

def build_optimizer(model):
    gcbert_params = list(model.graphcodebert.parameters())
    gcbert_param_ids = {id(p) for p in gcbert_params}
    other_params = [p for p in model.parameters() if id(p) not in gcbert_param_ids]

    return torch.optim.AdamW(
        [
            {"params": gcbert_params, "lr": LEARNING_RATE_GCBERT},
            {"params": other_params, "lr": LEARNING_RATE_OTHER},
        ],
        weight_decay=WEIGHT_DECAY,
    )


def build_scheduler(optimizer, num_training_steps: int):
    from transformers import get_linear_schedule_with_warmup
    num_warmup = int(num_training_steps * WARMUP_RATIO)
    return get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=num_warmup,
        num_training_steps=num_training_steps,
    )


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    set_seed(SEED)
    device = get_device()
    print(f"Device: {device}\n")

    # ---- Load data ----
    print(f"Loading preprocessed data from {PREPROCESSED_PATH.name}...")
    records = load_preprocessed()
    ast_vocab_size = load_ast_vocab_size()
    category_map = load_category_map()
    print(f"  {len(records)} records, AST vocab size: {ast_vocab_size}")
    print(f"  Categories: {len(category_map)}\n")

    train_records, val_records, test_records = split_by_field(records)

    print(f"  train:  {len(train_records)}")
    print(f"  val:    {len(val_records)}")
    print(f"  test:   {len(test_records)}")
    print()

    # ---- Datasets and loaders ----
    train_loader = DataLoader(
        ExceptionDataset(train_records),
        batch_size=BATCH_SIZE,
        shuffle=True,
        collate_fn=collate_fn,
    )
    val_loader = DataLoader(
        ExceptionDataset(val_records),
        batch_size=BATCH_SIZE,
        shuffle=False,
        collate_fn=collate_fn,
    )

    # ---- Model ----
    print("Building model...")
    model = DualStreamModel(ast_vocab_size=ast_vocab_size).to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  Trainable parameters: {n_params:,}")
    print(f"  Output classes:       {NUM_CATEGORIES}\n")

    # ---- Optimizer + scheduler ----
    optimizer = build_optimizer(model)
    num_training_steps = len(train_loader) * EPOCHS
    scheduler = build_scheduler(optimizer, num_training_steps)

    criterion = nn.CrossEntropyLoss()

    # ---- Training loop ----
    print("Starting training...\n")
    best_val_f1 = 0.0
    patience_counter = 0
    history = []

    for epoch in range(1, EPOCHS + 1):
        t0 = time.time()
        train_loss, train_metrics = train_one_epoch(
            model, train_loader, optimizer, criterion, device, scheduler
        )
        val_loss, val_metrics = evaluate(model, val_loader, criterion, device)
        elapsed = time.time() - t0

        print(f"Epoch {epoch}/{EPOCHS}  ({elapsed:.1f}s)")
        print(f"  train  loss={train_loss:.4f}  acc={train_metrics['accuracy']:.4f}  "
              f"macroF1={train_metrics['macro_f1']:.4f}")
        print(f"  val    loss={val_loss:.4f}  acc={val_metrics['accuracy']:.4f}  "
              f"macroF1={val_metrics['macro_f1']:.4f}")

        history.append({
            "epoch": epoch,
            "train_loss": train_loss,
            "train_acc": train_metrics["accuracy"],
            "train_macro_f1": train_metrics["macro_f1"],
            "val_loss": val_loss,
            "val_acc": val_metrics["accuracy"],
            "val_macro_f1": val_metrics["macro_f1"],
            "val_weighted_f1": val_metrics["weighted_f1"],
        })

        # Save best model based on validation macro F1
        if val_metrics["macro_f1"] > best_val_f1:
            best_val_f1 = val_metrics["macro_f1"]
            patience_counter = 0
            CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "val_macro_f1": val_metrics["macro_f1"],
                "val_accuracy": val_metrics["accuracy"],
                "ast_vocab_size": ast_vocab_size,
                "num_categories": NUM_CATEGORIES,
                "category_map": category_map,
            }, CHECKPOINT_PATH)
            print(f"  -> saved best model (val macro F1={best_val_f1:.4f})")
        else:
            patience_counter += 1
            print(f"  -> no improvement ({patience_counter}/{EARLY_STOP_PATIENCE})")
            if patience_counter >= EARLY_STOP_PATIENCE:
                print(f"\nEarly stopping at epoch {epoch}.")
                break
        print()

    # ---- Save training history ----
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=history[0].keys())
        writer.writeheader()
        writer.writerows(history)
    print(f"Wrote training history to {HISTORY_PATH.relative_to(PROJECT_ROOT)}")

    # ---- Final summary ----
    print()
    print("=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Best validation macro F1:  {best_val_f1:.4f}")
    print()
    print(f"Best model saved to: {CHECKPOINT_PATH.relative_to(PROJECT_ROOT)}")

    return 0


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    sys.exit(main())