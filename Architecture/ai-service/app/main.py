import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from app.config import ServiceConfig
from app.context_loader import ContextLoadError, ProjectContextLoader


logger = logging.getLogger(__name__)


def create_app(config: ServiceConfig | None = None) -> FastAPI:
    settings = config if config is not None else ServiceConfig.from_env()
    loader = ProjectContextLoader(settings.project_context_path)

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

    return application


app = create_app()


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings: ServiceConfig = app.state.config
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
