import asyncio
import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import ServiceConfig
from app.inference import (
    DEFAULT_MODEL_ID,
    RULE_SCHEMA_PATH,
    InferenceError,
    QwenModelService,
    RuleGenerationRequest,
    RuleGenerationService,
    RulePromptBuilder,
    clean_json_output,
    parse_model_output,
)
from app.main import create_app
from app.rag import RetrievedDocument
from test_rag import environment, request_json


class FakeRuleModel:
    model_id = DEFAULT_MODEL_ID

    def __init__(self, output='{"status":"AMBIGUOUS","rule":null,"reason_code":"MISSING_TARGET"}'):
        self.output = output
        self.is_loaded = False
        self.messages = []
        self.failure = None

    def generate(self, messages):
        if self.failure:
            raise self.failure
        self.is_loaded = True
        self.messages.append(messages)
        return self.output


def test_prompt_uses_the_shared_schema_and_all_its_allowed_values():
    messages = RulePromptBuilder().build_messages("Deny controller access.", [])
    system = messages[0]["content"]
    schema = json.loads(RULE_SCHEMA_PATH.read_text(encoding="utf-8"))
    included = json.loads(system.split("SHARED RULE JSON SCHEMA\n", 1)[1])
    assert included == schema
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "JSON only" in system
    assert "Do not check conflicts" in system


def test_prompt_includes_context_text_and_requirement_without_retrieval_metadata():
    document = RetrievedDocument(text="PaymentService depends on PaymentGateway.", document_type="RELATIONSHIP",
                                 source_id="hidden-source-id", project_name="hidden-project-name", score=.79)
    messages = RulePromptBuilder().build_messages("Only PaymentService may depend on PaymentGateway.", [document])
    user = messages[1]["content"]
    assert "PROJECT ARCHITECTURE CONTEXT\n[1]\nPaymentService depends on PaymentGateway." in user
    assert "DEVELOPER REQUIREMENT\nOnly PaymentService may depend on PaymentGateway." in user
    assert "hidden-source-id" not in user and "hidden-project-name" not in user and "0.79" not in user


def test_unavailable_schema_is_a_readable_error(tmp_path):
    with pytest.raises(InferenceError, match="shared architecture rule schema"):
        RulePromptBuilder(tmp_path / "missing.json").build_messages("Deny access.", [])


@pytest.mark.parametrize("text", ['  {"a": 1} \n', '```json\n{"a": 1}\n```', '```\n{"a": 1}\n```',
                                  '\n```JSON\r\n{"a": 1}\r\n```\n'])
def test_json_cleanup_removes_only_outer_whitespace_and_fences(text):
    assert clean_json_output(text) == '{"a": 1}'
    assert parse_model_output(text) == ({"a": 1}, True)


@pytest.mark.parametrize("text", ['{"action": "DENY",}', 'Explanation: {"a":1}', '```python\n{}\n```',
                                  '', 'NaN', '{"a":Infinity}', '{"a":1e999}', '```json\n{"a":1}\n```\nMore text'])
def test_invalid_json_is_not_repaired(text):
    assert parse_model_output(text) == (None, False)


@pytest.mark.parametrize("text,expected", [('null', None), ('[1,2]', [1, 2]), ('true', True),
                                          ('42', 42), ('"a string"', "a string"), ('{"unexpected":true}', {"unexpected": True})])
def test_json_parsing_does_not_perform_rule_schema_validation(text, expected):
    assert parse_model_output(text) == (expected, True)


def test_generation_passes_real_retriever_results_into_model(environment):
    model = FakeRuleModel()
    service = RuleGenerationService(environment.retriever, model, top_k=8)
    response = service.generate(RuleGenerationRequest(requirement="Only PaymentService may depend on PaymentGateway."))

    assert len(response.retrieved_context) == 8
    assert environment.embedder.query_calls == 1
    assert environment.retriever.is_indexed
    assert response.json_valid
    assert response.rule["reason_code"] == "MISSING_TARGET"
    assert all(document.text in model.messages[0][1]["content"] for document in response.retrieved_context)


def test_rag_can_be_disabled_without_loading_context_or_embeddings(environment):
    environment.retriever.loader = SimpleNamespace(get_context=lambda: None)
    model = FakeRuleModel()
    response = RuleGenerationService(environment.retriever, model).generate(
        RuleGenerationRequest(requirement="Controllers must not depend on repositories.", use_rag=False))
    assert response.retrieved_context == []
    assert environment.embedder.document_calls == 0
    assert "No retrieved context supplied." in model.messages[0][1]["content"]


