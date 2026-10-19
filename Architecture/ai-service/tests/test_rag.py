import asyncio
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import ServiceConfig
from app.context_loader import ProjectContextLoader
from app.main import create_app
from app.rag import (
    BGE_QUERY_PREFIX,
    DEFAULT_EMBEDDING_MODEL,
    ArchitectureRetriever,
    ContextDocumentBuilder,
    RAGError,
    SentenceTransformerEmbedder,
)


class FakeEmbedder:
    def __init__(self):
        self.document_calls = 0
        self.query_calls = 0
        self.fail = False

    def vector(self, text):
        terms = ["paymentservice", "paymentgateway", "reportingservice", "controller", "repositor", "must not"]
        return np.array([text.lower().count(term) for term in terms] + [1], dtype=np.float32)

    def embed_documents(self, texts):
        self.document_calls += 1
        if self.fail:
            raise RAGError("Test embedding failure")
        return np.stack([self.vector(text) for text in texts])

    def embed_query(self, query):
        self.query_calls += 1
        return self.vector(query)


def component(name, spring_type="SERVICE", entity_type="CLASS"):
    return {
        "name": name, "entity_type": entity_type, "spring_type": spring_type,
        "package": name.rsplit(".", 1)[0], "file_path": "src/main/java/" + name.replace(".", "/") + ".java",
        "annotations": ["Service"] if spring_type == "SERVICE" else [],
        "source_location": {"start_line": 1, "end_line": 4},
    }


def edge(source, target, relationship="DEPENDS_ON"):
    return {"source": source, "target": target, "relationship": relationship}


