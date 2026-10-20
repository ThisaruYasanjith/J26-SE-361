Set-Location "C:\4th Year\Research Work\Implementation Stage\J26-SE-361"
$rel = "Code Cleanliness/evaluation/results/final_evaluation/closure"
$required = @("$rel/FINAL_EVALUATION_RECONCILIATION.md", "$rel/FINAL_RESEARCH_EVIDENCE_SUMMARY.md", "$rel/measured_mlcq_confusion_metrics.csv")
foreach ($item in $required) { if (-not (Test-Path $item)) { throw "Missing evidence: $item" } }
git add -- "Code Cleanliness/evaluation/29f_finalize_existing_evidence.py"
git add -f -- "$rel"
git -c core.pager=cat diff --cached --stat
git commit -m "eval(cleanliness): consolidate measured research evidence and closure outputs"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed" }
git push origin CodeCleanliness
if ($LASTEXITCODE -ne 0) { throw "Git push failed" }
git status --short
