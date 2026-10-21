import asyncio
import json
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.config import ServiceConfig
from app.inference import DEFAULT_MODEL_ID, InferenceError, QwenModelService
from app.main import create_app
from test_inference import model_libraries
from test_rag import environment, request_json


@pytest.fixture
def adapter(tmp_path):
    directory = tmp_path / "saved-adapter"
    directory.mkdir()
    (directory / "adapter_config.json").write_text(json.dumps({
        "base_model_name_or_path": DEFAULT_MODEL_ID, "peft_type": "LORA", "task_type": "CAUSAL_LM",
    }), encoding="utf-8")
    (directory / "adapter_model.safetensors").write_bytes(b"mock adapter weights")
    return directory


@pytest.fixture
def peft_library(monkeypatch):
    calls = []

    class AdapterModel:
        def __init__(self, base):
            self.device = base.device
            self.base = base
            self.generated = 0

        def eval(self):
            return self

        def generate(self, **kwargs):
            self.generated += 1
            return self.base.generate(**kwargs)

    def load(base, path, **kwargs):
        model = AdapterModel(base)
        calls.append((base, path, kwargs, model))
        return model

    peft = SimpleNamespace(PeftModel=SimpleNamespace(from_pretrained=load))
    monkeypatch.setitem(sys.modules, "peft", peft)
    return SimpleNamespace(module=peft, calls=calls)


def test_explicit_base_mode_without_adapter_is_logged_and_lazy(model_libraries, caplog):
    with caplog.at_level("INFO"):
        model = QwenModelService(model_mode="BASE")
    assert "BASE mode" in caplog.text
    assert model.status().model_dump() == {
        "loaded": False, "model_id": DEFAULT_MODEL_ID, "base_model": DEFAULT_MODEL_ID,
        "model_mode": "BASE", "adapter_loaded": False, "device": None,
    }
    model.generate([])
    assert model.status().device == "cuda:0" and not model.status().adapter_loaded


def test_qlora_is_default_and_never_silently_selects_base(model_libraries):
    model = QwenModelService()
    with pytest.raises(InferenceError, match="QLORA_ADAPTER_PATH"):
        model.generate([])
    assert model.status().model_mode == "QLORA" and not model.is_loaded
    assert model_libraries.models == []


def test_adapter_wraps_nf4_base_and_is_reused_for_generation(adapter, model_libraries, peft_library):
    model = QwenModelService(adapter_path=adapter)
    assert model.status().model_mode == "QLORA" and not model.status().adapter_loaded
    model.generate([])
    model.generate([])
    assert len(peft_library.calls) == len(model_libraries.models) == 1
    base, path, options, wrapped = peft_library.calls[0]
    assert path == str(adapter.resolve())
    assert options == {"is_trainable": False, "local_files_only": True, "autocast_adapter_dtype": False}
    assert wrapped.generated == 2 and model._model is wrapped
    assert model_libraries.quantization[0]["bnb_4bit_quant_type"] == "nf4"
    assert model_libraries.models[0][1]["dtype"] is model_libraries.torch.float16
    assert model_libraries.models[0][1]["device_map"] == "auto"
    assert model.status().adapter_loaded and model.status().device == "cuda:0"
    assert model_libraries.tokenizers[0] == (DEFAULT_MODEL_ID, {"trust_remote_code": False})


@pytest.mark.parametrize("filename", ["adapter_config.json", "adapter_model.safetensors"])
def test_missing_required_artifacts_fail_before_loading_base(adapter, filename, model_libraries):
    (adapter / filename).unlink()
    model = QwenModelService(adapter_path=adapter)
    with pytest.raises(InferenceError, match=filename):
        model.generate([])
    assert not model.is_loaded and model_libraries.models == []


def test_missing_adapter_directory_is_clear(tmp_path, model_libraries):
    model = QwenModelService(adapter_path=tmp_path / "missing")
    with pytest.raises(InferenceError, match="adapter directory does not exist"):
        model.generate([])
    assert model_libraries.models == []


@pytest.mark.parametrize("config", ["{", {"base_model_name_or_path": "wrong/model", "peft_type": "LORA"},
                                    {"base_model_name_or_path": DEFAULT_MODEL_ID, "peft_type": "IA3"}])
def test_invalid_or_incompatible_adapter_config_is_rejected(adapter, config, model_libraries):
    (adapter / "adapter_config.json").write_text(config if isinstance(config, str) else json.dumps(config), encoding="utf-8")
    with pytest.raises(InferenceError, match="QLoRA adapter is configured but could not be loaded"):
        QwenModelService(adapter_path=adapter).generate([])
    assert model_libraries.models == []


