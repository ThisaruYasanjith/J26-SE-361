"""
diagnose_model.py
=================
Standalone diagnostic script for the fine-tuned CodeT5 model.

Bypasses FastAPI and Streamlit entirely.
Directly loads the model and runs inference on:
  1. Dataset record 001 (training example — sanity check)
  2. Dataset record 135 (mid-dataset)
  3. Dataset record 270 (last record — near holdout)
  4-6. Three custom examples NOT in the dataset (generalisation check)

Reports:
  - Raw model output (verbatim)
  - Whether it is valid JSON
  - Parsed old/new categories vs ground truth
  - Method body lengths
  - Token counts (input vs MAX_INPUT_LENGTH)
  - Whether output was truncated
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Set, Tuple

import torch
from transformers import AutoTokenizer, T5ForConditionalGeneration

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
MODEL_DIR   = BASE_DIR / "codet5-java-behavior-verified"
DATASET     = BASE_DIR / "dataset" / "behaviour_changes_dataset_270.json"

MAX_INPUT_TOKENS  = 512
MAX_NEW_TOKENS    = 384   # generous for full JSON with two method bodies
NUM_BEAMS         = 4     # beam search for best output quality

PERMITTED: Set[str] = {
    "STATE_MUTATION", "DATABASE_WRITE", "DATABASE_READ", "EXTERNAL_CALL",
    "FILE_OPERATION", "LOGGING", "EXCEPTION_BEHAVIOR", "OUTPUT_BEHAVIOR",
    "CALCULATION_TRANSFORMATION", "VALIDATION_CONTROL_FLOW",
}

SEP = "=" * 72

CUSTOM_CASES = [
    {
        "label": "Custom-A: pure calculation -> exception injection",
        "old": (
            "public double computeInterest(double principal, double rate, int years) {\n"
            "    return principal * rate * years;\n"
            "}"
        ),
        "new": (
            "public double computeInterest(double principal, double rate, int years) {\n"
            "    if (principal < 0) throw new IllegalArgumentException(\"principal must be positive\");\n"
            "    return principal * rate * years;\n"
            "}"
        ),
    },
    {
        "label": "Custom-B: file read -> DB write added",
        "old": (
            "public String loadConfig(java.nio.file.Path configPath) throws java.io.IOException {\n"
            "    return java.nio.file.Files.readString(configPath);\n"
            "}"
        ),
        "new": (
            "public String loadConfig(java.nio.file.Path configPath) throws java.io.IOException {\n"
            "    String content = java.nio.file.Files.readString(configPath);\n"
            "    configRepository.save(content);\n"
            "    return content;\n"
            "}"
        ),
    },
    {
        "label": "Custom-C: logging + state mutation added",
        "old": (
            "public void updateUsername(User user, String newName) {\n"
            "    user.setName(newName);\n"
            "}"
        ),
        "new": (
            "public void updateUsername(User user, String newName) {\n"
            "    logger.info(\"Updating username to \" + newName);\n"
            "    user.setName(newName);\n"
            "    this.lastModifiedUser = user;\n"
            "}"
        ),
    },
]

PROMPT_TEMPLATE = (
    "Identify all applicable behavioral categories for each Java method. "
    "Use only these categories: STATE_MUTATION, DATABASE_WRITE, DATABASE_READ, "
    "EXTERNAL_CALL, FILE_OPERATION, LOGGING, EXCEPTION_BEHAVIOR, OUTPUT_BEHAVIOR, "
    "CALCULATION_TRANSFORMATION, VALIDATION_CONTROL_FLOW. Classify each method independently "
    "using its code, not its name alone. Multiple categories are allowed. "
    'Return valid JSON with exactly this structure: {{"old_method":{{"categories":[],"method_body":"..."}},'
    '"new_method":{{"categories":[],"method_body":"..."}}}}. '
    "Extract the exact statements inside each method's braces, excluding the method declaration and outer braces. "
    "Preserve statement order and nested blocks. Do not classify behavioral drift.\n"
    "OLD METHOD:\n{old_method}\n"
    "NEW METHOD:\n{new_method}"
)


def build_prompt(old: str, new: str) -> str:
    return PROMPT_TEMPLATE.format(old_method=old.strip(), new_method=new.strip())


def run_inference(model, tokenizer, device, prompt: str):
    enc = tokenizer(
        prompt,
        return_tensors="pt",
        max_length=MAX_INPUT_TOKENS,
        truncation=True,
        padding=False,
    ).to(device)
    input_len = enc["input_ids"].shape[1]
    with torch.inference_mode():
        out = model.generate(  # type: ignore[arg-type]
            input_ids=enc["input_ids"],
            attention_mask=enc.get("attention_mask"),
            max_new_tokens=MAX_NEW_TOKENS,
            num_beams=NUM_BEAMS,
            early_stopping=True,
            do_sample=False,
        )
    output_len = out.shape[1]
    raw = tokenizer.decode(out[0], skip_special_tokens=True)  # type: ignore[union-attr]
    return raw, input_len, output_len


def try_parse(raw: str):
    text = raw.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    start = text.find("{")
    if start == -1:
        return False, {}
    text = text[start:]
    end = text.rfind("}")
    if end == -1:
        return False, {}
    try:
        data = json.loads(text[:end + 1])
        if "old_method" in data and "new_method" in data:
            return True, data
        return False, {}
    except json.JSONDecodeError:
        return False, {}


def report_case(label, old, new, model, tokenizer, device,
                gt_old_cats=None, gt_new_cats=None):
    print(f"\n{SEP}")
    print(f"  {label}")
    print(SEP)
    prompt = build_prompt(old, new)
    full_token_count = len(tokenizer.encode(prompt))
    t0 = time.time()
    raw, input_tokens, output_tokens = run_inference(model, tokenizer, device, prompt)
    elapsed = time.time() - t0
    print(f"\n[INPUT]  Full prompt tokens  : {full_token_count}  (limit: {MAX_INPUT_TOKENS})")
    if full_token_count > MAX_INPUT_TOKENS:
        print(f"  WARNING: TRUNCATED — {full_token_count - MAX_INPUT_TOKENS} tokens were dropped")
    print(f"[INPUT]  Tokens fed to model : {input_tokens}")
    print(f"[OUTPUT] Generated tokens    : {output_tokens}  (limit: {MAX_NEW_TOKENS})")
    print(f"[TIME]   Wall time           : {elapsed:.2f}s")
    print(f"\n[RAW OUTPUT]:\n{raw}")
    valid, data = try_parse(raw)
    print(f"\n[JSON VALID]: {valid}")
    if valid:
        old_cats = data["old_method"].get("categories", [])
        new_cats = data["new_method"].get("categories", [])
        old_body = data["old_method"].get("method_body", "")
        new_body = data["new_method"].get("method_body", "")
        bad_old = [c for c in old_cats if c not in PERMITTED]
        bad_new = [c for c in new_cats if c not in PERMITTED]
        print(f"\n  OLD categories : {old_cats}")
        if bad_old:
            print(f"  WARNING invalid: {bad_old}")
        print(f"  NEW categories : {new_cats}")
        if bad_new:
            print(f"  WARNING invalid: {bad_new}")
        print(f"\n  OLD body ({len(old_body)} chars): {old_body[:200]}")
        print(f"  NEW body ({len(new_body)} chars): {new_body[:200]}")
        if gt_old_cats is not None:
            pred_old = set(old_cats) & PERMITTED
            pred_new = set(new_cats) & PERMITTED
            gt_o = set(gt_old_cats)
            gt_n = set(gt_new_cats or [])
            print(f"\n  [vs GT] OLD: pred={sorted(pred_old)} expected={sorted(gt_o)} match={pred_old==gt_o}")
            print(f"  [vs GT] NEW: pred={sorted(pred_new)} expected={sorted(gt_n)} match={pred_new==gt_n}")
    else:
        print("  FAILED to parse JSON from raw output.")
    if output_tokens >= MAX_NEW_TOKENS - 2:
        print(f"\n  WARNING: output may be TRUNCATED ({output_tokens}/{MAX_NEW_TOKENS} tokens)")


def main():
    print(f"\n{SEP}")
    print("  CodeT5 Fine-Tuned Model — Diagnostic Inference")
    print(f"  Model: {MODEL_DIR}")
    print(SEP)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nDevice: {device}")
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = T5ForConditionalGeneration.from_pretrained(str(MODEL_DIR))
    model.to(device)  # type: ignore[arg-type]
    model.eval()
    print(f"Model loaded in {time.time() - t0:.1f}s")

    with open(DATASET, encoding="utf-8") as f:
        records = json.load(f)
    print(f"Dataset: {len(records)} records")

    def split_record(rec):
        inp = rec["input"]
        old = inp.split("OLD METHOD:\n")[1].split("\nNEW METHOD:\n")[0].strip()
        new = inp.split("\nNEW METHOD:\n")[1].strip()
        gt = json.loads(rec["output"])
        return old, new, gt["old_method"]["categories"], gt["new_method"]["categories"]

    r = records[0]
    old, new, go, gn = split_record(r)
    report_case(f"Dataset {r['id']} (training sanity check)", old, new, model, tokenizer, device, go, gn)

    r = records[134]
    old, new, go, gn = split_record(r)
    report_case(f"Dataset {r['id']} (mid-dataset)", old, new, model, tokenizer, device, go, gn)

    r = records[-1]
    old, new, go, gn = split_record(r)
    report_case(f"Dataset {r['id']} (last record, near holdout)", old, new, model, tokenizer, device, go, gn)

    for case in CUSTOM_CASES:
        report_case(case["label"], case["old"], case["new"], model, tokenizer, device)

    print(f"\n{SEP}")
    print("  Diagnostic complete.")
    print(SEP)


if __name__ == "__main__":
    main()
