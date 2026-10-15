"""
Module: explanation.py
Stage: LLM Explanation

Synthesizes technical findings across all pipeline stages into a clear, developer-facing
narrative. Leverages Groq Cloud LLM to produce deep semantic explanations,
reproducing scenarios where same-signature drift manifests as runtime bugs.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from groq import Groq

from src.method_parser import JavaMethod
from src.signature_checker import SignatureComparisonResult
from src.drift_engine import DriftReport
from src.impact_assessor import ImpactAssessment

load_dotenv()
logger = logging.getLogger(__name__)


class ExplanationReport(BaseModel):
    """Structured developer-oriented explanation of detected behavioral drift."""
    overview: str
    detailed_drift_breakdown: str
    failure_scenarios: List[str] = Field(
        default_factory=list,
        description="Specific edge cases or caller input scenarios where v1 and v2 diverge."
    )
    recommended_unit_tests: List[str] = Field(
        default_factory=list,
        description="Suggested JUnit test cases to catch the behavioral drift."
    )
    developer_guidance: str
    raw_llm_response: Optional[str] = None


class ExplanationGenerator:
    """
    Prompts Groq Cloud LLM to generate cohesive, actionable explanations of same-signature drift.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: int = 60,
        temperature: float = 0.2,
        client: Optional[Any] = None
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model_name = model_name or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", str(timeout_seconds)))
        self.temperature = float(os.getenv("TEMPERATURE", str(temperature)))
        self.client = client or (Groq(api_key=self.api_key) if self.api_key else None)

    def generate_explanation(
        self,
        v1: JavaMethod,
        v2: JavaMethod,
        sig_result: SignatureComparisonResult,
        drift_report: DriftReport,
        impact: ImpactAssessment
    ) -> ExplanationReport:
        """
        Queries Groq Cloud LLM to generate an in-depth explanatory narrative and JUnit test suggestions.
        """
        if not self.api_key:
            raise ConnectionError("GROQ_API_KEY is not configured.")

        prompt = self._build_explanation_prompt(v1, v2, sig_result, drift_report, impact)
        client = self.client or Groq(api_key=self.api_key)

        try:
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert senior Java architect and software governance researcher.\n"
                            "Analyze behavioral drift between two versions of a Java method with identical signatures.\n"
                            "You MUST return ONLY a valid JSON object matching the requested schema."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                timeout=self.timeout_seconds
            )
            raw_text = completion.choices[0].message.content or ""
            return self._parse_explanation_response(raw_text, drift_report, impact)
        except Exception as e:
            logger.error(f"Error querying Groq for explanation: {e}")
            raise ConnectionError(
                f"Failed to query Groq Cloud using model '{self.model_name}' for explanation: {e}"
            )

    def _build_explanation_prompt(
        self,
        v1: JavaMethod,
        v2: JavaMethod,
        sig_result: SignatureComparisonResult,
        drift_report: DriftReport,
        impact: ImpactAssessment
    ) -> str:
        """Creates the prompt guiding the LLM to explain the drift concisely and precisely."""
        flagged_areas = ", ".join(drift_report.flagged_drift_areas) or "None detected"

        return f"""Analyze this behavioral drift between two versions of a Java method with IDENTICAL method signatures:

METHOD SIGNATURE:
{v1.signature_str}

BASELINE VERSION (v1):
```java
{v1.raw_code}
```

MODIFIED VERSION (v2):
```java
{v2.raw_code}
```

DETECTED DRIFT METRICS:
- Drift Score: {drift_report.drift_score:.2f} (Severity: {drift_report.severity.value})
- Affected Dimensions: {flagged_areas}
- Risk Level: {impact.risk_level.value} (Blast Radius: {impact.blast_radius.value})
- Backward Compatibility Intact: {impact.backward_compatibility_intact}

TASK:
Provide a clear, technical explanation of the behavioral drift for code review.
You MUST output ONLY a valid JSON object matching this schema:
{{
  "overview": "Concise 2-sentence summary of the core behavioral change.",
  "detailed_drift_breakdown": "In-depth technical breakdown of logic changes and differences in side-effects or return values.",
  "failure_scenarios": [
    "Specific input example or edge case that will behave differently in v2 compared to v1"
  ],
  "recommended_unit_tests": [
    "Suggested JUnit test case description or snippet asserting the behavioral contract"
  ],
  "developer_guidance": "Clear advice for developers modifying or consuming this method."
}}
"""

    def _parse_explanation_response(
        self,
        raw_text: str,
        drift_report: DriftReport,
        impact: ImpactAssessment
    ) -> ExplanationReport:
        """Parses LLM JSON response or provides fallback structured content."""
        cleaned = raw_text.strip()

        # Handle markdown fences
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{") and candidate.endswith("}"):
                    cleaned = candidate
                    break

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start:end + 1]

        try:
            data = json.loads(cleaned)
            return ExplanationReport(
                overview=data.get("overview", drift_report.summary),
                detailed_drift_breakdown=data.get("detailed_drift_breakdown", ""),
                failure_scenarios=data.get("failure_scenarios", []),
                recommended_unit_tests=data.get("recommended_unit_tests", []),
                developer_guidance=data.get("developer_guidance", impact.executive_summary),
                raw_llm_response=raw_text
            )
        except json.JSONDecodeError:
            return ExplanationReport(
                overview=drift_report.summary,
                detailed_drift_breakdown=raw_text,
                failure_scenarios=[
                    "See detailed breakdown above for edge conditions where behavior diverged."
                ],
                recommended_unit_tests=[
                    "Implement regression tests verifying inputs across legacy boundary values."
                ],
                developer_guidance=impact.executive_summary,
                raw_llm_response=raw_text
            )
