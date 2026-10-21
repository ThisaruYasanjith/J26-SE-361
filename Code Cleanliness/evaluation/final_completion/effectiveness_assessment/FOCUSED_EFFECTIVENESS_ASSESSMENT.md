# Maintainability Triage — Focused Effectiveness Assessment

**Source:** Three uploaded experimental CSV files. **Assessment provenance:** AI-assisted documentary assessment, not independent human or blinded expert adjudication. No unobserved scoring was imputed.

## 1. Grouping

The 15 supplied pairs contain source path, Java symbol, concern and contextual excerpts, but **0/15 independent gold labels**. The previous analyzer pilot reported seven same-group pairs and eight different-group pairs, but this *blind* file does not include the prediction column. Therefore independent precision, recall and F1 **cannot be computed** from these inputs. The companion assessment comments identify what source evidence would matter, without converting speculation into ground truth. Grouping source context is not equivalent to independently verified same-defect membership.

## 2. Ranking

All 40 selected groups have exceedance_score=1.0, **0/40 independently assigned reference ranks**, 29/40 possible generated-code identifiers and a constant affected-file count of 1. The top-of-ranking selection and saturated exceedance prevent an unbiased correlation or NDCG evaluation. The implemented lexicographic ranking logic has dedicated JUnit evidence; that establishes rule consistency, **not independently established maintenance priority utility**. Real-world priority accuracy remains unresolved.

## 3. Qwen (three controlled cases, six stored responses)

No quality ratings were entered in the six-row CSV. Actual recorded mean generation times: base **11.14s**, fine-tuned **12.86s**. These six cases do not support superiority claims.

Qualitative source-supported observations: (i) CASE_03 base response invents a “2000 lines” characterization absent from supplied evidence; (ii) CASE_03 fine-tuned explicitly notes missing metrics but infers a *likely* SRP issue; (iii) CASE_02 fine-tuned correctly warns behavioral equivalence is not established; (iv) CASE_02 base mentions possible security vulnerabilities without a specific security finding; (v) CASE_01 fine-tuned repeats the measured complexity 14 and acknowledges uncertainty. See complete response excerpts and notes in `qwen_evidence_based_qualitative_review.csv`. These are **AI-assisted textual observations**, not blinded ratings, generalization estimates, or reference-human scoring.

## Conclusion and honest project claim

The three implementation pathways have already been demonstrated and regression tested. The available inputs **do not close their independent effectiveness-validation gaps**. Claiming independently measured grouping F1, rank accuracy or robust Qwen quality advantage would be unsupported. These limitations are suitable to disclose explicitly in a research handoff; further independent reference evidence would be required to remove them.
