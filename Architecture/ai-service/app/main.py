import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import ServiceConfig
from app.context_loader import ContextLoadError, ProjectContextLoader
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


def create_app(config: ServiceConfig | None = None, *, embedder: EmbeddingBackend | None = None) -> FastAPI:
    settings = config if config is not None else ServiceConfig.from_env()
    loader = ProjectContextLoader(settings.project_context_path)
    retriever = ArchitectureRetriever(
        loader,
        ContextDocumentBuilder(settings.base_rules_path, settings.custom_rules_path),
        embedder if embedder is not None else SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_cache_dir),
    )

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

    @application.post("/rag/retrieve", response_model=RetrievalResponse, response_model_exclude_none=True)
    def retrieve_rag(request: RetrievalRequest) -> RetrievalResponse:
        return RetrievalResponse(results=retriever.retrieve(request.query, request.top_k))

    return application


app = create_app()


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings: ServiceConfig = app.state.config
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