def store(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def environment(tmp_path):
    context = {
        "schema_version": "1.0", "project_name": "payments", "project_root": ".",
        "components": [component("demo.PaymentService"), component("demo.PaymentGateway", "NONE", "INTERFACE"),
                       component("demo.ReportingService")],
        "relationships": [edge("demo.PaymentService", "demo.PaymentGateway"),
                          edge("demo.PaymentService", "demo.PaymentGateway", "CALLS"),
                          edge("demo.ReportingService", "demo.PaymentGateway")],
    }
    context_path, base_path, custom_path = [tmp_path / name for name in ["context.json", "base.json", "custom.json"]]
    store(context_path, context)
    base_rules = json.loads(ServiceConfig().base_rules_path.read_text(encoding="utf-8"))
    store(base_path, base_rules)
    store(custom_path, {"rules": []})
    loader = ProjectContextLoader(context_path)
    loader.load()
    builder = ContextDocumentBuilder(base_path, custom_path)
    embedder = FakeEmbedder()
    config = ServiceConfig(project_context_path=context_path, base_rules_path=base_path, custom_rules_path=custom_path)
    return SimpleNamespace(context=context, context_path=context_path, base_path=base_path, custom_path=custom_path,
                           base_rules=base_rules, loader=loader, builder=builder, embedder=embedder, config=config,
                           retriever=ArchitectureRetriever(loader, builder, embedder))


def custom_rule(environment, exception=False):
    stored = copy.deepcopy(environment.base_rules[0])
    stored["rule_id"] = "PAYMENT_GATEWAY_ACCESS"
    stored["rule"].update(
        rule_type="EXCEPTION" if exception else "COMPONENT_ACCESS",
        source={"entity_type": "COMPONENT", "name": "PaymentService"},
        target={"entity_type": "COMPONENT", "name": "PaymentGateway"},
        action="ONLY", is_exception=exception,
    )
    return stored


def test_component_documents_preserve_real_metadata(environment):
    documents = environment.builder.build_documents(environment.loader.get_context())
    document = next(doc for doc in documents if doc.source_id == "demo.PaymentService")

    assert document.metadata == {"document_type": "COMPONENT", "source_id": "demo.PaymentService", "project_name": "payments"}
    for text in ["Component: PaymentService", "Qualified name: demo.PaymentService", "Spring type: SERVICE",
                 "Declaration type: CLASS", "Package: demo", "Annotations: Service", "File: src/main/java/demo/PaymentService.java"]:
        assert text in document.text
    assert "PaymentService depends on PaymentGateway." in document.text


def test_inheritance_is_recovered_from_context_relationships(environment):
    environment.context["relationships"] += [edge("demo.PaymentService", "demo.BaseService", "EXTENDS"),
                                             edge("demo.PaymentService", "demo.Auditable", "IMPLEMENTS"),
                                             edge("demo.PaymentGateway", "demo.ParentGateway", "EXTENDS")]
    store(environment.context_path, environment.context)
    documents = environment.builder.build_documents(environment.loader.reload())

    service = next(doc for doc in documents if doc.source_id == "demo.PaymentService")
    gateway = next(doc for doc in documents if doc.source_id == "demo.PaymentGateway")
    assert "Superclass: demo.BaseService" in service.text
    assert "Implemented interfaces: demo.Auditable" in service.text
    assert "Extended interfaces: demo.ParentGateway" in gateway.text


def test_relationship_documents_preserve_qualified_endpoints(environment):
    document = next(doc for doc in environment.builder.build_documents(environment.loader.get_context())
                    if doc.source_id == "demo.PaymentService CALLS demo.PaymentGateway")

    assert document.document_type == "RELATIONSHIP"
    assert "PaymentService CALLS PaymentGateway" in document.text
    assert "Source: demo.PaymentService (Spring type: SERVICE)" in document.text
    assert "Target: demo.PaymentGateway" in document.text


def test_base_rule_documents_keep_the_stored_rule_fields(environment):
    documents = [doc for doc in environment.builder.build_documents(environment.loader.get_context()) if doc.document_type == "BASE_RULE"]
    assert len(documents) == 8
    document = next(doc for doc in documents if doc.source_id == "LAYER_CONTROLLER_REPOSITORY_DENY")
    for text in ["LAYER_CONTROLLER_REPOSITORY_DENY", "LAYER_DEPENDENCY", "CONTROLLER (LAYER)",
                 "DEPENDS_ON", "REPOSITORY (LAYER)", "Action: DENY", "must not depend directly on"]:
        assert text in document.text


@pytest.mark.parametrize("exception", [False, True])
def test_loads_custom_rules_and_approved_exceptions(environment, exception):
    store(environment.custom_path, {"rules": [custom_rule(environment, exception)]})
    document = next(doc for doc in environment.builder.build_documents(environment.loader.get_context())
                    if doc.source_id == "PAYMENT_GATEWAY_ACCESS")

    assert document.document_type == ("EXCEPTION" if exception else "CUSTOM_RULE")
    assert "PaymentService (COMPONENT)" in document.text
    assert "PaymentGateway (COMPONENT)" in document.text
    assert "Action: ONLY" in document.text


def test_unusable_rule_envelopes_are_not_added_to_the_corpus(environment):
    store(environment.custom_path, {"rules": [{"status": "AMBIGUOUS", "rule": None, "reason_code": "MISSING_SOURCE"}]})
    assert len(environment.builder.build_documents(environment.loader.get_context())) == 14


def test_missing_optional_custom_file_is_allowed(environment):
    environment.custom_path.unlink()
    assert len(environment.builder.build_documents(environment.loader.get_context())) == 14


def test_document_order_does_not_depend_on_input_order(environment):
    first = environment.builder.build_documents(environment.loader.get_context())
    environment.context["components"].reverse()
    environment.context["relationships"].reverse()
    store(environment.context_path, environment.context)
    store(environment.base_path, list(reversed(environment.base_rules)))

    assert environment.builder.build_documents(environment.loader.reload()) == first


def test_builds_real_faiss_with_normalized_vectors(environment):
    assert environment.retriever.build_index() == 14
    assert environment.retriever.is_indexed
    assert len(environment.retriever.documents) == 14
    index = environment.retriever._snapshot.index
    assert index.ntotal == 14
    assert np.linalg.norm(index.reconstruct(0)) == pytest.approx(1.0)


def test_top_k_retrieval_returns_scores_and_metadata(environment):
    results = environment.retriever.retrieve("PaymentGateway", top_k=3)

    assert len(results) == 3
    assert results[0].document_type == "COMPONENT"
    assert results[0].source_id == "demo.PaymentGateway"
    assert results[0].project_name == "payments"
    assert results[0].text
    assert all(-1 <= result.score <= 1 for result in results)
    assert [result.score for result in results] == sorted([result.score for result in results], reverse=True)
    assert environment.embedder.document_calls == 1
    environment.retriever.retrieve("PaymentService", 1)
    assert environment.embedder.document_calls == 1


def test_query_retrieves_relevant_rule_documents(environment):
    results = environment.retriever.retrieve("Controllers must not directly access repositories.", 3)

    assert any(result.source_id == "LAYER_CONTROLLER_REPOSITORY_DENY" and result.document_type == "BASE_RULE" for result in results)


def test_query_can_retrieve_a_stored_custom_rule(environment):
    store(environment.custom_path, {"rules": [custom_rule(environment)]})
    results = environment.retriever.retrieve("Only PaymentService may depend on PaymentGateway.", 15)

    assert any(result.document_type == "CUSTOM_RULE" and result.source_id == "PAYMENT_GATEWAY_ACCESS" for result in results)


def test_top_k_larger_than_the_corpus_is_clamped(environment):
    assert len(environment.retriever.retrieve("PaymentGateway", 1000)) == 14


@pytest.mark.parametrize("top_k", [0, -1, 1.5, True, "5", None])
def test_invalid_top_k_is_rejected_before_embedding(environment, top_k):
    with pytest.raises(RAGError, match="positive integer"):
        environment.retriever.retrieve("PaymentGateway", top_k)
    assert environment.embedder.document_calls == 0


@pytest.mark.parametrize("query", ["", " ", None])
def test_empty_queries_are_rejected(environment, query):
    with pytest.raises(RAGError, match="non-empty"):
        environment.retriever.retrieve(query)


def test_no_context_is_a_readable_error(environment):
    loader = ProjectContextLoader(environment.context_path)
    retriever = ArchitectureRetriever(loader, environment.builder, environment.embedder)
    with pytest.raises(RAGError, match="No project context"):
        retriever.build_index()
    with pytest.raises(RAGError, match="No project context"):
        retriever.retrieve("PaymentGateway")


def test_missing_base_rules_is_reported_without_loading_embeddings(environment):
    environment.base_path.unlink()
    with pytest.raises(RAGError, match="Cannot load architecture rules"):
        environment.retriever.build_index()
    assert environment.embedder.document_calls == 0


@pytest.mark.parametrize("stored", ["{", '{"rules": null}', "[42]", '[{"status":"VALID","rule":null}]'])
def test_unreadable_rule_storage_produces_a_readable_error(environment, stored):
    environment.base_path.write_text(stored, encoding="utf-8")
    with pytest.raises(RAGError):
        environment.retriever.build_index()


def test_empty_corpus_is_reported_before_embedding(environment):
    environment.context.update(components=[], relationships=[])
    store(environment.context_path, environment.context)
    store(environment.base_path, [])
    environment.loader.reload()
    with pytest.raises(RAGError, match="corpus is empty"):
        environment.retriever.build_index()
    assert environment.embedder.document_calls == 0


def test_rebuild_reloads_changed_context_and_rules(environment):
    environment.retriever.build_index()
    environment.context["components"].append(component("demo.NewService"))
    store(environment.context_path, environment.context)
    store(environment.custom_path, {"rules": [custom_rule(environment)]})
    assert len(environment.retriever.documents) == 14

    assert environment.retriever.rebuild_index() == 16
    assert any(document.source_id == "demo.NewService" for document in environment.retriever.documents)
    assert any(document.document_type == "CUSTOM_RULE" for document in environment.retriever.documents)


def test_failed_rebuild_keeps_the_previous_index(environment):
    environment.retriever.build_index()
    previous = environment.retriever.documents
    environment.embedder.fail = True
    with pytest.raises(RAGError, match="Test embedding failure"):
        environment.retriever.rebuild_index()

    assert environment.retriever.documents == previous
    assert environment.retriever.retrieve("PaymentGateway", 1)


def test_failed_rebuild_cannot_query_an_index_for_a_different_context(environment):
    environment.retriever.build_index()
    environment.context["project_name"] = "changed"
    store(environment.context_path, environment.context)
    environment.embedder.fail = True
    with pytest.raises(RAGError):
        environment.retriever.rebuild_index()
    with pytest.raises(RAGError, match="context has changed"):
        environment.retriever.retrieve("PaymentGateway")


def test_failed_context_reload_keeps_the_last_good_snapshot(environment):
    environment.retriever.build_index()
    environment.context_path.write_text("{", encoding="utf-8")
    with pytest.raises(RAGError, match="Cannot reload project context"):
        environment.retriever.rebuild_index()
    assert environment.retriever.retrieve("PaymentGateway", 1)


def test_unavailable_faiss_is_a_readable_error(environment, monkeypatch):
    monkeypatch.setitem(sys.modules, "faiss", None)
    with pytest.raises(RAGError, match="FAISS index support is unavailable"):
        environment.retriever.build_index()


@pytest.mark.parametrize("vectors", [np.zeros((14, 3)), np.full((14, 3), np.nan), np.ones((2, 3))])
def test_invalid_embeddings_do_not_publish_an_index(environment, monkeypatch, vectors):
    monkeypatch.setattr(environment.embedder, "embed_documents", lambda texts: vectors)
    with pytest.raises(RAGError, match="Embedding output"):
        environment.retriever.build_index()
    assert not environment.retriever.is_indexed


def test_query_dimension_mismatch_is_reported(environment, monkeypatch):
    environment.retriever.build_index()
    monkeypatch.setattr(environment.embedder, "embed_query", lambda query: np.ones(3))
    with pytest.raises(RAGError, match="dimensions do not match"):
        environment.retriever.retrieve("PaymentGateway")


def test_embedding_adapter_is_lazy_and_prefixes_only_queries(monkeypatch):
    instances, encoded = [], []

    class Model:
        def __init__(self, name, **kwargs):
            instances.append((name, kwargs))

        def encode(self, texts, **kwargs):
            encoded.append((texts, kwargs))
            return np.ones((len(texts), 3), dtype=np.float32)

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model))
    embedder = SentenceTransformerEmbedder()
    assert not embedder.is_loaded
    assert instances == []
    embedder.embed_documents(["PaymentGateway component"])
    embedder.embed_query("PaymentGateway")
    assert len(instances) == 1
    assert instances[0][0] == DEFAULT_EMBEDDING_MODEL
    assert instances[0][1]["device"] == "cpu"
    assert encoded[0][0] == ["PaymentGateway component"]
    assert encoded[1][0] == [BGE_QUERY_PREFIX + "PaymentGateway"]
    assert encoded[0][1]["normalize_embeddings"] is True


