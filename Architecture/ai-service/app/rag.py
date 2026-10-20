from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator

from app.context_loader import ContextLoadError, ProjectContextLoader
from app.models import ArchitectureModel, NonEmptyString, ProjectContext


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DocumentType = Literal["COMPONENT", "RELATIONSHIP", "BASE_RULE", "CUSTOM_RULE", "EXCEPTION"]


class RAGError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RAGDocument:
    text: str
    document_type: DocumentType
    source_id: str
    project_name: str | None = None

    @property
    def metadata(self) -> dict[str, str]:
        metadata = {"document_type": self.document_type, "source_id": self.source_id}
        if self.project_name is not None:
            metadata["project_name"] = self.project_name
        return metadata


class RetrievalRequest(ArchitectureModel):
    query: NonEmptyString
    top_k: int = Field(default=5, ge=1)

    @field_validator("query")
    @classmethod
    def check_query(cls, query: str) -> str:
        if not query.strip():
            raise ValueError("query must not be blank.")
        return query.strip()


class RetrievedDocument(ArchitectureModel):
    text: str
    document_type: DocumentType
    source_id: str
    project_name: str | None = None
    score: float


class RetrievalResponse(ArchitectureModel):
    results: list[RetrievedDocument]


class RebuildResponse(ArchitectureModel):
    indexed: bool
    documents: int


def _short_name(name: str) -> str:
    return name.rsplit(".", 1)[-1]


