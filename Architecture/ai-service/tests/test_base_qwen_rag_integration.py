import json
import os
import subprocess
import time
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_QWEN_INTEGRATION") != "1", reason="Set RUN_QWEN_INTEGRATION=1 to run real Qwen + RAG.")
def test_real_base_qwen_with_rag():
    import torch

    from app.config import ServiceConfig
    from app.context_loader import ProjectContextLoader
    from app.inference import QwenModelService, RuleGenerationRequest, RuleGenerationService
    from app.rag import ArchitectureRetriever, ContextDocumentBuilder, SentenceTransformerEmbedder

    config = ServiceConfig.from_env()
    results_path = Path(__file__).resolve().parents[1] / ".tools" / "base-qwen-rag-results.json"
    requirements = [
        "Only PaymentService may depend on PaymentGateway.",
        "Allow ReportingService to depend on PaymentGateway.",
        "Controllers must not directly depend on repositories.",
    ]
    report = {
        "configuration": "BASE QWEN + RAG", "model_id": config.model_id,
        "embedding_model": config.embedding_model, "rag_top_k": config.rag_top_k,
        "max_new_tokens": config.model_max_new_tokens, "compute_dtype": "float16",
        "torch_version": torch.__version__, "cuda_available": torch.cuda.is_available(),
        "device": None, "model_load_time_seconds": None, "status": "running", "results": [],
    }
    try:
        try:
            hardware = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            report["physical_gpu"] = hardware.stdout.strip() or hardware.stderr.strip()
        except (OSError, subprocess.TimeoutExpired):
            report["physical_gpu"] = "nvidia-smi unavailable"

        loader = ProjectContextLoader(config.project_context_path)
        context = loader.load()
        report["project_name"] = context.project_name
        retriever = ArchitectureRetriever(
            loader, ContextDocumentBuilder(config.base_rules_path, config.custom_rules_path),
            SentenceTransformerEmbedder(config.embedding_model, config.embedding_cache_dir),
        )
        # Keep real retrieval evidence even if this machine cannot run the quantized generator.
        for requirement in requirements:
            started = time.perf_counter()
            documents = retriever.retrieve(requirement, config.rag_top_k)
            report["results"].append({
                "requirement": requirement, "retrieved_context": [item.model_dump(exclude_none=True) for item in documents],
                "retrieval_time_seconds": time.perf_counter() - started,
                "generated_text": None, "parsed_json": None, "json_valid": None,
                "generation_time_seconds": None, "status": "not_run",
            })
        report["documents"] = len(retriever.documents)
        if not report["cuda_available"]:
            report["status"] = "skipped"
            report["reason"] = "CUDA is unavailable in the installed PyTorch; no Qwen weights were downloaded or loaded."
            pytest.skip(report["reason"])

        model = QwenModelService(config.model_id, config.model_max_new_tokens, model_mode="BASE")
        generator = RuleGenerationService(retriever, model, config.rag_top_k)
        report["device"] = torch.cuda.get_device_name(0)
        for record in report["results"]:
            response = generator.generate(RuleGenerationRequest(requirement=record["requirement"]))
            record.update(
                generated_text=response.generated_text, parsed_json=response.rule, json_valid=response.json_valid,
                retrieved_context=[item.model_dump(exclude_none=True) for item in response.retrieved_context],
                generation_time_seconds=model.last_generation_time_seconds, status="completed",
            )
            report["model_load_time_seconds"] = model.load_time_seconds
        report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
