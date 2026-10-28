"""
Module: llm_analyzer.py
Stage: Local CodeT5 Semantic Analyzer & Behavioral Fingerprinting

Connects to the local FastAPI CodeT5 inference microservice running the fine-tuned
Salesforce/codet5-small model. Extracts structured behavioral categories,
exact method bodies, and builds standardized BehavioralFingerprint objects.
"""

import os
import json
import logging
from typing import List, Optional, Dict, Any, Tuple
import requests
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from src.method_parser import JavaMethod

load_dotenv()
logger = logging.getLogger(__name__)

# Permitted 10 behavioral categories
PERMITTED_CATEGORIES = {
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


class BehavioralFingerprint(BaseModel):
    """
    Structured semantic representation of a Java method's runtime behavior.
    Enhanced to carry the 10 behavioral categories and extracted method bodies.
    """
    method_name: str
    categories: List[str] = Field(
        default_factory=list,
        description="Fine-tuned CodeT5 predicted categories from the 10 supported types."
    )
    method_body: str = Field(
        default="",
        description="Extracted method body statements excluding outer braces."
    )
    preconditions: List[str] = Field(
        default_factory=list,
        description="Assumptions or parameter validation before execution (e.g. VALIDATION_CONTROL_FLOW)."
    )
    postconditions: List[str] = Field(
        default_factory=list,
        description="Guarantees or properties of return values (e.g. OUTPUT_BEHAVIOR, CALCULATION_TRANSFORMATION)."
    )
    state_mutations: List[str] = Field(
        default_factory=list,
        description="Modifications to instance/class variables or mutated input parameters (STATE_MUTATION)."
    )
    side_effects: List[str] = Field(
        default_factory=list,
        description="External interactions such as LOGGING, DATABASE_WRITE, EXTERNAL_CALL, FILE_OPERATION."
    )
    exceptions_thrown: List[str] = Field(
        default_factory=list,
        description="Explicit or implicit runtime exceptions raised under failure conditions (EXCEPTION_BEHAVIOR)."
    )
    return_behavior: str = Field(
        default="",
        description="Description of the core computation and return value rules."
    )
    invariants_and_assumptions: List[str] = Field(
        default_factory=list,
        description="Core state invariants maintained."
    )
    raw_llm_response: Optional[str] = Field(
        default=None,
        description="Raw output returned by the local model for provenance and auditability."
    )


def map_categories_to_fingerprint(
    method_name: str,
    categories: List[str],
    method_body: str,
    raw_output: Optional[str] = None
) -> BehavioralFingerprint:
    """
    Maps fine-tuned CodeT5 categories and method body into a BehavioralFingerprint
    for seamless integration with the multi-dimensional BehavioralDriftEngine.
    """
    preconditions: List[str] = []
    postconditions: List[str] = []
    state_mutations: List[str] = []
    side_effects: List[str] = []
    exceptions_thrown: List[str] = []
    return_behavior = ""

    cat_set = set(categories)

    if "VALIDATION_CONTROL_FLOW" in cat_set:
        preconditions.append("VALIDATION_CONTROL_FLOW: Input validation / control flow branching")

    if "STATE_MUTATION" in cat_set:
        state_mutations.append("STATE_MUTATION: Mutates internal object or parameter state")

    if "DATABASE_WRITE" in cat_set:
        side_effects.append("DATABASE_WRITE: Persists or modifies persistent records")

    if "DATABASE_READ" in cat_set:
        side_effects.append("DATABASE_READ: Queries persistent storage")
        postconditions.append("DATABASE_READ: Retrieval guarantees from data store")

    if "EXTERNAL_CALL" in cat_set:
        side_effects.append("EXTERNAL_CALL: Synchronous or asynchronous remote integration")

    if "FILE_OPERATION" in cat_set:
        side_effects.append("FILE_OPERATION: File system read, write, or mutation")

    if "LOGGING" in cat_set:
        side_effects.append("LOGGING: Diagnostic or audit log entries emitted")

    if "EXCEPTION_BEHAVIOR" in cat_set:
        exceptions_thrown.append("EXCEPTION_BEHAVIOR: Explicit runtime or checked exception handling/raising")

    if "CALCULATION_TRANSFORMATION" in cat_set:
        postconditions.append("CALCULATION_TRANSFORMATION: Mathematical, string, or entity transformation")

    if "OUTPUT_BEHAVIOR" in cat_set:
        postconditions.append("OUTPUT_BEHAVIOR: Computes and returns specific response data")
        return_behavior = "Computes and returns value based on input transformations."

    return BehavioralFingerprint(
        method_name=method_name,
        categories=categories,
        method_body=method_body,
        preconditions=preconditions,
        postconditions=postconditions,
        state_mutations=state_mutations,
        side_effects=side_effects,
        exceptions_thrown=exceptions_thrown,
        return_behavior=return_behavior,
        raw_llm_response=raw_output
    )


class LLMSemanticAnalyzer:
    """
    Interfaces with the local FastAPI CodeT5 service to classify Java methods
    and produce standardized BehavioralFingerprint objects.
    Replaces Groq Cloud API with local inference.
    """

    def __init__(
        self,
        service_url: Optional[str] = None,
        timeout_seconds: int = 60,
        api_key: Optional[str] = None,     # Kept for backward compatibility
        model_name: Optional[str] = None,  # Kept for backward compatibility
        temperature: float = 0.0,          # Kept for backward compatibility
        client: Optional[Any] = None       # Kept for backward compatibility
    ):
        raw_url = service_url or os.getenv("CODET5_SERVICE_URL", "http://localhost:8000")
        self.service_url = raw_url.rstrip("/")
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", str(timeout_seconds)))

    def check_connection(self) -> Dict[str, Any]:
        """
        Verifies connectivity to the local CodeT5 inference service.
        """
        health_url = f"{self.service_url}/health"
        try:
            resp = requests.get(health_url, timeout=min(5, self.timeout_seconds))
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "connected": True,
                    "provider": "Local CodeT5 (Salesforce/codet5-small)",
                    "status": data.get("status"),
                    "device": data.get("device"),
                    "model_path": data.get("model_path"),
                    "service_url": self.service_url,
                }
            return {
                "connected": False,
                "error": f"Service returned HTTP {resp.status_code}: {resp.text}",
                "service_url": self.service_url,
                "provider": "Local CodeT5"
            }
        except Exception as e:
            return {
                "connected": False,
                "error": (
                    f"Could not connect to local CodeT5 service at {self.service_url}. "
                    f"Please ensure 'python inference_service.py' is running. Error: {e}"
                ),
                "service_url": self.service_url,
                "provider": "Local CodeT5"
            }

    def analyze_pair(self, old_code: str, new_code: str) -> Dict[str, Any]:
        """
        Sends baseline and modified Java code to the local /analyze endpoint.
        Returns the structured analysis response.
        """
        analyze_url = f"{self.service_url}/analyze"
        payload = {
            "old_method": old_code,
            "new_method": new_code
        }
        try:
            resp = requests.post(
                analyze_url,
                json=payload,
                timeout=self.timeout_seconds,
                headers={"Content-Type": "application/json"}
            )
            if resp.status_code != 200:
                error_detail = resp.text
                try:
                    error_json = resp.json()
                    error_detail = error_json.get("detail", error_detail)
                except Exception:
                    pass
                raise RuntimeError(f"Local CodeT5 service returned HTTP {resp.status_code}: {error_detail}")

            return resp.json()
        except requests.exceptions.ConnectionError as ce:
            raise ConnectionError(
                f"Connection failed to local CodeT5 service at {analyze_url}. "
                f"Make sure the FastAPI service is running: {ce}"
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Local CodeT5 inference timed out after {self.timeout_seconds} seconds.")

    def extract_pair_fingerprints(
        self,
        v1: JavaMethod,
        v2: JavaMethod
    ) -> Tuple[BehavioralFingerprint, BehavioralFingerprint, Dict[str, Any]]:
        """
        Analyzes a pair of Java methods using the fine-tuned CodeT5 model.
        Returns (v1_fingerprint, v2_fingerprint, comparison_dict).
        """
        result = self.analyze_pair(v1.raw_code, v2.raw_code)

        old_res = result["old_method"]
        new_res = result["new_method"]
        comparison = result.get("comparison", {})
        raw_output = result.get("raw_output")

        fp1 = map_categories_to_fingerprint(
            method_name=v1.name,
            categories=old_res.get("categories", []),
            method_body=old_res.get("method_body", ""),
            raw_output=raw_output
        )

        fp2 = map_categories_to_fingerprint(
            method_name=v2.name,
            categories=new_res.get("categories", []),
            method_body=new_res.get("method_body", ""),
            raw_output=raw_output
        )

        return fp1, fp2, comparison

    def extract_fingerprint(
        self,
        method: JavaMethod,
        companion_method: Optional[JavaMethod] = None,
        is_baseline: bool = True
    ) -> BehavioralFingerprint:
        """
        Extracts the semantic fingerprint for a single Java method.
        If companion_method is provided, analyzes them as a pair;
        otherwise, analyzes method paired with itself to obtain classification.
        """
        v1_code = method.raw_code if is_baseline else (companion_method.raw_code if companion_method else method.raw_code)
        v2_code = (companion_method.raw_code if companion_method else method.raw_code) if is_baseline else method.raw_code

        result = self.analyze_pair(v1_code, v2_code)
        key = "old_method" if is_baseline else "new_method"
        method_data = result[key]

        return map_categories_to_fingerprint(
            method_name=method.name,
            categories=method_data.get("categories", []),
            method_body=method_data.get("method_body", ""),
            raw_output=result.get("raw_output")
        )

    def _parse_llm_json_response(self, method_name: str, raw_text: str) -> BehavioralFingerprint:
        """
        Legacy JSON parser preserved for backward compatibility with unit tests.
        """
        cleaned = raw_text.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{") and candidate.endswith("}"):
                    cleaned = candidate
                    break

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start:end + 1]

        try:
            data = json.loads(cleaned)
            # Check if CodeT5 format: {"old_method": {...}, "new_method": {...}}
            if "old_method" in data and isinstance(data["old_method"], dict):
                target = data["old_method"]
                return map_categories_to_fingerprint(
                    method_name=method_name,
                    categories=target.get("categories", []),
                    method_body=target.get("method_body", ""),
                    raw_output=raw_text
                )
            # Legacy format
            return BehavioralFingerprint(
                method_name=method_name,
                preconditions=data.get("preconditions", []),
                postconditions=data.get("postconditions", []),
                state_mutations=data.get("state_mutations", []),
                side_effects=data.get("side_effects", []),
                exceptions_thrown=data.get("exceptions_thrown", []),
                return_behavior=str(data.get("return_behavior", "")),
                invariants_and_assumptions=data.get("invariants_and_assumptions", []),
                raw_llm_response=raw_text
            )
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON from model output.")
            return BehavioralFingerprint(
                method_name=method_name,
                return_behavior="Raw output received but could not parse strict JSON.",
                raw_llm_response=raw_text
            )


# Alias for explicit CodeT5 naming
CodeT5Analyzer = LLMSemanticAnalyzer
