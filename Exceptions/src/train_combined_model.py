"""
Focused Trainer for the Combined Dual-Stream Model.

Trains DualStreamModel on the augmented data/processed/preprocessed.json
and saves the updated checkpoint to models/ablation_combined_15class.pt.

Usage:
    python src/train_combined_model.py [--epochs 5] [--batch-size 16]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["SAFETENSORS_FAST_GPU"] = "1"
os.environ["HF_HUB_DISABLE_SAFETENSORS_CONVERSION"] = "1"

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModel

# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREPROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessed.json"
AST_VOCAB_PATH = PROJECT_ROOT / "data" / "processed" / "ast_vocab.json"
CATEGORY_MAP_PATH = PROJECT_ROOT / "data" / "processed" / "category_map.json"
SAVE_PATH = PROJECT_ROOT / "models" / "ablation_combined_15class.pt"

GCBERT_MODEL_NAME = "microsoft/graphcodebert-base"

SEMANTIC_DIM = 768
AST_EMBED_DIM = 128
AST_HIDDEN_DIM = 128
AST_NUM_LAYERS = 2
AST_NUM_HEADS = 4
AST_FF_DIM = 512
FUSION_HIDDEN = 256
NUM_CATEGORIES = 15

LR_GCBERT = 2e-5
LR_OTHER = 1e-3
WEIGHT_DECAY = 0.01
MAX_GRAD_NORM = 1.0
SEED = 42


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
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
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),
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
# OPTIMIZER
# ============================================================

def build_optimizer(model: nn.Module) -> torch.optim.Optimizer:
    gc_params = []
    other_params = []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        if "graphcodebert" in name:
            gc_params.append(param)
        else:
            other_params.append(param)

    param_groups = [
        {"params": gc_params, "lr": LR_GCBERT, "weight_decay": WEIGHT_DECAY},
        {"params": other_params, "lr": LR_OTHER, "weight_decay": WEIGHT_DECAY},
    ]
    return torch.optim.AdamW(param_groups)


# ============================================================
# TRAINING & EVALUATION
# ============================================================

def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    all_preds = []
    all_labels = []

    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        ast_ids = batch["ast_ids"].to(device)
        labels = batch["label"].to(device)

        optimizer.zero_grad()
        logits = model(input_ids, attention_mask, ast_ids)
        loss = criterion(logits, labels)
        loss.backward()

        nn.utils.clip_grad_norm_(model.parameters(), MAX_GRAD_NORM)
        optimizer.step()

        total_loss += loss.item() * len(labels)
        preds = torch.argmax(logits, dim=-1).cpu().numpy()
        all_preds.extend(preds)
        all_labels.extend(labels.cpu().numpy())

    avg_loss = total_loss / len(all_labels)
    acc = accuracy_score(all_labels, all_preds)
    macro_f1 = f1_score(all_labels, all_preds, average="macro", zero_division=0)
    return avg_loss, {"accuracy": acc, "macro_f1": macro_f1}


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    all_preds = []
    all_labels = []

    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        ast_ids = batch["ast_ids"].to(device)
        labels = batch["label"].to(device)

        logits = model(input_ids, attention_mask, ast_ids)
        loss = criterion(logits, labels)

        total_loss += loss.item() * len(labels)
        preds = torch.argmax(logits, dim=-1).cpu().numpy()
        all_preds.extend(preds)
        all_labels.extend(labels.cpu().numpy())

    avg_loss = total_loss / len(all_labels)
    acc = accuracy_score(all_labels, all_preds)
    macro_f1 = f1_score(all_labels, all_preds, average="macro", zero_division=0)
    weighted_f1 = f1_score(all_labels, all_preds, average="weighted", zero_division=0)
    return avg_loss, {"accuracy": acc, "macro_f1": macro_f1, "weighted_f1": weighted_f1}


def main():
    parser = argparse.ArgumentParser(description="Train Combined Dual-Stream Model")
    parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size")
    args = parser.parse_args()

    set_seed(SEED)
    device = get_device()
    print(f"Device: {device}")

    # Load data
    print("Loading data...")
    with PREPROCESSED_PATH.open(encoding="utf-8") as f:
        records = json.load(f)
    with AST_VOCAB_PATH.open(encoding="utf-8") as f:
        ast_vocab = json.load(f)
    with CATEGORY_MAP_PATH.open(encoding="utf-8") as f:
        category_map = json.load(f)

    print(f"Loaded {len(records)} records, AST vocab size: {len(ast_vocab)}, Categories: {len(category_map)}")

    # Split dataset based on record['split']
    train_records = [r for r in records if r.get("split") == "train"]
    val_records = [r for r in records if r.get("split") == "val"]
    test_records = [r for r in records if r.get("split") == "test"]

    print(f"Splits -> Train: {len(train_records)}, Val: {len(val_records)}, Test: {len(test_records)}")

    train_loader = DataLoader(ExceptionDataset(train_records), batch_size=args.batch_size, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(ExceptionDataset(val_records), batch_size=args.batch_size, shuffle=False, collate_fn=collate_fn)
    test_loader = DataLoader(ExceptionDataset(test_records), batch_size=args.batch_size, shuffle=False, collate_fn=collate_fn)

    # Initialize model
    print("Initializing DualStreamModel...")
    model = DualStreamModel(ast_vocab_size=len(ast_vocab)).to(device)
    optimizer = build_optimizer(model)
    criterion = nn.CrossEntropyLoss()

    best_val_f1 = 0.0
    print(f"\nStarting training for {args.epochs} epochs...\n")

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss, train_metrics = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_metrics = evaluate(model, val_loader, criterion, device)
        elapsed = time.time() - t0

        print(f"Epoch {epoch}/{args.epochs} ({elapsed:.1f}s)")
        print(f"  train loss={train_loss:.4f}  acc={train_metrics['accuracy']:.4f}  macroF1={train_metrics['macro_f1']:.4f}")
        print(f"  val   loss={val_loss:.4f}  acc={val_metrics['accuracy']:.4f}  macroF1={val_metrics['macro_f1']:.4f}")

        if val_metrics["macro_f1"] > best_val_f1:
            best_val_f1 = val_metrics["macro_f1"]
            torch.save({
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "val_macro_f1": best_val_f1,
                "num_categories": NUM_CATEGORIES,
                "category_map": category_map,
            }, SAVE_PATH)
            print(f"  -> Saved new best model to {SAVE_PATH.name} (val macro F1={best_val_f1:.4f})")
        print()

    # Final evaluation on test set
    checkpoint = torch.load(SAVE_PATH, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    test_loss, test_metrics = evaluate(model, test_loader, criterion, device)

    print("=" * 60)
    print("FINAL TEST PERFORMANCE ON BALANCED DATASET")
    print("=" * 60)
    print(f"  Accuracy:    {test_metrics['accuracy']:.4f}")
    print(f"  Macro F1:    {test_metrics['macro_f1']:.4f}")
    print(f"  Weighted F1: {test_metrics['weighted_f1']:.4f}")
    print("=" * 60)
    print(f"Checkpoint ready at: {SAVE_PATH}")
    return 0


if __name__ == "__main__":
    main()
