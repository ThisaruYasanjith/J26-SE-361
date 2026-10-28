"""
Integration and Unit Tests for CodeT5 Local Behavioral Analysis Service
Verifies:
1. Model files and configuration validity
2. Output JSON parsing and validation
3. Rejection of invalid categories (only 10 permitted categories)
4. Clean extraction of method bodies (excluding declarations and outer braces)
5. Comparison logic (added, removed, retained categories)
6. FastAPI /health and /analyze endpoint behavior
7. Zero reliance on Groq API
8. Evaluation against actual dataset records
"""

import os
import json
import pytest
from pathlib import Path

from fastapi.testclient import TestClient

# Import from the local microservice
from inference_service import (
    app,
    PERMITTED_CATEGORIES,
    validate_and_parse_output,
    compute_comparison,
    clean_json_string,
    PROMPT_TEMPLATE,
    model_state,
    load_fine_tuned_codet5
)
from src.llm_analyzer import LLMSemanticAnalyzer, map_categories_to_fingerprint
from src.method_parser import MethodParser
from src.signature_checker import SignatureChecker
from src.drift_engine import BehavioralDriftEngine
from src.impact_assessor import ImpactAssessor
from src.explanation import ExplanationGenerator


BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BASE_DIR / "dataset" / "behaviour_changes_dataset_270.json"
MODEL_PATH = BASE_DIR / "codet5-java-behavior-verified"


