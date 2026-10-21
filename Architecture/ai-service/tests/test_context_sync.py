import asyncio
import json
from dataclasses import replace

import pytest

from app.context_loader import ContextLoadError, ProjectContextLoader
from app.main import create_app
from test_inference import FakeRuleModel
from test_rag import component, custom_rule, edge, environment, request_json, store


def replacement():
    return {
        "schema_version": "1.0", "project_name": "orders", "project_root": ".",
        "components": [component("orders.OrderService"), component("orders.OrderRepository", "REPOSITORY")],
        "relationships": [edge("orders.OrderService", "orders.OrderRepository")],
    }


def test_sync_persists_metadata_and_updates_status(environment, caplog):
    application = create_app(environment.config, embedder=environment.embedder)

    async def scenario():
        async with application.router.lifespan_context(application):
            with caplog.at_level("INFO"):
                status, response = await request_json(application, "/context/project", replacement(), method="PUT")
            assert status == 200
            assert response == {"updated": True, "project_name": "orders", "components": 2,
                                "relationships": 1, "rag_invalidated": True}
            assert await request_json(application, "/context/status", method="GET") == (
                200, {"loaded": True, "project_name": "orders", "components": 2, "relationships": 1})
            assert json.loads(environment.context_path.read_text(encoding="utf-8")) == replacement()
            assert application.state.context_loader.get_context().project_name == "orders"
            assert environment.embedder.document_calls == 0  # Rebuilding is deferred until retrieval.

    asyncio.run(scenario())
    assert "orders: 2 components, 1 relationships; RAG index invalidated" in caplog.text
    assert "OrderService" not in caplog.text


def test_sync_initializes_a_missing_context_file_and_directory(environment):
    path = environment.context_path.parent / "new-storage" / "project_context.json"
    config = replace(environment.config, project_context_path=path)
    application = create_app(config, embedder=environment.embedder)

    async def scenario():
        async with application.router.lifespan_context(application):
            assert await request_json(application, "/context/status", method="GET") == (200, {"loaded": False})
            assert (await request_json(application, "/context/project", replacement(), method="PUT"))[0] == 200
            assert path.is_file()
            assert ProjectContextLoader(path).load().project_name == "orders"

    asyncio.run(scenario())


@pytest.mark.parametrize("mutate", [
    lambda data: data.pop("schema_version"),
    lambda data: data.update(schema_version="2.0"),
    lambda data: data.update(project_name=""),
    lambda data: data.pop("project_root"),
    lambda data: data.update(components="not an array"),
    lambda data: data.pop("relationships"),
    lambda data: data["components"][0].update(entity_type="METHOD"),
    lambda data: data["components"][0].update(source_code="class Secret {}"),
    lambda data: data["relationships"][0].update(relationship="UNKNOWN"),
    lambda data: data.update(source_code="class Secret {}"),
])
def test_invalid_sync_preserves_disk_memory_and_index(environment, mutate):
    application = create_app(environment.config, embedder=environment.embedder)
    original_bytes = environment.context_path.read_bytes()
    incoming = replacement()
    mutate(incoming)

    async def scenario():
        async with application.router.lifespan_context(application):
            retriever = application.state.rag_retriever
            retriever.build_index()
            original_context = application.state.context_loader.get_context()
            original_index = retriever._snapshot
            status, response = await request_json(application, "/context/project", incoming, method="PUT")
            assert status == 422
            assert response["detail"]
            assert application.state.context_loader.get_context() is original_context
            assert retriever._snapshot is original_index
            assert environment.context_path.read_bytes() == original_bytes

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["replace", "fsync"])
def test_write_failure_preserves_disk_memory_and_index(environment, monkeypatch, operation):
    application = create_app(environment.config, embedder=environment.embedder)
    original_bytes = environment.context_path.read_bytes()

    def fail(*args):
        raise PermissionError("Test storage failure")

    async def scenario():
        async with application.router.lifespan_context(application):
            retriever = application.state.rag_retriever
            retriever.build_index()
            original_index = retriever._snapshot
            original_context = application.state.context_loader.get_context()
            monkeypatch.setattr(f"app.context_loader.os.{operation}", fail)
            status, response = await request_json(application, "/context/project", replacement(), method="PUT")
            assert status == 503
            assert "Cannot store project context" in response["detail"]
            assert application.state.context_loader.get_context() is original_context
            assert retriever._snapshot is original_index
            assert environment.context_path.read_bytes() == original_bytes
            assert not list(environment.context_path.parent.glob(".project-context-*.tmp"))

    asyncio.run(scenario())


def test_loader_revalidates_input_before_replacing_context(environment):
    original = environment.loader.get_context()
    original_bytes = environment.context_path.read_bytes()
    with pytest.raises(ContextLoadError, match="Invalid project context structure"):
        environment.loader.replace({"project_name": "invalid"})
    invalid_model = original.model_copy(deep=True)
    invalid_model.schema_version = "wrong"
    with pytest.raises(ContextLoadError, match="schema_version"):
        environment.loader.replace(invalid_model)
    assert environment.loader.get_context() is original
    assert environment.context_path.read_bytes() == original_bytes


def test_next_generation_rebuilds_new_context_and_preserves_rules_and_model(environment):
    store(environment.custom_path, {"rules": [custom_rule(environment)]})
    rule_files = (environment.base_path.read_bytes(), environment.custom_path.read_bytes())
    model = FakeRuleModel()
    application = create_app(environment.config, embedder=environment.embedder, model=model)

    async def scenario():
        async with application.router.lifespan_context(application):
            retriever = application.state.rag_retriever
            # Generate once so the same model is already loaded before synchronization.
            assert (await request_json(application, "/rules/generate", {"requirement": "PaymentGateway access"}))[0] == 200
            assert model.is_loaded and retriever.is_indexed
            assert environment.embedder.document_calls == 1
            assert (await request_json(application, "/context/project", replacement(), method="PUT"))[0] == 200
            assert not retriever.is_indexed
            assert model.is_loaded and len(model.messages) == 1
            assert environment.embedder.document_calls == 1
            status, result = await request_json(application, "/rules/generate", {"requirement": "OrderService access"})
            assert status == 200 and result["schema_valid"]
            assert environment.embedder.document_calls == 2
            assert any("orders.OrderService" in doc.text for doc in retriever.documents)
            assert not any(doc.source_id == "demo.PaymentService" for doc in retriever.documents)
            assert sum(doc.document_type == "BASE_RULE" for doc in retriever.documents) == 8
            assert any(doc.source_id == "PAYMENT_GATEWAY_ACCESS" for doc in retriever.documents)
            assert all(doc["project_name"] == "orders" for doc in result["retrieved_context"] if doc["document_type"] in {"COMPONENT", "RELATIONSHIP"})
            assert "OrderService" in model.messages[-1][1]["content"]
            assert len(model.messages) == 2

    asyncio.run(scenario())
    assert (environment.base_path.read_bytes(), environment.custom_path.read_bytes()) == rule_files
