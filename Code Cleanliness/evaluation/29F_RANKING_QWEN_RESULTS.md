# 29F — Ranking and Qwen Experimental Evidence

## Ranking dataset
- Candidate groups: 40
- Suspected generated-code groups: 29
- Independent reference ranks available: 0
- Generated-code detection is filename/identifier heuristic only.
- Spearman, NDCG and Top-k agreement cannot be established without
  independent reference judgments.
- Existing 40-case ranking sample requires representative source review.

## Qwen controlled comparison
- Recorded responses: 6
- Distinct cases: 3
- Models: base, fine_tuned
- Per-case generation-time and response-length comparisons saved.
- All response times come from previously recorded measurements.
- Response length does not measure explanation quality.
- Human correctness, relevance, actionability and grounding ratings
  remain unfilled, so quality superiority is not established.

## Evaluation conclusion
Computational descriptive comparisons are complete on preserved
evidence. Independent ranking accuracy and Qwen explanation-quality
validation remain outstanding.