def test_1_model_files_exist():
    """Verify that the fine-tuned CodeT5 directory contains all complete model artifacts."""
    assert MODEL_PATH.exists(), f"Model directory missing at {MODEL_PATH}"
    assert (MODEL_PATH / "config.json").exists()
    assert (MODEL_PATH / "model.safetensors").exists()
    assert (MODEL_PATH / "tokenizer.json").exists()
    assert (MODEL_PATH / "tokenizer_config.json").exists()
    assert (MODEL_PATH / "generation_config.json").exists()

    with open(MODEL_PATH / "config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    assert config.get("model_type") == "t5"
    assert "T5ForConditionalGeneration" in config.get("architectures", [])


def test_2_permitted_categories_completeness():
    """Verify all 10 mandated behavioral categories are recognized."""
    expected = {
        "STATE_MUTATION",
        "DATABASE_WRITE",
        "DATABASE_READ",
        "EXTERNAL_CALL",
        "FILE_OPERATION",
        "LOGGING",
        "EXCEPTION_BEHAVIOR",
        "OUTPUT_BEHAVIOR",
        "CALCULATION_TRANSFORMATION",
        "VALIDATION_CONTROL_FLOW",
    }
    assert PERMITTED_CATEGORIES == expected
    assert len(PERMITTED_CATEGORIES) == 10


def test_3_output_validation_success():
    """Test parsing of valid CodeT5 JSON generation."""
    raw_output = json.dumps({
        "old_method": {
            "categories": ["DATABASE_READ", "LOGGING"],
            "method_body": "accountRepository.findById(id);\nlogger.info(\"Read done\");"
        },
        "new_method": {
            "categories": ["DATABASE_READ", "DATABASE_WRITE", "LOGGING"],
            "method_body": "accountRepository.save(account);\nlogger.info(\"Saved\");"
        }
    })

    result = validate_and_parse_output(raw_output)
    assert "old_method" in result
    assert "new_method" in result
    assert result["old_method"]["categories"] == ["DATABASE_READ", "LOGGING"]
    assert "DATABASE_WRITE" in result["new_method"]["categories"]
    assert result["old_method"]["method_body"].startswith("accountRepository")


def test_4_output_validation_rejects_unsupported_categories():
    """Verify categories outside the 10 permitted categories are strictly rejected."""
    raw_output = json.dumps({
        "old_method": {
            "categories": ["DATABASE_READ", "HALLUCINATED_CATEGORY", "NETWORK_CALL"],
            "method_body": "foo();"
        },
        "new_method": {
            "categories": ["STATE_MUTATION", "INVALID_DRIFT_TYPE"],
            "method_body": "bar();"
        }
    })

    result = validate_and_parse_output(raw_output)
    # The hallucinated/invalid categories must NOT be present in validated output
    assert "HALLUCINATED_CATEGORY" not in result["old_method"]["categories"]
    assert "NETWORK_CALL" not in result["old_method"]["categories"]
    assert "INVALID_DRIFT_TYPE" not in result["new_method"]["categories"]
    assert result["old_method"]["categories"] == ["DATABASE_READ"]
    assert result["new_method"]["categories"] == ["STATE_MUTATION"]


def test_5_output_validation_handles_malformed_json_safely():
    """Verify malformed JSON raises descriptive ValueError without server crash."""
    with pytest.raises(ValueError, match="Failed to parse model generation as JSON|no valid JSON object"):
        validate_and_parse_output("This is not JSON at all.")

    with pytest.raises(ValueError, match="missing required key 'new_method'"):
        validate_and_parse_output('{"old_method": {"categories": [], "method_body": ""}}')


def test_6_method_body_strips_outer_braces():
    """Ensure outer braces are stripped from method bodies if present."""
    raw_output = json.dumps({
        "old_method": {
            "categories": ["LOGGING"],
            "method_body": "{\n    logger.info(\"test\");\n}"
        },
        "new_method": {
            "categories": ["LOGGING"],
            "method_body": "logger.info(\"test\");"
        }
    })
    result = validate_and_parse_output(raw_output)
    assert result["old_method"]["method_body"] == 'logger.info("test");'


def test_7_behavioral_comparison_delta_logic():
    """Verify comparison accurately identifies added, removed, and retained categories."""
    old_cats = ["DATABASE_READ", "FILE_OPERATION", "LOGGING"]
    new_cats = ["DATABASE_READ", "DATABASE_WRITE", "EXCEPTION_BEHAVIOR"]

    comp = compute_comparison(old_cats, new_cats)
    assert set(comp.added_categories) == {"DATABASE_WRITE", "EXCEPTION_BEHAVIOR"}
    assert set(comp.removed_categories) == {"FILE_OPERATION", "LOGGING"}
    assert set(comp.retained_categories) == {"DATABASE_READ"}
    assert comp.drift_detected is True

    # Identity check
    same_comp = compute_comparison(old_cats, old_cats)
    assert same_comp.added_categories == []
    assert same_comp.removed_categories == []
    assert same_comp.retained_categories == old_cats
    assert same_comp.drift_detected is False


def test_8_no_groq_dependencies_in_pipeline():
    """Confirm the pipeline runs without requiring GROQ_API_KEY or Groq packages."""
    os.environ.pop("GROQ_API_KEY", None)
    parser = MethodParser()
    checker = SignatureChecker()
    drift_engine = BehavioralDriftEngine()
    assessor = ImpactAssessor()
    explainer = ExplanationGenerator()

    v1_code = "public void doAction(String s) { System.out.println(s); }"
    v2_code = "public void doAction(String s) { if (s == null) throw new RuntimeException(); }"

    v1 = parser.parse(v1_code)
    v2 = parser.parse(v2_code)
    sig_res = checker.check(v1, v2)
    assert sig_res.is_same_signature is True

    fp1 = map_categories_to_fingerprint("doAction", ["LOGGING"], "System.out.println(s);")
    fp2 = map_categories_to_fingerprint("doAction", ["EXCEPTION_BEHAVIOR", "VALIDATION_CONTROL_FLOW"], "if (s == null) throw new RuntimeException();")

    drift = drift_engine.analyze(fp1, fp2)
    assert drift.drift_detected is True

    impact = assessor.assess(sig_res, drift)
    explanation = explainer.generate_explanation(v1, v2, sig_res, drift, impact)

    assert explanation is not None
    assert len(explanation.recommended_unit_tests) > 0


def test_9_dataset_ground_truth_parsing():
    """Verify that dataset entries conform to expected schema and categories."""
    assert DATASET_PATH.exists(), f"Dataset file not found at {DATASET_PATH}"
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    assert len(records) >= 270
    sample = records[0]
    assert "input" in sample
    assert "output" in sample

    output_data = json.loads(sample["output"])
    assert "old_method" in output_data
    assert "new_method" in output_data

    for cat in output_data["old_method"]["categories"]:
        assert cat in PERMITTED_CATEGORIES
    for cat in output_data["new_method"]["categories"]:
        assert cat in PERMITTED_CATEGORIES


def test_10_fastapi_analyze_mocked_inference():
    """Test the /analyze endpoint structure and validation handling via FastAPI TestClient."""
    with TestClient(app) as client:
        # Check health endpoint
        health_resp = client.get("/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert "permitted_categories" in health_data
        assert len(health_data["permitted_categories"]) == 10

        # Bad request: empty methods
        bad_resp = client.post("/analyze", json={"old_method": "", "new_method": ""})
        assert bad_resp.status_code in [400, 503]


def test_11_fastapi_analyze_pipeline_signature_mismatch():
    """Verify that /analyze_pipeline correctly detects and reports signature mismatch."""
    with TestClient(app) as client:
        payload = {
            "old_method": "public int calculate(int x) { return x * 2; }",
            "new_method": "public double calculate(double x) { return x * 2.0; }"
        }
        resp = client.post("/analyze_pipeline", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "signature_mismatch"
        assert data["stage2_signature"]["is_same_signature"] is False
        assert len(data["stage2_signature"]["mismatches"]) > 0


def test_12_fastapi_analyze_pipeline_empty_validation():
    """Verify that /analyze_pipeline rejects empty method inputs."""
    with TestClient(app) as client:
        bad_resp = client.post("/analyze_pipeline", json={"old_method": "", "new_method": ""})
        assert bad_resp.status_code == 400

