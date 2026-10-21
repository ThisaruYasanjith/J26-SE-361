import copy
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from jsonschema import Draft7Validator

from app.config import ServiceConfig
from app.conformance_engine import ConformanceEngine, ConformanceError, package_matches
from app.custom_rule_store import CustomRuleStore, CustomRuleStoreError
from app.models import ProjectContext


def entity(name, spring_type="NONE", entity_type="CLASS"):
    return {
        "name": name, "entity_type": entity_type, "spring_type": spring_type,
        "package": name.rsplit(".", 1)[0], "annotations": [],
        "file_path": "src/main/java/" + name.replace(".", "/") + ".java",
        "source_location": {"start_line": 3, "end_line": 30},
    }


def relationship(source, target, kind="DEPENDS_ON", location=None):
    edge = {"source": source, "target": target, "relationship": kind}
    if location:
        edge["source_location"] = location
    return edge


def make_rule(rule_id="CUSTOM_001", source="PaymentService", target="PaymentGateway", action="DENY", *,
              source_type="COMPONENT", target_type="COMPONENT", relationship="DEPENDS_ON",
              rule_type="COMPONENT_ACCESS", exception=False):
    return {"rule_id": rule_id, "status": "VALID", "reason_code": None, "rule": {
        "rule_type": rule_type, "source": {"entity_type": source_type, "name": source},
        "relationship": relationship, "target": {"entity_type": target_type, "name": target},
        "action": action, "scope": {"type": "PROJECT", "value": None}, "is_exception": exception,
    }}


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def rig(tmp_path):
    names = {
        "controller": "demo.controller.AdminController", "controller2": "demo.controller.PaymentController",
        "service": "demo.service.PaymentService", "reporting": "demo.service.ReportingService",
        "repository": "demo.repository.PaymentRepository", "gateway": "demo.gateway.PaymentGateway",
    }
    data = {"schema_version": "1.0", "project_name": "payments", "project_root": ".", "components": [
        entity(names["controller"], "CONTROLLER"), entity(names["controller2"], "CONTROLLER"),
        entity(names["service"], "SERVICE"), entity(names["reporting"], "SERVICE"),
        entity(names["repository"], "REPOSITORY", "INTERFACE"), entity(names["gateway"], "NONE", "INTERFACE"),
    ], "relationships": []}
    base_rules = json.loads(ServiceConfig().base_rules_path.read_text(encoding="utf-8"))
    base_path, custom_path = tmp_path / "base.json", tmp_path / "custom.json"
    write(base_path, base_rules)
    write(custom_path, {"rules": []})
    return SimpleNamespace(data=data, names=names, base_rules=base_rules, base_path=base_path, custom_path=custom_path,
                           engine=ConformanceEngine(base_path, CustomRuleStore(custom_path)))


def evaluate(rig, custom=(), *, base=None):
    write(rig.base_path, rig.base_rules if base is None else base)
    write(rig.custom_path, {"rules": list(custom)})
    return rig.engine.check(ProjectContext.model_validate(rig.data))


@pytest.mark.parametrize("source,target", [("controller", "service"), ("service", "repository")])
def test_layer_permissions_are_optional_and_allow_matching_edges(rig, source, target):
    assert evaluate(rig).conformant  # ALLOW never requires an edge to exist.
    rig.data["relationships"] = [relationship(rig.names[source], rig.names[target])]
    assert evaluate(rig).conformant


@pytest.mark.parametrize("source,target,rule_id", [
    ("controller", "repository", "LAYER_CONTROLLER_REPOSITORY_DENY"),
    ("repository", "service", "LAYER_REPOSITORY_SERVICE_DENY"),
    ("repository", "controller", "LAYER_REPOSITORY_CONTROLLER_DENY"),
])
def test_base_layer_denials(rig, source, target, rule_id):
    rig.data["relationships"] = [relationship(rig.names[source], rig.names[target])]
    result = evaluate(rig)
    assert not result.conformant
    assert [(item.rule_id, item.source, item.target) for item in result.violations] == [
        (rule_id, rig.names[source], rig.names[target])]
    assert result.summary.model_dump() == {"total": 1, "base_rule_violations": 1, "custom_rule_violations": 0}


