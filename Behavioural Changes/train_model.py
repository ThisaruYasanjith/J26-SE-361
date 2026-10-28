"""
train_model.py
==============
Fine-tunes Salesforce/codet5-small on the Java behavioral change dataset.

Features:
  - 90 / 10 stratified train/validation split
  - Seq2Seq training with HuggingFace Trainer
  - Saves BEST checkpoint (lowest eval loss) as 'codet5-java-behavior-v2'
  - Evaluates on holdout after training (JSON validity + category F1)
  - Works on CPU and GPU (auto-detects CUDA)
  - Resumes from 'codet5-java-behavior-verified' base model

Usage:
    python train_model.py                     # train with defaults
    python train_model.py --epochs 20         # override epoch count
    python train_model.py --eval-only         # skip training, evaluate existing model
    python train_model.py --output-dir codet5-java-behavior-v2

Requirements (already in requirements.txt):
    torch>=2.0.0  transformers>=4.40.0  safetensors>=0.4.0
"""

import argparse
import json
import math
import os
import random
import time
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoTokenizer,
    T5ForConditionalGeneration,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    DataCollatorForSeq2Seq,
    EarlyStoppingCallback,
)

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent
BASE_MODEL_DIR  = BASE_DIR / "codet5-java-behavior-verified"   # fine-tuning starts here
OUTPUT_DIR      = BASE_DIR / "codet5-java-behavior-v2"         # new best checkpoint saved here
DATASET_PATH    = BASE_DIR / "dataset" / "behaviour_changes_dataset_270.json"

# ── Hyperparameters (tuned for 270-record dataset) ───────────────────────────
DEFAULT_EPOCHS          = 20      # small dataset needs more epochs
DEFAULT_LR              = 2e-4    # standard T5 fine-tune rate
DEFAULT_BATCH_SIZE      = 4       # per-device (increase to 8 if >8GB RAM/VRAM)
DEFAULT_GRAD_ACCUM      = 2       # effective batch = 4 * 2 = 8
DEFAULT_WARMUP_STEPS    = 50
DEFAULT_WEIGHT_DECAY    = 0.01
MAX_INPUT_LENGTH        = 512
MAX_TARGET_LENGTH       = 384
SEED                    = 42
VAL_SPLIT_RATIO         = 0.10    # 10% holdout → ~27 records

PERMITTED: Set[str] = {
    "STATE_MUTATION", "DATABASE_WRITE", "DATABASE_READ", "EXTERNAL_CALL",
    "FILE_OPERATION", "LOGGING", "EXCEPTION_BEHAVIOR", "OUTPUT_BEHAVIOR",
    "CALCULATION_TRANSFORMATION", "VALIDATION_CONTROL_FLOW",
}

SEP = "=" * 72


# ── Dataset ──────────────────────────────────────────────────────────────────
class BehavioralDataset(Dataset):
    """
    Wraps the 270-record JSON dataset as a HuggingFace-compatible Seq2Seq dataset.
    Each record: {"id": ..., "input": "...", "output": "..."}
    """

    def __init__(
        self,
        records: List[Dict[str, Any]],
        tokenizer,
        max_input_len: int = MAX_INPUT_LENGTH,
        max_target_len: int = MAX_TARGET_LENGTH,
    ):
        self.records = records
        self.tokenizer = tokenizer
        self.max_input_len = max_input_len
        self.max_target_len = max_target_len

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index: int) -> Dict[str, Any]:
        rec = self.records[index]
        inp = rec["input"]
        tgt = rec["output"]

        model_inputs = self.tokenizer(
            inp,
            max_length=self.max_input_len,
            truncation=True,
            padding=False,
        )

        try:
            labels = self.tokenizer(
                text_target=tgt,
                max_length=self.max_target_len,
                truncation=True,
                padding=False,
            )
        except TypeError:
            labels = self.tokenizer(
                tgt,
                max_length=self.max_target_len,
                truncation=True,
                padding=False,
            )

        model_inputs["labels"] = labels["input_ids"]
        return model_inputs


# ── Evaluation helpers ───────────────────────────────────────────────────────
def try_parse_output(text: str) -> Tuple[bool, Set[str], Set[str]]:
    """Returns (valid_json, old_cats, new_cats)."""
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return False, set(), set()
    text = text[start:]
    end = text.rfind("}")
    if end == -1:
        return False, set(), set()
    try:
        data = json.loads(text[:end + 1])
        if "old_method" not in data or "new_method" not in data:
            return False, set(), set()
        old_cats = set(c for c in data["old_method"].get("categories", []) if c in PERMITTED)
        new_cats = set(c for c in data["new_method"].get("categories", []) if c in PERMITTED)
        return True, old_cats, new_cats
    except json.JSONDecodeError:
        return False, set(), set()


