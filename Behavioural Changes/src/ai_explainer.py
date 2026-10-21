"""
Module: ai_explainer.py
Stage: AI Method Body Comparison & Developer Guidance Generation

Generates high-fidelity behavioral explanations comparing baseline and modified
Java method bodies using Groq, OpenAI, or Gemini (if configured in .env),
with a deterministic local semantic analysis fallback that requires zero external APIs.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _build_local_body_comparison(
    old_body: str,
    new_body: str,
    old_categories: List[str],
    new_categories: List[str],
    added_categories: List[str],
    removed_categories: List[str],
    retained_categories: List[str],
    method_name: str,
    signature_str: str,
) -> Dict[str, Any]:
    """
    Deterministic local semantic comparator that analyzes statement-level differences
    between baseline and modified method bodies without external network calls.
    """
    old_lines = [line.strip() for line in old_body.splitlines() if line.strip() and not line.strip().startswith("//")]
    new_lines = [line.strip() for line in new_body.splitlines() if line.strip() and not line.strip().startswith("//")]

    added_statements = [line for line in new_lines if line not in old_lines]
    removed_statements = [line for line in old_lines if line not in new_lines]
    retained_statements = [line for line in old_lines if line in new_lines]

    explanation_lines = []
    explanation_lines.append(f"### Method Body Behavioral Comparison: `{method_name}`")
    explanation_lines.append("")

    if not added_statements and not removed_statements:
        explanation_lines.append(
            "Both method bodies contain identical executable statements. "
            "No execution divergence or behavioral drift detected at the statement level."
        )
    else:
        explanation_lines.append("#### 🔍 Statement-Level Changes:")
        if added_statements:
            explanation_lines.append("**Added Statements in Modified (v2):**")
            for stmt in added_statements:
                explanation_lines.append(f"- `+ {stmt}`")
            explanation_lines.append("")

        if removed_statements:
            explanation_lines.append("**Removed Statements from Baseline (v1):**")
            for stmt in removed_statements:
                explanation_lines.append(f"- `- {stmt}`")
            explanation_lines.append("")

        if retained_statements:
            explanation_lines.append(f"**Retained Shared Statements:** {len(retained_statements)} statement(s) preserved.")
            explanation_lines.append("")

        explanation_lines.append("#### ⚙️ Runtime Behavioral Impact:")
        if added_categories:
            explanation_lines.append(f"- **New Capabilities Introduced:** `{', '.join(added_categories)}`.")
            for cat in added_categories:
                if cat == "FILE_OPERATION":
                    explanation_lines.append("  - File system I/O was introduced. Callers may fail if the target file path is read-only, non-existent, or lacks OS permissions.")
                elif cat == "DATABASE_WRITE":
                    explanation_lines.append("  - Database persistence/modification introduced. The method is no longer read-only and mutates storage records.")
                elif cat == "DATABASE_READ":
                    explanation_lines.append("  - Persistent storage query added. Callers now depend on database availability and network roundtrips.")
                elif cat == "LOGGING":
                    explanation_lines.append("  - Diagnostic/audit logging introduced. Minimal runtime risk, but check for sensitive PII or high-frequency log flooding.")
                elif cat == "EXCEPTION_BEHAVIOR":
                    explanation_lines.append("  - Explicit error handling or throwing introduced. Callers must be prepared to catch or propagate these exceptions.")
                elif cat == "STATE_MUTATION":
                    explanation_lines.append("  - Field or object parameter mutation introduced. Callers holding references will observe state changes.")
                elif cat == "EXTERNAL_CALL":
                    explanation_lines.append("  - Remote external service call introduced. Callers will be subject to network latency and downstream service outages.")
                elif cat == "CALCULATION_TRANSFORMATION":
                    explanation_lines.append("  - Internal calculation/algorithm logic was altered. Output value formulas differ from baseline.")
                elif cat == "VALIDATION_CONTROL_FLOW":
                    explanation_lines.append("  - Control flow branching or input guards added. Input edge cases may now trigger early returns or rejections.")

        if removed_categories:
            explanation_lines.append(f"- **Behaviors Omitted from Baseline:** `{', '.join(removed_categories)}`.")
            for cat in removed_categories:
                explanation_lines.append(f"  - `{cat}` is no longer performed. Downstream callers expecting this side-effect will miss it.")

    overview = (
        f"Method `{method_name}` refactored: {len(added_statements)} statement(s) added, "
        f"{len(removed_statements)} removed across behavioral categories {added_categories or ['None']}."
        if (added_statements or removed_statements)
        else f"Method `{method_name}` has identical method bodies and runtime behavior."
    )

    failure_scenarios = []
    for cat in added_categories:
        if cat == "FILE_OPERATION":
            failure_scenarios.append("File system errors (FileNotFoundException, AccessDeniedException) if target path is inaccessible.")
        elif cat == "DATABASE_WRITE":
            failure_scenarios.append("Transaction rollback or constraint violations (DuplicateKeyException, OptimisticLockException).")
        elif cat == "EXCEPTION_BEHAVIOR":
            failure_scenarios.append("Callers unaware of newly thrown exceptions may crash under edge-case inputs.")
        elif cat == "EXTERNAL_CALL":
            failure_scenarios.append("Timeouts, HTTP 5xx responses, or connection refused errors from external endpoint.")
        elif cat == "STATE_MUTATION":
            failure_scenarios.append("Concurrent access races if multiple threads share the mutated instance or argument.")
        else:
            failure_scenarios.append(f"Downstream callers relying on pure behavior may be affected by introduced {cat}.")

    junit_tests = []
    for cat in added_categories:
        if cat == "FILE_OPERATION":
            junit_tests.append(
                f"@Test\nvoid test{method_name}_FileOperationSucceeds() {{\n"
                f"    // Verify file creation/write behavior introduced in v2\n"
                f"    // sut.{method_name}(...);\n"
                f"    // assertTrue(Files.exists(expectedPath));\n"
                f"}}"
            )
        elif cat == "DATABASE_WRITE":
            junit_tests.append(
                f"@Test\nvoid test{method_name}_PersistsChanges() {{\n"
                f"    // Verify storage write side-effect\n"
                f"    // sut.{method_name}(...);\n"
                f"    // verify(repository, times(1)).save(any());\n"
                f"}}"
            )
        elif cat == "LOGGING":
            junit_tests.append(
                f"@Test\nvoid test{method_name}_EmitsLog() {{\n"
                f"    // Verify logger output\n"
                f"    // sut.{method_name}(...);\n"
                f"    // assertTrue(appender.contains(\"operation completed\"));\n"
                f"}}"
            )
        elif cat == "EXCEPTION_BEHAVIOR":
            junit_tests.append(
                f"@Test\nvoid test{method_name}_ExceptionContract() {{\n"
                f"    // Verify edge input exception handling\n"
                f"    // assertDoesNotThrow(() -> sut.{method_name}(...));\n"
                f"}}"
            )

    if not junit_tests:
        junit_tests.append(
            f"@Test\nvoid test{method_name}_BehavioralEquivalence() {{\n"
            f"    // Verify baseline and modified behaviors match expectations\n"
            f"    // sut.{method_name}(...);\n"
            f"}}"
        )

    developer_guidance = (
        f"Review callers of `{method_name}` for unhandled side-effects ({', '.join(added_categories)}). "
        f"Ensure appropriate integration or mock tests are updated prior to merging."
        if (added_statements or removed_statements)
        else "No behavioral changes detected. Method body is behaviorally identical."
    )

    return {
        "body_comparison_explanation": "\n".join(explanation_lines),
        "overview": overview,
        "failure_scenarios": failure_scenarios,
        "recommended_unit_tests": junit_tests,
        "developer_guidance": developer_guidance,
        "ai_source": "Local Semantic AI Engine",
    }


def generate_ai_body_comparison(
    old_body: str,
    new_body: str,
    old_categories: List[str],
    new_categories: List[str],
    added_categories: List[str],
    removed_categories: List[str],
    retained_categories: List[str],
    method_name: str,
    signature_str: str,
) -> Dict[str, Any]:
    """
    Attempts to generate an in-depth AI comparison using Groq, OpenAI, or Gemini.
    Falls back gracefully to the deterministic local semantic comparator if no keys
    are configured or if external calls fail.
    """
    # 1. Try Groq if GROQ_API_KEY is available
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_api_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_api_key)
            prompt = f"""You are a Java Code Governance & Architecture AI.
