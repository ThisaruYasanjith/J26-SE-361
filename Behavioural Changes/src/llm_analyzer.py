"""
Module: llm_analyzer.py
Stage: LLM Semantic Analyzer & Behavioral Fingerprinting

Connects to a local Ollama instance running a pretrained Code LLM (e.g. codellama,
deepseek-coder, qwen2.5-coder) to extract structured behavioral fingerprints
from Java method implementations.
"""

import os
import json
import logging
from typing import List, Optional, Dict, Any
import requests
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from src.method_parser import JavaMethod

load_dotenv()
logger = logging.getLogger(__name__)


class BehavioralFingerprint(BaseModel):
    """
    Structured semantic representation of a Java method's runtime behavior.
    """
    method_name: str
    preconditions: List[str] = Field(
        default_factory=list,
        description="Assumptions or parameter validation before execution (e.g. null checks, range checks)."
    )
    postconditions: List[str] = Field(
        default_factory=list,
        description="Guarantees or properties of return values upon normal completion."
    )
    state_mutations: List[str] = Field(
        default_factory=list,
        description="Modifications to instance/class variables or mutated input parameters."
    )
    side_effects: List[str] = Field(
        default_factory=list,
        description="External interactions such as logging, I/O, database access, or event publishing."
    )
    exceptions_thrown: List[str] = Field(
        default_factory=list,
        description="Explicit or implicit runtime exceptions raised under failure conditions."
    )
    return_behavior: str = Field(
        default="",
        description="Description of the core computation and return value rules."
    )
    invariants_and_assumptions: List[str] = Field(
        default_factory=list,
        description="Loop invariants, concurrency locks, or core state invariants maintained."
    )
    raw_llm_response: Optional[str] = Field(
        default=None,
        description="Raw output returned by the LLM for provenance and auditability."
    )


class LLMSemanticAnalyzer:
    """
    Interfaces with Ollama API to semantically analyze Java method behavior
    and produce standardized BehavioralFingerprint objects.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: int = 120,
        temperature: float = 0.1
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "codellama:7b")
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", str(timeout_seconds)))
        self.temperature = float(os.getenv("TEMPERATURE", str(temperature)))

    def check_connection(self) -> Dict[str, Any]:
        """
        Verifies connectivity to Ollama server and returns available models.
        """
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name") for m in data.get("models", [])]
                return {
                    "connected": True,
                    "available_models": models,
                    "target_model_present": any(self.model_name in m for m in models),
                    "base_url": self.base_url
                }
            return {
                "connected": False,
                "error": f"Ollama returned HTTP status {resp.status_code}",
                "base_url": self.base_url
            }
        except requests.exceptions.RequestException as e:
            return {
                "connected": False,
                "error": str(e),
                "base_url": self.base_url
            }

    def extract_fingerprint(self, method: JavaMethod) -> BehavioralFingerprint:
        """
        Prompts Ollama to extract the semantic behavioral fingerprint of a Java method.
        """
        prompt = self._build_fingerprint_prompt(method)
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout_seconds
            )
            resp.raise_for_status()
            result_json = resp.json()
            raw_text = result_json.get("response", "")
            return self._parse_llm_json_response(method.name, raw_text)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error communicating with Ollama: {e}")
            raise ConnectionError(
                f"Failed to query Ollama at {self.base_url} using model '{self.model_name}': {e}"
            )

    def _build_fingerprint_prompt(self, method: JavaMethod) -> str:
        """Constructs a strict system prompt to elicit structured JSON behavioral analysis."""
        return f"""You are an expert static analysis and formal methods assistant.
Analyze the following Java method and extract its precise semantic behavioral fingerprint.

METHOD SIGNATURE:
{method.signature_str}

METHOD IMPLEMENTATION:
```java
{method.raw_code}
```

You MUST return ONLY a valid, raw JSON object (with no explanation outside JSON, no markdown backticks, no markdown formatting).
Use this exact JSON schema:
{{
  "preconditions": ["list of explicit or implicit assumptions and input validation checks"],
  "postconditions": ["list of guarantees about the return value or state upon normal completion"],
  "state_mutations": ["list of modified instance fields, object mutations, or global states"],
  "side_effects": ["list of I/O operations, logging, external API calls, DB operations"],
  "exceptions_thrown": ["list of exceptions explicitly thrown or triggered under specific error conditions"],
  "return_behavior": "clear description of how the return value is computed across logical branches",
  "invariants_and_assumptions": ["list of loop invariants or internal state guarantees"]
}}
"""

    def _parse_llm_json_response(self, method_name: str, raw_text: str) -> BehavioralFingerprint:
        """Safely parses JSON from the LLM output, handling markdown fences or preamble."""
        cleaned = raw_text.strip()

        # Strip markdown ```json ... ``` code fences if present
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{") and candidate.endswith("}"):
                    cleaned = candidate
                    break

        # Locate outermost curly braces
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start:end + 1]

        try:
            data = json.loads(cleaned)
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
            # Fallback when model produces unparsable text
            logger.warning("Failed to decode JSON from LLM output. Creating fallback fingerprint.")
            return BehavioralFingerprint(
                method_name=method_name,
                return_behavior="Raw output received but could not parse strict JSON.",
                raw_llm_response=raw_text
            )
