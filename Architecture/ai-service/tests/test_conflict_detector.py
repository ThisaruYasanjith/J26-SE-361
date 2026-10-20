import copy

import pytest

from app.conflict_detector import ConflictDetector
from test_rule_validator import valid_rule


def saved_rule(rule, rule_id="CUSTOM_001"):
    result = copy.deepcopy(rule)
    result["rule_id"] = rule_id
    return result


@pytest.mark.parametrize("existing_action,new_action,different_source", [
    ("ONLY", "ALLOW", True), ("ONLY", "ONLY", True),
    ("DENY", "ALLOW", False), ("ALLOW", "DENY", False),
    ("ALLOW", "ONLY", True),
])
def test_required_conflicts_are_detected_in_both_directions(valid_rule, existing_action, new_action, different_source):
    existing = saved_rule(valid_rule)
    existing["rule"]["action"] = existing_action
    candidate = copy.deepcopy(valid_rule)
    candidate["rule"]["action"] = new_action
    if different_source:
        candidate["rule"]["source"]["name"] = "ReportingService"
    result = ConflictDetector().detect(candidate, [existing])
    assert result.has_conflict and not result.duplicate
    assert result.conflicts[0].existing_rule_id == "CUSTOM_001"
    assert result.conflicts[0].reason
    reverse = ConflictDetector().detect(existing, [saved_rule(candidate)])
    assert reverse.has_conflict


def test_duplicate_ignores_ids_and_object_key_order(valid_rule):
    candidate = dict(reversed(list(valid_rule.items())))
    candidate["rule"] = dict(reversed(list(candidate["rule"].items())))
    candidate["rule_id"] = "MODEL_ASSIGNED_ID"
    result = ConflictDetector().detect(candidate, [saved_rule(valid_rule)])
    assert result.model_dump() == {"has_conflict": False, "duplicate": True, "conflicts": []}


@pytest.mark.parametrize("change", ["target_name", "target_type", "relationship", "source_type", "rule_type"])
def test_matching_uses_exact_entities_relationship_and_rule_type(valid_rule, change):
    candidate = copy.deepcopy(valid_rule)
    candidate["rule"]["action"] = "ALLOW"
    candidate["rule"]["source"]["name"] = "ReportingService"
    if change == "target_name":
        candidate["rule"]["target"]["name"] = "OtherGateway"
    elif change == "target_type":
        candidate["rule"]["target"]["entity_type"] = "INTERFACE"
    elif change == "relationship":
        candidate["rule"]["relationship"] = "CALLS"
    elif change == "source_type":
        candidate["rule"]["source"] = {"entity_type": "CLASS", "name": "PaymentService"}
        candidate["rule"]["action"] = "DENY"
        existing = saved_rule(valid_rule)
        existing["rule"]["action"] = "ALLOW"
        assert not ConflictDetector().detect(candidate, [existing]).has_conflict
        return
    else:
        candidate["rule"]["rule_type"] = "LAYER_DEPENDENCY"
    result = ConflictDetector().detect(candidate, [saved_rule(valid_rule)])
    assert not result.has_conflict and not result.duplicate


def test_allow_for_the_only_source_does_not_conflict(valid_rule):
    candidate = copy.deepcopy(valid_rule)
    candidate["rule"]["action"] = "ALLOW"
    result = ConflictDetector().detect(candidate, [saved_rule(valid_rule)])
    assert not result.has_conflict and not result.duplicate


@pytest.mark.parametrize("exception_field", ["is_exception", "rule_type"])
def test_exception_precedence_is_not_guessed(valid_rule, exception_field):
    candidate = copy.deepcopy(valid_rule)
    candidate["rule"].update(action="ALLOW", source={"entity_type": "COMPONENT", "name": "ReportingService"})
    candidate["rule"][exception_field] = True if exception_field == "is_exception" else "EXCEPTION"
    result = ConflictDetector().detect(candidate, [saved_rule(valid_rule)])
    assert not result.has_conflict and not result.duplicate
    assert ConflictDetector().detect(candidate, [saved_rule(candidate)]).duplicate


def test_conflict_order_is_stable_and_inputs_are_preserved(valid_rule):
    second = saved_rule(valid_rule, "CUSTOM_002")
    second["rule"]["source"]["name"] = "SecondService"
    existing = [second, saved_rule(valid_rule)]
    candidate = copy.deepcopy(valid_rule)
    candidate["rule"]["source"]["name"] = "ReportingService"
    before = copy.deepcopy((candidate, existing))
    result = ConflictDetector().detect(candidate, existing)
    assert [item.existing_rule_id for item in result.conflicts] == ["CUSTOM_001", "CUSTOM_002"]
    assert (candidate, existing) == before