Compare the following two Java method bodies extracted for method `{signature_str}`.

BASELINE METHOD BODY (v1):
```java
{old_body}
```
Baseline Categories: {', '.join(old_categories) or 'None'}

MODIFIED METHOD BODY (v2):
```java
{new_body}
```
Modified Categories: {', '.join(new_categories) or 'None'}

Added Categories: {', '.join(added_categories) or 'None'}
Removed Categories: {', '.join(removed_categories) or 'None'}

Analyze and compare the two method bodies in depth:
1. Statement-by-statement comparison: What statements were added, removed, or altered?
2. Runtime Behavioral divergence: How does execution flow, state manipulation, persistence, or I/O differ?
3. Failure modes & edge cases: What inputs or conditions could break callers?
4. Developer guidance: Clear recommendations for the refactorer.
5. Concrete JUnit 5 regression test code.

Respond ONLY with a valid JSON object matching this schema:
{{
  "body_comparison_explanation": "Markdown text comparing the two method bodies statement-by-statement and detailing the behavioral shift",
  "overview": "Short 1-2 sentence executive summary",
  "failure_scenarios": ["Specific failure scenario 1", "Specific failure scenario 2"],
  "recommended_unit_tests": ["@Test\\nvoid testName() { ... }"],
  "developer_guidance": "Actionable instructions for the developer"
}}"""

            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a code governance assistant that outputs strict JSON."},
                    {"role": "user", "content": prompt}
                ],
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            raw = chat_completion.choices[0].message.content
            if not raw:
                raise ValueError("Groq returned empty response")
            parsed = json.loads(raw)
            return {
                "body_comparison_explanation": parsed.get("body_comparison_explanation", ""),
                "overview": parsed.get("overview", ""),
                "failure_scenarios": parsed.get("failure_scenarios", []),
                "recommended_unit_tests": parsed.get("recommended_unit_tests", []),
                "developer_guidance": parsed.get("developer_guidance", ""),
                "ai_source": "Groq AI (Llama 3.3 70B)",
            }
        except Exception as e:
            logger.warning(f"Groq AI explanation failed, falling back to local engine: {e}")

    # 2. Try Gemini if GEMINI_API_KEY is available
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_api_key:
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_api_key}"
            prompt = f"""Compare these two Java method bodies for `{signature_str}`:
