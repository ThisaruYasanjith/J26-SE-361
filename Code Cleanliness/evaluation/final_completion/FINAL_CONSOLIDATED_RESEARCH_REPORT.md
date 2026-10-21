# Code Cleanliness & Maintainability — Final Consolidated Evidence Report

**Project:** J26-SE-361 — Automated Code Governance Tool for Deviation Detection in Software  
**Component:** Code Cleanliness & Maintainability — Maintainability Triage  
**Evidence cut-off:** 21 October 2026  
**Confirmed branch and evidence commit:** `CodeCleanliness`, `f6f852a`

## Scope and workflow

The Java analyzer performs repository-level scanning, parsing, symbol/relationship extraction, detection of twelve maintainability concerns, evidence-aware issue grouping, and lexicographic priority ordering. The VS Code extension displays grouped, ranked results and requests Qwen explanations through the inference service. These capabilities are implemented and observed; the strength of each empirical validation differs.

## 1. Implementation and end-to-end evidence

- Java Maven test suite: **156 passed; 0 failures; 0 errors; 0 skipped** (observed local output).
- Live VS Code demonstration: **5 Java files parsed, 0 parse failures, 6 findings, 2 issue groups**; source evidence, ranking and Qwen response displayed.
- Integration screenshots archived under `final_completion/integration_screenshots/VSCode_Integration_0.png` through `_5.png` in commit `f6f852a`.

## 2. Detection evaluation against MLCQ (selected sample)

The scored dataset includes **72 observations** (36 per concern), with eight additional originally selected items excluded from scoring. These are sample-specific results; they should not be represented as whole-dataset performance.

| Evaluated concern / system | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Long Method — analyzer | 8 | 0 | 9 | 19 | 1.00 | 0.4706 | 0.64 |
| Long Method — PMD proxy | 2 | 0 | 15 | 19 | 1.00 | 0.1176 | 0.2105 |
| Blob/God Class — analyzer | 0 | 0 | 17 | 19 | Undefined | 0.00 | 0.00 |
| Blob/God Class — PMD proxy | 9 | 0 | 8 | 19 | 1.00 | 0.5294 | 0.6923 |

**Interpretation:** The analyzer's Long Method sample recall is higher than this PMD proxy. Its Blob/God Class sample recall is substantially lower. Differences between MLCQ labels and detector operational definitions constrain interpretation. No general overall superiority claim is warranted.

## 3. Grouping effectiveness

- Controlled source pilot: **6 findings**, **2 groups**, **15 pairs**; analyzer classifies **7 related / 8 unrelated**.
- Structural consistency audit: **0 contradictory assignments, 0 transitivity violations** on this small complete pilot.
- AI-assisted preliminary assessment of 14 pairs (one uncertain): **TP 1, FP 5, TN 8, FN 0**, diagnostic precision **0.1667**, recall **1.0**, F1 **0.2857**.
- **Crucial validity boundary:** AI-assisted judgments are not independent human or independently substantiated reference labels. The diagnostic F1 must **not** be reported as validated grouping accuracy. The sample is far too small for representative effectiveness claims.

## 4. Priority ranking effectiveness

- **11 dedicated ranking JUnit tests** passed, incorporated in 156-test suite. Tests check expected algorithm behavior, including saturation, tie-breaking, maximum exceedance, ordering determinism, and unsupported evidence.
- Actual algorithm: lexicographic order of maximum normalized boundary exceedance, distinct concerns, affected source files, evidence-supported findings, then stable group ID. It has **no empirically calibrated weights**.
- In a top-selected 40-group audit: **40/40 primary exceedance scores = 1.0**, and **29/40** identifiers flagged *possibly generated* using a heuristic (not verified source attribution).
- No independent priority-reference labels; no defensible Spearman, NDCG, or ranking-effectiveness number. Saturation and selection bias are observed limitations.

## 5. Qwen base vs fine-tuned comparison

- Base model: `Qwen/Qwen2.5-Coder-7B-Instruct`; LoRA fine-tuned adapter available and successfully served in Kaggle; extension receives a live explanation.
- Three controlled cases with one response each from base and fine-tuned (**n=3 per model**).
- Base: mean generation time **11.14 s**, mean response length **124 words**, numeric evidence-screen flags **3**.
- Fine-tuned: mean generation time **12.86 s**, mean response length **115.33 words**, numeric evidence-screen flags **1**.
- Response-only numerals are **potential grounding-check targets, not confirmed hallucinations**. Four review-rating columns are unfilled. The sample does not justify LoRA superiority claims in correctness, relevance, actionability, grounding, or quality.

## 6. Scalability: recorded real Java source experiments

Apache Commons Lang source files were copied into flattened temporary source sets. Each size was measured once, with no statistical repetitions. Source layout/dependencies were not maintained unchanged; throughput in native repository context remains uncertain.

| Selected Java files | Elapsed seconds | Exit code |
|---:|---:|---:|
| 100 | 19.387 | 0 |
| 250 | 26.094 | 0 |
| 500 | 613.553 | 0 |

500-file run: **500 parsed**, **0 failed**, **4,160 findings**, **1,250 groups**. The large time increase at 500 files is an observed potential bottleneck; **linear scaling must not be claimed**, and 1,000 files were not tested. The batch method is documented as `single_run_copied_java_sources_flattened_dependency_structure`.

## 7. Completion and unverified claims

**Demonstrated:** repository-wide implementation and supported concern detection, issue grouping and deterministic ranking, end-to-end VS Code/Qwen inference, automated regression tests, sample-level detector comparison, and source-file scalability experiments up to 500 files. Evidence and integration screenshots were previously pushed to `CodeCleanliness` at `f6f852a`.

**Not established by the available evidence:** independent grouping precision/recall/F1; priority rank usefulness relative to external maintenance judgment; superiority of fine-tuned Qwen explanation quality; representative performance at 1,000 files. These are open scientific validity limits, and are not disguised as passing experiments.

## 8. Reproduction / evidence pointers

- Main evaluation notebook: `evaluation/notebooks/29f_reproducible_evaluation.ipynb`
- Grouping notebook: `evaluation/notebooks/29f_grouping_validation.ipynb`
- Ranking notebook: `evaluation/notebooks/29f_ranking_validation.ipynb`
- Qwen notebook: `evaluation/notebooks/29f_llm_quality_validation.ipynb`
- Detailed recorded results: `evaluation/results/final_evaluation/`
- Reconciliation audit: `evaluation/results/final_evaluation/closure/FINAL_EVALUATION_RECONCILIATION.md`
- Benchmark logs: `evaluation/final_completion/benchmark_results/benchmark_measurements.csv`, `console_100.txt`, `console_250.txt`, `console_500.txt`
- Live extension screenshots: `evaluation/final_completion/integration_screenshots/`

**Conclusion:** Implementation and documented evidence handoff are complete within the verified scope. Full independent research effectiveness validation is not established and must remain an explicit limitation.
