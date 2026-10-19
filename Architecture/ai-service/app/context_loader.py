import json
from pathlib import Path

from pydantic import ValidationError

from app.models import ProjectContext


class ContextLoadError(RuntimeError):
    """A context file could not be read or did not match the data contract."""


class ProjectContextLoader:
    def __init__(self, context_path: str | Path) -> None:
        self.context_path = Path(context_path).expanduser().resolve()
        self._context: ProjectContext | None = None

    def load(self) -> ProjectContext:
        try:
            text = self.context_path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise ContextLoadError(f"Project context file not found: {self.context_path}") from error
        except UnicodeDecodeError as error:
            raise ContextLoadError(f"Project context is not valid UTF-8: {self.context_path}") from error
        except OSError as error:
            raise ContextLoadError(f"Cannot read project context {self.context_path}: {error}") from error

        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise ContextLoadError(
                f"Invalid JSON in {self.context_path} at line {error.lineno}, "
                f"column {error.colno}: {error.msg}"
            ) from error

        try:
            context = ProjectContext.model_validate(data)
        except ValidationError as error:
            # Field paths are more useful here than dumping the entire input document into logs.
            details = "; ".join(
                f"{'.'.join(map(str, issue['loc'])) or '<root>'}: {issue['msg']}"
                for issue in error.errors(include_url=False, include_input=False)
            )
            raise ContextLoadError(f"Invalid project context structure in {self.context_path}: {details}") from error

        # A failed reload must not replace the last context that loaded successfully.
        self._context = context
        return context

    def reload(self) -> ProjectContext:
        return self.load()

    def get_context(self) -> ProjectContext | None:
        return self._context

    def is_loaded(self) -> bool:
        return self._context is not None
