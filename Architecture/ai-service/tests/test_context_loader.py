import asyncio
import json
import logging
from pathlib import Path

import pytest

from app.config import ServiceConfig
from app.context_loader import ContextLoadError, ProjectContextLoader
from app.main import create_app


@pytest.fixture
def context_data() -> dict:
    return {
        "schema_version": "1.0",
        "project_name": "architecture-demo-project",
        "project_root": ".",
        "components": [
            {
                "name": "demo.service.PaymentService",
                "entity_type": "CLASS",
                "spring_type": "SERVICE",
                "package": "demo.service",
                "file_path": "src/main/java/demo/service/PaymentService.java",
                "annotations": ["Service", "Deprecated"],
                "source_location": {"start_line": 3, "end_line": 12},
            },
            {
                "name": "demo.repository.PaymentRepository",
                "entity_type": "INTERFACE",
                "spring_type": "REPOSITORY",
                "package": "demo.repository",
                "file_path": "src/main/java/demo/repository/PaymentRepository.java",
                "annotations": ["Repository"],
                "source_location": {"start_line": 2, "end_line": 5},
            },
        ],
        "relationships": [
            {
                "source": "demo.service.PaymentService",
                "target": "demo.repository.PaymentRepository",
                "relationship": "DEPENDS_ON",
                "source_location": {"start_line": 6, "end_line": 6},
            },
            {
                "source": "demo.service.PaymentService",
                "target": "demo.repository.PaymentRepository",
                "relationship": "CALLS",
            },
        ],
    }


@pytest.fixture
def context_path(tmp_path: Path, context_data: dict) -> Path:
    path = tmp_path / ".architecture" / "project_context.json"
    path.parent.mkdir()
    write_context(path, context_data)
    return path


