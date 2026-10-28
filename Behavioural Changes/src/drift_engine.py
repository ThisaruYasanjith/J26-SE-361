"""
Module: drift_engine.py
Stage: Behavioral Drift Engine

Quantifies multi-dimensional behavioral divergence between two method versions
by analyzing delta differences across preconditions, postconditions, state mutations,
side effects, thrown exceptions, and return behavior.
"""

from enum import Enum
from typing import List, Dict, Any, Set, Optional
from pydantic import BaseModel, Field
from src.llm_analyzer import BehavioralFingerprint


class DriftSeverity(str, Enum):
    """Classification of behavioral drift severity."""
    NONE = "None"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class DimensionDelta(BaseModel):
    """Specific delta metrics for a single behavioral dimension."""
    dimension: str
    weight: float
    has_drift: bool
    added_behaviors: List[str] = Field(default_factory=list)
    removed_behaviors: List[str] = Field(default_factory=list)
    similarity_score: float = 1.0


class DriftReport(BaseModel):
    """Comprehensive quantification of behavioral drift between v1 and v2."""
    drift_detected: bool
    drift_score: float = Field(..., ge=0.0, le=1.0)
    severity: DriftSeverity
    flagged_drift_areas: List[str] = Field(default_factory=list)
    dimension_deltas: List[DimensionDelta] = Field(default_factory=list)
    summary: str


class BehavioralDriftEngine:
    """
    Computes weighted multi-dimensional drift between two BehavioralFingerprint instances.
    """

    DIMENSION_WEIGHTS: Dict[str, float] = {
        "exceptions_thrown": 0.25,
        "state_mutations": 0.20,
        "side_effects": 0.20,
        "preconditions": 0.15,
        "postconditions": 0.10,
        "return_behavior": 0.10,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.DIMENSION_WEIGHTS

    def analyze(self, fp1: BehavioralFingerprint, fp2: BehavioralFingerprint) -> DriftReport:
        """
        Analyzes two behavioral fingerprints and computes the composite drift report.
        """
        deltas: List[DimensionDelta] = []
        flagged_areas: List[str] = []
        total_drift = 0.0

        # Dimension checks: list-based
        list_dimensions = [
            ("exceptions_thrown", fp1.exceptions_thrown, fp2.exceptions_thrown),
            ("state_mutations", fp1.state_mutations, fp2.state_mutations),
            ("side_effects", fp1.side_effects, fp2.side_effects),
            ("preconditions", fp1.preconditions, fp2.preconditions),
            ("postconditions", fp1.postconditions, fp2.postconditions),
        ]

        for dim_name, v1_items, v2_items in list_dimensions:
            weight = self.weights.get(dim_name, 0.15)
            s1 = set(item.strip().lower() for item in v1_items if item.strip())
            s2 = set(item.strip().lower() for item in v2_items if item.strip())

            added = [item for item in v2_items if item.strip().lower() not in s1]
            removed = [item for item in v1_items if item.strip().lower() not in s2]

            union = s1 | s2
            if not union:
                sim = 1.0
            else:
                intersection = s1 & s2
                sim = len(intersection) / len(union)

            has_drift = (len(added) > 0 or len(removed) > 0)
            dim_drift = 1.0 - sim
            total_drift += dim_drift * weight

            if has_drift:
                flagged_areas.append(dim_name)

            deltas.append(DimensionDelta(
                dimension=dim_name,
                weight=weight,
                has_drift=has_drift,
                added_behaviors=added,
                removed_behaviors=removed,
                similarity_score=sim
            ))

        # Return behavior comparison
        ret_weight = self.weights.get("return_behavior", 0.10)
        ret1 = (fp1.return_behavior or "").strip().lower()
        ret2 = (fp2.return_behavior or "").strip().lower()
        ret_drift = 0.0 if ret1 == ret2 else (0.5 if not ret1 or not ret2 else 0.8)
        ret_has_drift = ret1 != ret2

        if ret_has_drift and ret_drift > 0:
            flagged_areas.append("return_behavior")
            total_drift += ret_drift * ret_weight

        deltas.append(DimensionDelta(
            dimension="return_behavior",
            weight=ret_weight,
            has_drift=ret_has_drift,
            added_behaviors=[fp2.return_behavior] if ret_has_drift and fp2.return_behavior else [],
            removed_behaviors=[fp1.return_behavior] if ret_has_drift and fp1.return_behavior else [],
            similarity_score=1.0 - ret_drift
        ))

        drift_score = min(1.0, max(0.0, total_drift))
        drift_detected = drift_score > 0.05 or len(flagged_areas) > 0

        # Determine severity
        if drift_score == 0.0:
            severity = DriftSeverity.NONE
        elif drift_score < 0.20:
            severity = DriftSeverity.LOW
        elif drift_score < 0.45:
            severity = DriftSeverity.MEDIUM
        elif drift_score < 0.70:
            severity = DriftSeverity.HIGH
        else:
            severity = DriftSeverity.CRITICAL

        summary = (
            f"No significant behavioral drift detected (score: {drift_score:.2f})."
            if not drift_detected
            else f"Behavioral drift detected (score: {drift_score:.2f}, severity: {severity.value}) across {len(flagged_areas)} dimension(s): {', '.join(flagged_areas)}."
        )

        return DriftReport(
            drift_detected=drift_detected,
            drift_score=drift_score,
            severity=severity,
            flagged_drift_areas=flagged_areas,
            dimension_deltas=deltas,
            summary=summary
        )
