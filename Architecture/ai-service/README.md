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

## Base Qwen + RAG

`POST /rules/generate` retrieves architecture documents, builds a chat prompt from the shared `Architecture/schemas/rule.schema.json`, and runs the base `Qwen/Qwen3-4B-Instruct-2507` model. The first RAG-enabled request builds the index automatically when a project context is loaded. Missing context returns HTTP 409 before model inference. Set `use_rag` to `false` to generate without retrieval or a loaded project context.

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/rules/generate `
  -ContentType "application/json" `
  -Body '{"requirement":"Only PaymentService may depend on PaymentGateway.","use_rag":true}'
Invoke-RestMethod http://127.0.0.1:8000/model/status
```

| Environment variable | Default |
| --- | --- |
| `MODEL_ID` | `Qwen/Qwen3-4B-Instruct-2507` |
| `MODEL_MAX_NEW_TOKENS` | `180` |
| `RAG_TOP_K` | `8` |

The tokenizer and Qwen weights load only on the first generation request and are reused. `/health` and `/model/status` do not load them. Status returns `{"loaded":false,"model_id":"Qwen/Qwen3-4B-Instruct-2507"}` before loading, with `loaded: true` after a successful load. Generation requests are serialized to avoid overlapping GPU allocations.

This configuration uses bitsandbytes NF4 with double quantization, FP16 compute and model dtype, and `device_map="auto"`. Install a CUDA-enabled PyTorch build suitable for your NVIDIA GPU before inference. A CPU-only installation returns a readable HTTP 503 before downloading Qwen weights. Loading and generation failures also return HTTP 503 while health checks remain available. There is no automatic fallback to a different model or precision. Model downloads use the standard Hugging Face cache configuration, including `HF_HOME`.

The response preserves the exact `generated_text`. Whitespace and a complete outer JSON/code fence are removed only for parsing. `rule` contains the parsed JSON value; on invalid JSON it is null and `json_valid` is false. `json_valid` reports JSON syntax, not compliance with the architecture rule schema. No rule validation, persistence, conflict detection or conformance checking runs here. The `retrieved_context` array contains the actual documents and similarity scores used for the prompt. Generation uses greedy decoding; the token limit may leave an incomplete JSON result, which is returned without repair.

The implementation follows the [Qwen model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) for chat formatting and the [Transformers bitsandbytes documentation](https://huggingface.co/docs/transformers/quantization/bitsandbytes) for quantized loading, with FP16 explicitly selected for this project.

Run the opt-in integration test separately on a machine with sufficient GPU memory:

```powershell
$env:PROJECT_CONTEXT_PATH = "../architecture-demo-project/.architecture/project_context.json"
$env:RUN_QWEN_INTEGRATION = "1"
.\.venv\Scripts\pytest.exe -m integration -s
Remove-Item Env:RUN_QWEN_INTEGRATION
```

The test runs the three research requirements against real embeddings and FAISS, then Qwen if CUDA is available. It saves the retrieved documents, untouched model output, parsed JSON, syntax validity and load/generation timings to the ignored `.tools/base-qwen-rag-results.json`. Without CUDA it still saves real retrieval results and records Qwen generation as skipped; output and timing fields remain null. Normal `pytest` runs skip this test and mock inference in the unit tests.