def test_embedding_model_load_failure_is_readable(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Model cache is unavailable")

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=fail))
    embedder = SentenceTransformerEmbedder()
    with pytest.raises(RAGError, match="Cannot load embedding model.*Model cache is unavailable"):
        embedder.embed_query("PaymentGateway")
    assert not embedder.is_loaded


async def request_json(application, path, payload=None, method="POST"):
    messages = []

    async def receive():
        return {"type": "http.request", "body": json.dumps(payload).encode() if payload is not None else b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await application({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
                       "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
                       "headers": [(b"content-type", b"application/json")]}, receive, send)
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(body)


def test_health_and_startup_leave_the_real_embedding_adapter_unloaded(environment):
    async def check():
        application = create_app(environment.config)
        async with application.router.lifespan_context(application):
            assert await request_json(application, "/health", method="GET") == (200, {"status": "ok"})
            assert not application.state.rag_retriever.embedder.is_loaded
            assert not application.state.rag_retriever.is_indexed

    asyncio.run(check())


def test_rag_endpoints_build_and_retrieve_typed_results(environment):
    async def check():
        application = create_app(environment.config, embedder=environment.embedder)
        async with application.router.lifespan_context(application):
            assert await request_json(application, "/rag/rebuild") == (200, {"indexed": True, "documents": 14})
            status, response = await request_json(application, "/rag/retrieve", {"query": "PaymentGateway", "top_k": 2})
            assert status == 200
            assert len(response["results"]) == 2
            assert response["results"][0]["source_id"] == "demo.PaymentGateway"
            assert set(response["results"][0]) == {"text", "document_type", "source_id", "project_name", "score"}

    asyncio.run(check())


def test_first_retrieval_builds_the_index_lazily(environment):
    async def check():
        application = create_app(environment.config, embedder=environment.embedder)
        async with application.router.lifespan_context(application):
            assert environment.embedder.document_calls == 0
            status, response = await request_json(application, "/rag/retrieve", {"query": "PaymentGateway"})
            assert status == 200
            assert len(response["results"]) == 5
            assert environment.embedder.document_calls == 1

    asyncio.run(check())


@pytest.mark.parametrize("top_k", [0, -1, True, "5", 1.5])
def test_api_rejects_invalid_top_k(environment, top_k):
    async def check():
        application = create_app(environment.config, embedder=environment.embedder)
        async with application.router.lifespan_context(application):
            status, response = await request_json(application, "/rag/retrieve", {"query": "PaymentGateway", "top_k": top_k})
            assert status == 422
            assert response["detail"]
            assert environment.embedder.document_calls == 0

    asyncio.run(check())


def test_api_reports_missing_context_and_keeps_health_available(environment):
    environment.context_path.unlink()

    async def check():
        application = create_app(environment.config, embedder=environment.embedder)
        async with application.router.lifespan_context(application):
            for path, payload in [("/rag/rebuild", None), ("/rag/retrieve", {"query": "PaymentGateway"})]:
                status, response = await request_json(application, path, payload)
                assert status == 409
                assert "No project context" in response["detail"]
            assert await request_json(application, "/health", method="GET") == (200, {"status": "ok"})

    asyncio.run(check())


def test_api_reports_embedding_failure_without_disabling_health(environment):
    environment.embedder.fail = True

    async def check():
        application = create_app(environment.config, embedder=environment.embedder)
        async with application.router.lifespan_context(application):
            status, response = await request_json(application, "/rag/rebuild")
            assert status == 503
            assert "Test embedding failure" in response["detail"]
            assert await request_json(application, "/health", method="GET") == (200, {"status": "ok"})

    asyncio.run(check())
