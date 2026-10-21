# Maintainability Triage — Final Three Evaluation Areas

**Evidence cut-off:** 21 October 2026. **Branch / latest confirmed commit:** `CodeCleanliness` / `f6f852a`.

This file states verified results, controlled diagnostics, and unestablished claims separately. It does **not** assert that missing external labels or ratings exist.

## 1. Grouping effectiveness

**Completed evidence.** A pilot on 5 Java source files produced 6 findings and 2 groups. Pairwise diagnostic sample: 15 finding pairs; system marked 7 as related and 8 as unrelated. The previously recorded AI-assisted pilot assessment on 14 assessed pairs produced TP=1, FP=5, TN=8, FN=0; diagnostic precision 1/6 = 0.1667, recall 1/1 = 1.0, F1 = 2/7 = 0.2857. One pair remained uncertain. These figures are **not independent ground-truth scores** and cannot be generalized. Automated consistency checks found no contradictory pair labels and no transitivity violation on the 15-pair sample. The live VS Code extension also demonstrated grouping.

**Status:** Working grouping mechanism verified; **independent grouping effectiveness (precision/recall/F1) not established**. Without independently justified relationship references, no valid independent grouping F1 can be computed.

## 2. Ranking effectiveness

**Completed evidence.** 11 dedicated ranking JUnit tests (7 existing plus 4 regression cases) passed as part of the **156/156 passing** Java Maven suite. Tests cover boundary exceedance, saturation, maximum group exceedance, distinct-concern and supported-evidence tie breakers, deterministic ordering, and invalid identifiers. The algorithm is **lexicographic**, not a calibrated weighted model: boundary exceedance, distinct concerns, affected files, supported findings, then stable ID. In the top-selected 40-group audit **all 40 exceedance scores were 1.0**. A filename/ID heuristic flagged 29/40 groups as *possibly* generated code; this is not source-verified. No independent priority reference rankings were provided. The live extension demonstrated output priorities.

**Status:** Algorithm implementation and its specified ordering rules verified; **real-world ranking effectiveness and correlation/NDCG against independent priorities not established**. The saturation and sample-selection biases must be disclosed.

## 3. Qwen explanation quality

**Completed evidence.** Fine-tuned Qwen2.5-Coder-7B-Instruct adapter was restored to Kaggle inference and demonstrated in the VS Code extension. Recorded controlled comparison: **three scenarios**, each answered once by base and fine-tuned models (six responses total). Base mean generation time **11.14 s**, mean response length **124 words**, three numeric references not present verbatim in supplied evidence; fine-tuned mean **12.86 s**, mean response length **115.33 words**, one response-only numerical reference. These are **screening flags, not established hallucinations**. The four subjective-quality rating columns remain empty, so no quality-score means, effect size, or significance test is justified. Tiny sample and weakly supervised training limit generalization.

**Status:** Inference and a descriptive base/LoRA comparison verified; **superiority in factual correctness, relevance, actionability, grounding, or general quality not established**.

## Other already completed evidence

- Java analyzer: **156 tests, 0 failed, 0 errors, 0 skipped**; automated end-to-end demo on 5 files: 5 parsed, 0 failed, 6 findings, 2 groups; live Qwen explanation observed.
- MLCQ comparison on 72 scored observations: Long Method, TP=8 FP=0 FN=9 TN=19, F1=0.64; Blob/God Class, TP=0 FP=0 FN=17 TN=19, F1=0 (precision undefined). Do not claim overall superiority over PMD.
- Larger Java benchmark on Apache Commons Lang copied files (flattened dependency structure, single runs): 100 files **19.387s**, 250 **26.094s**, 500 **613.553s**; all command exit codes 0 and saved JSON. For 500: 500 parsed, zero failed, 4,160 findings, 1,250 groups. Strong non-linear slowdown is an observed limitation; 1,000-file behavior untested.
- Evidence and screenshots pushed to GitHub in commit **`f6f852a`**.

## Research-level completion decision

**Finished and reproducibly documented:** software implementation; automated checks; demonstrated extension+LLM integration; recorded selected detection benchmark; grouping and ranking diagnostic analyses; descriptive LLM comparison; 100/250/500 source-file scalability runs; evidence archive and Git handoff.

**Not scientifically established:** independent grouping F1, independently validated real-world priority usefulness, fine-tuned model explanation-quality superiority, and behavior at 1,000 files. A report cannot legitimately label those established without independent reference evidence. They are declared limitations, **not invented negative results**.

**No additional algorithm changes or inference training are necessary merely to publish the honest observed findings.**
