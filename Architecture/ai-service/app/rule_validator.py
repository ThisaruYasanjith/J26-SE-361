from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path
from typing import Iterable

from jsonschema import ValidationError, validators
from jsonschema.exceptions import SchemaError
from pydantic import Field, JsonValue

from app.config import RULES_DIRECTORY
from app.models import ArchitectureModel


RULE_SCHEMA_PATH = RULES_DIRECTORY.parent / "schemas" / "rule.schema.json"


class RuleValidationSetupError(RuntimeError):
    """The shared schema could not be loaded or compiled."""


class RuleValidationIssue(ArchitectureModel):
    path: str
    message: str


class RuleValidationResult(ArchitectureModel):
    valid: bool
    errors: list[RuleValidationIssue] = Field(default_factory=list)


def _path(parts: Iterable[str | int]) -> str:
    return ".".join(str(part) for part in parts) or "$"


def _schema_issues(error: ValidationError) -> Iterable[RuleValidationIssue]:
    # For an object, show failures inside the nullable rule branch instead of "object or null" noise.
    if error.validator == "anyOf" and isinstance(error.instance, dict):
        for child in error.context:
            if child.validator == "type" and child.schema.get("type") == "null":
                continue
            yield from _schema_issues(child)
    elif error.validator == "required":
        for name in error.validator_value:
            if name not in error.instance:
                yield RuleValidationIssue(path=_path([*error.absolute_path, name]), message="Required field is missing.")
    else:
        yield RuleValidationIssue(path=_path(error.absolute_path), message=error.message)


class RuleValidator:
    def __init__(self, schema_path: Path = RULE_SCHEMA_PATH) -> None:
        self.schema_path = Path(schema_path)

    @cached_property
    def _validator(self):
        try:
            schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
            validator_class = validators.validator_for(schema)
            validator_class.check_schema(schema)
            return validator_class(schema)
        except (OSError, ValueError, SchemaError) as error:
            raise RuleValidationSetupError(f"Cannot load the shared architecture rule schema: {error}") from error

    def validate(self, output: JsonValue) -> RuleValidationResult:
        issues = [issue for error in self._validator.iter_errors(output) for issue in _schema_issues(error)]

        if isinstance(output, dict):
            status, rule = output.get("status"), output.get("rule")
            # The shared schema permits a partial rule here; generated uncertain results must use null.
            if status in ("AMBIGUOUS", "UNSUPPORTED") and rule is not None:
                issues.append(RuleValidationIssue(path="rule", message=f"rule must be null when status is {status}."))
            if status == "VALID" and isinstance(rule, dict):
                for side in ("source", "target"):
                    entity = rule.get(side)
                    name = entity.get("name") if isinstance(entity, dict) else None
                    if isinstance(name, str) and name and not name.strip():
                        issues.append(RuleValidationIssue(path=f"rule.{side}.name", message="Name must not be blank."))

        # Conditional schemas can report the same failure twice. Keep the result stable and concise.
        unique = sorted({(issue.path, issue.message) for issue in issues})
        errors = [RuleValidationIssue(path=path, message=message) for path, message in unique]
        return RuleValidationResult(valid=not errors, errors=errors)