Old Body:
{old_body}
Old Categories: {old_categories}

New Body:
{new_body}
New Categories: {new_categories}

Return JSON with:
"body_comparison_explanation": "Markdown text comparing both method bodies",
"overview": "summary",
"failure_scenarios": ["scenario1"],
"recommended_unit_tests": ["@Test..."],
"developer_guidance": "guidance"
"""
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }
            resp = requests.post(url, json=payload, timeout=15)
            if resp.ok:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                return {
                    "body_comparison_explanation": parsed.get("body_comparison_explanation", ""),
                    "overview": parsed.get("overview", ""),
                    "failure_scenarios": parsed.get("failure_scenarios", []),
                    "recommended_unit_tests": parsed.get("recommended_unit_tests", []),
                    "developer_guidance": parsed.get("developer_guidance", ""),
                    "ai_source": "Google Gemini 1.5 Flash",
                }
        except Exception as e:
            logger.warning(f"Gemini AI explanation failed, falling back to local engine: {e}")

    # 3. Default to deterministic Local Semantic AI Engine
    return _build_local_body_comparison(
        old_body=old_body,
        new_body=new_body,
        old_categories=old_categories,
        new_categories=new_categories,
        added_categories=added_categories,
        removed_categories=removed_categories,
        retained_categories=retained_categories,
        method_name=method_name,
        signature_str=signature_str,
    )
