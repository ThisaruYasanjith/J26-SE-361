Milestone 29F — Method-level boundary agreement benchmark

Place both files in: Code Cleanliness/evaluation/
  build_29f_method_benchmark.py
  MethodBoundaryReference.java

Run from repository root (PowerShell):
  python "Code Cleanliness/evaluation/build_29f_method_benchmark.py" "$PWD"

Prerequisites: JDK with javac, Maven dependencies already resolved (JavaParser core 3.27.1), matplotlib (optional).

Inputs: Analyzer main Java source + analyzer/evaluation/reports/analyzer-self-analysis-2026-10-18.json
Outputs: evaluation/results/29f_method_boundary_benchmark/
  all_method_reference_metrics.csv
  all_method_predictions.csv
  boundary_results.json
  long_method_confusion.png and high_complexity_confusion.png (if matplotlib available)

IMPORTANT: This is a SAME-CONVENTION JavaParser AST reference reimplementation.
It measures boundary-rule agreement for all Java methods, including non-detections.
It is NOT independent manual code smell ground truth. Matching the algorithm does
not prove threshold calibration or maintainability-smell precision/recall/F1.
For rigorous maintainability-smell metrics, human-labeled or external benchmark
positive AND negative examples are still required.

If 57 Java files parsed in historical report but source changed after Oct 18,
expect some differences. Do not hide them; re-run analyzer on same snapshot.
