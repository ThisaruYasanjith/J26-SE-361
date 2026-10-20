import json

from pydantic import Field

from app.models import ArchitectureModel


class RuleConflict(ArchitectureModel):
    existing_rule_id: str
    reason: str


class ConflictResult(ArchitectureModel):
    has_conflict: bool
    duplicate: bool
    conflicts: list[RuleConflict] = Field(default_factory=list)


def semantic_rule_key(envelope: dict) -> str:
    # IDs belong to storage; the complete rule body determines semantic equality.
    return json.dumps(envelope["rule"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class ConflictDetector:
    """Compare already validated VALID envelopes without consulting the model or project graph."""

    def detect(self, candidate: dict, existing_rules: list[dict]) -> ConflictResult:
        conflicts = []
        duplicate = False
        rule = candidate["rule"]
        key = semantic_rule_key(candidate)
        for existing in sorted(existing_rules, key=lambda entry: entry["rule_id"]):
            other = existing["rule"]
            if semantic_rule_key(existing) == key:
                duplicate = True
                continue
            # Exceptions remain distinct stored rules. Their precedence needs a later explicit policy.
            if rule["is_exception"] or other["is_exception"] or "EXCEPTION" in (rule["rule_type"], other["rule_type"]):
                continue
            if (rule["rule_type"], rule["scope"], rule["relationship"], rule["target"]) != (
                other["rule_type"], other["scope"], other["relationship"], other["target"]
            ):
                continue
            same_source = rule["source"] == other["source"]
            reason = None
            if not same_source:
                if other["action"] == "ONLY" and rule["action"] in ("ALLOW", "ONLY"):
                    reason = f"Existing ONLY rule restricts {other['target']['name']} access to {other['source']['name']}."
                elif rule["action"] == "ONLY" and other["action"] in ("ALLOW", "ONLY"):
                    reason = f"New ONLY rule excludes the source {other['source']['name']} permitted by the existing rule."
            elif {rule["action"], other["action"]} == {"ALLOW", "DENY"}:
                reason = "ALLOW and DENY contradict each other for the same source, relationship, target and scope."
            if reason is not None:
                conflicts.append(RuleConflict(existing_rule_id=existing["rule_id"], reason=reason))
        return ConflictResult(has_conflict=bool(conflicts), duplicate=duplicate, conflicts=conflicts)