def test_invalid_output_keeps_the_exact_generated_text(environment):
    text = '  ```json\n{"status":"VALID",}\n```  '
    response = RuleGenerationService(environment.retriever, FakeRuleModel(text)).generate(
        RuleGenerationRequest(requirement="Deny access.", use_rag=False))
    assert response.generated_text == text
    assert response.rule is None
    assert response.json_valid is False


def test_non_text_output_is_a_readable_error(environment):
    with pytest.raises(InferenceError, match="non-text output"):
        RuleGenerationService(environment.retriever, FakeRuleModel(None)).generate(
            RuleGenerationRequest(requirement="Deny access.", use_rag=False))


@pytest.fixture
def model_libraries(monkeypatch):
    calls = SimpleNamespace(tokenizers=[], models=[], quantization=[], generated=[], decoded=[])

    class Inputs(dict):
        def to(self, device):
            assert device == "cuda:0"
            return self

    class Tokenizer:
        eos_token_id = 99

        def apply_chat_template(self, messages, **kwargs):
            assert kwargs == {"tokenize": False, "add_generation_prompt": True}
            return "formatted chat"

        def __call__(self, texts, **kwargs):
            assert texts == ["formatted chat"] and kwargs == {"return_tensors": "pt"}
            return Inputs(input_ids=np.array([[1, 2, 3]]))

        def decode(self, tokens, **kwargs):
            calls.decoded.append((tokens, kwargs))
            return '{"status":"VALID"}'

    class Model:
        device = "cuda:0"

        def eval(self):
            return self

        def generate(self, **kwargs):
            calls.generated.append(kwargs)
            return [[1, 2, 3, 7, 8]]

    def tokenizer_loader(model_id, **kwargs):
        calls.tokenizers.append((model_id, kwargs))
        return Tokenizer()

    def model_loader(model_id, **kwargs):
        calls.models.append((model_id, kwargs))
        return Model()

    def quantization(**kwargs):
        calls.quantization.append(kwargs)
        return kwargs

    calls.torch = SimpleNamespace(float16=object(), cuda=SimpleNamespace(is_available=lambda: True), inference_mode=nullcontext)
    calls.transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=tokenizer_loader),
        AutoModelForCausalLM=SimpleNamespace(from_pretrained=model_loader), BitsAndBytesConfig=quantization)
    monkeypatch.setitem(sys.modules, "torch", calls.torch)
    monkeypatch.setitem(sys.modules, "transformers", calls.transformers)
    return calls


def test_model_load_is_lazy_reused_and_uses_fp16_nf4(model_libraries):
    model = QwenModelService(max_new_tokens=180)
    assert not model.is_loaded and model_libraries.models == []
    messages = [{"role": "user", "content": "Deny access."}]
    assert model.generate(messages) == '{"status":"VALID"}'
    model.generate(messages)
    assert model.is_loaded
    assert len(model_libraries.models) == len(model_libraries.tokenizers) == 1
    assert model_libraries.quantization == [{
        "load_in_4bit": True, "bnb_4bit_quant_type": "nf4", "bnb_4bit_use_double_quant": True,
        "bnb_4bit_compute_dtype": model_libraries.torch.float16,
    }]
    options = model_libraries.models[0][1]
    assert options["dtype"] is model_libraries.torch.float16
    assert options["device_map"] == "auto" and options["trust_remote_code"] is False
    assert model_libraries.generated[0]["max_new_tokens"] == 180
    assert model_libraries.generated[0]["do_sample"] is False
    assert model_libraries.decoded[0] == ([7, 8], {"skip_special_tokens": True})
    assert model.load_time_seconds >= 0 and model.last_generation_time_seconds >= 0


def test_missing_cuda_fails_before_any_model_download(model_libraries):
    model_libraries.torch.cuda.is_available = lambda: False
    model = QwenModelService()
    with pytest.raises(InferenceError, match="CUDA-enabled PyTorch"):
        model.generate([])
    assert not model.is_loaded
    assert model_libraries.tokenizers == model_libraries.models == []


def test_failed_model_load_can_be_retried(model_libraries):
    loader = model_libraries.transformers.AutoModelForCausalLM.from_pretrained

    def fail(*args, **kwargs):
        raise RuntimeError("Not enough device memory")

    model_libraries.transformers.AutoModelForCausalLM.from_pretrained = fail
    model = QwenModelService()
    with pytest.raises(InferenceError, match="Cannot load base model.*Not enough device memory"):
        model.generate([])
    assert not model.is_loaded
    model_libraries.transformers.AutoModelForCausalLM.from_pretrained = loader
    model.generate([])
    assert model.is_loaded


def test_generation_failure_is_readable_and_keeps_the_model_loaded(model_libraries):
    model = QwenModelService()
    model.generate([])

    def fail(**kwargs):
        raise RuntimeError("Generation ran out of memory")

    model._model.generate = fail
    with pytest.raises(InferenceError, match="generation failed.*out of memory"):
        model.generate([])
    assert model.is_loaded


