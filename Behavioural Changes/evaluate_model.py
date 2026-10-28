"""
Independent Evaluation Script for Fine-Tuned CodeT5 Java Behavioral Analysis
Evaluates model generalization on test examples from the dataset.
"""

import os
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

import torch
from transformers import AutoTokenizer, T5ForConditionalGeneration

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "codet5-java-behavior-verified"
DATASET_PATH = BASE_DIR / "dataset" / "behaviour_changes_dataset_270.json"

PERMITTED_CATEGORIES = {
    "STATE_MUTATION",
    "DATABASE_WRITE",
    "DATABASE_READ",
    "EXTERNAL_CALL",
    "FILE_OPERATION",
    "LOGGING",
    "EXCEPTION_BEHAVIOR",
    "OUTPUT_BEHAVIOR",
    "CALCULATION_TRANSFORMATION",
    "VALIDATION_CONTROL_FLOW",
}


def parse_prompt_methods(prompt_text: str) -> Tuple[str, str]:
    """Extracts old_method and new_method source code from a dataset prompt."""
    old_marker = "OLD METHOD:\n"
    new_marker = "\nNEW METHOD:\n"

    old_idx = prompt_text.find(old_marker)
    new_idx = prompt_text.find(new_marker)

    if old_idx == -1 or new_idx == -1:
        raise ValueError("Could not find method delimiters in dataset prompt.")

    old_code = prompt_text[old_idx + len(old_marker):new_idx].strip()
    new_code = prompt_text[new_idx + len(new_marker):].strip()
    return old_code, new_code


