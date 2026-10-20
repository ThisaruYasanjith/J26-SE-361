import asyncio
import copy
import json

import pytest

from app.inference import RuleGenerationRequest, RuleGenerationService
from app.main import create_app
from app.rule_validator import RULE_SCHEMA_PATH, RuleValidationSetupError, RuleValidator
from test_inference import FakeRuleModel
from test_rag import environment, request_json


@pytest.fixture
def valid_rule():
    return {
        "status": "VALID",
        "rule": {
            "rule_type": "COMPONENT_ACCESS",
            "source": {"entity_type": "COMPONENT", "name": "PaymentService"},
            "relationship": "DEPENDS_ON",
            "target": {"entity_type": "COMPONENT", "name": "PaymentGateway"},
            "action": "ONLY", "scope": {"type": "PROJECT", "value": None}, "is_exception": False,
        },
        "reason_code": None,
    }


def set_value(output, path, value):
    names = path.split(".")
    parent = output
    for name in names[:-1]:
        parent = parent[name]
    parent[names[-1]] = value


def test_valid_rule_is_accepted_without_changes(valid_rule):
    original = copy.deepcopy(valid_rule)
    assert RuleValidator().validate(valid_rule).model_dump() == {"valid": True, "errors": []}
    assert valid_rule == original


@pytest.mark.parametrize("status", ["AMBIGUOUS", "UNSUPPORTED"])
def test_uncertain_status_accepts_null_rule_and_allowed_reason(status):
    result = RuleValidator().validate({"status": status, "rule": None, "reason_code": "MISSING_TARGET"})
    assert result.valid and result.errors == []


@pytest.mark.parametrize("path,value", [
    ("status", "UNKNOWN"), ("status", None), ("status", []),
    ("rule", None), ("reason_code", "MISSING_SOURCE"),
    ("rule.rule_type", "UNKNOWN"), ("rule.source", None), ("rule.target", None),
    ("rule.source.entity_type", "UNKNOWN"), ("rule.target.entity_type", "UNKNOWN"),
    ("rule.relationship", "USES"), ("rule.action", "PERMIT"),
    ("rule.source.name", ""), ("rule.target.name", ""),
    ("rule.source.name", " \n "), ("rule.target.name", "\t"),
    ("rule.source.name", 12), ("rule.target.name", None),
    ("rule.scope.type", "PACKAGE"), ("rule.scope.value", "payments"),
    ("rule.is_exception", "false"), ("rule.is_exception", 1), ("rule.is_exception", None),
])
def test_invalid_fields_have_precise_paths(valid_rule, path, value):
    set_value(valid_rule, path, value)
    original = copy.deepcopy(valid_rule)
    result = RuleValidator().validate(valid_rule)
    assert not result.valid
    assert any(issue.path == path for issue in result.errors)
    assert valid_rule == original


@pytest.mark.parametrize("path", [
    "status", "rule", "reason_code", "rule.rule_type", "rule.source", "rule.target",
    "rule.source.entity_type", "rule.source.name", "rule.target.entity_type", "rule.target.name",
    "rule.relationship", "rule.action", "rule.scope", "rule.scope.type", "rule.scope.value", "rule.is_exception",
])
def test_missing_fields_are_reported_at_the_field(valid_rule, path):
    names = path.split(".")
    parent = valid_rule
    for name in names[:-1]:
        parent = parent[name]
    del parent[names[-1]]
    result = RuleValidator().validate(valid_rule)
    assert not result.valid
    assert any(issue.path == path and issue.message == "Required field is missing." for issue in result.errors)


@pytest.mark.parametrize("status", ["AMBIGUOUS", "UNSUPPORTED"])
def test_uncertain_status_rejects_a_rule_even_when_shared_schema_permits_it(valid_rule, status):
    valid_rule.update(status=status, reason_code="MULTIPLE_INTERPRETATIONS")
    result = RuleValidator().validate(valid_rule)
    assert result.model_dump() == {"valid": False, "errors": [
        {"path": "rule", "message": f"rule must be null when status is {status}."},
    ]}


@pytest.mark.parametrize("status", ["AMBIGUOUS", "UNSUPPORTED"])
@pytest.mark.parametrize("reason", [None, "UNKNOWN_REASON", "", 42])
def test_uncertain_status_requires_a_valid_non_null_reason(status, reason):
    result = RuleValidator().validate({"status": status, "rule": None, "reason_code": reason})
    assert not result.valid and any(issue.path == "reason_code" for issue in result.errors)


