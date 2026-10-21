import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from pydantic import ValidationError

from app.models import ProjectContext


logger = logging.getLogger(__name__)


class ContextLoadError(RuntimeError):
    """A context file could not be read or did not match the data contract."""


class ProjectContextLoader:
    def __init__(self, context_path: str | Path) -> None:
        self.context_path = Path(context_path).expanduser().resolve()
        self._context: ProjectContext | None = None
        self._lock = threading.RLock()

    def load(self) -> ProjectContext:
        with self._lock:
            return self._load()

    def _load(self) -> ProjectContext:
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

        context = self._validate(data)
        # A failed reload must not replace the last context that loaded successfully.
        self._context = context
        return context

    def _validate(self, data: object) -> ProjectContext:
        try:
            return ProjectContext.model_validate(data)
        except ValidationError as error:
            # Field paths are more useful here than dumping the entire input document into logs.
            details = "; ".join(
                f"{'.'.join(map(str, issue['loc'])) or '<root>'}: {issue['msg']}"
                for issue in error.errors(include_url=False, include_input=False)
            )
            raise ContextLoadError(f"Invalid project context structure in {self.context_path}: {details}") from error

    def replace(self, data: ProjectContext | dict) -> ProjectContext:
        with self._lock:
            # Revalidate model instances too, since a caller might have changed one after construction.
            context = self._validate(data.model_dump(exclude_none=True) if isinstance(data, ProjectContext) else data)
            temporary_path = None
            try:
                self.context_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.context_path.parent,
                                                 prefix=".project-context-", suffix=".tmp", delete=False) as stream:
                    temporary_path = Path(stream.name)
                    json.dump(context.model_dump(mode="json", exclude_none=True), stream, indent=2, ensure_ascii=False, allow_nan=False)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, self.context_path)
            except (OSError, ValueError) as error:
                raise ContextLoadError(f"Cannot store project context at {self.context_path}: {error}") from error
            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Could not remove temporary context file %s", temporary_path)
            # Publish only after replacement succeeds; failed writes leave both disk and memory intact.
            self._context = context
            return context

    def reload(self) -> ProjectContext:
        return self.load()

    def get_context(self) -> ProjectContext | None:
        with self._lock:
            return self._context

    def is_loaded(self) -> bool:
        return self.get_context() is not None
