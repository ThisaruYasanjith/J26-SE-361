"""
Module: signature_checker.py
Stage: Same-Signature Verification

Responsible for verifying that baseline (v1) and modified (v2) Java methods
share the identical signature. If signatures differ, the change represents an
overt API contract modification rather than silent behavioral drift.
"""

from typing import List, Optional
import re
from pydantic import BaseModel, Field
from src.method_parser import JavaMethod


class SignatureMismatch(BaseModel):
    """Details of a specific signature discrepancy."""
    component: str  # e.g., 'name', 'parameter_count', 'parameter_types', 'return_type'
    baseline_value: str
    modified_value: str
    description: str


class SignatureComparisonResult(BaseModel):
    """Result of signature equivalence check between two Java method versions."""
    is_same_signature: bool
    method_name: str
    mismatches: List[SignatureMismatch] = Field(default_factory=list)
    summary: str

    @property
    def allows_drift_analysis(self) -> bool:
        """Indicates if the methods are eligible for same-signature behavioral drift analysis."""
        return self.is_same_signature


class SignatureChecker:
    """Verifies whether two JavaMethod objects possess the exact same signature."""

    def __init__(self, strict_modifiers: bool = False, strict_exceptions: bool = False):
        self.strict_modifiers = strict_modifiers
        self.strict_exceptions = strict_exceptions

    def check(self, v1: JavaMethod, v2: JavaMethod) -> SignatureComparisonResult:
        """
        Compares baseline v1 against modified v2 for identical method signatures.
        """
        mismatches: List[SignatureMismatch] = []

        # 1. Method Name Check
        if v1.name != v2.name:
            mismatches.append(SignatureMismatch(
                component="name",
                baseline_value=v1.name,
                modified_value=v2.name,
                description=f"Method name changed from '{v1.name}' to '{v2.name}'."
            ))

        # 2. Return Type Check
        norm_ret1 = self._normalize_type(v1.return_type)
        norm_ret2 = self._normalize_type(v2.return_type)
        if norm_ret1 != norm_ret2:
            mismatches.append(SignatureMismatch(
                component="return_type",
                baseline_value=v1.return_type,
                modified_value=v2.return_type,
                description=f"Return type changed from '{v1.return_type}' to '{v2.return_type}'."
            ))

        # 3. Parameter Count Check
        if len(v1.parameters) != len(v2.parameters):
            mismatches.append(SignatureMismatch(
                component="parameter_count",
                baseline_value=str(len(v1.parameters)),
                modified_value=str(len(v2.parameters)),
                description=f"Parameter count mismatch: baseline has {len(v1.parameters)}, modified has {len(v2.parameters)}."
            ))
        else:
            # 4. Parameter Types Order & Equivalence Check
            for idx, (p1, p2) in enumerate(zip(v1.parameters, v2.parameters)):
                norm_p1 = self._normalize_type(p1.type)
                norm_p2 = self._normalize_type(p2.type)
                if norm_p1 != norm_p2:
                    mismatches.append(SignatureMismatch(
                        component=f"parameter_type_at_{idx}",
                        baseline_value=f"{p1.type} {p1.name}",
                        modified_value=f"{p2.type} {p2.name}",
                        description=f"Parameter {idx + 1} type changed from '{p1.type}' to '{p2.type}'."
                    ))

        # 5. Optional Strict Checks: Modifiers and Thrown Exceptions
        if self.strict_modifiers:
            v1_mods = set(v1.modifiers)
            v2_mods = set(v2.modifiers)
            if v1_mods != v2_mods:
                mismatches.append(SignatureMismatch(
                    component="modifiers",
                    baseline_value=" ".join(v1.modifiers),
                    modified_value=" ".join(v2.modifiers),
                    description="Method access modifiers differ."
                ))

        if self.strict_exceptions:
            v1_exc = set(v1.thrown_exceptions)
            v2_exc = set(v2.thrown_exceptions)
            if v1_exc != v2_exc:
                mismatches.append(SignatureMismatch(
                    component="thrown_exceptions",
                    baseline_value=", ".join(v1.thrown_exceptions),
                    modified_value=", ".join(v2.thrown_exceptions),
                    description="Declared thrown exceptions differ."
                ))

        is_same = len(mismatches) == 0
        summary = (
            f"Signatures are identical for method '{v1.name}'."
            if is_same
            else f"Signatures differ: {len(mismatches)} mismatch(es) found."
        )

        return SignatureComparisonResult(
            is_same_signature=is_same,
            method_name=v1.name,
            mismatches=mismatches,
            summary=summary
        )

    def _normalize_type(self, type_str: str) -> str:
        """Removes redundant whitespace and canonicalizes basic type notations."""
        cleaned = re.sub(r"\s+", "", type_str)
        # Map common aliases if needed (e.g. java.lang.String to String)
        if cleaned.startswith("java.lang."):
            cleaned = cleaned.replace("java.lang.", "")
        return cleaned