def evaluate_dataset_samples(num_samples: int = 10):
    """
    Evaluates the fine-tuned CodeT5 model on the final holdout samples of the 270-record dataset.
    """
    print(f"Loading dataset from: {DATASET_PATH}")
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    total_records = len(records)
    print(f"Total dataset records: {total_records}")

    # Use the final records (e.g. 261-270) as holdout test records
    test_records = records[-num_samples:]
    print(f"Evaluating on {len(test_records)} holdout test records (IDs: {[r['id'] for r in test_records]})\n")

    print(f"Loading CodeT5 model from: {MODEL_DIR}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Inference device: {device}")

    start_load = time.time()
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = T5ForConditionalGeneration.from_pretrained(str(MODEL_DIR))
    model.to(device)  # type: ignore[arg-type]
    model.eval()
    print(f"Model loaded in {time.time() - start_load:.2f} seconds.\n")

    valid_json_count = 0
    old_category_matches = 0
    new_category_matches = 0
    total_expected_old = 0
    total_predicted_old = 0
    total_correct_old = 0
    total_expected_new = 0
    total_predicted_new = 0
    total_correct_new = 0

    results = []

    for idx, rec in enumerate(test_records, 1):
        rec_id = rec["id"]
        input_prompt = rec["input"]
        ground_truth = json.loads(rec["output"])

        gt_old_cats = set(ground_truth["old_method"]["categories"])
        gt_new_cats = set(ground_truth["new_method"]["categories"])
        gt_old_body = ground_truth["old_method"]["method_body"].strip()
        gt_new_body = ground_truth["new_method"]["method_body"].strip()

        # Tokenize and generate
        inputs = tokenizer(  # type: ignore[operator]
            input_prompt,
            return_tensors="pt",
            max_length=512,
            truncation=True,
            padding=False
        ).to(device)

        with torch.inference_mode():
            outputs = model.generate(  # type: ignore[arg-type]
                input_ids=inputs["input_ids"],
                attention_mask=inputs.get("attention_mask"),
                max_length=512,
                num_beams=1,
                do_sample=False,
                early_stopping=True,
            )

        gen_text = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()  # type: ignore[union-attr]

        # Check JSON parsing
        is_valid_json = False
        pred_old_cats: Set[str] = set()
        pred_new_cats: Set[str] = set()
        pred_old_body = ""
        pred_new_body = ""

        try:
            start_b = gen_text.find("{")
            end_b = gen_text.rfind("}")
            if start_b != -1 and end_b != -1:
                json_str = gen_text[start_b:end_b + 1]
                data = json.loads(json_str)
                if "old_method" in data and "new_method" in data:
                    is_valid_json = True
                    pred_old_cats = set(c for c in data["old_method"].get("categories", []) if c in PERMITTED_CATEGORIES)
                    pred_new_cats = set(c for c in data["new_method"].get("categories", []) if c in PERMITTED_CATEGORIES)
                    pred_old_body = data["old_method"].get("method_body", "").strip()
                    pred_new_body = data["new_method"].get("method_body", "").strip()
        except Exception as e:
            is_valid_json = False

        if is_valid_json:
            valid_json_count += 1

        # Accuracy tallies
        correct_old = len(pred_old_cats & gt_old_cats)
        correct_new = len(pred_new_cats & gt_new_cats)

        total_correct_old += correct_old
        total_predicted_old += len(pred_old_cats)
        total_expected_old += len(gt_old_cats)

        total_correct_new += correct_new
        total_predicted_new += len(pred_new_cats)
        total_expected_new += len(gt_new_cats)

        old_match = (pred_old_cats == gt_old_cats)
        new_match = (pred_new_cats == gt_new_cats)
        if old_match:
            old_category_matches += 1
        if new_match:
            new_category_matches += 1

        print(f"[{idx}/{len(test_records)}] Record ID: {rec_id}")
        print(f"  Valid JSON: {is_valid_json}")
        print(f"  Old Method Categories -> Predicted: {sorted(list(pred_old_cats))} | Expected: {sorted(list(gt_old_cats))} | Match: {old_match}")
        print(f"  New Method Categories -> Predicted: {sorted(list(pred_new_cats))} | Expected: {sorted(list(gt_new_cats))} | Match: {new_match}")
        print(f"  Old Body Length: Pred={len(pred_old_body)} vs GT={len(gt_old_body)}")
        print(f"  New Body Length: Pred={len(pred_new_body)} vs GT={len(gt_new_body)}")
        print()

        results.append({
            "id": rec_id,
            "valid_json": is_valid_json,
            "old_match": old_match,
            "new_match": new_match,
            "pred_old": sorted(list(pred_old_cats)),
            "gt_old": sorted(list(gt_old_cats)),
            "pred_new": sorted(list(pred_new_cats)),
            "gt_new": sorted(list(gt_new_cats)),
        })

    # Summary Statistics
    precision_old = total_correct_old / max(total_predicted_old, 1)
    recall_old = total_correct_old / max(total_expected_old, 1)
    f1_old = 2 * (precision_old * recall_old) / max((precision_old + recall_old), 1e-6)

    precision_new = total_correct_new / max(total_predicted_new, 1)
    recall_new = total_correct_new / max(total_expected_new, 1)
    f1_new = 2 * (precision_new * recall_new) / max((precision_new + recall_new), 1e-6)

    print("=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total Test Cases Evaluated: {len(test_records)}")
    print(f"Valid JSON Generation Rate: {valid_json_count}/{len(test_records)} ({valid_json_count/len(test_records)*100:.1f}%)")
    print(f"Old Method Exact Category Set Match: {old_category_matches}/{len(test_records)} ({old_category_matches/len(test_records)*100:.1f}%)")
    print(f"New Method Exact Category Set Match: {new_category_matches}/{len(test_records)} ({new_category_matches/len(test_records)*100:.1f}%)")
    print(f"Old Method - Precision: {precision_old*100:.1f}%, Recall: {recall_old*100:.1f}%, F1: {f1_old*100:.1f}%")
    print(f"New Method - Precision: {precision_new*100:.1f}%, Recall: {recall_new*100:.1f}%, F1: {f1_new*100:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    evaluate_dataset_samples(num_samples=10)