@pytest.mark.parametrize("spring_type,segment", [("CONTROLLER", "controller"), ("SERVICE", "service"), ("REPOSITORY", "repository")])
@pytest.mark.parametrize("correct", [True, False])
def test_base_package_placement_uses_spring_metadata(rig, spring_type, segment, correct):
    package = f"com.example.order.{segment}" if correct else f"com.example.{segment}s"
    rig.data["components"] = [entity(f"{package}.MisleadingName", spring_type)]
    result = evaluate(rig)
    assert result.conformant == correct
    if not correct:
        assert result.violations[0].rule_id == f"PACKAGE_{spring_type}_REQUIRE"
        assert result.violations[0].relationship == "LOCATED_IN"


@pytest.mark.parametrize("package,selector,expected", [
    ("com.example.controller", "controller", True), ("com.example.order.controller", "controller", True),
    ("com.example.controllers", "controller", False), ("com.example.controllerish", "controller", False),
    ("com.serviceable", "service", False), ("", "service", False),
    ("com.example.service.internal", "com.example.service", True),
    ("com.example.services", "com.example.service", False), ("other.com.example.service", "com.example.service", False),
])
def test_package_matching_boundaries(package, selector, expected):
    assert package_matches(package, selector) == expected


@pytest.mark.parametrize("name", ["PaymentService", "demo.service.PaymentService"])
def test_specific_deny_resolves_simple_and_qualified_names(rig, name):
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"])]
    result = evaluate(rig, [make_rule(source=name)])
    assert result.summary.custom_rule_violations == 1
    assert result.violations[0].rule_id == "CUSTOM_001"


def test_class_interface_and_package_selectors(rig):
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"])]
    rule = make_rule(source_type="CLASS", target_type="INTERFACE")
    assert evaluate(rig, [rule]).summary.custom_rule_violations == 1
    rule["rule"]["source"] = {"entity_type": "PACKAGE", "name": "demo.service"}
    assert evaluate(rig, [rule]).summary.custom_rule_violations == 1
    rule["rule"]["target"]["entity_type"] = "CLASS"
    assert evaluate(rig, [rule]).conformant  # An interface is not silently treated as a class.


@pytest.mark.parametrize("action", ["ALLOW", "ONLY"])
def test_permission_and_only_holder_do_not_create_false_violations(rig, action):
    rule = make_rule(action=action)
    assert evaluate(rig, [rule]).conformant
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"])]
    assert evaluate(rig, [rule]).conformant


def test_only_restricts_incoming_access_not_the_holders_other_dependencies(rig):
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"]),
                                 relationship(rig.names["service"], rig.names["repository"]),
                                 relationship(rig.names["reporting"], rig.names["gateway"])]
    result = evaluate(rig, [make_rule(action="ONLY")])
    assert len(result.violations) == 1
    violation = result.violations[0]
    assert violation.source == rig.names["reporting"] and violation.target == rig.names["gateway"]
    assert "Only PaymentService may depend on" in violation.message


@pytest.mark.parametrize("present", [True, False])
def test_dependency_require_is_existential_per_source(rig, present):
    if present:
        rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"])]
    result = evaluate(rig, [make_rule(action="REQUIRE")])
    assert result.conformant == present
    if not present:
        assert result.violations[0].source == rig.names["service"]
        assert result.violations[0].start_line == 3


def test_require_layer_target_needs_one_matching_target_not_every_target(rig):
    rig.data["components"].append(entity("demo.repository.OtherRepository", "REPOSITORY"))
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["repository"])]
    rule = make_rule(target="REPOSITORY", target_type="LAYER", action="REQUIRE")
    assert evaluate(rig, [rule]).conformant


