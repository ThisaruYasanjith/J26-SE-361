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

## Architecture retrieval

`POST /rag/rebuild` reloads the context and stored rules, creates documents, and rebuilds a CPU FAISS index. `POST /rag/retrieve` accepts a query and an optional positive integer `top_k` (default `5`). A first retrieval builds the index if necessary.

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/rag/rebuild
Invoke-RestMethod -Method Post http://127.0.0.1:8000/rag/retrieve `
  -ContentType "application/json" `
  -Body '{"query":"Only PaymentService may depend on PaymentGateway.","top_k":5}'
```

The embedding model defaults to `BAAI/bge-small-en-v1.5`. It loads only when a RAG build or retrieval needs embeddings; startup and health checks do not import Sentence Transformers or download weights. Sentence Transformers brings PyTorch and Transformers as transitive embedding dependencies. These are not direct dependencies or Qwen inference integrations.

The index, its ordered documents, and their metadata stay together in memory. Restarting the service requires another build. There is no file watcher: use `/rag/rebuild` after changing the context or rule files. If rebuilding fails, the previous index remains intact; an index for a different loaded context cannot be queried until rebuilt.

Additional configuration:

| Environment variable | Default |
| --- | --- |
| `BASE_RULES_PATH` | `Architecture/rules/base-rules.json`, located relative to the source checkout |
| `CUSTOM_RULES_PATH` | `Architecture/rules/custom-rules.json`, located relative to the source checkout |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` |
| `EMBEDDING_CACHE_DIR` | Sentence Transformers' default cache |

Custom rules use `{"rules": [...]}` with the same stored rule envelope as base rules. The file starts empty. Stored `VALID` entries are included; entries marked `is_exception: true` or `rule_type: EXCEPTION` become exception documents. This collection is for already-approved stored rules; the service does not approve or evaluate them.

All returned scores are cosine-style similarities from normalized embeddings. The retriever follows the [BGE model card](https://huggingface.co/BAAI/bge-small-en-v1.5) by adding its retrieval instruction to queries only. The same retriever can be used by later base-model and adapter-backed inference code.

Results are the global top-k by vector similarity; document types do not have reserved slots. Related dependency, call, and import documents can outrank component descriptions. Increase `top_k` when a query needs broader context across document types.

Normal tests use a deterministic embedding substitute with real FAISS and make no model-download requests. Real BGE checks are run separately during integration validation.
