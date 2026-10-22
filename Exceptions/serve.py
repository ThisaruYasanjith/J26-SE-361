"""
Exception Defect Detection Microservice.

Loads the trained ablation combined model (ablation_combined_15class.pt)
and provides an HTTP API endpoint (/analyze) to detect exception handling defects
in Java source files.

Usage:
    python serve.py [--port 8000] [--host 127.0.0.1]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import tree_sitter
import tree_sitter_java
from transformers import AutoConfig, AutoModel, AutoTokenizer

# Suppress Hugging Face warnings
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["HF_HUB_DISABLE_SAFETENSORS_CONVERSION"] = "1"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ExceptionService")

# ============================================================
# CONFIG & PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
AST_VOCAB_PATH = PROJECT_ROOT / "data" / "processed" / "ast_vocab.json"
CATEGORY_MAP_PATH = PROJECT_ROOT / "data" / "processed" / "category_map.json"
CHECKPOINT_PATH = PROJECT_ROOT / "models" / "ablation_combined_15class.pt"

GCBERT_MODEL_NAME = "microsoft/graphcodebert-base"
MAX_TOKEN_LEN = 512
MAX_AST_LEN = 256

SEMANTIC_DIM = 768
AST_EMBED_DIM = 128
AST_HIDDEN_DIM = 128
AST_NUM_LAYERS = 2
AST_NUM_HEADS = 4
AST_FF_DIM = 512
FUSION_HIDDEN = 256
NUM_CATEGORIES = 15

# ============================================================
# CATEGORY METADATA
# ============================================================

CATEGORY_METADATA = {
    "clean": {
        "title": "Clean Exception Handling",
        "severity": "Clean",
        "description": "No exception handling defects detected in this construct.",
        "recommendation": "No changes needed.",
    },
    "empty_catch": {
        "title": "Empty Catch Block",
        "severity": "Critical",
        "description": "Caught exception is completely ignored without logging, rethrowing, or error recovery.",
        "recommendation": "Handle the exception, log the stack trace with a logger, or rethrow.",
    },
    "overly_broad_catch": {
        "title": "Overly Broad Catch",
        "severity": "Warning",
        "description": "Catches generic Exception or Throwable, which may inadvertently catch and mask unexpected runtime defects.",
        "recommendation": "Catch specific checked and unchecked exception types rather than generic Exception.",
    },
    "print_stacktrace": {
        "title": "Print Stack Trace in Production",
        "severity": "Warning",
        "description": "Uses printStackTrace() instead of a structured logging framework, risking loss of context or sensitive data leaks.",
        "recommendation": "Replace e.printStackTrace() with logger.error(\"...\", e).",
    },
    "wrong_propagation": {
        "title": "Wrong Exception Propagation",
        "severity": "High",
        "description": "An exception is re-thrown in a way that obscures the original fault or violates method contracts.",
        "recommendation": "Ensure propagated exceptions preserve the correct domain abstraction.",
    },
    "exception_swallowing": {
        "title": "Exception Swallowing",
        "severity": "Critical",
        "description": "The caught exception is swallowed and execution proceeds as if nothing failed.",
        "recommendation": "Do not swallow exceptions; propagate or gracefully notify callers.",
    },
    "inappropriate_handling": {
        "title": "Inappropriate Handling",
        "severity": "Medium",
        "description": "The catch block contains inadequate error recovery logic for the anticipated failure.",
        "recommendation": "Implement appropriate fallback, clean recovery, or graceful degradation.",
    },
    "swallows_declared_exception": {
        "title": "Swallows Declared Exception",
        "severity": "High",
        "description": "Method declares an exception in its 'throws' clause but internally catches and suppresses it.",
        "recommendation": "Either let the declared exception escape or remove it from the method signature.",
    },
    "ambiguous_error_return": {
        "title": "Ambiguous Error Return",
        "severity": "Medium",
        "description": "Catch block returns null, -1, or false, creating ambiguity between valid return states and failures.",
        "recommendation": "Consider using Optional<T> or throwing a dedicated domain exception.",
    },
    "inconsistent_with_precheck": {
        "title": "Inconsistent with Precheck",
        "severity": "Medium",
        "description": "A defensive pre-check (such as null check) exists, but related exceptions are still caught inconsistently.",
        "recommendation": "Align defensive validation and exception handling consistently across the method.",
    },
    "corrupted_state_on_exception": {
        "title": "Corrupted State on Exception",
        "severity": "Critical",
        "description": "State was modified before the exception occurred without subsequent rollback, leaving objects corrupted.",
        "recommendation": "Follow the commit-or-rollback pattern or reorder statements to mutate state only after failure-prone operations.",
    },
    "missing_retry": {
        "title": "Missing Retry Policy",
        "severity": "Low",
        "description": "Transient network or I/O failure caught without an automated retry mechanism.",
        "recommendation": "Consider adding an exponential backoff retry policy for transient failures.",
    },
    "lost_exception_cause": {
        "title": "Lost Exception Cause",
        "severity": "High",
        "description": "A new exception is instantiated and thrown without passing the original caught exception as its cause.",
        "recommendation": "Chain the original exception: throw new CustomException(\"...\", e).",
    },
    "wrong_exception_type": {
        "title": "Wrong Exception Type",
        "severity": "Medium",
        "description": "Caught or thrown exception type poorly reflects the actual error condition.",
        "recommendation": "Use a semantically accurate exception class matching the failure domain.",
    },
    "empty_catch_with_context": {
        "title": "Empty Catch With Context",
        "severity": "Low",
        "description": "Catch block is empty, though comments or context indicate intentional suppression.",
        "recommendation": "Document suppression explicitly (e.g. rename parameter to 'ignored').",
    },
}

# ============================================================
# TREE SITTER SETUP
# ============================================================

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
_PARSER = tree_sitter.Parser(JAVA_LANGUAGE)

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    text = _BLOCK_COMMENT_RE.sub("", text)
    text = _LINE_COMMENT_RE.sub("", text)
    return text


def _cleanup_whitespace(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    cleaned: list[str] = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                cleaned.append("")
        else:
            blank_run = 0
            cleaned.append(ln)
    while cleaned and cleaned[0].strip() == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()
    return "\n".join(cleaned)


def _walk(node: tree_sitter.Node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _find_try_statements(root: tree_sitter.Node) -> list[tree_sitter.Node]:
    result: list[tree_sitter.Node] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in ("try_statement", "try_with_resources_statement"):
            result.append(node)
        for child in reversed(node.children):
            stack.append(child)
    result.sort(key=lambda n: n.start_byte)
    return result


def _find_enclosing_method(try_node: tree_sitter.Node) -> tree_sitter.Node | None:
    node = try_node.parent
    while node is not None:
        if node.type in ("method_declaration", "constructor_declaration"):
            return node
        node = node.parent
    return None


def _find_enclosing_class(method_node: tree_sitter.Node) -> tree_sitter.Node | None:
    node = method_node.parent
    while node is not None:
        if node.type in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "record_declaration",
        ):
            return node
        node = node.parent
    return None


def _get_node_text(node: tree_sitter.Node | None, source: bytes) -> str:
    if node is None:
        return "<unknown>"
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _serialize_ast(code: str, ast_vocab: dict[str, int]) -> list[int]:
    unk_id = ast_vocab.get("<unk>", 1)
    pad_id = ast_vocab.get("<pad>", 0)
    wrapped = f"class _Wrap {{ {code} }}"
    try:
        tree = _PARSER.parse(wrapped.encode("utf-8"))
    except Exception:
        return [pad_id] * MAX_AST_LEN

    if tree is None:
        return [pad_id] * MAX_AST_LEN

    ids: list[int] = []
    for node in _walk(tree.root_node):
        ids.append(ast_vocab.get(node.type, unk_id))
        if len(ids) >= MAX_AST_LEN:
            break

    if len(ids) < MAX_AST_LEN:
        ids += [pad_id] * (MAX_AST_LEN - len(ids))
    return ids


# ============================================================
# MODEL DEFINITION (DualStreamModel from 09_ablation.py)
# ============================================================

class DualStreamModel(nn.Module):
    def __init__(self, ast_vocab_size: int):
        super().__init__()
        config = AutoConfig.from_pretrained(GCBERT_MODEL_NAME)
        self.graphcodebert = AutoModel.from_config(config)
        self.ast_embedding = nn.Embedding(
            num_embeddings=ast_vocab_size,
            embedding_dim=AST_EMBED_DIM,
            padding_idx=0,
        )
        self.ast_position_embedding = nn.Embedding(
            num_embeddings=256,
            embedding_dim=AST_EMBED_DIM,
        )
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=AST_EMBED_DIM,
            nhead=AST_NUM_HEADS,
            dim_feedforward=AST_FF_DIM,
            dropout=0.1,
            batch_first=True,
        )
        self.ast_transformer = nn.TransformerEncoder(
            encoder_layer, num_layers=AST_NUM_LAYERS
        )
        self.ast_projection = nn.Linear(AST_EMBED_DIM, AST_HIDDEN_DIM)

        fusion_input_dim = SEMANTIC_DIM + AST_HIDDEN_DIM
        self.classifier = nn.Sequential(
            nn.Linear(fusion_input_dim, FUSION_HIDDEN),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(FUSION_HIDDEN, NUM_CATEGORIES),
        )

    def forward(self, input_ids, attention_mask, ast_ids):
        gc_out = self.graphcodebert(
            input_ids=input_ids, attention_mask=attention_mask
        )
        semantic_vec = gc_out.pooler_output

        ast_mask = ast_ids == 0
        B, L = ast_ids.shape
        positions = torch.arange(L, device=ast_ids.device).unsqueeze(0).expand(B, L)
        ast_emb = self.ast_embedding(ast_ids) + self.ast_position_embedding(positions)
        ast_out = self.ast_transformer(ast_emb, src_key_padding_mask=ast_mask)
        mask_float = (~ast_mask).float().unsqueeze(-1)
        pooled = (ast_out * mask_float).sum(dim=1) / mask_float.sum(dim=1).clamp(min=1.0)
        structural_vec = self.ast_projection(pooled)

        combined = torch.cat([semantic_vec, structural_vec], dim=-1)
        return self.classifier(combined)


# ============================================================
# INFERENCE ENGINE
# ============================================================

class ExceptionInferenceEngine:
    def __init__(self, checkpoint_path: Path = CHECKPOINT_PATH):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")

        # Load AST vocab
        with AST_VOCAB_PATH.open(encoding="utf-8") as f:
            self.ast_vocab = json.load(f)
        logger.info(f"Loaded AST vocabulary ({len(self.ast_vocab)} node types)")

        # Load category map
        with CATEGORY_MAP_PATH.open(encoding="utf-8") as f:
            self.category_map = json.load(f)
        self.id_to_category = {v: k for k, v in self.category_map.items()}
        logger.info(f"Loaded category map ({len(self.category_map)} classes)")

        # Load tokenizer
        logger.info(f"Loading tokenizer: {GCBERT_MODEL_NAME}")
        self.tokenizer = AutoTokenizer.from_pretrained(GCBERT_MODEL_NAME)

        # Initialize model
        logger.info(f"Loading ablation combined model weights from {checkpoint_path.name}...")
        self.model = DualStreamModel(ast_vocab_size=len(self.ast_vocab))
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()
        logger.info("Model loaded and ready for inference!")

    @torch.no_grad()
    def analyze_code(self, source_code: str, file_path: str = "") -> dict[str, Any]:
        source_bytes = source_code.encode("utf-8")
        tree = _PARSER.parse(source_bytes)
        if tree is None:
            return {
                "status": "error",
                "message": "Failed to parse source file with tree-sitter.",
                "defects": [],
            }

        try_nodes = _find_try_statements(tree.root_node)
        if not try_nodes:
            return {
                "status": "success",
                "filePath": file_path,
                "totalAnalyzed": 0,
                "defects": [],
                "message": "No try-catch blocks found in this file.",
            }

        defects = []
        clean_count = 0

        for i, try_node in enumerate(try_nodes, start=1):
            method_node = _find_enclosing_method(try_node)
            if method_node is None:
                continue

            class_node = _find_enclosing_class(method_node)
            method_name = _get_node_text(method_node.child_by_field_name("name"), source_bytes)
            class_name = _get_node_text(
                class_node.child_by_field_name("name") if class_node else None,
                source_bytes,
            )

            # Extract method source
            raw_method_code = source_bytes[method_node.start_byte:method_node.end_byte].decode(
                "utf-8", errors="replace"
            )
            cleaned_code = _cleanup_whitespace(_strip_comments(raw_method_code))

            if len(cleaned_code) < 15 or "try" not in cleaned_code:
                continue

            # Tokenize semantic stream
            enc = self.tokenizer(
                cleaned_code,
                max_length=MAX_TOKEN_LEN,
                truncation=True,
                padding="max_length",
                return_tensors="pt",
            )
            input_ids = enc["input_ids"].to(self.device)
            attention_mask = enc["attention_mask"].to(self.device)

            # Tokenize structural stream
            ast_ids_list = _serialize_ast(cleaned_code, self.ast_vocab)
            ast_ids = torch.tensor([ast_ids_list], dtype=torch.long, device=self.device)

            # Forward pass
            logits = self.model(input_ids, attention_mask, ast_ids)
            probs = F.softmax(logits, dim=-1)[0]
            pred_id = int(torch.argmax(probs).item())
            confidence = float(probs[pred_id].item())
            category_name = self.id_to_category.get(pred_id, "clean")

            try_start_line = try_node.start_point[0] + 1
            try_end_line = try_node.end_point[0] + 1
            method_start_line = method_node.start_point[0] + 1
            method_end_line = method_node.end_point[0] + 1

            if category_name == "clean":
                clean_count += 1
                continue

            meta = CATEGORY_METADATA.get(
                category_name,
                {
                    "title": category_name.replace("_", " ").title(),
                    "severity": "Medium",
                    "description": f"Potential exception handling defect: {category_name}.",
                    "recommendation": "Review catch block structure and error handling.",
                },
            )

            defects.append({
                "id": f"defect-{i}",
                "category": category_name,
                "title": meta["title"],
                "severity": meta["severity"],
                "description": meta["description"],
                "recommendation": meta["recommendation"],
                "className": class_name,
                "methodName": method_name,
                "tryStartLine": try_start_line,
                "tryEndLine": try_end_line,
                "methodStartLine": method_start_line,
                "methodEndLine": method_end_line,
                "confidence": round(confidence * 100, 1),
            })

        return {
            "status": "success",
            "filePath": file_path,
            "totalAnalyzed": len(try_nodes),
            "cleanCount": clean_count,
            "defectCount": len(defects),
            "defects": defects,
        }


# Global inference engine reference
_ENGINE: ExceptionInferenceEngine | None = None


# ============================================================
# HTTP REQUEST HANDLER
# ============================================================

class ExceptionServiceHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            resp = {
                "status": "healthy",
                "service": "Exception Defect Detection Microservice",
                "model": "ablation_combined_15class.pt",
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_POST(self):
        if self.path.startswith("/analyze"):
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body)
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": f"Invalid JSON payload: {e}"}).encode("utf-8"))
                return

            source_code = payload.get("code", "")
            file_path = payload.get("filePath", "")

            if not source_code:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "'code' property is required in payload."}).encode("utf-8"))
                return

            assert _ENGINE is not None
            try:
                result = _ENGINE.analyze_code(source_code, file_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))
            except Exception as e:
                logger.exception("Error during analysis:")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()


def run_server(host: str = "127.0.0.1", port: int = 8000):
    global _ENGINE
    logger.info("Initializing Exception Defect Inference Engine...")
    _ENGINE = ExceptionInferenceEngine()

    server = ThreadingHTTPServer((host, port), ExceptionServiceHandler)
    logger.info(f"Microservice is running at http://{host}:{port}/")
    logger.info("Endpoints available:")
    logger.info(f"  GET  http://{host}:{port}/health")
    logger.info(f"  POST http://{host}:{port}/analyze")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down microservice...")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exception Detection Microservice")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    args = parser.parse_args()
    run_server(args.host, args.port)
