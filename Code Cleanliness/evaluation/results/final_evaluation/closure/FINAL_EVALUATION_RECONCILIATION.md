# Final Evaluation Evidence Reconciliation

Generated: 2026-10-20T20:32:37.166185+00:00

## Scope and interpretation
This report is computed exclusively from locally stored CSV inputs. It does not create human judgments, independent labels, external ground truth, or new model inference. The tested implementation may be complete even where empirical quality remains uncertain.

## Available computed observations

- Ranking: 40 selected rows; 40/40 valid score values saturated at 1.0. Identifier-only generated-code heuristic flagged 29 rows (not source verified). The independent priority-rank column has 0 numeric labels. No ranking relevance correlation, NDCG or validated ranking accuracy is claimed.
- Grouping: 15 candidate pairs, including 7 system-positive and 8 system-negative assignments. Independent-label fields found: none identified. Structural consistency is not precision, recall, or F1.
- Qwen: base: n=3, mean latency=11.14s, mean response length=124.00 words, response-only numeric references=3; fine_tuned: n=3, mean latency=12.86s, mean response length=115.33 words, response-only numeric references=1. Quality ratings filled in 0/6 rows. Numeric-only screening flags are not hallucination verdicts. Timing and response length cannot establish model quality or LoRA superiority.

## Completion boundaries
- **Detection comparison:** use the existing PMD/MLCQ experiment as reported; this script does not recalculate its sample-level ground truth.
- **Grouping:** pair predictions and transitivity checks alone do not establish grouping accuracy.
- **Ranking:** selected top-ranked groups and source-unverified generated-code flags cannot establish priority utility or unbiased retrieval performance.
- **LLM:** a six-output controlled demonstration cannot establish statistically representative generalization or quality superiority.
- **Scalability:** previously recorded 5/10/20/40-file timings are preliminary and do not establish performance at 100–1,000 files.
- **External human reviews:** not performed. No review scores are imputed.

## Evidence files
- `completion_evidence_inventory.csv`: source/status inventory.
- `ranking_row_audit.csv`: per-group score and possible-generated heuristic (when available).
- `qwen_response_grounding_screen.csv`: per-output numeric-reference checks (when available).

## Status
This closes the descriptive evidence-reconciliation step, NOT every scientific evaluation requirement. Remaining effectiveness gaps require independent, credible benchmarks or explicitly bounded claims.