@pytest.mark.parametrize("kind", ["CALLS", "IMPORTS", "EXTENDS", "IMPLEMENTS"])
def test_other_analyzed_relationships_use_their_exact_type(rig, kind):
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"], kind)]
    assert evaluate(rig, [make_rule(relationship=kind)]).summary.custom_rule_violations == 1
    assert evaluate(rig, [make_rule()]).conformant


def test_custom_package_placement_and_multiple_rules(rig):
    placement = make_rule(source="PaymentService", target="application", target_type="PACKAGE",
                          relationship="LOCATED_IN", action="REQUIRE", rule_type="PACKAGE_PLACEMENT")
    dependency = make_rule("CUSTOM_002", action="REQUIRE")
    result = evaluate(rig, [placement, dependency])
    assert result.summary.custom_rule_violations == 2
    assert {item.relationship for item in result.violations} == {"LOCATED_IN", "DEPENDS_ON"}


def test_specific_exception_suppresses_only_the_matching_base_violation(rig):
    rig.data["relationships"] = [relationship(rig.names["controller"], rig.names["repository"]),
                                 relationship(rig.names["controller2"], rig.names["repository"])]
    exception = make_rule(source="AdminController", target="PaymentRepository", action="ALLOW", exception=True)
    result = evaluate(rig, [exception])
    assert [item.source for item in result.violations] == [rig.names["controller2"]]


def test_exception_suppresses_matching_broad_custom_and_base_restrictions_in_any_order(rig):
    rig.data["relationships"] = [relationship(rig.names["controller"], rig.names["repository"])]
    broad = make_rule(source="CONTROLLER", target="REPOSITORY", source_type="LAYER", target_type="LAYER")
    exception = make_rule("CUSTOM_002", source="AdminController", target="PaymentRepository", action="ALLOW", exception=True)
    first = evaluate(rig, [broad, exception])
    second = evaluate(rig, [exception, broad])
    assert first.conformant and first.model_dump() == second.model_dump()


def test_equal_specificity_exception_restrictions_win_instead_of_storage_order(rig):
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"])]
    deny = make_rule(exception=True)
    allow = make_rule("CUSTOM_002", action="ALLOW", exception=True)
    assert not evaluate(rig, [deny, allow]).conformant


@pytest.mark.parametrize("marker", ["flag", "rule_type"])
def test_exception_overrides_a_specific_custom_denial_at_equal_specificity(rig, marker):
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"])]
    allow = make_rule("CUSTOM_002", action="ALLOW", exception=marker == "flag",
                      rule_type="EXCEPTION" if marker == "rule_type" else "COMPONENT_ACCESS")
    assert evaluate(rig, [make_rule(), allow]).conformant
    allow["rule"].update(is_exception=False, rule_type="COMPONENT_ACCESS")
    assert not evaluate(rig, [make_rule(), allow]).conformant


def test_broad_allow_does_not_silently_waive_base_denial(rig):
    rig.data["relationships"] = [relationship(rig.names["controller"], rig.names["repository"])]
    allow = make_rule(source="CONTROLLER", target="REPOSITORY", action="ALLOW", source_type="LAYER", target_type="LAYER")
    assert not evaluate(rig, [allow]).conformant


def test_overlapping_package_permission_is_not_assumed_narrower_than_a_layer(rig):
    rig.data["relationships"] = [relationship(rig.names["controller"], rig.names["repository"])]
    allow = make_rule(source="demo.controller", target="PaymentRepository", action="ALLOW", source_type="PACKAGE")
    assert not evaluate(rig, [allow]).conformant


def test_package_precedence_is_based_on_selector_domains_not_incidental_project_members(rig):
    rig.data["components"] = [entity("demo.foo.bar.Service")]
    rig.data["relationships"] = [relationship("demo.foo.bar.Service", "external.PaymentGateway")]
    broad = make_rule(source="foo", source_type="PACKAGE", target="external.PaymentGateway")
    overlap = make_rule("CUSTOM_002", source="bar", source_type="PACKAGE", target="external.PaymentGateway",
                        action="ALLOW", exception=True)
    assert not evaluate(rig, [broad, overlap], base=[]).conformant


