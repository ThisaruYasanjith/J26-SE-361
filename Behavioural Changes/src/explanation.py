"""
Module: explanation.py
Stage: Developer Explanation & Regression Test Synthesis

Synthesizes technical findings across all pipeline stages into a clear, developer-facing
narrative and targeted JUnit regression test recommendations based on detected
behavioral category shifts and drift dimensions. Does not require external APIs.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
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
    Synthesizes actionable explanations and JUnit regression test templates
    from CodeT5 behavioral classifications, drift scores, and impact assessments.
    Runs locally without external API dependencies.
    """

    def __init__(
        self,
        service_url: Optional[str] = None,
        timeout_seconds: int = 60,
        api_key: Optional[str] = None,     # Kept for backward compatibility
        model_name: Optional[str] = None,  # Kept for backward compatibility
        temperature: float = 0.2,          # Kept for backward compatibility
        client: Optional[Any] = None       # Kept for backward compatibility
    ):
        self.service_url = service_url or os.getenv("CODET5_SERVICE_URL", "http://localhost:8000")
        self.timeout_seconds = timeout_seconds

    def generate_explanation(
        self,
        v1: JavaMethod,
        v2: JavaMethod,
        sig_result: SignatureComparisonResult,
        drift_report: DriftReport,
        impact: ImpactAssessment
    ) -> ExplanationReport:
        """
        Synthesizes an in-depth explanatory narrative and JUnit test suggestions
        directly from the pipeline analysis.
        """
        method_name = v1.name
        params_str = ", ".join(f"{p.type} {p.name}" for p in v1.parameters)

        if not drift_report.drift_detected:
            return ExplanationReport(
                overview=f"Method `{method_name}` exhibits no detectable behavioral drift between baseline and modified implementations.",
                detailed_drift_breakdown=(
                    f"Both versions maintain identical behavioral classifications and execution contracts across all checked dimensions. "
                    f"Signature: `{v1.signature_str}`."
                ),
                failure_scenarios=[
                    "No divergent runtime execution paths identified."
                ],
                recommended_unit_tests=[
                    f"""@Test
void test{method_name}_Equivalence() {{
    // Verify baseline and modified implementations yield identical outputs
    // Method signature: {v1.return_type} {method_name}({params_str})
}}"""
                ],
                developer_guidance="The refactoring appears behaviorally safe. Existing unit test suites should pass without regressions."
            )

        # Flagged areas
        flagged = drift_report.flagged_drift_areas
        overview = (
            f"Behavioral drift of severity **{drift_report.severity.value}** (Score: {drift_report.drift_score*100:.1f}%) "
            f"detected in same-signature Java method `{method_name}`. "
            f"Impact blast radius: **{impact.blast_radius.value}** with risk level **{impact.risk_level.value}**."
        )

        breakdown_lines = [
            f"**Method:** `{v1.signature_str}`",
            f"**Summary:** {drift_report.summary}",
            f"**Backward Compatibility:** {'Intact' if impact.backward_compatibility_intact else 'COMPROMISED'}",
            ""
        ]

        failure_scenarios: List[str] = []
        unit_tests: List[str] = []

        for delta in drift_report.dimension_deltas:
            if not delta.has_drift:
                continue
            dim = delta.dimension
            breakdown_lines.append(f"- **{dim.upper()}** (divergence weight: {delta.weight:.2f}):")
            if delta.added_behaviors:
                breakdown_lines.append(f"  - *Added in modified version:* {', '.join(delta.added_behaviors)}")
            if delta.removed_behaviors:
                breakdown_lines.append(f"  - *Removed from baseline:* {', '.join(delta.removed_behaviors)}")

            # Tailor failure scenarios and JUnit tests
            if "exception" in dim.lower():
                failure_scenarios.append(
                    f"Callers invoking `{method_name}` under edge conditions may encounter newly introduced exceptions "
                    f"where previous versions returned safe fallbacks or handled errors silently."
                )
                unit_tests.append(
                    f"""@Test
void test{method_name}_ExceptionContract() {{
    // Verify method properly handles edge inputs without unexpected exceptions
    // Expected behavior under invalid inputs:
    assertDoesNotThrow(() -> {{
        // instance.{method_name}(...);
    }});
}}"""
                )

            if "state" in dim.lower() or "mutation" in dim.lower():
                failure_scenarios.append(
                    f"Passing shared objects or mutable arguments into `{method_name}` may result in unexpected side-effects "
                    f"or race conditions in concurrent caller threads."
                )
                unit_tests.append(
                    f"""@Test
void test{method_name}_StateImmutability() {{
    // Verify caller arguments are not silently mutated
    // Snapshot original state before call:
    // instance.{method_name}(...);
    // assertEquals(originalSnapshot, currentArgumentState);
}}"""
                )

            if "side_effect" in dim.lower():
                failure_scenarios.append(
                    f"External side effects (I/O, database persistence, logging, or remote integrations) diverge between versions, "
                    f"potentially duplicating operations or omitting necessary audit traces."
                )
                unit_tests.append(
                    f"""@Test
void test{method_name}_SideEffects() {{
    // Verify external service / repository interactions
    // verify(repositoryMock, times(1)).operation(...);
}}"""
                )

            if "precondition" in dim.lower():
                failure_scenarios.append(
                    f"Tightened validation or control flow checks in `{method_name}` may reject arguments previously accepted by baseline."
                )
                unit_tests.append(
                    f"""@Test
void test{method_name}_PreconditionBoundary() {{
    // Test boundary conditions that previously succeeded
    assertNotNull(instance.{method_name}(/* test boundaries */));
}}"""
                )

        if not failure_scenarios:
            failure_scenarios.append(
                f"Computation logic or return formatting diverges, potentially affecting downstream business calculations."
            )

        if not unit_tests:
            unit_tests.append(
                f"""@Test
void test{method_name}_RegressionGuard() {{
    // Verify return computation consistency
    {v1.return_type} result = instance.{method_name}(/* arguments */);
    assertNotNull(result);
}}"""
            )

        guidance = (
            f"Review the {len(flagged)} affected behavioral dimension(s) ({', '.join(flagged)}). "
            f"{impact.executive_summary} "
            f"Deploy the suggested JUnit regression guards to detect unintended behavioral drift in CI/CD before merging."
        )

        return ExplanationReport(
            overview=overview,
            detailed_drift_breakdown="\n".join(breakdown_lines),
            failure_scenarios=failure_scenarios,
            recommended_unit_tests=unit_tests,
            developer_guidance=guidance,
            raw_llm_response="Generated deterministically by local CodeT5 behavioral governance pipeline."
        )

    def _parse_explanation_response(
        self,
        raw_text: str,
        drift_report: DriftReport,
        impact: ImpactAssessment
    ) -> ExplanationReport:
        """Helper to parse raw JSON if provided in legacy tests."""
        try:
            data = json.loads(raw_text)
            return ExplanationReport(
                overview=data.get("overview", "Analysis completed."),
                detailed_drift_breakdown=data.get("detailed_drift_breakdown", ""),
                failure_scenarios=data.get("failure_scenarios", []),
                recommended_unit_tests=data.get("recommended_unit_tests", []),
                developer_guidance=data.get("developer_guidance", ""),
                raw_llm_response=raw_text
            )
        except Exception:
            return ExplanationReport(
                overview="Drift analysis completed.",
                detailed_drift_breakdown=drift_report.summary,
                failure_scenarios=[],
                recommended_unit_tests=[],
                developer_guidance=impact.executive_summary,
                raw_llm_response=raw_text
            )