def evaluate_on_holdout(
    model,
    tokenizer,
    device: torch.device,
    val_records: List[Dict[str, Any]],
    num_beams: int = 4,
    label: str = "Holdout Evaluation",
):
    """Runs inference on val_records and prints F1 / JSON validity report."""
    print(f"\n{SEP}")
    print(f"  {label}  ({len(val_records)} records)")
    print(SEP)

    model.eval()
    valid_json = 0
    total_correct_old = total_predicted_old = total_expected_old = 0
    total_correct_new = total_predicted_new = total_expected_new = 0
    exact_old = exact_new = 0

    for rec in val_records:
        gt = json.loads(rec["output"])
        gt_old = set(gt["old_method"]["categories"]) & PERMITTED
        gt_new = set(gt["new_method"]["categories"]) & PERMITTED

        enc = tokenizer(
            rec["input"],
            return_tensors="pt",
            max_length=MAX_INPUT_LENGTH,
            truncation=True,
            padding=False,
        ).to(device)

        with torch.inference_mode():
            out = model.generate(  # type: ignore[arg-type]
                input_ids=enc["input_ids"],
                attention_mask=enc.get("attention_mask"),
                max_new_tokens=MAX_TARGET_LENGTH,
                num_beams=num_beams,
                do_sample=False,
            )

        raw = tokenizer.decode(out[0], skip_special_tokens=True)  # type: ignore[union-attr]
        ok, pred_old, pred_new = try_parse_output(raw)

        if ok:
            valid_json += 1

        correct_old = len(pred_old & gt_old)
        correct_new = len(pred_new & gt_new)

        total_correct_old  += correct_old
        total_predicted_old += len(pred_old)
        total_expected_old  += len(gt_old)

        total_correct_new  += correct_new
        total_predicted_new += len(pred_new)
        total_expected_new  += len(gt_new)

        if pred_old == gt_old:
            exact_old += 1
        if pred_new == gt_new:
            exact_new += 1

    n = len(val_records)

    def f1(tp, pp, ep):
        p = tp / max(pp, 1)
        r = tp / max(ep, 1)
        return 2 * p * r / max(p + r, 1e-9)

    f1_old = f1(total_correct_old, total_predicted_old, total_expected_old)
    f1_new = f1(total_correct_new, total_predicted_new, total_expected_new)

    print(f"\n  Valid JSON      : {valid_json}/{n}  ({valid_json/n*100:.1f}%)")
    print(f"  Old: Exact match: {exact_old}/{n}  ({exact_old/n*100:.1f}%)   F1: {f1_old*100:.1f}%")
    print(f"  New: Exact match: {exact_new}/{n}  ({exact_new/n*100:.1f}%)   F1: {f1_new*100:.1f}%")
    print(SEP)

    return {
        "valid_json_pct": valid_json / n,
        "f1_old": f1_old,
        "f1_new": f1_new,
        "exact_old_pct": exact_old / n,
        "exact_new_pct": exact_new / n,
    }


