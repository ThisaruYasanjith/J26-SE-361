# 29F — Research Evaluation Completion Report

Generated: 2026-10-20 20:43

## 1. Implementation
Repository-wide Java AST-based maintainability triage,
issue grouping, priority ranking and Qwen-assisted explanations
are implemented and integrated with VS Code.

Previous Java automated testing: 152 tests passed.

## 2. External detection and baseline evaluation
MLCQ reference comparison and PMD baseline experiments have
already been preserved in the main evaluation notebook.

These concern-specific results must not be combined into
an unsupported overall detector score.

## 3. Scalability
Existing measured evaluations cover 5, 10, 20 and 40 files.
Single-run measurements are preliminary evidence, not
a comprehensive scalability guarantee for 1000 files.

## 4. Grouping
- Five Java files parsed successfully.
- Six findings and two reported issue groups.
- Fifteen candidate finding pairs.
- Fourteen AI-assisted judgments and one uncertain judgment.
- Preliminary AI-assisted agreement:
  Precision 0.1667, Recall 1.0000, F1 0.2857.
- This is not independently validated accuracy.
- Observed concern: potential over-grouping.

## 5. Priority ranking
- Candidate review cases: 40
- Independent human ranking agreement not established.
- Descriptive evidence saved separately.

## 6. Qwen explanations
- Preserved base-versus-LoRA comparison records: 6
- Response and generation-time evidence preserved.
- Human-rated correctness, relevance and actionability
  are not independently established.
- Fine-tuned superiority must not be assumed.

## 7. Research status
The implementation and reproducible preliminary experiments
are completed. Broad, independent research validation
remains incomplete, particularly for grouping, priority
ranking and generated explanation quality.
