# LLM4Refactoring Suitability Labeling Protocol

## 1. Purpose

This protocol establishes reproducible criteria for reviewing LLM4Refactoring examples for the Code Cleanliness & Maintainability component of J26-SE-361.

The intended LLM task is to generate evidence-grounded maintainability explanations and refactoring guidance using verified code-analysis findings and relevant source-code context.

The original dataset is retained unchanged.

## 2. Data Sources

- LLM4Refactoring: Java before/after refactoring examples and associated metadata.
- Java Maintainability Analyzer: measured metrics, detected concerns and supporting evidence.
- Why We Refactor?: supplementary developer motivation evidence, when relevant and available.
- MLCQ: separate code-smell calibration and evaluation resource, not automatic explanation labels.

## 3. Review Criteria

Each example must be evaluated for:

1. **Source validity:** Before/after code is accessible, nonempty and sufficiently parseable for the intended analysis.
2. **Transformation validity:** The stated refactoring is supported by comparison of the code versions and source metadata.
3. **Maintainability relevance:** One or more of the 12 proposal-defined concerns is supported by concrete evidence, rather than inferred solely from the refactoring type.
4. **Context adequacy:** Available code and repository relationships are sufficient to support the claimed explanation. Missing dependencies or unknown behavior must be recorded.
5. **Explanation support:** Recommendations must be consistent with observed changes and available evidence; unsupported motivations must not be presented as verified developer intent.
6. **Independence:** Related examples, duplicate code and examples originating from the same repository must be handled appropriately to avoid training, validation and test leakage.

## 4. Review Decisions

- **INCLUDE:** All necessary conditions for the intended training or evaluation record are supported by reviewed evidence.
- **EXCLUDE:** A documented condition makes the example unsuitable for the intended task.
- **NEEDS_CONTEXT:** The example cannot be assessed adequately without additional project context or evidence.
- **NEEDS_REVIEW:** The example has not yet received a complete, justified review.

A quality flag does not automatically require exclusion.

## 5. Concern Labeling Rules

Only proposal-defined concern identifiers may be assigned.

A recorded refactoring operation is not equivalent to a confirmed maintainability concern. For example, Extract Method alone does not establish Long Method, and Extract Class alone does not establish SRP risk.

Every verified concern must have an associated evidence reference. If the evidence is incomplete, the concern remains unverified.

## 6. Labeling and Verification Process

For each example:

1. Inspect its existing quality flags and duplicate relationships.
2. Compare the before and after code and the stated refactoring.
3. Inspect relevant analyzer measurements and detected findings.
4. Review any necessary repository context or available motivation evidence.
5. Record the review decision, reason, verified concerns, evidence reference, context availability and reviewer.
6. Recheck unclear or disputed decisions before accepting the example into an explanation dataset.

Automated data checks and human-reviewed labels must remain distinguishable.

## 7. Training Data Construction

Only suitable, reviewed examples may be considered for evidence-grounded explanation records.

Inputs should include relevant source context and verified maintainability evidence. Targets should explain the supported issue, its implications and an appropriate improvement grounded in the available refactoring evidence.

Refactoring code alone must not be treated as a verified explanation label.

## 8. Dataset Splitting and Evaluation

Training, validation and test sets should be separated by source project where feasible.

Exact or related code examples must not cross partitions. Dataset size, class distribution, project coverage and limitations must be reported.

The effectiveness of LLM adaptation must be evaluated against an appropriate baseline using held-out examples. The existence of 180 source examples does not guarantee adequate final training data.

## 9. Research Integrity

- Preserve the original dataset and source metadata.
- Do not fabricate developer motivations, maintainability concerns or explanations.
- Keep inclusion and exclusion reasons auditable.
- Report uncertainty and missing context.
- Document dataset limitations and potential label bias.
- Verify data licensing and redistribution obligations before publishing derived artifacts.
