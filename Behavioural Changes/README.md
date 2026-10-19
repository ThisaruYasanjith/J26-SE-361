# Behavioral Drift Detection in Same-Signature Java Methods

**Research Component:** Individual Research Project for Software Governance Platform (`J26-SE-361`)  
**Component Directory:** `Behavioural Changes`  
**AI Inference Engine:** Local Fine-Tuned CodeT5 (`Salesforce/codet5-small`) — 100% Offline, Zero External AI APIs

---

## 📌 Problem Overview

When software engineers modify an existing Java method without altering its signature (i.e., method name, parameter types, return type, and access modifiers remain identical), the Java compiler generates no warnings or syntax errors.

However, the **runtime behavior** may quietly diverge:
- Return value computation changes (e.g., shifted boundary conditions, altered calculation logic).
- Implicit preconditions tighten (e.g., throwing unexpected exceptions on previously valid inputs).
- Unannounced state mutations or side-effects are introduced (e.g., modifying caller-passed collections, new database writes, file I/O).
- Exception contracts are violated (e.g., unchecked exceptions replace safe fallback values).

This phenomenon—**Same-Signature Behavioral Drift**—is a major source of silent software regressions and architectural degradation in evolving codebases.

---

## 🏗️ Architecture & Pipeline Flow

The project integrates a local Python backend inference service powered by a fine-tuned CodeT5 model with both an interactive Streamlit dashboard and a VS Code extension:

```
┌─────────────────────────┐
│    Java Method Input    │ (Raw Java method code v1 vs v2)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Same-Signature Verifier │ (Verifies exact method signature equivalence)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Local CodeT5 Service    │ (POST /analyze on http://localhost:8000)
│ (Salesforce/codet5-sm)  │ Evaluates 10 supported behavioral categories & method bodies
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Behavioral Drift Engine │ (Quantifies multi-dimensional category & behavior deltas)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    Impact Assessment    │ (Blast radius, backward compatibility, systemic risk)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Developer Guidance     │ (Synthesizes risk breakdown and JUnit regression tests)
└────────────┬────────────┘
             │
     ┌───────┴──────────────────┐
     ▼                          ▼
┌─────────────────────┐   ┌───────────────────────────┐
│ Streamlit Dashboard │   │    VS Code Extension      │
│ (http://localhost:  │   │  (Code Analyzer Sidebar   │
│  8501)              │   │   → Behavioural Details)  │
└─────────────────────┘   └───────────────────────────┘
```

---

## 🏷️ Supported Behavioral Categories

The fine-tuned CodeT5 model predicts classifications strictly from the following 10 verified categories:

1. `STATE_MUTATION`: Modifies object instance fields, class state, or caller-passed objects.
2. `DATABASE_WRITE`: Performs INSERT, UPDATE, DELETE, or save operations on persistent repositories.
3. `DATABASE_READ`: Queries databases, finds entities by ID, or reads persistent collections.
4. `EXTERNAL_CALL`: Calls external microservices, REST clients, message brokers, or third-party APIs.
5. `FILE_OPERATION`: Reads, writes, creates, deletes, or copies files on the filesystem.
6. `LOGGING`: Emits diagnostic logging statements (e.g. SLF4J, Log4j, `logger.info`, `logger.debug`).
7. `EXCEPTION_BEHAVIOR`: Explicitly throws, catches, or alters runtime or checked exceptions.
8. `OUTPUT_BEHAVIOR`: Formats and returns calculated or transformed response values to callers.
9. `CALCULATION_TRANSFORMATION`: Mathematical operations, string manipulations, or algorithmic data transforms.
10. `VALIDATION_CONTROL_FLOW`: Parameter preconditions, null checks, range validations, or branching structures.

---

## 📁 Project Structure & File Purpose

```
Behavioural Changes/
├── codet5-java-behavior-verified/   # Local fine-tuned CodeT5 model & tokenizer files
│   ├── config.json                  # Model architecture (T5ForConditionalGeneration)
│   ├── generation_config.json       # Generation settings
│   ├── model.safetensors            # Fine-tuned weights (~242 MB)
│   ├── tokenizer.json               # Fast tokenizer definition
│   └── tokenizer_config.json        # Special tokens and tokenizer configuration
├── dataset/
│   └── behaviour_changes_dataset_270.json  # 270 paired Java method training/eval records
├── src/
│   ├── __init__.py                  # Package marker
│   ├── method_parser.py             # Stage 1: Java AST & regex parsing into structured models
│   ├── signature_checker.py         # Stage 2: Verification of same-signature equivalence
│   ├── llm_analyzer.py              # Stages 3 & 4: Local CodeT5 service client & fingerprint mapper
│   ├── drift_engine.py              # Stage 5: Multi-dimensional drift quantification and scoring
│   ├── impact_assessor.py           # Stage 6: Blast radius, backward compatibility & architectural risk
│   └── explanation.py               # Stage 7: Local developer narrative & JUnit test generation
├── tests/
│   ├── __init__.py                  # Test package marker
│   ├── test_pipeline.py             # Pipeline unit tests (AST, signature, drift, impact)
│   └── test_codet5_integration.py   # CodeT5 integration & validation test suite
├── app.py                           # Streamlit visual dashboard
├── inference_service.py             # FastAPI local microservice exposing POST /analyze
├── evaluate_model.py                # Standalone holdout dataset evaluation benchmark
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment template
├── .env                             # Local service configuration
└── README.md                        # Documentation
```