def test_specific_custom_permission_overrides_broader_base_and_custom_denials(rig):
    rig.data["relationships"] = [relationship(rig.names["controller"], rig.names["repository"])]
    broad = make_rule(source="CONTROLLER", target="REPOSITORY", source_type="LAYER", target_type="LAYER")
    specific = make_rule("CUSTOM_002", source="AdminController", target="PaymentRepository", action="ALLOW")
    assert evaluate(rig, [broad, specific]).conformant


def test_only_restriction_requires_exception_to_allow_another_equally_specific_source(rig):
    rig.data["relationships"] = [relationship(rig.names["reporting"], rig.names["gateway"])]
    allow = make_rule("CUSTOM_002", source="ReportingService", action="ALLOW")
    assert not evaluate(rig, [make_rule(action="ONLY"), allow]).conformant
    allow["rule"]["is_exception"] = True
    assert evaluate(rig, [make_rule(action="ONLY"), allow]).conformant


def test_exception_does_not_waive_a_different_relationship_or_target(rig):
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"], "CALLS")]
    exception = make_rule("CUSTOM_002", action="ALLOW", exception=True)
    assert not evaluate(rig, [make_rule(relationship="CALLS"), exception]).conformant
    exception["rule"].update(relationship="CALLS", target={"entity_type": "COMPONENT", "name": "PaymentRepository"})
    assert not evaluate(rig, [make_rule(relationship="CALLS"), exception]).conformant


def test_ordinary_permission_cannot_override_an_exception_denial(rig):
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"])]
    deny = make_rule(source="SERVICE", source_type="LAYER", exception=True)
    allow = make_rule("CUSTOM_002", action="ALLOW")
    assert not evaluate(rig, [deny, allow]).conformant


def test_explicit_alternative_package_exception_can_waive_placement_requirement(rig):
    rig.data["components"] = [entity("demo.controller.MisplacedAuditService", "SERVICE")]
    exception = make_rule(source="MisplacedAuditService", target="controller", target_type="PACKAGE",
                          relationship="LOCATED_IN", action="ALLOW", exception=True)
    assert evaluate(rig, [exception]).conformant


def test_allow_is_not_a_waiver_for_a_missing_required_dependency(rig):
    permission = make_rule("CUSTOM_002", action="ALLOW", exception=True)
    assert not evaluate(rig, [make_rule(action="REQUIRE"), permission]).conformant


def test_missing_entities_are_not_invented(rig):
    assert evaluate(rig, [make_rule(source="MissingSource", action="REQUIRE")]).conformant
    missing_target = make_rule(target="MissingTarget", action="REQUIRE")
    result = evaluate(rig, [missing_target])
    assert not result.conformant and result.violations[0].target == "MissingTarget"
    assert evaluate(rig, [make_rule(target="MissingTarget")]).conformant
    rig.data["relationships"] = [relationship(rig.names["reporting"], rig.names["gateway"])]
    assert not evaluate(rig, [make_rule(source="MissingSource", action="ONLY")]).conformant


def test_ambiguous_simple_name_fails_clearly_instead_of_matching_multiple_entities(rig):
    rig.data["components"].append(entity("other.service.PaymentService", "SERVICE"))
    with pytest.raises(ConformanceError, match="Ambiguous entity name PaymentService"):
        evaluate(rig, [make_rule()])
    assert evaluate(rig, [make_rule(source=rig.names["service"])]).conformant


def test_duplicate_canonical_entities_are_reported(rig):
    rig.data["components"].append(copy.deepcopy(rig.data["components"][0]))
    with pytest.raises(ConformanceError, match="Duplicate project entity"):
        evaluate(rig)


def test_source_evidence_locations_and_declaration_fallback(rig):
    rig.data["relationships"] = [relationship(rig.names["service"], rig.names["gateway"],
                                             location={"start_line": 12, "end_line": 14})]
    violation = evaluate(rig, [make_rule()]).violations[0]
    assert (violation.start_line, violation.end_line) == (12, 14)
    assert violation.file_path == "src/main/java/demo/service/PaymentService.java"
    rig.data["relationships"][0].pop("source_location")
    violation = evaluate(rig, [make_rule()]).violations[0]
    assert (violation.start_line, violation.end_line) == (3, 30)


