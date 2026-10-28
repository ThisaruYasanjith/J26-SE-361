"""
Module: impact_assessor.py
Stage: Impact Assessment & Architectural Blast Radius

Assesses the architectural blast radius, backward compatibility implications,
and systemic risk level of detected same-signature behavioral drift.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from src.signature_checker import SignatureComparisonResult
from src.drift_engine import DriftReport, DriftSeverity


class RiskLevel(str, Enum):
    """Systemic risk classification."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class BlastRadius(str, Enum):
    """Scope of callers potentially compromised by behavioral drift."""
    LOCAL_METHOD = "Local Method"
    PACKAGE_PRIVATE = "Package / Class"
    CROSS_MODULE = "Cross-Module / Public API"
    SYSTEM_WIDE = "System-Wide / Critical"


class ImpactAssessment(BaseModel):
    """Synthesized impact evaluation of behavioral drift."""
    risk_level: RiskLevel
    blast_radius: BlastRadius
    backward_compatibility_intact: bool
    executive_summary: str
    silent_regression_risk: str
    architectural_risks: List[str] = Field(default_factory=list)
    recommended_mitigations: List[str] = Field(default_factory=list)


class ImpactAssessor:
    """
    Evaluates blast radius and architectural risk based on method visibility,
    signature equivalence, and behavioral divergence scores.
    """

    def assess(
        self,
        sig_result: SignatureComparisonResult,
        drift_report: DriftReport,
        visibility_modifier: str = "public"
    ) -> ImpactAssessment:
        """
        Computes the architectural impact assessment report.
        """
        vis_lower = visibility_modifier.lower()

        # Determine blast radius based on visibility
        if "public" in vis_lower:
            blast_radius = BlastRadius.CROSS_MODULE
        elif "protected" in vis_lower or "package" in vis_lower:
            blast_radius = BlastRadius.PACKAGE_PRIVATE
        else:
            blast_radius = BlastRadius.LOCAL_METHOD

        # Assess backward compatibility
        backward_compatibility_intact = True
        architectural_risks: List[str] = []
        recommended_mitigations: List[str] = []

        # Exceptions thrown or preconditions tightened break backward compatibility
        if "exceptions_thrown" in drift_report.flagged_drift_areas:
            backward_compatibility_intact = False
            architectural_risks.append(
                "Runtime exception behavior has diverged, threatening callers expecting legacy contracts."
            )
            recommended_mitigations.append(
                "Verify exception handling in all upstream callers or preserve legacy unchecked behavior."
            )

        if "preconditions" in drift_report.flagged_drift_areas:
            backward_compatibility_intact = False
            architectural_risks.append(
                "Preconditions have tightened or changed; previously valid arguments may now fail."
            )
            recommended_mitigations.append(
                "Ensure caller arguments satisfy tightened constraints or add backward-compatible default fallbacks."
            )

        if "state_mutations" in drift_report.flagged_drift_areas:
            architectural_risks.append(
                "Unannounced state mutations detected, potentially causing race conditions or side effects in caller objects."
            )
            recommended_mitigations.append(
                "Avoid mutating caller arguments directly; employ immutable data structures or defensive copying."
            )

        if "side_effects" in drift_report.flagged_drift_areas:
            architectural_risks.append(
                "External side-effects (I/O, logging, external state) have altered runtime footprint."
            )
            recommended_mitigations.append(
                "Audit side-effect performance impact and transaction boundary implications."
            )

        if "return_behavior" in drift_report.flagged_drift_areas:
            architectural_risks.append(
                "Return value calculation logic diverged across logical paths."
            )
            recommended_mitigations.append(
                "Write regression unit tests to assert return values across both boundary and nominal inputs."
            )

        # Risk level determination
        if drift_report.severity == DriftSeverity.NONE:
            risk_level = RiskLevel.LOW
        elif drift_report.severity == DriftSeverity.LOW:
            risk_level = RiskLevel.LOW if blast_radius != BlastRadius.CROSS_MODULE else RiskLevel.MEDIUM
        elif drift_report.severity == DriftSeverity.MEDIUM:
            risk_level = RiskLevel.MEDIUM if blast_radius != BlastRadius.CROSS_MODULE else RiskLevel.HIGH
        elif drift_report.severity in [DriftSeverity.HIGH, DriftSeverity.CRITICAL]:
            risk_level = RiskLevel.CRITICAL if blast_radius == BlastRadius.CROSS_MODULE else RiskLevel.HIGH
        else:
            risk_level = RiskLevel.MEDIUM

        if not architectural_risks:
            architectural_risks.append("No immediate architectural risks detected under identical behavior.")

        if not recommended_mitigations:
            recommended_mitigations.append("Retain existing integration and regression test suites.")

        silent_risk = (
            "High vulnerability to silent regressions: compiler will pass cleanly despite runtime semantic deviations."
            if drift_report.drift_detected and backward_compatibility_intact is False
            else "Standard regression risk under version update."
        )

        exec_summary = (
            f"Risk Level: {risk_level.value} | Blast Radius: {blast_radius.value} | "
            f"Backward Compatibility: {'INTACT' if backward_compatibility_intact else 'COMPROMISED'}."
        )

        return ImpactAssessment(
            risk_level=risk_level,
            blast_radius=blast_radius,
            backward_compatibility_intact=backward_compatibility_intact,
            executive_summary=exec_summary,
            silent_regression_risk=silent_risk,
            architectural_risks=architectural_risks,
            recommended_mitigations=recommended_mitigations
        )
