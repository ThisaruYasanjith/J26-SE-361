"""
Focused Trainer for Ablation Study: Semantic-Only and Structural-Only Models.

Trains SemanticOnlyModel and/or StructuralOnlyModel on the current augmented
dataset (data/processed/preprocessed.json) and saves:
  - models/ablation_semantic_15class.pt
  - models/ablation_structural_15class.pt

Note: This leaves models/ablation_combined_15class.pt completely untouched.

Usage:
  python src/train_ablation_models.py --model both
  python src/train_ablation_models.py --model semantic --epochs-semantic 5
  python src/train_ablation_models.py --model structural --epochs-structural 30
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
from transformers import AutoModel


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREPROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessed.json"
AST_VOCAB_PATH = PROJECT_ROOT / "data" / "processed" / "ast_vocab.json"
CATEGORY_MAP_PATH = PROJECT_ROOT / "data" / "processed" / "category_map.json"
MODELS_DIR = PROJECT_ROOT / "models"

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
# MODELS
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
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),
        )

    def forward(self, input_ids, attention_mask, ast_ids=None):
        gc_out = self.graphcodebert(input_ids=input_ids, attention_mask=attention_mask)
        return self.classifier(gc_out.pooler_output)


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
        self.ast_transformer = nn.TransformerEncoder(encoder_layer, num_layers=AST_NUM_LAYERS)
        self.ast_projection = nn.Linear(AST_EMBED_DIM, AST_HIDDEN_DIM)
        self.classifier = nn.Sequential(
            nn.Linear(AST_HIDDEN_DIM, FUSION_HIDDEN),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),
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

    param_groups = []
    if gc_params:
        param_groups.append({"params": gc_params, "lr": LR_GCBERT, "weight_decay": WEIGHT_DECAY})
    if other_params:
        param_groups.append({"params": other_params, "lr": LR_OTHER, "weight_decay": WEIGHT_DECAY})

    return torch.optim.AdamW(param_groups)


# ============================================================
# TRAIN & EVALUATION
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


def train_single_model(
    name: str,
    model: nn.Module,
    epochs: int,
    train_loader: DataLoader,
    val_loader: DataLoader,
    test_loader: DataLoader,
    category_map: dict,
    save_path: Path,
    device: torch.device,
):
    print("=" * 60)
    print(f"TRAINING {name.upper()} ({epochs} epochs)")
    print("=" * 60)
    model.to(device)
    optimizer = build_optimizer(model)
    criterion = nn.CrossEntropyLoss()

    best_val_f1 = 0.0

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        train_loss, train_metrics = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_metrics = evaluate(model, val_loader, criterion, device)
        elapsed = time.time() - t0

        print(f"Epoch {epoch:2d}/{epochs} ({elapsed:.1f}s) "
              f"| train loss={train_loss:.4f} acc={train_metrics['accuracy']:.4f} macroF1={train_metrics['macro_f1']:.4f} "
              f"| val loss={val_loss:.4f} acc={val_metrics['accuracy']:.4f} macroF1={val_metrics['macro_f1']:.4f}")

        if val_metrics["macro_f1"] > best_val_f1:
            best_val_f1 = val_metrics["macro_f1"]
            save_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "val_macro_f1": best_val_f1,
                "num_categories": NUM_CATEGORIES,
                "category_map": category_map,
            }, save_path)
            print(f"  -> Saved new best {name} to {save_path.name} (val macro F1={best_val_f1:.4f})")

    # Evaluate best checkpoint on test set
    print(f"\nLoading best checkpoint for {name} from {save_path.name}...")
    checkpoint = torch.load(save_path, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    test_loss, test_metrics = evaluate(model, test_loader, criterion, device)
    print(f"Test Evaluation for {name}:")
    print(f"  Accuracy:    {test_metrics['accuracy']:.4f}")
    print(f"  Macro F1:    {test_metrics['macro_f1']:.4f}")
    print(f"  Weighted F1: {test_metrics['weighted_f1']:.4f}")
    print(f"Checkpoint saved at: {save_path}\n")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Train Semantic and/or Structural Ablation Models")
    parser.add_argument("--model", choices=["both", "semantic", "structural"], default="both",
                        help="Which ablation model to train (default: both)")
    parser.add_argument("--epochs-semantic", type=int, default=5,
                        help="Number of epochs for semantic model (default: 5)")
    parser.add_argument("--epochs-structural", type=int, default=30,
                        help="Number of epochs for structural model (default: 30)")
    parser.add_argument("--batch-size", type=int, default=16,
                        help="Batch size (default: 16)")
    args = parser.parse_args()

    set_seed(SEED)
    device = get_device()
    print(f"Device: {device}")

    print("Loading data...")
    with PREPROCESSED_PATH.open(encoding="utf-8") as f:
        records = json.load(f)
    with AST_VOCAB_PATH.open(encoding="utf-8") as f:
        ast_vocab = json.load(f)
    with CATEGORY_MAP_PATH.open(encoding="utf-8") as f:
        category_map = json.load(f)

    print(f"Loaded {len(records)} records, AST vocab size: {len(ast_vocab)}, Categories: {len(category_map)}")

    train_records = [r for r in records if r.get("split") == "train"]
    val_records = [r for r in records if r.get("split") == "val"]
    test_records = [r for r in records if r.get("split") == "test"]
    print(f"Splits -> Train: {len(train_records)}, Val: {len(val_records)}, Test: {len(test_records)}\n")

    train_loader = DataLoader(ExceptionDataset(train_records), batch_size=args.batch_size, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(ExceptionDataset(val_records), batch_size=args.batch_size, shuffle=False, collate_fn=collate_fn)
    test_loader = DataLoader(ExceptionDataset(test_records), batch_size=args.batch_size, shuffle=False, collate_fn=collate_fn)

    # 1. Semantic Only
    if args.model in ("both", "semantic"):
        semantic_model = SemanticOnlyModel()
        train_single_model(
            name="Semantic Only",
            model=semantic_model,
            epochs=args.epochs_semantic,
            train_loader=train_loader,
            val_loader=val_loader,
            test_loader=test_loader,
            category_map=category_map,
            save_path=MODELS_DIR / "ablation_semantic_15class.pt",
            device=device,
        )

    # 2. Structural Only
    if args.model in ("both", "structural"):
        structural_model = StructuralOnlyModel(ast_vocab_size=len(ast_vocab))
        train_single_model(
            name="Structural Only",
            model=structural_model,
            epochs=args.epochs_structural,
            train_loader=train_loader,
            val_loader=val_loader,
            test_loader=test_loader,
            category_map=category_map,
            save_path=MODELS_DIR / "ablation_structural_15class.pt",
            device=device,
        )

    print("=" * 60)
    print("Ablation training complete!")
    print(f"Models directory: {MODELS_DIR}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    main()
