# Maintainability Triage - Final Evaluation Evidence

## Reproduction

The MLCQ benchmark is implemented in:
- Code Cleanliness/evaluation/prepare_mlcq_source_batch.py
- Code Cleanliness/evaluation/run_29f_mlcq_batch.py

The Java analysis is executed by MaintainabilityTriageCli.

PMD version 7.14.0 was run using:
- Code Cleanliness/evaluation/results/29f_baselines/pmd-benchmark-pom.xml

The PMD sample-matching comparison was calculated using
the existing MLCQ predictions and PMD XML violations.

## Detection evaluation

Long Method (36 scored):
TP=8, FP=0, FN=9, TN=19, F1=0.640

Blob/God Class (36 scored):
TP=0, FP=0, FN=17, TN=19, F1=0.000
Precision is undefined because there were no predicted positives.

## Limitations

These are preliminary benchmark results, not final calibrated accuracy.
One of the 72 Java source files failed analyzer parsing.
MLCQ annotation and AST element boundaries may not coincide exactly.
Blob and GOD_CLASS are not necessarily identical definitions.
The selected sample is balanced/purposive, not population representative.
PMD NcssCount is only a partial Long Method proxy.
The PMD comparison requires an additional source-coverage and
matching audit before making comparative superiority claims.
Generated Java parser sources can influence observed results.
No measurements have been fabricated or adjusted.
