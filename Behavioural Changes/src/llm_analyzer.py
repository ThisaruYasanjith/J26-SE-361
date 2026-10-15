"""
Module: llm_analyzer.py
Stage: LLM Semantic Analyzer & Behavioral Fingerprinting

Connects to Groq Cloud API running high-performance open models (e.g. llama-3.3-70b-versatile,
llama-3.1-8b-instant) to extract structured behavioral fingerprints from Java method implementations.
"""

import os
import json
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from groq import Groq

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
    Interfaces with Groq Cloud API to semantically analyze Java method behavior
    and produce standardized BehavioralFingerprint objects.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: int = 60,
        temperature: float = 0.1,
        client: Optional[Any] = None
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model_name = model_name or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", str(timeout_seconds)))
        self.temperature = float(os.getenv("TEMPERATURE", str(temperature)))
        self.client = client or (Groq(api_key=self.api_key) if self.api_key else None)

    def check_connection(self) -> Dict[str, Any]:
        """
        Verifies connectivity to Groq Cloud API and returns available models.
        """
        if not self.api_key:
            return {
                "connected": False,
                "error": "GROQ_API_KEY is not set. Please provide a valid Groq API key in your .env file or UI.",
                "provider": "Groq Cloud"
            }

        try:
            client = self.client or Groq(api_key=self.api_key)
            models_resp = client.models.list()
            available = [m.id for m in models_resp.data]
            return {
                "connected": True,
                "available_models": available,
                "target_model_present": any(self.model_name in m for m in available),
                "model_name": self.model_name,
                "provider": "Groq Cloud"
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "model_name": self.model_name,
                "provider": "Groq Cloud"
            }

    def extract_fingerprint(self, method: JavaMethod) -> BehavioralFingerprint:
        """
        Prompts Groq Cloud LLM to extract the semantic behavioral fingerprint of a Java method.
        """
        if not self.api_key:
            raise ConnectionError("GROQ_API_KEY is not configured.")

        prompt = self._build_fingerprint_prompt(method)
        client = self.client or Groq(api_key=self.api_key)

        try:
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert static analysis and formal methods assistant.\n"
                            "Analyze the Java method and extract its precise semantic behavioral fingerprint.\n"
                            "You MUST return ONLY a valid JSON object matching the requested schema."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                timeout=self.timeout_seconds
            )
            raw_text = completion.choices[0].message.content or ""
            return self._parse_llm_json_response(method.name, raw_text)
        except Exception as e:
            logger.error(f"Error querying Groq: {e}")
            raise ConnectionError(
                f"Failed to query Groq Cloud using model '{self.model_name}': {e}"
            )

    def _build_fingerprint_prompt(self, method: JavaMethod) -> str:
        """Constructs a strict system prompt to elicit structured JSON behavioral analysis."""
        return f"""Analyze the following Java method and extract its precise semantic behavioral fingerprint.

METHOD SIGNATURE:
{method.signature_str}

METHOD IMPLEMENTATION:
```java
{method.raw_code}
```

You MUST return ONLY a valid, raw JSON object with this exact schema:
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
            logger.warning("Failed to decode JSON from LLM output. Creating fallback fingerprint.")
            return BehavioralFingerprint(
                method_name=method_name,
                return_behavior="Raw output received but could not parse strict JSON.",
                raw_llm_response=raw_text
            )