def test_results_ids_and_counts_are_deterministic_and_schema_compatible(rig):
    rig.data["relationships"] = [relationship(rig.names["controller"], rig.names["repository"]),
                                 relationship(rig.names["service"], rig.names["gateway"])]
    rules = [make_rule(), make_rule("CUSTOM_002", action="REQUIRE", source="ReportingService")]
    first = evaluate(rig, rules)
    rig.data["components"].reverse()
    rig.data["relationships"].reverse()
    rig.base_rules.reverse()
    second = evaluate(rig, list(reversed(rules)))
    assert first.model_dump() == second.model_dump()
    schema = json.loads((ServiceConfig().base_rules_path.parent.parent / "schemas" / "violation.schema.json").read_text(encoding="utf-8"))
    for violation in first.violations:
        Draft7Validator(schema).validate(violation.model_dump(exclude_none=True))
    assert first.summary.model_dump() == {"total": 3, "base_rule_violations": 1, "custom_rule_violations": 2}
    assert first.rule_metadata["CUSTOM_001"].model_dump() == {"rule_type": "COMPONENT_ACCESS", "rule_source": "CUSTOM"}


def test_identical_evidence_is_deduplicated_but_distinct_occurrences_are_preserved(rig):
    first = relationship(rig.names["service"], rig.names["gateway"], location={"start_line": 5, "end_line": 5})
    second = copy.deepcopy(first)
    second["source_location"] = {"start_line": 8, "end_line": 8}
    rig.data["relationships"] = [first, copy.deepcopy(first), second]
    result = evaluate(rig, [make_rule()])
    assert len(result.violations) == 2
    assert len({item.violation_id for item in result.violations}) == 2


@pytest.mark.parametrize("status", ["AMBIGUOUS", "UNSUPPORTED", "PENDING", "REJECTED"])
def test_unapproved_entries_in_custom_storage_are_not_evaluated(rig, status):
    write(rig.custom_path, {"rules": [{"rule_id": "CUSTOM_001", "status": status, "rule": None, "reason_code": "MISSING_TARGET"}]})
    with pytest.raises(CustomRuleStoreError):
        rig.engine.check(ProjectContext.model_validate(rig.data))


@pytest.mark.parametrize("contents", ["{", "{}", '[{"status":"VALID"}]'])
def test_invalid_base_storage_fails_instead_of_claiming_conformance(rig, contents):
    rig.base_path.write_text(contents, encoding="utf-8")
    with pytest.raises(ConformanceError):
        rig.engine.check(ProjectContext.model_validate(rig.data))


def test_missing_custom_store_is_an_empty_approved_collection(rig):
    rig.custom_path.unlink()
    assert rig.engine.check(ProjectContext.model_validate(rig.data)).conformant


def test_duplicate_rule_ids_across_stores_are_rejected(rig):
    with pytest.raises(ConformanceError, match="duplicate rule ID"):
        evaluate(rig, [make_rule(rig.base_rules[0]["rule_id"])])


@pytest.mark.parametrize("rule", [
    make_rule(target="service", target_type="COMPONENT", relationship="LOCATED_IN"),
    make_rule(rule_type="PACKAGE_PLACEMENT"),
    make_rule(source="UNKNOWN", source_type="LAYER"),
])
def test_schema_valid_but_unsupported_semantic_combinations_fail_clearly(rig, rule):
    with pytest.raises(ConformanceError):
        evaluate(rig, [rule])


def test_engine_imports_no_inference_or_embedding_modules():
    result = subprocess.run([sys.executable, "-c", "import sys; import app.conformance_engine; "
                             "assert not {'app.inference', 'app.rag', 'torch', 'transformers', 'sentence_transformers', 'faiss'} & sys.modules.keys()"],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