class ContextDocumentBuilder:
    def __init__(self, base_rules_path: Path, custom_rules_path: Path | None = None) -> None:
        self.base_rules_path = Path(base_rules_path)
        self.custom_rules_path = Path(custom_rules_path) if custom_rules_path is not None else None

    def build_documents(self, context: ProjectContext) -> list[RAGDocument]:
        documents = []
        components = {component.name: component for component in context.components}
        for component in context.components:
            lines = [
                f"Component: {_short_name(component.name)}",
                f"Qualified name: {component.name}",
                f"Spring type: {component.spring_type}",
                f"Declaration type: {component.entity_type}",
                f"Package: {component.package or '(default package)'}",
                f"Annotations: {', '.join(component.annotations) or '(none)'}",
                f"File: {component.file_path}",
            ]
            # The context stores inheritance as edges, rather than extra component fields.
            parents = sorted({edge.target for edge in context.relationships
                              if edge.source == component.name and edge.relationship == "EXTENDS"})
            interfaces = sorted({edge.target for edge in context.relationships
                                 if edge.source == component.name and edge.relationship == "IMPLEMENTS"})
            if parents:
                label = "Extended interfaces" if component.entity_type == "INTERFACE" else "Superclass"
                lines.append(f"{label}: {', '.join(parents)}")
            if interfaces:
                lines.append(f"Implemented interfaces: {', '.join(interfaces)}")
            verbs = {"DEPENDS_ON": "depends on", "CALLS": "calls", "EXTENDS": "extends", "IMPLEMENTS": "implements"}
            related = sorted({f"{_short_name(edge.source)} {verbs[edge.relationship]} {_short_name(edge.target)}."
                              for edge in context.relationships if edge.relationship in verbs
                              and component.name in (edge.source, edge.target)})
            if related:
                # Keep component summaries small; every relationship also has its own full document.
                lines.append("Related architecture:\n" + "\n".join(related[:12]))
            documents.append(RAGDocument("\n".join(lines), "COMPONENT", component.name, context.project_name))

        for edge in context.relationships:
            source = components.get(edge.source)
            target = components.get(edge.target)
            lines = [
                "Architecture relationship:",
                f"{_short_name(edge.source)} {edge.relationship} {_short_name(edge.target)}",
                f"Source: {edge.source}" + (f" (Spring type: {source.spring_type})" if source else ""),
                f"Target: {edge.target}" + (f" (Spring type: {target.spring_type})" if target else ""),
            ]
            source_id = f"{edge.source} {edge.relationship} {edge.target}"
            documents.append(RAGDocument("\n".join(lines), "RELATIONSHIP", source_id, context.project_name))

        documents.extend(self._rule_documents(self.base_rules_path, "BASE_RULE"))
        if self.custom_rules_path is not None and self.custom_rules_path.exists():
            documents.extend(self._rule_documents(self.custom_rules_path, "CUSTOM_RULE"))
        order = {kind: i for i, kind in enumerate(["COMPONENT", "RELATIONSHIP", "BASE_RULE", "CUSTOM_RULE", "EXCEPTION"])}
        return sorted(documents, key=lambda document: (order[document.document_type], document.source_id, document.text))

    def _rule_documents(self, path: Path, kind: Literal["BASE_RULE", "CUSTOM_RULE"]) -> list[RAGDocument]:
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RAGError(f"Cannot load architecture rules from {path}: {error}", 400) from error
        entries = stored.get("rules") if isinstance(stored, dict) else stored
        if not isinstance(entries, list):
            raise RAGError(f"Architecture rules in {path} must be a list or an object containing a rules list.", 400)

        documents = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise RAGError(f"Cannot describe a non-object rule entry in {path}.", 400)
            if entry.get("status") != "VALID":
                continue
            # Read stored rules for retrieval only. Schema validation and rule evaluation come later.
            try:
                rule = entry["rule"]
                source, target = rule["source"], rule["target"]
                rule_id = entry["rule_id"]
                lines = [
                    f"Architecture rule: {rule_id}",
                    f"Rule type: {rule['rule_type']}",
                    f"Source: {source['name']} ({source['entity_type']})",
                    f"Relationship: {rule['relationship']}",
                    f"Target: {target['name']} ({target['entity_type']})",
                    f"Action: {rule['action']}",
                ]
                if not isinstance(rule_id, str) or not rule_id:
                    raise ValueError("a stored rule needs a non-empty rule_id")
                description = self._rule_description(rule)
                if description:
                    lines.append(description)
                if "scope" in rule:
                    lines.append(f"Scope: {json.dumps(rule['scope'], sort_keys=True)}")
                is_exception = rule.get("is_exception") is True or rule["rule_type"] == "EXCEPTION"
                document_type = "EXCEPTION" if is_exception else kind
                if is_exception:
                    lines.append("Approved exception from the stored rules collection.")
                documents.append(RAGDocument("\n".join(lines), document_type, rule_id))
            except (KeyError, TypeError, ValueError, AttributeError) as error:
                raise RAGError(f"Cannot describe rule entry in {path}: {error}", 400) from error
        return documents

    @staticmethod
    def _rule_description(rule: dict) -> str:
        def label(entity: dict) -> str:
            name = entity["name"]
            if entity["entity_type"] == "LAYER":
                return f"{name.title()} components"
            if entity["entity_type"] == "PACKAGE":
                return f"{name} packages"
            return name

        verbs = {"DEPENDS_ON": "depend directly on", "CALLS": "call", "IMPORTS": "import",
                 "EXTENDS": "extend", "IMPLEMENTS": "implement", "LOCATED_IN": "be located in"}
        actions = {"ALLOW": "may", "DENY": "must not", "REQUIRE": "must"}
        # Leave ONLY in its stored form instead of guessing which side its exclusivity applies to.
        if rule["relationship"] not in verbs or rule["action"] not in actions:
            return ""
        return f"{label(rule['source'])} {actions[rule['action']]} {verbs[rule['relationship']]} {label(rule['target'])}."


class EmbeddingBackend(Protocol):
    def embed_documents(self, texts: list[str]) -> Any: ...

    def embed_query(self, query: str) -> Any: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL, cache_dir: Path | None = None) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _encode(self, texts: list[str]) -> Any:
        with self._lock:
            if self._model is None:
                try:
                    # Keep the heavy imports and any model download out of startup and health checks.
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(
                        self.model_name, device="cpu", trust_remote_code=False,
                        cache_folder=str(self.cache_dir) if self.cache_dir is not None else None,
                    )
                except Exception as error:
                    raise RAGError(f"Cannot load embedding model {self.model_name}: {error}") from error
            try:
                return self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
            except Exception as error:
                raise RAGError(f"Cannot generate embeddings with {self.model_name}: {error}") from error

    def embed_documents(self, texts: list[str]) -> Any:
        return self._encode(texts)

    def embed_query(self, query: str) -> Any:
        # BGE's retrieval instruction belongs on queries, not on corpus documents.
        return self._encode([BGE_QUERY_PREFIX + query])[0]


@dataclass(frozen=True)
class _IndexSnapshot:
    index: Any
    documents: tuple[RAGDocument, ...]
    context_signature: str