# ── Main ─────────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune CodeT5 on Java behavioral dataset")
    parser.add_argument("--epochs",      type=int,   default=DEFAULT_EPOCHS)
    parser.add_argument("--lr",          type=float, default=DEFAULT_LR)
    parser.add_argument("--batch-size",  type=int,   default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--output-dir",  type=str,   default=str(OUTPUT_DIR))
    parser.add_argument("--base-model",  type=str,   default=str(BASE_MODEL_DIR))
    parser.add_argument("--eval-only",   action="store_true",
                        help="Skip training, evaluate OUTPUT_DIR model on holdout")
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir  = Path(args.output_dir)
    base_model  = Path(args.base_model)

    print(f"\n{SEP}")
    print(f"  CodeT5 Fine-Tuning Script")
    print(f"  Base model : {base_model}")
    print(f"  Output dir : {output_dir}")
    print(f"  Dataset    : {DATASET_PATH}")
    print(SEP)

    # ── Load dataset ──
    with open(DATASET_PATH, encoding="utf-8") as f:
        records = json.load(f)
    print(f"\nLoaded {len(records)} records from dataset.")

    # ── Split train / val ──
    random.seed(SEED)
    shuffled = list(records)
    random.shuffle(shuffled)
    val_count  = max(1, int(len(shuffled) * VAL_SPLIT_RATIO))
    val_records   = shuffled[:val_count]
    train_records = shuffled[val_count:]
    print(f"Split: {len(train_records)} train  /  {len(val_records)} validation")

    # ── Device ──
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu":
        threads = min(os.cpu_count() or 4, 8)
        torch.set_num_threads(threads)
        print(f"Device: CPU  ({threads} threads)")
        print("  Tip: GPU training is ~10x faster. Training on CPU will take ~30-60 min.")
    else:
        print(f"Device: GPU  ({torch.cuda.get_device_name(0)})")

    # ── Load tokenizer & model ──
    print(f"\nLoading tokenizer from: {base_model}")
    tokenizer = AutoTokenizer.from_pretrained(str(base_model))

    if args.eval_only:
        # Evaluate output_dir model on holdout
        print(f"\nEval-only mode. Loading model from: {output_dir}")
        model = T5ForConditionalGeneration.from_pretrained(str(output_dir))
        model.to(device)  # type: ignore[arg-type]
        evaluate_on_holdout(model, tokenizer, device, val_records, label="Post-Training Holdout Eval")
        return

    print(f"Loading base model from: {base_model}")
    t0 = time.time()
    model = T5ForConditionalGeneration.from_pretrained(str(base_model))
    print(f"Model loaded in {time.time() - t0:.1f}s")

    # ── Pre-training baseline ──
    model.to(device)  # type: ignore[arg-type]
    print("\nRunning PRE-TRAINING baseline evaluation on validation set...")
    pre_metrics = evaluate_on_holdout(
        model, tokenizer, device, val_records, num_beams=1, label="PRE-TRAINING Baseline"
    )

    # ── Build datasets ──
    train_dataset = BehavioralDataset(train_records, tokenizer)
    val_dataset   = BehavioralDataset(val_records,   tokenizer)

    # ── Training arguments ──
    steps_per_epoch = math.ceil(len(train_records) / (args.batch_size * DEFAULT_GRAD_ACCUM))
    warmup = min(DEFAULT_WARMUP_STEPS, steps_per_epoch * 2)

    training_args = Seq2SeqTrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=DEFAULT_GRAD_ACCUM,
        learning_rate=args.lr,
        weight_decay=DEFAULT_WEIGHT_DECAY,
        warmup_steps=warmup,
        lr_scheduler_type="cosine",

        # Evaluation & checkpointing
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,

        # Generation
        predict_with_generate=False,   # use loss-based eval during training for speed

        # Seq2Seq
        generation_max_length=MAX_TARGET_LENGTH,
        generation_num_beams=1,   # training eval uses greedy for speed

        # Logging (logs go to output_dir/checkpoints by default in transformers 5.x)
        logging_steps=max(1, steps_per_epoch // 2),
        report_to="none",

        # Misc
        seed=SEED,
        fp16=torch.cuda.is_available(),   # mixed precision on GPU only
        dataloader_num_workers=0,         # avoids multiprocessing issues on Windows
        remove_unused_columns=True,
    )

    data_collator = DataCollatorForSeq2Seq(
        tokenizer,  # type: ignore[arg-type]
        model=model,
        label_pad_token_id=-100,
        pad_to_multiple_of=8 if torch.cuda.is_available() else None,
    )

    # transformers >=4.46 renamed 'tokenizer' to 'processing_class' in Trainer.
    # Try the new name first; fall back to the old name for older versions.
    try:
        trainer = Seq2SeqTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            processing_class=tokenizer,  # transformers >=4.46 / 5.x
            data_collator=data_collator,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=4)],
        )
    except TypeError:
        trainer = Seq2SeqTrainer(  # type: ignore[call-arg]
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            tokenizer=tokenizer,          # type: ignore[call-arg]  # transformers <4.46
            data_collator=data_collator,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=4)],
        )

    # ── Train ──
    print(f"\n{SEP}")
    print(f"  Starting Training")
    print(f"  Epochs         : {args.epochs}")
    print(f"  Learning rate  : {args.lr}")
    print(f"  Batch size     : {args.batch_size} × {DEFAULT_GRAD_ACCUM} grad_accum = {args.batch_size * DEFAULT_GRAD_ACCUM} effective")
    print(f"  Warmup steps   : {warmup}")
    print(f"  Steps/epoch    : {steps_per_epoch}")
    print(f"  Early stopping : 4 epochs patience on eval_loss")
    print(SEP)

    t0 = time.time()
    trainer.train()
    elapsed = time.time() - t0
    print(f"\nTraining completed in {elapsed/60:.1f} minutes.")

    # ── Save best model ──
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nSaving best model to: {output_dir}")
    trainer.save_model(str(output_dir))
    assert tokenizer is not None, "Tokenizer must be loaded before saving"
    tokenizer.save_pretrained(str(output_dir))
    print("Model saved.")

    # ── Post-training evaluation ──
    print("\nRunning POST-TRAINING evaluation on validation holdout (beam search)...")
    post_metrics = evaluate_on_holdout(
        model, tokenizer, device, val_records,
        num_beams=4, label="POST-TRAINING Holdout Eval"
    )

    # ── Summary ──
    print(f"\n{SEP}")
    print("  Training Summary")
    print(SEP)
    print(f"  {'Metric':<30} {'Before':>10}  {'After':>10}")
    print(f"  {'-'*52}")
    for key, label in [
        ("valid_json_pct",  "Valid JSON (%)"),
        ("f1_old",          "Old Method F1 (%)"),
        ("f1_new",          "New Method F1 (%)"),
        ("exact_old_pct",   "Old Exact Match (%)"),
        ("exact_new_pct",   "New Exact Match (%)"),
    ]:
        bef = pre_metrics[key] * 100
        aft = post_metrics[key] * 100
        arrow = "▲" if aft > bef else ("▼" if aft < bef else "=")
        print(f"  {label:<30} {bef:>9.1f}%  {aft:>9.1f}% {arrow}")
    print(SEP)

    print(f"\nNew model saved to: {output_dir}")
    print("To use the retrained model, update your .env:")
    print(f"  MODEL_DIR={output_dir.name}")


if __name__ == "__main__":
    main()
