"""
Module: explanation.py
Stage: LLM Explanation

Synthesizes technical findings across all pipeline stages into a clear, developer-facing
narrative. Leverages the Ollama code LLM to produce deep semantic explanations,
reproducing scenarios where same-signature drift manifests as runtime bugs.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
import requests
from pydantic import BaseModel, Field
from dotenv import load_dotenv

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
    Prompts Ollama to generate cohesive, actionable explanations of same-signature drift.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: int = 120,
        temperature: float = 0.2
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "codellama:7b")
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", str(timeout_seconds)))
        self.temperature = float(os.getenv("TEMPERATURE", str(temperature)))

    def generate_explanation(
        self,
        v1: JavaMethod,
        v2: JavaMethod,
        sig_result: SignatureComparisonResult,
        drift_report: DriftReport,
        impact: ImpactAssessment
    ) -> ExplanationReport:
        """
        Queries Ollama to generate an in-depth explanatory narrative and JUnit test suggestions.
        """
        prompt = self._build_explanation_prompt(v1, v2, sig_result, drift_report, impact)
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout_seconds
            )
            resp.raise_for_status()
            raw_text = resp.json().get("response", "")
            return self._parse_explanation_response(raw_text, drift_report, impact)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error querying Ollama for explanation: {e}")
            raise ConnectionError(
                f"Failed to query Ollama at {self.base_url} for explanation: {e}"
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

        return f"""You are an expert senior Java architect and software governance researcher.
Analyze this behavioral drift between two versions of a Java method with IDENTICAL method signatures:

METHOD SIGNATURE (Identical in both versions):
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