---

## 🔌 Local FastAPI Inference Microservice (`POST /analyze`)

The inference service loads `Salesforce/codet5-small` **once** at server startup and caches it in memory.

### Request Format
```http
POST /analyze HTTP/1.1
Content-Type: application/json

{
  "old_method": "public Object buildInventoryItemSummary(...) { ... }",
  "new_method": "public Object buildInventoryItemSummary(...) { ... }"
}
```

### Response Format
```json
{
  "old_method": {
    "categories": ["FILE_OPERATION", "OUTPUT_BEHAVIOR", "CALCULATION_TRANSFORMATION"],
    "method_body": "java.nio.file.Files.copy(path, backupPath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);\nreturn \"INVENTORYITEM-\" + itemId;"
  },
  "new_method": {
    "categories": ["DATABASE_WRITE", "FILE_OPERATION", "OUTPUT_BEHAVIOR", "CALCULATION_TRANSFORMATION"],
    "method_body": "inventoryRepository.updateStatus(itemId, \"PENDING\");\njava.nio.file.Files.deleteIfExists(path);\nreturn String.valueOf(itemId);"
  },
  "comparison": {
    "added_categories": ["DATABASE_WRITE"],
    "removed_categories": [],
    "retained_categories": ["FILE_OPERATION", "OUTPUT_BEHAVIOR", "CALCULATION_TRANSFORMATION"],
    "drift_detected": true
  },
  "raw_output": "{\"old_method\":{...},\"new_method\":{...}}"
}
```

### Health Check Endpoint
```http
GET /health HTTP/1.1
```
Returns:
```json
{
  "status": "ready",
  "device": "cpu",
  "model_path": ".../codet5-java-behavior-verified",
  "permitted_categories": ["CALCULATION_TRANSFORMATION", "DATABASE_READ", ...]
}
```

---

## 💻 Hardware Requirements & Offline Execution

- **Offline**: Zero internet connectivity required during execution. All weights, tokenizers, and dependencies run locally.
- **CPU**: Standard dual-core or quad-core x86_64 CPU (Inference takes ~1-3s per method pair).
- **GPU (Optional)**: CUDA-enabled NVIDIA GPU with 2GB+ VRAM automatically accelerates generation if PyTorch CUDA is installed.
- **Memory**: Minimum 4GB system RAM (~1GB consumed by Python + model weights).

---

## 🚀 Execution Instructions

### 1. Configure Environment
Verify `.env` has the local service URL:
```env
CODET5_SERVICE_URL=http://localhost:8000
MODEL_DIR=codet5-java-behavior-verified
HOST=0.0.0.0
PORT=8000
REQUEST_TIMEOUT_SECONDS=60
MAX_INPUT_LENGTH=512
MAX_OUTPUT_LENGTH=512
```

### 2. Start the FastAPI CodeT5 Inference Service
In a terminal, run:
```bash
.venv\Scripts\python.exe -m uvicorn inference_service:app --host 0.0.0.0 --port 8000
```
or:
```bash
.venv\Scripts\python.exe inference_service.py
```

### 3. Start the Streamlit Demonstration Dashboard
In a second terminal, run:
```bash
.venv\Scripts\python.exe -m streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

### 4. Use the VS Code Extension
In the `VS Code` directory:
```bash
cd "../VS Code"
npm run compile
```
Press `F5` in VS Code to launch the **Extension Development Host**.  
In the activity bar, open the **Code Analyzer** icon and click **Behavioural Launch Window**.
The interactive panel allows pasting Java methods, selecting presets, and querying the local CodeT5 backend!

### 5. Run the Test Suite
```bash
.venv\Scripts\python.exe -m pytest -v
```

### 6. Run the Independent Holdout Dataset Evaluation
```bash
.venv\Scripts\python.exe evaluate_model.py
```
Evaluates the model on holdout dataset records and outputs generalization metrics.