def test_peft_failure_never_publishes_or_uses_base_instead(adapter, model_libraries, peft_library):
    def fail(*args, **kwargs):
        raise RuntimeError("Bad adapter /private/runtime/path")

    peft_library.module.PeftModel.from_pretrained = fail
    model = QwenModelService(adapter_path=adapter)
    with pytest.raises(InferenceError, match="QLoRA adapter is configured but could not be loaded") as error:
        model.generate([])
    assert "/private/runtime/path" not in str(error.value)
    assert not model.is_loaded and not model.status().adapter_loaded
    assert model_libraries.generated == []


def test_adapter_tokenizer_is_used_locally_and_not_replaced_on_failure(adapter, model_libraries, peft_library):
    (adapter / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    QwenModelService(adapter_path=adapter).generate([])
    assert model_libraries.tokenizers[0] == (str(adapter), {"trust_remote_code": False, "local_files_only": True})
    calls = len(model_libraries.models)
    model_libraries.transformers.AutoTokenizer.from_pretrained = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Incomplete saved tokenizer"))
    with pytest.raises(InferenceError, match="QLoRA adapter"):
        QwenModelService(adapter_path=adapter).generate([])
    assert len(model_libraries.models) == calls


def test_environment_modes_and_legacy_base_model_alias(monkeypatch, adapter):
    for key in ("MODEL_MODE", "BASE_MODEL", "MODEL_ID", "QLORA_ADAPTER_PATH"):
        monkeypatch.delenv(key, raising=False)
    assert ServiceConfig.from_env().model_mode == "QLORA"
    monkeypatch.setenv("MODEL_MODE", "BASE")
    assert ServiceConfig.from_env().model_mode == "BASE"
    monkeypatch.setenv("MODEL_MODE", "QLORA")
    monkeypatch.setenv("QLORA_ADAPTER_PATH", str(adapter))
    monkeypatch.setenv("BASE_MODEL", DEFAULT_MODEL_ID)
    config = ServiceConfig.from_env()
    assert config.qlora_adapter_path == adapter and config.model_id == DEFAULT_MODEL_ID


@pytest.mark.parametrize("mode,path", [("OTHER", None), ("BASE", "configured-adapter")])
def test_invalid_mode_combinations_cannot_ignore_adapter(mode, path):
    with pytest.raises(ValueError):
        ServiceConfig(model_mode=mode, qlora_adapter_path=path)
    with pytest.raises(ValueError):
        QwenModelService(model_mode=mode, adapter_path=path)


def test_conflicting_base_model_environment_values_are_rejected(monkeypatch):
    monkeypatch.setenv("BASE_MODEL", DEFAULT_MODEL_ID)
    monkeypatch.setenv("MODEL_ID", "other/model")
    with pytest.raises(ValueError, match="must agree"):
        ServiceConfig.from_env()


def test_model_status_and_generation_use_the_configured_adapter(environment, adapter, model_libraries, peft_library):
    app = create_app(replace(environment.config, qlora_adapter_path=adapter), embedder=environment.embedder)

    async def scenario():
        async with app.router.lifespan_context(app):
            status, before = await request_json(app, "/model/status", method="GET")
            assert status == 200 and before["model_mode"] == "QLORA" and not before["adapter_loaded"]
            assert peft_library.calls == [] and "adapter_path" not in before
            assert (await request_json(app, "/rules/generate", {"requirement": "Deny access.", "use_rag": False}))[0] == 200
            status, after = await request_json(app, "/model/status", method="GET")
            assert after["base_model"] == DEFAULT_MODEL_ID and after["adapter_loaded"] and after["device"] == "cuda:0"
            assert len(peft_library.calls) == 1

    asyncio.run(scenario())


def test_broken_adapter_returns_503_while_health_and_conformance_stay_available(environment, tmp_path):
    app = create_app(replace(environment.config, qlora_adapter_path=tmp_path / "missing"))

    async def scenario():
        async with app.router.lifespan_context(app):
            status, response = await request_json(app, "/rules/generate", {"requirement": "Deny access.", "use_rag": False})
            assert status == 503 and "QLoRA adapter" in response["detail"]
            assert await request_json(app, "/health", method="GET") == (200, {"status": "ok"})
            assert (await request_json(app, "/conformance/check"))[0] == 200
            assert not app.state.rule_generator.model.is_loaded

    asyncio.run(scenario())
