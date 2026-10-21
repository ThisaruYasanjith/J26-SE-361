import asyncio
import json

from jsonschema import Draft7Validator

from app.config import ServiceConfig
from app.main import create_app
from test_conformance_engine import entity, make_rule, relationship, rig, write
from test_rag import request_json


class UnavailableModel:
    model_id = "unavailable-test-model"
    is_loaded = False

    def generate(self, messages):
        raise AssertionError("Conformance must never call model inference")


class ForbiddenEmbedder:
    def embed_documents(self, texts):
        raise AssertionError("Conformance must never build embeddings")

    def embed_query(self, query):
        raise AssertionError("Conformance must never retrieve embeddings")


def application(rig, *, has_context=True):
    context_path = rig.base_path.parent / "context.json"
    if has_context:
        write(context_path, rig.data)
    return create_app(ServiceConfig(project_context_path=context_path, base_rules_path=rig.base_path,
                                    custom_rules_path=rig.custom_path),
                      model=UnavailableModel(), embedder=ForbiddenEmbedder())


def test_endpoint_conformant_without_a_loaded_model_or_rag_index(rig):
    rig.data["relationships"] = [relationship(rig.names["controller"], rig.names["service"]),
                                 relationship(rig.names["service"], rig.names["repository"])]
    app = application(rig)

    async def scenario():
        async with app.router.lifespan_context(app):
            status, result = await request_json(app, "/conformance/check")
            assert status == 200
            assert result == {"project_name": "payments", "conformant": True, "violations": [], "rule_metadata": {},
                              "summary": {"total": 0, "base_rule_violations": 0, "custom_rule_violations": 0}}
            assert not app.state.rag_retriever.is_indexed
            assert await request_json(app, "/model/status", method="GET") == (
                200, {"loaded": False, "model_id": "unavailable-test-model"})

    asyncio.run(scenario())


def test_endpoint_without_context_returns_clear_409(rig):
    app = application(rig, has_context=False)

    async def scenario():
        async with app.router.lifespan_context(app):
            status, response = await request_json(app, "/conformance/check")
            assert status == 409
            assert "Analyze and sync a project first" in response["detail"]
            assert "conformant" not in response

    asyncio.run(scenario())


def test_endpoint_uses_synced_context_and_newly_approved_rules_with_correct_counts(rig, caplog):
    app = application(rig)
    incoming = rig.data | {"relationships": [relationship(rig.names["controller"], rig.names["repository"],
                                                            location={"start_line": 8, "end_line": 8}),
                                            relationship(rig.names["reporting"], rig.names["gateway"])]}
    incoming["components"] = [*incoming["components"], entity("demo.controller.MisplacedAuditService", "SERVICE")]

    async def scenario():
        async with app.router.lifespan_context(app):
            assert (await request_json(app, "/context/project", incoming, method="PUT"))[0] == 200
            rule = make_rule(action="ONLY")
            status, approval = await request_json(app, "/rules/approve", {"rule": rule})
            assert status == 200
            with caplog.at_level("INFO"):
                status, response = await request_json(app, "/conformance/check")
            assert status == 200 and not response["conformant"]
            assert response["summary"] == {"total": 3, "base_rule_violations": 2, "custom_rule_violations": 1}
            assert {item["rule_id"] for item in response["violations"]} == {
                "LAYER_CONTROLLER_REPOSITORY_DENY", "PACKAGE_SERVICE_REQUIRE", approval["rule_id"]}
            assert response["rule_metadata"][approval["rule_id"]] == {"rule_source": "CUSTOM", "rule_type": "COMPONENT_ACCESS"}
            assert next(item for item in response["violations"] if item["source"] == rig.names["controller"])["start_line"] == 8
            schema = json.loads((ServiceConfig().base_rules_path.parent.parent / "schemas" / "violation.schema.json").read_text(encoding="utf-8"))
            for violation in response["violations"]:
                Draft7Validator(schema).validate(violation)
            assert (await request_json(app, "/conformance/check"))[1] == response
            assert not app.state.rag_retriever.is_indexed

    asyncio.run(scenario())
    assert "3 violations (2 base, 1 custom)" in caplog.text
    assert "MisplacedAuditService" not in caplog.text


def test_endpoint_applies_newly_approved_exception_without_retrieval(rig):
    rig.data["relationships"] = [relationship(rig.names["controller"], rig.names["repository"])]
    app = application(rig)

    async def scenario():
        async with app.router.lifespan_context(app):
            assert (await request_json(app, "/conformance/check"))[1]["summary"]["total"] == 1
            exception = make_rule(source="AdminController", target="PaymentRepository", action="ALLOW", exception=True)
            assert (await request_json(app, "/rules/approve", {"rule": exception}))[0] == 200
            status, response = await request_json(app, "/conformance/check")
            assert status == 200 and response["conformant"]
            assert response["summary"]["total"] == 0
            assert not app.state.rag_retriever.is_indexed

    asyncio.run(scenario())


def test_invalid_stored_rules_return_service_error_instead_of_false_conformance(rig):
    write(rig.custom_path, {"rules": [{"status": "AMBIGUOUS", "rule": None, "reason_code": "MISSING_TARGET"}]})
    app = application(rig)

    async def scenario():
        async with app.router.lifespan_context(app):
            status, response = await request_json(app, "/conformance/check")
            assert status == 503 and "invalid" in response["detail"]
            assert "conformant" not in response

    asyncio.run(scenario())


def test_ambiguous_rule_name_returns_readable_service_error(rig):
    rig.data["components"].append(entity("other.service.PaymentService", "SERVICE"))
    write(rig.custom_path, {"rules": [make_rule()]})
    app = application(rig)

    async def scenario():
        async with app.router.lifespan_context(app):
            status, response = await request_json(app, "/conformance/check")
            assert status == 503 and "use a qualified name" in response["detail"]

    asyncio.run(scenario())
