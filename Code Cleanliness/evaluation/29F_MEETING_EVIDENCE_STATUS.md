# 29F — Final Research Evaluation Status
Generated from preserved evidence on 2026-10-20.

## Component
Code Cleanliness & Maintainability — Maintainability Triage.

## Verified implementation evidence
- Repository-wide Java maintainability analysis implemented.
- VS Code integration demonstrated successfully.
- Java analyzer automated tests: 152 passed (previously verified).
- Five-file grouping pilot: five parsed, zero failures,
  six maintainability findings and two related issue groups.
- Detection comparison completed on a selected MLCQ sample,
  with PMD baseline evidence retained.
- Scalability measurements collected at 5, 10, 20 and 40 files.
- Qwen base-model and LoRA explanation outputs retained.

## Grouping pilot
- 15 finding pairs generated from non-generated Java test sources.
- 7 pairs assigned the same group and 8 different groups.
- 14 pairs provisionally assessed using AI-assisted review.
- Preliminary agreement: precision 0.1667, recall 1.0000,
  F1 0.2857, with one uncertain pair.
- These are NOT independently validated accuracy metrics.
- Main risk observed: potentially excessive grouping of
  conceptually distinct maintainability issues.

## Ranking validation
- Existing review records: 40.
- Independent ranking metrics are pending validated human judgments.
- Review columns: group_id, analyzer_rank, exceedance_score, concerns, affected_files, findings, independent_priority_rank

## LLM explanation-quality validation
- Existing comparison records: 6.
- Base and LoRA outputs are retained as controlled examples.
- No claim of generalizable improvement without blinded review.
- Review columns: case_id, case_type, model, concern, evidence, response, generation_seconds, correctness_1_to_5, relevance_1_to_5, actionability_1_to_5, grounding_1_to_5, unsupported_claims_count

## Interpretation and limitations
- Detection concern-specific scores must not be presented as
  a single overall detector score.
- Selected MLCQ examples and approximate location matching
  limit external validity.
- Grouping agreement is preliminary and AI-assisted.
- Ranking human agreement and LLM human quality scores
  must not be fabricated.
- Further independent evaluation is required before claiming
  mature research validation.

## Meeting conclusion
An integrated maintainability-triage prototype is operational,
with reproducible detection and scalability experiments,
Qwen explanation evidence, and a documented grouping pilot.
The initial grouping assessment also identifies actionable
limitations for refinement and larger independent validation.