def write_context(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_valid_context_loading(context_path: Path) -> None:
    loader = ProjectContextLoader(context_path)
    assert not loader.is_loaded()
    assert loader.get_context() is None

    context = loader.load()

    assert loader.is_loaded()
    assert loader.get_context() is context


def test_missing_context_file(tmp_path: Path) -> None:
    loader = ProjectContextLoader(tmp_path / "missing.json")

    with pytest.raises(ContextLoadError, match="Project context file not found"):
        loader.load()

    assert not loader.is_loaded()
    assert loader.get_context() is None


def test_malformed_json_reports_its_position(context_path: Path) -> None:
    context_path.write_text('{"project_name": }', encoding="utf-8")

    with pytest.raises(ContextLoadError, match=r"Invalid JSON.*line 1, column"):
        ProjectContextLoader(context_path).load()


def test_invalid_structure_reports_the_field(context_path: Path, context_data: dict) -> None:
    del context_data["components"]
    write_context(context_path, context_data)

    with pytest.raises(ContextLoadError, match=r"Invalid project context structure.*components"):
        ProjectContextLoader(context_path).load()


def test_loaded_project_metadata(context_path: Path) -> None:
    context = ProjectContextLoader(context_path).load()

    assert context.schema_version == "1.0"
    assert context.project_name == "architecture-demo-project"
    assert context.project_root == "."


def test_component_and_relationship_counts(context_path: Path) -> None:
    context = ProjectContextLoader(context_path).load()

    assert len(context.components) == 2
    assert len(context.relationships) == 2


def test_preserves_component_and_relationship_details(context_path: Path) -> None:
    context = ProjectContextLoader(context_path).load()
    service = context.components[0]

    assert service.entity_type == "CLASS"
    assert service.spring_type == "SERVICE"
    assert service.package == "demo.service"
    assert service.annotations == ["Service", "Deprecated"]
    assert service.file_path == "src/main/java/demo/service/PaymentService.java"
    assert service.source_location.start_line == 3
    assert service.source_location.end_line == 12
    assert context.components[1].entity_type == "INTERFACE"
    assert context.relationships[0].source == service.name
    assert context.relationships[0].target == context.components[1].name
    assert context.relationships[0].relationship == "DEPENDS_ON"
    assert context.relationships[0].source_location.start_line == 6
    assert context.relationships[1].source_location is None


def test_reload_replaces_context_after_success(context_path: Path, context_data: dict) -> None:
    loader = ProjectContextLoader(context_path)
    original = loader.load()
    context_data["project_name"] = "updated-project"
    write_context(context_path, context_data)

    updated = loader.reload()

    assert updated.project_name == "updated-project"
    assert updated is loader.get_context()
    assert updated is not original


@pytest.mark.parametrize("failure", ["malformed", "invalid", "missing"])
def test_failed_reload_keeps_last_valid_context(context_path: Path, failure: str) -> None:
    loader = ProjectContextLoader(context_path)
    original = loader.load()
    if failure == "malformed":
        context_path.write_text("{", encoding="utf-8")
    elif failure == "invalid":
        write_context(context_path, {})
    else:
        context_path.unlink()

    with pytest.raises(ContextLoadError):
        loader.reload()

    assert loader.is_loaded()
    assert loader.get_context() is original


@pytest.mark.parametrize("version", ["1.0.0", "2.0", 1.0])
def test_rejects_unsupported_schema_versions(context_path: Path, context_data: dict, version: object) -> None:
    context_data["schema_version"] = version
    write_context(context_path, context_data)

    with pytest.raises(ContextLoadError, match="schema_version"):
        ProjectContextLoader(context_path).load()


@pytest.mark.parametrize("level", ["root", "component", "relationship", "location"])
def test_unknown_fields_are_reported_instead_of_discarded(context_path: Path, context_data: dict, level: str) -> None:
    target = {
        "root": context_data,
        "component": context_data["components"][0],
        "relationship": context_data["relationships"][0],
        "location": context_data["components"][0]["source_location"],
    }[level]
    target["unexpected_field"] = "must not be silently lost"
    write_context(context_path, context_data)

    with pytest.raises(ContextLoadError, match="unexpected_field"):
        ProjectContextLoader(context_path).load()


@pytest.mark.parametrize("line", [0, -1, "3", True, 1.5])
def test_source_lines_are_strict_positive_integers(context_path: Path, context_data: dict, line: object) -> None:
    context_data["components"][0]["source_location"]["start_line"] = line
    write_context(context_path, context_data)

    with pytest.raises(ContextLoadError, match="start_line"):
        ProjectContextLoader(context_path).load()


def test_rejects_reversed_line_ranges(context_path: Path, context_data: dict) -> None:
    context_data["components"][0]["source_location"] = {"start_line": 5, "end_line": 2}
    write_context(context_path, context_data)

    with pytest.raises(ContextLoadError, match="end_line must be at or after start_line"):
        ProjectContextLoader(context_path).load()


@pytest.mark.parametrize("field", ["entity_type", "spring_type"])
def test_rejects_unknown_component_types(context_path: Path, context_data: dict, field: str) -> None:
    context_data["components"][0][field] = "UNKNOWN"
    write_context(context_path, context_data)

    with pytest.raises(ContextLoadError, match=field):
        ProjectContextLoader(context_path).load()


def test_rejects_unknown_relationship_types(context_path: Path, context_data: dict) -> None:
    context_data["relationships"][0]["relationship"] = "USES"
    write_context(context_path, context_data)

    with pytest.raises(ContextLoadError, match="relationship"):
        ProjectContextLoader(context_path).load()


def test_rejects_duplicate_annotations(context_path: Path, context_data: dict) -> None:
    context_data["components"][0]["annotations"] = ["Service", "Service"]
    write_context(context_path, context_data)

    with pytest.raises(ContextLoadError, match="Annotation names must be unique"):
        ProjectContextLoader(context_path).load()


def test_optional_relationship_location_must_be_omitted_instead_of_null(context_path: Path, context_data: dict) -> None:
    context_data["relationships"][1]["source_location"] = None
    write_context(context_path, context_data)

    with pytest.raises(ContextLoadError, match="Omit source_location"):
        ProjectContextLoader(context_path).load()


def test_default_package_and_empty_project_are_supported(context_path: Path, context_data: dict) -> None:
    context_data["components"][0]["package"] = ""
    write_context(context_path, context_data)
    assert ProjectContextLoader(context_path).load().components[0].package == ""
    context_data["components"] = []
    context_data["relationships"] = []
    write_context(context_path, context_data)
    loader = ProjectContextLoader(context_path)
    loader.load()
    assert loader.is_loaded()
    assert loader.get_context().components == []


def test_non_object_json_is_a_structure_error(context_path: Path) -> None:
    write_context(context_path, [])

    with pytest.raises(ContextLoadError, match=r"Invalid project context structure.*<root>"):
        ProjectContextLoader(context_path).load()


def test_invalid_utf8_is_readable(context_path: Path) -> None:
    context_path.write_bytes(b"\xff\xfe")

    with pytest.raises(ContextLoadError, match="not valid UTF-8"):
        ProjectContextLoader(context_path).load()


def test_directory_paths_report_read_errors(tmp_path: Path) -> None:
    with pytest.raises(ContextLoadError, match="Cannot read project context"):
        ProjectContextLoader(tmp_path).load()


def test_relative_context_paths_use_the_working_directory(context_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert ProjectContextLoader(Path(".architecture/project_context.json")).load().project_name == "architecture-demo-project"


def test_config_reads_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECT_CONTEXT_PATH", "../demo/.architecture/project_context.json")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8123")

    config = ServiceConfig.from_env()

    assert config.project_context_path == Path("../demo/.architecture/project_context.json")
    assert config.host == "0.0.0.0"
    assert config.port == 8123


def test_config_defaults_are_portable(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ["PROJECT_CONTEXT_PATH", "HOST", "PORT"]:
        monkeypatch.delenv(name, raising=False)

    config = ServiceConfig.from_env()

    assert not config.project_context_path.is_absolute()
    assert config.host == "127.0.0.1"
    assert config.port == 8000


@pytest.mark.parametrize("port", ["not-a-number", "0", "65536", "-1"])
def test_invalid_port_configuration_is_clear(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    monkeypatch.setenv("PORT", port)

    with pytest.raises(ValueError, match="PORT must be an integer between 1 and 65535"):
        ServiceConfig.from_env()


@pytest.mark.parametrize("variable", ["HOST", "PROJECT_CONTEXT_PATH"])
def test_empty_configuration_values_are_rejected(monkeypatch: pytest.MonkeyPatch, variable: str) -> None:
    monkeypatch.setenv(variable, " ")

    with pytest.raises(ValueError, match=variable):
        ServiceConfig.from_env()


async def request_json(application, path: str) -> tuple[int, dict]:
    # Exercise the ASGI app directly without adding httpx as another test dependency.
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await application(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
        },
        receive,
        send,
    )
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(body)


def test_startup_loads_context_and_endpoints_report_status(context_path: Path) -> None:
    async def check():
        application = create_app(ServiceConfig(project_context_path=context_path))
        async with application.router.lifespan_context(application):
            assert await request_json(application, "/health") == (200, {"status": "ok"})
            assert await request_json(application, "/context/status") == (
                200,
                {"loaded": True, "project_name": "architecture-demo-project", "components": 2, "relationships": 2},
            )

    asyncio.run(check())


def test_missing_context_does_not_prevent_startup(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    async def check():
        application = create_app(ServiceConfig(project_context_path=tmp_path / "missing.json"))
        async with application.router.lifespan_context(application):
            assert await request_json(application, "/health") == (200, {"status": "ok"})
            assert await request_json(application, "/context/status") == (200, {"loaded": False})

    with caplog.at_level(logging.WARNING):
        asyncio.run(check())
    assert "No project context loaded" in caplog.text
    assert "file not found" in caplog.text


def test_invalid_context_is_reported_without_disabling_health(context_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    context_path.write_text("{", encoding="utf-8")

    async def check():
        application = create_app(ServiceConfig(project_context_path=context_path))
        async with application.router.lifespan_context(application):
            assert await request_json(application, "/health") == (200, {"status": "ok"})
            assert await request_json(application, "/context/status") == (200, {"loaded": False})

    with caplog.at_level(logging.WARNING):
        asyncio.run(check())
    assert "Invalid JSON" in caplog.text


def test_separate_applications_do_not_share_context(context_path: Path, tmp_path: Path) -> None:
    async def check():
        loaded = create_app(ServiceConfig(project_context_path=context_path))
        unloaded = create_app(ServiceConfig(project_context_path=tmp_path / "missing.json"))
        async with loaded.router.lifespan_context(loaded), unloaded.router.lifespan_context(unloaded):
            assert (await request_json(loaded, "/context/status"))[1]["loaded"] is True
            assert await request_json(unloaded, "/context/status") == (200, {"loaded": False})

    asyncio.run(check())
