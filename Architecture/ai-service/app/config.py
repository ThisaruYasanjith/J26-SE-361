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
    model_mode: str = "QLORA"
    qlora_adapter_path: Path | None = None
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
        if self.model_mode not in {"BASE", "QLORA"}:
            raise ValueError("MODEL_MODE must be BASE or QLORA.")
        if self.model_mode == "BASE" and self.qlora_adapter_path is not None:
            raise ValueError("MODEL_MODE=BASE cannot be combined with QLORA_ADAPTER_PATH. Choose QLORA to load the adapter.")
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

        adapter_path = os.environ.get("QLORA_ADAPTER_PATH")
        if adapter_path is not None and not adapter_path.strip():
            raise ValueError("QLORA_ADAPTER_PATH must not be blank when set.")
        base_model = os.environ.get("BASE_MODEL", os.environ.get("MODEL_ID", "Qwen/Qwen3-4B-Instruct-2507"))
        if not base_model.strip():
            raise ValueError("BASE_MODEL / MODEL_ID must not be empty.")
        if "BASE_MODEL" in os.environ and "MODEL_ID" in os.environ and os.environ["BASE_MODEL"] != os.environ["MODEL_ID"]:
            raise ValueError("BASE_MODEL and legacy MODEL_ID must agree when both are set.")
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
            model_id=base_model,
            model_mode=os.environ.get("MODEL_MODE", "QLORA").strip().upper(),
            qlora_adapter_path=Path(adapter_path).expanduser() if adapter_path is not None else None,
            model_max_new_tokens=positive_integer("MODEL_MAX_NEW_TOKENS", "180"),
            rag_top_k=positive_integer("RAG_TOP_K", "8"),
        )
