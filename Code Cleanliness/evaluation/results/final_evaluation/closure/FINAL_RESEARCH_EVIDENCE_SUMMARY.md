# Maintainability Triage — final evidence consolidation

## Scope and provenance
This report is a **secondary reconciliation** of user-provided exported evaluation data (`per_sample_predictions.csv`) and previously observed execution logs. It is not a new analyzer run, new PMD execution, independent human review, or full validation of proposal targets.

## Verified Java testing
- Full Maven test suite: **156 tests, 0 failures, 0 errors, 0 skipped; BUILD SUCCESS** (observed user terminal output, 2026-10-21).
- Revision `6629a09` pushed to remote branch `CodeCleanliness`; working tree clean at time of that output.
- The four newer regression cases explicitly test saturation, secondary tie-breaking, supported-finding tie-breaking, and max-exceedance behavior. Passing means conformity to the specified ranking rules, **not priority validity**.

## Detection experiment — independently sourced MLCQ review labels, sampled
Source: `per_sample_predictions.csv` supplied in the conversation; score only `evaluation_status == SCORED`. Comparison is label-alignment on a small selected sample, not comprehensive generalization. The original labels are sourced from reviewer votes; their relationship to each tool's detection definition is imperfect.

| Concern | Scored / excluded | TP | FP | FN | TN | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|---|---|---|---|---|
| long method | 36 / 4 | 8 | 0 | 9 | 19 | 1.000 | 0.471 | 0.640 | 0.750 |
| blob | 36 / 4 | 0 | 0 | 17 | 19 | undefined | 0.000 | 0.000 | 0.528 |

- **Important:** Blob/God-Class yields no positive predictions in this scored sample, so its positive-class precision is **undefined**, not 100%. Recall and F1 are zero.
- PMD comparisons from previous notebook runs must be kept **concern-specific**, with original scripts and outputs; this pack does not recompute PMD or assert superiority.

## Grouping and ranking outcomes
- Evidence-backed five-file grouping pilot: 15 candidate pairs, seven predicted same group and eight predicted different; no independent annotations. Zero contradictions/transitivity violations are *consistency*, not precision/recall/F1.
- Provisional AI-assisted assessment reported 1 TP, 5 FP, 0 FN, 8 TN on 14 assessed pairs. This **must never be labeled independent expert validation**.
- Ranking selected top 40 groups: **all 40 exceedance scores = 1.0**; **29/40** groups matched an identifier-based possible-generated-code heuristic; independent priority labels **0/40**. Therefore Spearman, NDCG, and rank-accuracy cannot be computed validly.
- Source Java ranker is **deterministic lexicographic**: highest clamped boundary exceedance; distinct concerns; affected files; supported findings; group ID. It does **not** implement empirically calibrated weighting or direct maintenance-effort prediction.

## Qwen LoRA comparison (descriptive, three controlled cases)
- Base: 3 outputs; mean time **11.14 s**; mean response **124 words**; 3 response-only numeric references.
- Fine-tuned adapter: 3 outputs; mean time **12.86 s**; mean response **115.33 words**; 1 response-only numeric reference.
- Numeric-reference counts are *screening flags*, not verified hallucinations; 0/6 rated quality rows. No conclusion of fine-tuned model superiority is supported by this comparison.
- Kaggle T4 adapter/inference server was restored per user confirmation, but an end-to-end VS Code client request has **not** been captured in the supplied current logs.

## Scalability evidence (single runs, preliminary)
| Files | Measured seconds | Peak RSS MB |
|---|---:|---:|
| 5 | 0.802 | 82.25 |
| 10 | 1.076 | 92.26 |
| 20 | 1.819 | 197.18 |
| 40 | 3.523 | 278.41 |

These are one-off observed benchmarks, not extrapolations to 100–1,000 files; hardware, warm-up, GC, and sample composition limit generalization.

## Proposal requirements and honest completion boundary
- Implemented and Java-test-verified: repository-oriented parsing/analysis, 12 concern detectors, grouping/ranking, evidence exports; VS Code integration and Qwen demonstration have earlier positive evidence.
- Partial empirical validity: detection evaluated for 2 categories on a small sampled MLCQ subset; PMD comparisons concern-specific; initial scale tests up to 40 files.
- **Not scientifically established:** independent grouping effectiveness on representative repositories; priority utility against external maintenance decisions; general Qwen explanation-quality improvement; empirically calibrated thresholds; broad baseline coverage including SonarQube and Checkstyle; 100–1,000 file performance.
- The approved proposal calls for those evaluations. Do not recast incomplete objectives as completed. Actual results and limitations are stronger evidence than invented reviewers or inflated scores.

## Handoff procedure
1. Retain existing `results/final_evaluation/closure/` outputs created by `29f_finalize_existing_evidence.py`. Copy the **new** `measured_mlcq_confusion_metrics.csv` and this report to the same closure folder.
2. Run one end-to-end extension analysis with Kaggle server running and capture the request response, ranked-group UI, and explanation if successful (avoid exposing the token).
3. Execute `mvn -B test` only if source changed since commit `6629a09`; otherwise use verified 156-test log.
4. Commit documentation and measured results with provenance. Do not claim unrun extension checks passed.
