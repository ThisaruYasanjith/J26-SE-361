import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import ServiceConfig
from app.context_loader import ContextLoadError, ProjectContextLoader
from app.models import ProjectContext, ProjectContextSyncResponse
from app.conflict_detector import ConflictResult
from app.custom_rule_store import (
    CustomRuleStore,
    CustomRuleStoreError,
    RuleApprovalRequest,
    RuleApprovalResponse,
    RuleCheckRequest,
)
from app.inference import (
    InferenceError,
    ModelStatus,
    QwenModelService,
    RuleGenerationRequest,
    RuleGenerationResponse,
    RuleGenerationService,
    RuleModelBackend,
)
from app.rag import (
    ArchitectureRetriever,
    ContextDocumentBuilder,
    EmbeddingBackend,
    RAGError,
    RebuildResponse,
    RetrievalRequest,
    RetrievalResponse,
    SentenceTransformerEmbedder,
)


logger = logging.getLogger(__name__)


def create_app(config: ServiceConfig | None = None, *, embedder: EmbeddingBackend | None = None,
               model: RuleModelBackend | None = None) -> FastAPI:
    settings = config if config is not None else ServiceConfig.from_env()
    loader = ProjectContextLoader(settings.project_context_path)
    retriever = ArchitectureRetriever(
        loader,
        ContextDocumentBuilder(settings.base_rules_path, settings.custom_rules_path),
        embedder if embedder is not None else SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_cache_dir),
    )
    base_model = model if model is not None else QwenModelService(settings.model_id, settings.model_max_new_tokens)
    generator = RuleGenerationService(retriever, base_model, settings.rag_top_k)
    custom_rules = CustomRuleStore(settings.custom_rules_path, on_change=retriever.invalidate_index)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            context = loader.load()
            logger.info("Loaded project context for %s", context.project_name)
        except ContextLoadError as error:
            # Health checks remain available while a context file is missing or needs fixing.
            logger.warning("No project context loaded: %s", error)
        yield

    application = FastAPI(title="Architecture AI Service", lifespan=lifespan)
    application.state.config = settings
    application.state.context_loader = loader
    application.state.rag_retriever = retriever
    application.state.rule_generator = generator
    application.state.custom_rule_store = custom_rules

    @application.exception_handler(CustomRuleStoreError)
    async def custom_rule_error(request: Request, error: CustomRuleStoreError) -> JSONResponse:
        content = {"detail": str(error)}
        if error.validation_errors is not None:
            content["validation_errors"] = [issue.model_dump() for issue in error.validation_errors]
        if error.conflict_result is not None:
            content.update(error.conflict_result.model_dump())
        return JSONResponse(status_code=error.status_code, content=content)

    @application.exception_handler(InferenceError)
    async def inference_error(request: Request, error: InferenceError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": str(error)})

    @application.exception_handler(RAGError)
    async def rag_error(request: Request, error: RAGError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": str(error)})

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/context/status")
    def context_status() -> dict[str, bool | str | int]:
        context = loader.get_context()
        if context is None:
            return {"loaded": False}
        return {
            "loaded": True,
            "project_name": context.project_name,
            "components": len(context.components),
            "relationships": len(context.relationships),
        }

    @application.post("/rag/rebuild", response_model=RebuildResponse)
    def rebuild_rag() -> RebuildResponse:
        count = retriever.rebuild_index()
        return RebuildResponse(indexed=True, documents=count)

    @application.put("/context/project", response_model=ProjectContextSyncResponse)
    def sync_project_context(context: ProjectContext) -> ProjectContextSyncResponse:
        try:
            updated = retriever.update_project_context(context)
        except ContextLoadError as error:
            logger.error("Project context synchronization failed: %s", error)
            raise HTTPException(status_code=503, detail="Cannot store project context. Check the backend context path and permissions.") from error
        logger.info("Synchronized project %s: %d components, %d relationships; RAG index invalidated",
                    updated.project_name, len(updated.components), len(updated.relationships))
        return ProjectContextSyncResponse(updated=True, project_name=updated.project_name,
                                          components=len(updated.components), relationships=len(updated.relationships), rag_invalidated=True)

    @application.post("/rag/retrieve", response_model=RetrievalResponse, response_model_exclude_none=True)
    def retrieve_rag(request: RetrievalRequest) -> RetrievalResponse:
        return RetrievalResponse(results=retriever.retrieve(request.query, request.top_k))

    @application.get("/model/status", response_model=ModelStatus)
    def model_status() -> ModelStatus:
        return ModelStatus(loaded=base_model.is_loaded, model_id=base_model.model_id)

    @application.post("/rules/generate", response_model=RuleGenerationResponse)
    def generate_rule(request: RuleGenerationRequest) -> RuleGenerationResponse:
        return generator.generate(request)

    @application.post("/rules/check-conflicts", response_model=ConflictResult)
    def check_rule_conflicts(request: RuleCheckRequest) -> ConflictResult:
        return custom_rules.check_conflicts(request.rule)

    @application.post("/rules/approve", response_model=RuleApprovalResponse)
    def approve_rule(request: RuleApprovalRequest) -> RuleApprovalResponse:
        return custom_rules.approve_rule(request.rule, confirm_conflicts=request.confirm_conflicts)

    return application


app = create_app()


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings: ServiceConfig = app.state.config
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
