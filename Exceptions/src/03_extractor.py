"""
Extractor for Java exception-handling constructs.

For each try-catch construct in a .java file, extracts one record with:
  - code: the full enclosing method source, comments stripped
  - metadata: file path, method name, class name, line ranges, etc.

This module is the linchpin of the pipeline. It is used:
  1. At training time (Python) to build dataset.json
  2. At runtime (via a parallel JS implementation) in the VS Code extension

Both implementations must produce IDENTICAL `code` fields. Test on the
same files, diff character-by-character before trusting either one.

Run standalone for testing:
    python src/03_extractor.py <path-to-java-file>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import tree_sitter
import tree_sitter_java

# ============================================================
# PARSER SETUP
# ============================================================

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
_PARSER = tree_sitter.Parser(JAVA_LANGUAGE)


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def extract_from_file(file_path: str | Path) -> list[dict[str, Any]]:
    """
    Extract all try-catch constructs from a Java file.

    Returns a list of records, one per try statement.
    Each record's `code` field is the enclosing method source,
    comments stripped.
    """
    path = Path(file_path)

    if not _is_processable_file(path):
        return []

    try:
        source = path.read_bytes()
    except OSError:
        return []

    tree = _parse_source(source)
    if tree is None:
        return []

    try_nodes = _find_try_statements(tree.root_node)
    if not try_nodes:
        return []

    records: list[dict[str, Any]] = []
    for try_node in try_nodes:
        method_node = _find_enclosing_method(try_node)
        if method_node is None:
            continue

        code = _extract_method_source(method_node, source)
        code = _strip_comments(code)
        code = _cleanup_whitespace(code)

        record = {
            "code": code,
            "file_path": str(path),
            "method_name": _get_method_name(method_node, source),
            "class_name": _get_class_name(method_node, source),
            "method_start_line": method_node.start_point[0] + 1,
            "method_end_line": method_node.end_point[0] + 1,
            "try_start_line": try_node.start_point[0] + 1,
            "try_end_line": try_node.end_point[0] + 1,
            "construct_type": _classify_construct(try_node, source),
            "caught_exception_types": _get_caught_types(try_node, source),
            "has_finally": _has_finally(try_node),
        }

        if _validate_record(record):
            records.append(record)

    return records


# ============================================================
# FILE VALIDATION
# ============================================================

def _is_processable_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix != ".java":
        return False
    size = path.stat().st_size
    if size < 10 or size > 5 * 1024 * 1024:
        return False
    return True


# ============================================================
# PARSING
# ============================================================

def _parse_source(source: bytes) -> tree_sitter.Tree | None:
    try:
        return _PARSER.parse(source)
    except Exception:
        return None


# ============================================================
# TRY DISCOVERY
# ============================================================

def _find_try_statements(root: tree_sitter.Node) -> list[tree_sitter.Node]:
    """Collect all try_statement nodes in the AST."""
    result: list[tree_sitter.Node] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "try_statement":
            result.append(node)
        # Push children in reverse so we process left-to-right
        for child in reversed(node.children):
            stack.append(child)
    # Sort by position so output is deterministic
    result.sort(key=lambda n: n.start_byte)
    return result


# ============================================================
# ENCLOSING METHOD / CLASS
# ============================================================

def _find_enclosing_method(try_node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Walk up the AST to the nearest method or constructor declaration."""
    node = try_node.parent
    while node is not None:
        if node.type in ("method_declaration", "constructor_declaration"):
            return node
        node = node.parent
    return None


