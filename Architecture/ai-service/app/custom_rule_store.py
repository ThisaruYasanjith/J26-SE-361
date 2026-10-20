from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Callable

from pydantic import JsonValue

from app.config import RULES_DIRECTORY
from app.conflict_detector import ConflictDetector, ConflictResult, semantic_rule_key
from app.models import ArchitectureModel
from app.rule_validator import RuleValidationIssue, RuleValidationSetupError, RuleValidator


logger = logging.getLogger(__name__)


class RuleCheckRequest(ArchitectureModel):
    rule: JsonValue


class RuleApprovalRequest(RuleCheckRequest):
    confirm_conflicts: bool = False


class RuleApprovalResponse(ArchitectureModel):
    approved: bool
    rule_id: str
    conflicts_confirmed: bool
    duplicate: bool


class CustomRuleStoreError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503, *,
                 validation_errors: list[RuleValidationIssue] | None = None,
                 conflict_result: ConflictResult | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.validation_errors = validation_errors
        self.conflict_result = conflict_result


def _rule_order(entry: dict) -> tuple:
    number = re.fullmatch(r"CUSTOM_(\d+)", entry["rule_id"])
    return (0, int(number[1]), entry["rule_id"]) if number else (1, entry["rule_id"])


class CustomRuleStore:
    # Apps sharing a file in this process must share the whole read/check/write transaction lock.
    _locks_guard = threading.Lock()
    _path_locks: dict[Path, threading.RLock] = {}

    def __init__(self, path: Path = RULES_DIRECTORY / "custom-rules.json", *,
                 validator: RuleValidator | None = None, on_change: Callable[[], None] | None = None) -> None:
        self.path = Path(path).expanduser().resolve()
        self.validator = validator if validator is not None else RuleValidator()
        self.detector = ConflictDetector()
        self.on_change = on_change
        with self._locks_guard:
            self._lock = self._path_locks.setdefault(self.path, threading.RLock())

    def _validate(self, entry: JsonValue, *, stored: bool = False) -> dict:
        try:
            result = self.validator.validate(entry)
        except RuleValidationSetupError as error:
            raise CustomRuleStoreError(str(error)) from error
        errors = list(result.errors)
        if isinstance(entry, dict) and entry.get("status") != "VALID":
            errors.append(RuleValidationIssue(path="status", message="Only schema-valid VALID rules can be approved or checked."))
        if stored and isinstance(entry, dict) and (
            not isinstance(entry.get("rule_id"), str) or not entry["rule_id"].strip()
        ):
            errors.append(RuleValidationIssue(path="rule_id", message="A stored rule requires a non-empty rule_id."))
        if errors:
            raise CustomRuleStoreError(
                "Stored custom rule is invalid." if stored else "A schema-valid VALID rule is required.",
                503 if stored else 422, validation_errors=errors,
            )
        return entry

    def load_rules(self) -> list[dict]:
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return []
            except (OSError, ValueError) as error:
                raise CustomRuleStoreError(f"Cannot read custom rules from {self.path}: {error}") from error
            if not isinstance(data, dict) or set(data) != {"rules"} or not isinstance(data["rules"], list):
                raise CustomRuleStoreError("Custom rule storage must be an object containing only a rules list.")
            entries = [self._validate(entry, stored=True) for entry in data["rules"]]
            ids = [entry["rule_id"] for entry in entries]
            if len(ids) != len(set(ids)):
                raise CustomRuleStoreError("Custom rule storage contains duplicate rule IDs.")
            return sorted(entries, key=_rule_order)

    def check_conflicts(self, candidate: JsonValue) -> ConflictResult:
        with self._lock:
            return self.detector.detect(self._validate(candidate), self.load_rules())

    def approve_rule(self, candidate: JsonValue, *, confirm_conflicts: bool = False) -> RuleApprovalResponse:
        if type(confirm_conflicts) is not bool:
            raise CustomRuleStoreError("confirm_conflicts must be a boolean.", 422)
        with self._lock:
            candidate = self._validate(candidate)
            existing = self.load_rules()
            result = self.detector.detect(candidate, existing)
            if result.duplicate:
                # Re-approval is idempotent, even if a later explicitly overridden rule now contradicts it.
                duplicate = next(entry for entry in existing if semantic_rule_key(entry) == semantic_rule_key(candidate))
                return RuleApprovalResponse(approved=True, rule_id=duplicate["rule_id"], conflicts_confirmed=False, duplicate=True)
            if result.has_conflict and not confirm_conflicts:
                raise CustomRuleStoreError(
                    "Rule conflicts with approved custom rules. Set confirm_conflicts=true to approve explicitly.",
                    409, conflict_result=result,
                )
            numbers = [int(match[1]) for entry in existing if (match := re.fullmatch(r"CUSTOM_(\d+)", entry["rule_id"]))]
            rule_id = f"CUSTOM_{max(numbers, default=0) + 1:03d}"
            approved = copy.deepcopy(candidate)
            # IDs come from this store, even when a caller supplies a generated or stale rule_id.
            approved["rule_id"] = rule_id
            self._persist(sorted([*existing, approved], key=_rule_order))
            if self.on_change is not None:
                self.on_change()
            return RuleApprovalResponse(
                approved=True, rule_id=rule_id, conflicts_confirmed=result.has_conflict, duplicate=False,
            )

    def _persist(self, entries: list[dict]) -> None:
        temporary_path = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Use the same directory so replacement stays on the same filesystem, including on Windows.
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as stream:
                temporary_path = Path(stream.name)
                json.dump({"rules": entries}, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        except (OSError, ValueError) as error:
            raise CustomRuleStoreError(f"Cannot persist custom rules to {self.path}: {error}") from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove temporary custom-rule file %s", temporary_path)
