import asyncio
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.custom_rule_store import CustomRuleStore, CustomRuleStoreError
from app.main import create_app
from test_conflict_detector import saved_rule
from test_rag import environment, request_json
from test_rule_validator import valid_rule


def write_rules(path, rules):
    path.write_text(json.dumps({"rules": rules}), encoding="utf-8")


def test_empty_or_missing_store_is_empty(tmp_path):
    path = tmp_path / "custom.json"
    assert CustomRuleStore(path).load_rules() == []
    assert not path.exists()
    write_rules(path, [])
    assert CustomRuleStore(path).load_rules() == []


def test_loading_sorts_existing_rules_without_rewriting_file(tmp_path, valid_rule):
    path = tmp_path / "custom.json"
    write_rules(path, [saved_rule(valid_rule, "CUSTOM_010"), saved_rule(valid_rule, "CUSTOM_002")])
    original = path.read_bytes()
    assert [entry["rule_id"] for entry in CustomRuleStore(path).load_rules()] == ["CUSTOM_002", "CUSTOM_010"]
    assert path.read_bytes() == original


def test_approval_persists_rule_with_backend_id_and_preserves_input(tmp_path, valid_rule):
    path = tmp_path / "new" / "custom.json"
    candidate = copy.deepcopy(valid_rule)
    candidate["rule_id"] = "MODEL_ID"
    before = copy.deepcopy(candidate)
    result = CustomRuleStore(path).approve_rule(candidate)
    assert result.model_dump() == {"approved": True, "rule_id": "CUSTOM_001", "conflicts_confirmed": False, "duplicate": False}
    stored = CustomRuleStore(path).load_rules()
    assert stored == [{**valid_rule, "rule_id": "CUSTOM_001"}]
    assert candidate == before


def test_ids_follow_the_highest_existing_number_including_gaps(tmp_path, valid_rule):
    path = tmp_path / "custom.json"
    write_rules(path, [saved_rule(valid_rule, "CUSTOM_999"), saved_rule(valid_rule, "CUSTOM_002")])
    valid_rule["rule"]["target"]["name"] = "OtherGateway"
    store = CustomRuleStore(path)
    assert store.approve_rule(valid_rule).rule_id == "CUSTOM_1000"
    assert [entry["rule_id"] for entry in store.load_rules()] == ["CUSTOM_002", "CUSTOM_999", "CUSTOM_1000"]


@pytest.mark.parametrize("kind", ["bad_action", "ambiguous", "unsupported", "non_object"])
def test_invalid_or_uncertain_candidate_never_changes_storage(tmp_path, valid_rule, kind):
    path = tmp_path / "custom.json"
    write_rules(path, [])
    original = path.read_bytes()
    if kind == "bad_action":
        valid_rule["rule"]["action"] = "PERMIT"
    elif kind in ("ambiguous", "unsupported"):
        valid_rule.update(status=kind.upper(), rule=None, reason_code="MISSING_TARGET")
    else:
        valid_rule = None
    with pytest.raises(CustomRuleStoreError) as error:
        CustomRuleStore(path).approve_rule(valid_rule)
    assert error.value.status_code == 422 and error.value.validation_errors
    assert path.read_bytes() == original


@pytest.mark.parametrize("content", ["{", "[]", '{"rules":null}', '{"rules":[],"extra":1}',
                                    '{"rules":[{"status":"VALID"}]}'])
def test_invalid_storage_is_not_overwritten(tmp_path, valid_rule, content):
    path = tmp_path / "custom.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CustomRuleStoreError):
        CustomRuleStore(path).approve_rule(valid_rule)
    assert path.read_text(encoding="utf-8") == content


def test_stored_rules_require_unique_non_empty_ids(tmp_path, valid_rule):
    path = tmp_path / "custom.json"
    for entries in [[valid_rule], [saved_rule(valid_rule, " ")], [saved_rule(valid_rule), saved_rule(valid_rule)]]:
        write_rules(path, entries)
        with pytest.raises(CustomRuleStoreError):
            CustomRuleStore(path).load_rules()


def test_duplicate_is_idempotent_and_does_not_trigger_refresh(tmp_path, valid_rule):
    path = tmp_path / "custom.json"
    changed = []
    store = CustomRuleStore(path, on_change=lambda: changed.append(True))
    first = store.approve_rule(valid_rule)
    original = path.read_bytes()
    result = store.approve_rule({**valid_rule, "rule_id": "IGNORED"})
    assert result.duplicate and result.rule_id == first.rule_id
    assert path.read_bytes() == original and changed == [True]


def test_conflict_requires_confirmation_and_is_rechecked_when_approving(tmp_path, valid_rule):
    store = CustomRuleStore(tmp_path / "custom.json")
    candidate = copy.deepcopy(valid_rule)
    candidate["rule"].update(action="ALLOW", source={"entity_type": "COMPONENT", "name": "ReportingService"})
    assert not store.check_conflicts(candidate).has_conflict
    store.approve_rule(valid_rule)
    original = store.path.read_bytes()
    with pytest.raises(CustomRuleStoreError) as error:
        store.approve_rule(candidate)
    assert error.value.status_code == 409
    assert error.value.conflict_result.conflicts[0].existing_rule_id == "CUSTOM_001"
    assert store.path.read_bytes() == original
    result = store.approve_rule(candidate, confirm_conflicts=True)
    assert result.rule_id == "CUSTOM_002" and result.conflicts_confirmed
    assert len(CustomRuleStore(store.path).load_rules()) == 2
    assert store.approve_rule(valid_rule).duplicate