def test_health_and_status_do_not_import_or_load_qwen(environment, monkeypatch):
    # Any accidental heavy import would fail while these lightweight endpoints run.
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "transformers", None)

    async def check():
        application = create_app(environment.config)
        async with application.router.lifespan_context(application):
            assert await request_json(application, "/health", method="GET") == (200, {"status": "ok"})
            assert await request_json(application, "/model/status", method="GET") == (
                200, {"loaded": False, "model_id": DEFAULT_MODEL_ID})
            assert not application.state.rule_generator.model.is_loaded

    asyncio.run(check())


def test_endpoint_returns_raw_output_parsed_json_and_status_after_load(environment):
    model = FakeRuleModel('```json\n{"status":"AMBIGUOUS","rule":null,"reason_code":"MISSING_TARGET"}\n```')

    async def check():
        application = create_app(environment.config, embedder=environment.embedder, model=model)
        async with application.router.lifespan_context(application):
            status, response = await request_json(application, "/rules/generate", {"requirement": "Deny access."})
            assert status == 200 and response["json_valid"] is True
            assert response["generated_text"] == model.output
            assert response["rule"]["status"] == "AMBIGUOUS"
            assert len(response["retrieved_context"]) == 8
            assert await request_json(application, "/model/status", method="GET") == (
                200, {"loaded": True, "model_id": DEFAULT_MODEL_ID})

    asyncio.run(check())


@pytest.mark.parametrize("payload", [{}, {"requirement": ""}, {"requirement": " \n "}, {"requirement": None},
                                      {"requirement": 12}, {"requirement": "Deny access.", "use_rag": "true"},
                                      {"requirement": "Deny access.", "model": "adapter"}])
def test_endpoint_rejects_invalid_requests_before_loading(environment, payload):
    model = FakeRuleModel()

    async def check():
        application = create_app(environment.config, embedder=environment.embedder, model=model)
        async with application.router.lifespan_context(application):
            status, response = await request_json(application, "/rules/generate", payload)
            assert status == 422 and response["detail"]
            assert not model.is_loaded and environment.embedder.document_calls == 0

    asyncio.run(check())


def test_endpoint_reports_missing_context_without_calling_model(environment):
    environment.context_path.unlink()
    model = FakeRuleModel()

    async def check():
        application = create_app(environment.config, embedder=environment.embedder, model=model)
        async with application.router.lifespan_context(application):
            status, response = await request_json(application, "/rules/generate", {"requirement": "Deny access."})
            assert status == 409 and "No project context" in response["detail"]
            assert not model.is_loaded

    asyncio.run(check())


@pytest.mark.parametrize("output", ["not JSON", ""])
def test_endpoint_reports_invalid_json_without_discarding_output(environment, output):
    async def check():
        application = create_app(environment.config, model=FakeRuleModel(output))
        async with application.router.lifespan_context(application):
            status, response = await request_json(application, "/rules/generate", {"requirement": "Deny access.", "use_rag": False})
            assert status == 200
            assert response == {"generated_text": output, "json_valid": False, "rule": None, "retrieved_context": []}

    asyncio.run(check())


@pytest.mark.parametrize("message", ["Cannot load base model", "Base model generation failed"])
def test_endpoint_model_errors_leave_health_available(environment, message):
    model = FakeRuleModel()
    model.failure = InferenceError(message)

    async def check():
        application = create_app(environment.config, model=model)
        async with application.router.lifespan_context(application):
            status, response = await request_json(application, "/rules/generate", {"requirement": "Deny access.", "use_rag": False})
            assert status == 503 and response["detail"] == message
            assert await request_json(application, "/health", method="GET") == (200, {"status": "ok"})

    asyncio.run(check())


def test_inference_configuration_defaults():
    config = ServiceConfig()
    assert config.model_id == DEFAULT_MODEL_ID
    assert config.model_max_new_tokens == 180 and config.rag_top_k == 8


def test_inference_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "local/model")
    monkeypatch.setenv("MODEL_MAX_NEW_TOKENS", "200")
    monkeypatch.setenv("RAG_TOP_K", "10")
    config = ServiceConfig.from_env()
    assert config.model_id == "local/model" and config.model_max_new_tokens == 200 and config.rag_top_k == 10


@pytest.mark.parametrize("variable,value", [("MODEL_ID", " "), ("MODEL_MAX_NEW_TOKENS", "0"),
                                           ("MODEL_MAX_NEW_TOKENS", "abc"), ("RAG_TOP_K", "-1"), ("RAG_TOP_K", "1.5")])
def test_invalid_inference_configuration_is_readable(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError, match=variable):
        ServiceConfig.from_env()
