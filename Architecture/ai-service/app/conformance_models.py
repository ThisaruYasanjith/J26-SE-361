from typing import Literal

from pydantic import Field

from app.models import ArchitectureModel, NonEmptyString, RelationshipType, SourceLocation


class ArchitectureViolation(SourceLocation):
    # Keep this payload within violation.schema.json; rule provenance belongs to the response lookup.
    violation_id: NonEmptyString
    rule_id: NonEmptyString
    severity: Literal["INFO", "WARNING", "ERROR"]
    message: NonEmptyString
    source: NonEmptyString
    target: NonEmptyString | None = None
    relationship: RelationshipType | Literal["LOCATED_IN"] | None = None
    file_path: NonEmptyString
    explanation: NonEmptyString
    suggested_correction: NonEmptyString


class ConformanceRuleInfo(ArchitectureModel):
    rule_type: NonEmptyString
    rule_source: Literal["BASE", "CUSTOM"]


class ConformanceSummary(ArchitectureModel):
    total: int = Field(ge=0)
    base_rule_violations: int = Field(ge=0)
    custom_rule_violations: int = Field(ge=0)


class ConformanceResult(ArchitectureModel):
    project_name: NonEmptyString
    conformant: bool
    violations: list[ArchitectureViolation]
    summary: ConformanceSummary
    rule_metadata: dict[str, ConformanceRuleInfo]