def test_exception_flag_is_preserved_in_storage(tmp_path, valid_rule):
    valid_rule["rule"]["is_exception"] = True
    store = CustomRuleStore(tmp_path / "custom.json")
    store.approve_rule(valid_rule)
    assert store.load_rules()[0]["rule"]["is_exception"] is True


def test_direct_store_confirmation_requires_a_boolean(tmp_path, valid_rule):
    store = CustomRuleStore(tmp_path / "custom.json")
    with pytest.raises(CustomRuleStoreError, match="must be a boolean"):
        store.approve_rule(valid_rule, confirm_conflicts="false")
    assert not store.path.exists()


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_failed_persistence_preserves_previous_file_and_cleans_temp(tmp_path, valid_rule, monkeypatch, failure):
    path = tmp_path / "custom.json"
    write_rules(path, [])
    original = path.read_bytes()
    changes = []
    store = CustomRuleStore(path, on_change=lambda: changes.append(True))

    def fail(*args):
        raise OSError("simulated write failure")

    with monkeypatch.context() as patch:
        patch.setattr("app.custom_rule_store.os." + failure, fail)
        with pytest.raises(CustomRuleStoreError, match="Cannot persist custom rules"):
            store.approve_rule(valid_rule)
    assert path.read_bytes() == original and changes == []
    assert list(tmp_path.glob("*.tmp")) == []
    assert store.approve_rule(valid_rule).rule_id == "CUSTOM_001"


def test_concurrent_approvals_share_a_transaction_lock(tmp_path, valid_rule):
    path = tmp_path / "custom.json"

    def approve(number):
        rule = copy.deepcopy(valid_rule)
        rule["rule"]["target"]["name"] = f"Gateway{number}"
        return CustomRuleStore(path).approve_rule(rule).rule_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(approve, range(8)))
    assert sorted(ids) == [f"CUSTOM_{i:03d}" for i in range(1, 9)]
    assert len(CustomRuleStore(path).load_rules()) == 8


def test_approved_rule_appears_in_existing_rag_builder(environment, valid_rule):
    result = CustomRuleStore(environment.custom_path).approve_rule(valid_rule)
    documents = environment.builder.build_documents(environment.loader.get_context())
    document = next(item for item in documents if item.source_id == result.rule_id)
    assert document.document_type == "CUSTOM_RULE"
    assert "PaymentService (COMPONENT)" in document.text and "Action: ONLY" in document.text


def test_api_workflow_conflicts_override_duplicate_and_rag_refresh(environment, valid_rule):
    async def check():
        app = create_app(environment.config, embedder=environment.embedder)
        async with app.router.lifespan_context(app):
            retriever = app.state.rag_retriever
            retriever.build_index()
            status, first = await request_json(app, "/rules/approve", {"rule": valid_rule})
            assert status == 200 and first["rule_id"] == "CUSTOM_001"
            assert not retriever.is_indexed and environment.embedder.document_calls == 1
            candidate = copy.deepcopy(valid_rule)
            candidate["rule"].update(action="ALLOW", source={"entity_type": "COMPONENT", "name": "ReportingService"})
            status, conflict = await request_json(app, "/rules/check-conflicts", {"rule": candidate})
            assert status == 200 and conflict["has_conflict"] and not conflict["duplicate"]
            assert conflict["conflicts"][0]["existing_rule_id"] == "CUSTOM_001"
            status, blocked = await request_json(app, "/rules/approve", {"rule": candidate, "confirm_conflicts": False})
            assert status == 409 and blocked["has_conflict"]
            status, approved = await request_json(app, "/rules/approve", {"rule": candidate, "confirm_conflicts": True})
            assert status == 200 and approved["conflicts_confirmed"] and approved["rule_id"] == "CUSTOM_002"
            status, duplicate = await request_json(app, "/rules/approve", {"rule": candidate})
            assert status == 200 and duplicate["duplicate"] and duplicate["rule_id"] == "CUSTOM_002"
            assert len(CustomRuleStore(environment.custom_path).load_rules()) == 2
            status, _ = await request_json(app, "/rag/retrieve", {"query": "PaymentGateway"})
            assert status == 200 and retriever.is_indexed
            assert environment.embedder.document_calls == 2
            assert {"CUSTOM_001", "CUSTOM_002"}.issubset({item.source_id for item in retriever.documents})
            assert not app.state.rule_generator.model.is_loaded

    asyncio.run(check())


@pytest.mark.parametrize("endpoint", ["/rules/approve", "/rules/check-conflicts"])
@pytest.mark.parametrize("kind", ["invalid", "uncertain"])
def test_api_rejects_ineligible_rules(environment, valid_rule, endpoint, kind):
    if kind == "invalid":
        valid_rule["rule"]["action"] = "INVALID"
    else:
        valid_rule.update(status="AMBIGUOUS", rule=None, reason_code="MISSING_TARGET")

    async def check():
        app = create_app(environment.config)
        async with app.router.lifespan_context(app):
            status, response = await request_json(app, endpoint, {"rule": valid_rule})
            assert status == 422 and response["validation_errors"]
            assert CustomRuleStore(environment.custom_path).load_rules() == []

    asyncio.run(check())


def test_api_confirmation_requires_a_boolean(environment, valid_rule):
    async def check():
        app = create_app(environment.config)
        async with app.router.lifespan_context(app):
            status, _ = await request_json(app, "/rules/approve", {"rule": valid_rule, "confirm_conflicts": "true"})
            assert status == 422

    asyncio.run(check())