class ArchitectureRetriever:
    def __init__(self, loader: ProjectContextLoader, builder: ContextDocumentBuilder,
                 embedder: EmbeddingBackend | None = None) -> None:
        self.loader = loader
        self.builder = builder
        self.embedder = embedder if embedder is not None else SentenceTransformerEmbedder()
        self._snapshot: _IndexSnapshot | None = None
        self._lock = threading.RLock()

    @property
    def documents(self) -> tuple[RAGDocument, ...]:
        with self._lock:
            return self._snapshot.documents if self._snapshot is not None else ()

    @property
    def is_indexed(self) -> bool:
        return self._snapshot is not None

    def invalidate_index(self) -> None:
        with self._lock:
            # The next retrieval rebuilds from disk; approval itself needs no embeddings or model load.
            self._snapshot = None

    def _context(self) -> ProjectContext:
        context = self.loader.get_context()
        if context is None:
            raise RAGError("No project context is loaded. Load a valid project context before using RAG.", 409)
        return context

    @staticmethod
    def _signature(context: ProjectContext) -> str:
        return hashlib.sha256(context.model_dump_json(exclude_none=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize(values: Any, expected_rows: int) -> Any:
        import numpy as np

        vectors = np.asarray(values, dtype=np.float32)
        if vectors.ndim == 1 and expected_rows == 1:
            vectors = vectors.reshape(1, -1)
        if vectors.ndim != 2 or vectors.shape[0] != expected_rows or vectors.shape[1] == 0:
            raise RAGError("Embedding output has an invalid shape.")
        if not np.isfinite(vectors).all():
            raise RAGError("Embedding output contains non-finite values.")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if (norms == 0).any():
            raise RAGError("Embedding output contains an empty vector.")
        return np.ascontiguousarray(vectors / norms, dtype=np.float32)

    def build_index(self) -> int:
        with self._lock:
            context = self._context()
            documents = self.builder.build_documents(context)
            if not documents:
                raise RAGError("The RAG document corpus is empty.", 409)
            try:
                import faiss
            except ImportError as error:
                raise RAGError("FAISS index support is unavailable. Install the retrieval dependencies.") from error
            try:
                vectors = self._normalize(self.embedder.embed_documents([document.text for document in documents]), len(documents))
                index = faiss.IndexFlatIP(vectors.shape[1])
                index.add(vectors)
            except RAGError:
                raise
            except Exception as error:
                raise RAGError(f"Cannot build the FAISS index: {error}") from error
            # Publish the index and its ordered documents together, only after the build succeeds.
            self._snapshot = _IndexSnapshot(index, tuple(documents), self._signature(context))
            return len(documents)

    def rebuild_index(self) -> int:
        with self._lock:
            self._context()
            try:
                self.loader.reload()
            except ContextLoadError as error:
                raise RAGError(f"Cannot reload project context for rebuilding: {error}", 400) from error
            return self.build_index()

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedDocument]:
        if not isinstance(query, str) or not query.strip():
            raise RAGError("query must be a non-empty string.", 422)
        if type(top_k) is not int or top_k < 1:
            raise RAGError("top_k must be a positive integer.", 422)
        with self._lock:
            context = self._context()
            if self._snapshot is None:
                self.build_index()
            snapshot = self._snapshot
            if snapshot is None:
                raise RAGError("The FAISS index is unavailable. Rebuild the RAG index.")
            if snapshot.context_signature != self._signature(context):
                raise RAGError("The loaded project context has changed. Rebuild the RAG index before retrieving.", 409)
            try:
                query_vector = self._normalize(self.embedder.embed_query(query.strip()), 1)
                if query_vector.shape[1] != snapshot.index.d:
                    raise RAGError("Query embedding dimensions do not match the FAISS index. Rebuild the index.")
                scores, positions = snapshot.index.search(query_vector, min(top_k, len(snapshot.documents)))
            except RAGError:
                raise
            except Exception as error:
                raise RAGError(f"Cannot search the FAISS index: {error}") from error
            results = []
            for score, position in zip(scores[0], positions[0]):
                if position < 0:
                    continue
                document = snapshot.documents[int(position)]
                results.append(RetrievedDocument(text=document.text, score=max(-1.0, min(1.0, float(score))), **document.metadata))
            return sorted(results, key=lambda result: (-result.score, result.document_type, result.source_id))