def _find_enclosing_class(method_node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Walk up the AST to the nearest class/interface/enum declaration."""
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


# ============================================================
# SOURCE EXTRACTION
# ============================================================

def _extract_method_source(method_node: tree_sitter.Node, source: bytes) -> str:
    """Return the source bytes of the method as a UTF-8 string."""
    return source[method_node.start_byte:method_node.end_byte].decode("utf-8")


def _get_method_name(method_node: tree_sitter.Node, source: bytes) -> str:
    """Return the method's name identifier."""
    name_node = method_node.child_by_field_name("name")
    if name_node is None:
        return "<unknown>"
    return source[name_node.start_byte:name_node.end_byte].decode("utf-8")


def _get_class_name(method_node: tree_sitter.Node, source: bytes) -> str:
    """Return the enclosing class name, or '<unknown>'."""
    class_node = _find_enclosing_class(method_node)
    if class_node is None:
        return "<unknown>"
    name_node = class_node.child_by_field_name("name")
    if name_node is None:
        return "<unknown>"
    return source[name_node.start_byte:name_node.end_byte].decode("utf-8")


# ============================================================
# COMMENT STRIPPING
# ============================================================

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    """
    Remove // line comments and /* */ block comments from Java source.

    NOTE: This is a regex-based approach. It does not handle comment-like
    sequences inside string literals. Our synthetic dataset never has
    such cases, and real-world code rarely does inside methods.
    """
    text = _BLOCK_COMMENT_RE.sub("", text)
    text = _LINE_COMMENT_RE.sub("", text)
    return text


# ============================================================
# WHITESPACE CLEANUP
# ============================================================

def _cleanup_whitespace(text: str) -> str:
    """
    - Trim trailing whitespace on each line
    - Collapse 3+ consecutive blank lines into 1
    - Strip leading/trailing blank lines of the method
    """
    lines = text.splitlines()
    # Strip trailing whitespace per line
    lines = [ln.rstrip() for ln in lines]
    # Collapse runs of blank lines
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
    # Strip leading/trailing blank lines
    while cleaned and cleaned[0].strip() == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()
    return "\n".join(cleaned)


# ============================================================
# CONSTRUCT METADATA
# ============================================================

def _classify_construct(try_node: tree_sitter.Node, source: bytes) -> str:
    """
    Determine the try-catch construct type.

    - "try-with-resources"  : try (Resource r = ...) { ... }
    - "try-catch-finally"   : try { ... } catch (...) { ... } finally { ... }
    - "multi-catch"         : catch (A | B e) { ... }
    - "try-catch"           : default
    """
    has_resources = any(child.type == "resource_specification" for child in try_node.children)
    has_finally = _has_finally(try_node)
    has_multi_catch = _has_multi_catch(try_node, source)

    if has_resources:
        return "try-with-resources"
    if has_finally:
        return "try-catch-finally"
    if has_multi_catch:
        return "multi-catch"
    return "try-catch"


def _has_finally(try_node: tree_sitter.Node) -> bool:
    for child in try_node.children:
        if child.type == "finally_clause":
            return True
    return False


def _has_multi_catch(try_node: tree_sitter.Node, source: bytes) -> bool:
    """
    Return True if any catch clause has a union type (A | B).

    In tree-sitter-java, `catch_type` is present in every catch clause.
    The multi-catch signal is whether the catch_type's source text
    contains a `|` (the union separator).
    """
    for child in try_node.children:
        if child.type != "catch_clause":
            continue
        for sub in _walk(child):
            if sub.type == "catch_type":
                node_text = source[sub.start_byte:sub.end_byte].decode("utf-8")
                if "|" in node_text:
                    return True
    return False


def _get_caught_types(try_node: tree_sitter.Node, source: bytes) -> list[str]:
    """
    Return the list of exception types caught by this try statement.

    Examples:
        catch (IOException e) { ... }              -> ["IOException"]
        catch (IOException | SQLException e) {...} -> ["IOException", "SQLException"]
        two catch clauses                          -> combined list
    """
    caught: list[str] = []
    for child in try_node.children:
        if child.type != "catch_clause":
            continue
        # Walk only the catch_formal_parameter node(s) inside this catch_clause.
        for sub in child.children:
            if sub.type == "catch_formal_parameter":
                for desc in _walk(sub):
                    if desc.type in ("type_identifier", "scoped_type_identifier"):
                        caught.append(source[desc.start_byte:desc.end_byte].decode("utf-8"))
    # Deduplicate while preserving order
    seen = set()
    result = []
    for t in caught:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _walk(node: tree_sitter.Node):
    """Yield node and all descendants in pre-order."""
    yield node
    for child in node.children:
        yield from _walk(child)


# ============================================================
# VALIDATION
# ============================================================

def _validate_record(record: dict[str, Any]) -> bool:
    code = record["code"]
    if not code or len(code) < 20:
        return False
    if "try" not in code:
        return False
    if "catch" not in code and "finally" not in code:
        return False
    if code.count("{") != code.count("}"):
        return False
    if len(code) > 4000:
        return False
    return True


# ============================================================
# CLI
# ============================================================

def _main():
    if len(sys.argv) != 2:
        print("Usage: python src/03_extractor.py <path-to-java-file>", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    records = extract_from_file(file_path)

    if not records:
        print("No records extracted.")
        sys.exit(0)

    for i, record in enumerate(records, 1):
        print(f"\n===== Record {i} of {len(records)} =====")
        print(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()