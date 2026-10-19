# Architecture AI service

Requires Python 3.11 or newer. Run these commands from `Architecture/ai-service` in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\pytest.exe

$env:PROJECT_CONTEXT_PATH = "../architecture-demo-project/.architecture/project_context.json"
$env:HOST = "127.0.0.1"
$env:PORT = "8000"
.\.venv\Scripts\python.exe -m app.main
```

`PROJECT_CONTEXT_PATH` defaults to `../architecture-demo-project/.architecture/project_context.json`, relative to the directory used to start the service. `HOST` defaults to `127.0.0.1` and `PORT` to `8000`. The installed `architecture-ai-service` command uses the same configuration.

The service loads schema version `1.0` contexts at startup. A missing or invalid file produces a warning while the service remains available. The loader's `reload()` method replaces the in-memory context only after a successful load.

- `GET /health` returns `{"status": "ok"}`.
- `GET /context/status` returns `{"loaded": false}` or the loaded project name and component/relationship counts.
