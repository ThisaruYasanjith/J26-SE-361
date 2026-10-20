import os
from dataclasses import dataclass
from pathlib import Path


RULES_DIRECTORY = Path(__file__).resolve().parents[2] / "rules"


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    project_context_path: Path = Path("../architecture-demo-project/.architecture/project_context.json")
    host: str = "127.0.0.1"
    port: int = 8000
    base_rules_path: Path = RULES_DIRECTORY / "base-rules.json"
    custom_rules_path: Path = RULES_DIRECTORY / "custom-rules.json"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: Path | None = None
    model_id: str = "Qwen/Qwen3-4B-Instruct-2507"
    model_max_new_tokens: int = 180
    rag_top_k: int = 8

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("HOST must not be empty.")
        if not 1 <= self.port <= 65535:
            raise ValueError("PORT must be an integer between 1 and 65535.")
        if not self.embedding_model.strip():
            raise ValueError("EMBEDDING_MODEL must not be empty.")
        if not self.model_id.strip():
            raise ValueError("MODEL_ID must not be empty.")
        if type(self.model_max_new_tokens) is not int or self.model_max_new_tokens < 1:
            raise ValueError("MODEL_MAX_NEW_TOKENS must be a positive integer.")
        if type(self.rag_top_k) is not int or self.rag_top_k < 1:
            raise ValueError("RAG_TOP_K must be a positive integer.")

    @classmethod
    def from_env(cls) -> "ServiceConfig":
        context_path = os.environ.get(
            "PROJECT_CONTEXT_PATH",
            "../architecture-demo-project/.architecture/project_context.json",
        )
        if not context_path.strip():
            raise ValueError("PROJECT_CONTEXT_PATH must not be empty.")
        try:
            port = int(os.environ.get("PORT", "8000"))
        except ValueError as error:
            raise ValueError("PORT must be an integer between 1 and 65535.") from error

        def positive_integer(variable: str, default: str) -> int:
            try:
                value = int(os.environ.get(variable, default))
                if value < 1:
                    raise ValueError
                return value
            except ValueError as error:
                raise ValueError(f"{variable} must be a positive integer.") from error

        # Relative paths are interpreted from the directory used to start the service.
        return cls(
            project_context_path=Path(context_path).expanduser(),
            host=os.environ.get("HOST", "127.0.0.1"),
            port=port,
            base_rules_path=Path(os.environ.get("BASE_RULES_PATH", str(RULES_DIRECTORY / "base-rules.json"))).expanduser(),
            custom_rules_path=Path(os.environ.get("CUSTOM_RULES_PATH", str(RULES_DIRECTORY / "custom-rules.json"))).expanduser(),
            embedding_model=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
            embedding_cache_dir=Path(os.environ["EMBEDDING_CACHE_DIR"]).expanduser()
            if os.environ.get("EMBEDDING_CACHE_DIR") else None,
            model_id=os.environ.get("MODEL_ID", "Qwen/Qwen3-4B-Instruct-2507"),
            model_max_new_tokens=positive_integer("MODEL_MAX_NEW_TOKENS", "180"),
            rag_top_k=positive_integer("RAG_TOP_K", "8"),
        )