@pytest.mark.parametrize("status", ["AMBIGUOUS", "UNSUPPORTED"])
def test_uncertain_status_requires_reason_field(status):
    result = RuleValidator().validate({"status": status, "rule": None})
    assert not result.valid and result.errors[0].path == "reason_code"


@pytest.mark.parametrize("output", [None, [], "a rule", 42, True])
def test_non_object_json_is_schema_invalid(output):
    result = RuleValidator().validate(output)
    assert not result.valid and result.errors[0].path == "$"


def test_unknown_fields_are_not_silently_discarded(valid_rule):
    valid_rule["rule"]["confidence"] = .9
    result = RuleValidator().validate(valid_rule)
    assert not result.valid and any("confidence" in issue.message for issue in result.errors)


def test_validation_is_deterministic_and_duplicate_free(valid_rule):
    valid_rule["rule"].update(action="UNKNOWN", relationship="USES")
    first = RuleValidator().validate(valid_rule)
    second = RuleValidator().validate(dict(reversed(list(valid_rule.items()))))
    assert first == second
    assert len(first.errors) == 2
    assert [issue.path for issue in first.errors] == ["rule.action", "rule.relationship"]


def test_names_and_semantic_values_are_never_normalized(valid_rule):
    valid_rule["rule"]["source"]["name"] = " PaymentService "
    valid_rule["rule"]["action"] = " only "
    before = copy.deepcopy(valid_rule)
    result = RuleValidator().validate(valid_rule)
    assert not result.valid and any(issue.path == "rule.action" for issue in result.errors)
    assert valid_rule == before


def test_schema_changes_are_read_from_the_supplied_file(valid_rule, tmp_path):
    schema = json.loads(RULE_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema["definitions"]["rule"]["properties"]["action"]["enum"] = ["DENY"]
    path = tmp_path / "rule.schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    assert RuleValidator().validate(valid_rule).valid
    result = RuleValidator(path).validate(valid_rule)
    assert not result.valid and any(issue.path == "rule.action" for issue in result.errors)


@pytest.mark.parametrize("content", [None, "{", '{"type":42}'])
def test_unavailable_or_invalid_schema_is_a_setup_error(tmp_path, content):
    path = tmp_path / "rule.schema.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    validator = RuleValidator(path)
    with pytest.raises(RuleValidationSetupError, match="shared architecture rule schema"):
        validator.validate({})


@pytest.mark.parametrize("valid", [True, False])
def test_service_validates_parsed_output_and_keeps_original_text(environment, valid_rule, valid):
    if not valid:
        valid_rule["rule"]["action"] = "UNKNOWN"
    text = "  ```json\n" + json.dumps(valid_rule) + "\n```  "
    response = RuleGenerationService(environment.retriever, FakeRuleModel(text)).generate(
        RuleGenerationRequest(requirement="Only PaymentService may depend on PaymentGateway.", use_rag=False))
    assert response.json_valid is True
    assert response.schema_valid is valid
    assert bool(response.validation_errors) is not valid
    assert response.generated_text == text and response.rule == valid_rule


@pytest.mark.parametrize("valid", [True, False])
def test_api_reports_schema_validity_without_discarding_the_rule(environment, valid_rule, valid):
    if not valid:
        valid_rule["rule"]["action"] = "UNKNOWN"
    text = json.dumps(valid_rule)

    async def check():
        app = create_app(environment.config, model=FakeRuleModel(text))
        async with app.router.lifespan_context(app):
            status, response = await request_json(app, "/rules/generate", {"requirement": "Deny access.", "use_rag": False})
            assert status == 200 and response["json_valid"] is True
            assert response["schema_valid"] is valid
            assert bool(response["validation_errors"]) is not valid
            assert response["generated_text"] == text and response["rule"] == valid_rule
            if not valid:
                assert response["validation_errors"][0]["path"] == "rule.action"

    asyncio.run(check())


def test_json_null_is_parse_valid_but_schema_invalid(environment):
    response = RuleGenerationService(environment.retriever, FakeRuleModel("null")).generate(
        RuleGenerationRequest(requirement="Deny access.", use_rag=False))
    assert response.json_valid and not response.schema_valid
    assert response.rule is None and response.validation_errors[0].path == "$"
