"""
Module: method_parser.py
Stage: Java Method Input & Parsing

Responsible for parsing raw Java method code into structured object models.
Supports isolated method snippets, annotations, generics, and class-wrapped declarations.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import re


class MethodParameter(BaseModel):
    """Represents a single parameter of a Java method."""
    type: str
    name: str


class JavaMethod(BaseModel):
    """Represents a parsed Java method."""
    raw_code: str
    name: str
    return_type: str
    parameters: List[MethodParameter] = Field(default_factory=list)
    modifiers: List[str] = Field(default_factory=list)
    annotations: List[str] = Field(default_factory=list)
    thrown_exceptions: List[str] = Field(default_factory=list)
    body: str = ""
    docstring: Optional[str] = None

    @property
    def signature_str(self) -> str:
        """Normalized representation of the method signature."""
        params_str = ", ".join(f"{p.type} {p.name}" for p in self.parameters)
        mods_str = " ".join(self.modifiers) + " " if self.modifiers else ""
        throws_str = f" throws {', '.join(self.thrown_exceptions)}" if self.thrown_exceptions else ""
        return f"{mods_str}{self.return_type} {self.name}({params_str}){throws_str}".strip()


class MethodParser:
    """Parser to extract structured JavaMethod models from raw Java code strings."""

    def __init__(self):
        # Regex to match annotations
        self._annotation_pattern = re.compile(r"@\w+(?:\([^)]*\))?")
        
        # Regex to match Java method declaration headers
        self._header_pattern = re.compile(
            r"(?:(/\*\*.*?\*/)\s*)?"  # Optional javadoc comment
            r"((?:@\w+(?:\([^)]*\))?\s*)*)"  # Optional annotations
            r"((?:(?:public|protected|private|static|final|synchronized|abstract|default)\s+)*)"  # Modifiers
            r"([\w<>\[\],\s\?]+?)\s+"  # Return type (with generics)
            r"(\b[a-zA-Z_]\w*\b)\s*"  # Method name
            r"\(([^)]*)\)\s*"  # Parameters
            r"(?:throws\s+([^{;]+))?\s*"  # Throws clause
            r"(\{.*|;)",  # Body start or abstract semicolon
            re.DOTALL
        )

    def parse(self, code: str) -> JavaMethod:
        """
        Parses a single Java method string into a JavaMethod instance.
        Uses AST-based extraction when possible with robust regex fallback.
        """
        cleaned_code = code.strip()

        # Try AST parsing via javalang if available
        try:
            import javalang
            wrapped = f"public class WrapperClass {{\n{cleaned_code}\n}}"
            tree = javalang.parse.parse(wrapped)
            if tree.types and tree.types[0].methods:
                ast_method = tree.types[0].methods[0]
                parameters = [
                    MethodParameter(
                        type=self._format_ast_type(param.type),
                        name=param.name
                    )
                    for param in ast_method.parameters
                ]
                return_type = "void" if ast_method.return_type is None else self._format_ast_type(ast_method.return_type)
                modifiers = list(ast_method.modifiers) if ast_method.modifiers else []
                throws = list(ast_method.throws) if ast_method.throws else []
                annotations = [
                    f"@{ann.name}" if not hasattr(ann, 'element') or not ann.element else f"@{ann.name}({ann.element})"
                    for ann in (ast_method.annotations or [])
                ]

                return JavaMethod(
                    raw_code=cleaned_code,
                    name=ast_method.name,
                    return_type=return_type,
                    parameters=parameters,
                    modifiers=modifiers,
                    annotations=annotations,
                    thrown_exceptions=throws,
                    body=self._extract_body(cleaned_code),
                    docstring=self._extract_docstring(cleaned_code)
                )
        except Exception:
            # Fall back to regex parser
            pass

        return self._parse_regex(cleaned_code)

    def _format_ast_type(self, type_node: Any) -> str:
        """Formats a javalang type node into a string type, preserving sub_types, generics, and dimensions."""
        if hasattr(type_node, 'name'):
            curr = type_node
            names = []
            while curr:
                names.append(curr.name)
                curr = getattr(curr, 'sub_type', None)
            base = ".".join(names)
            if hasattr(type_node, 'arguments') and type_node.arguments:
                arg_strs = []
                for arg in type_node.arguments:
                    if hasattr(arg, 'type') and arg.type:
                        arg_strs.append(self._format_ast_type(arg.type))
                    elif hasattr(arg, 'pattern_type') and arg.pattern_type:
                        arg_strs.append(str(arg.pattern_type))
                    else:
                        arg_strs.append(str(arg))
                base += f"<{', '.join(arg_strs)}>"
            if hasattr(type_node, 'dimensions') and type_node.dimensions:
                base += "[]" * len(type_node.dimensions)
            return base
        return str(type_node)

    def _parse_regex(self, code: str) -> JavaMethod:
        """Regex-based parser for isolated method snippets."""
        match = self._header_pattern.search(code)
        if not match:
            # Fallback for unconventional headers
            lines = code.strip().splitlines()
            first_line = lines[0] if lines else "unknownMethod()"
            return JavaMethod(
                raw_code=code,
                name="unknownMethod",
                return_type="void",
                parameters=[],
                modifiers=[],
                annotations=[],
                thrown_exceptions=[],
                body=self._extract_body(code)
            )

        docstring = match.group(1)
        raw_annotations = match.group(2) or ""
        raw_modifiers = match.group(3) or ""
        return_type = re.sub(r"\s+", " ", match.group(4).strip())
        name = match.group(5).strip()
        raw_params = match.group(6) or ""
        raw_throws = match.group(7) or ""

        annotations = [ann.strip() for ann in self._annotation_pattern.findall(raw_annotations)]
        modifiers = [m for m in raw_modifiers.split() if m]
        thrown_exceptions = [t.strip() for t in raw_throws.split(",") if t.strip()]

        parameters: List[MethodParameter] = []
        if raw_params.strip():
            param_parts = self._split_parameters(raw_params)
            for part in param_parts:
                tokens = part.split()
                if len(tokens) >= 2:
                    p_name = tokens[-1]
                    p_type = " ".join(tokens[:-1])
                    parameters.append(MethodParameter(type=p_type, name=p_name))
                elif len(tokens) == 1:
                    parameters.append(MethodParameter(type=tokens[0], name="arg"))

        body = self._extract_body(code)

        return JavaMethod(
            raw_code=code,
            name=name,
            return_type=return_type,
            parameters=parameters,
            modifiers=modifiers,
            annotations=annotations,
            thrown_exceptions=thrown_exceptions,
            body=body,
            docstring=docstring
        )

    def _split_parameters(self, raw_params: str) -> List[str]:
        """Splits parameter string taking generic brackets into account."""
        parts = []
        current = []
        depth = 0
        for char in raw_params:
            if char in "<[(":
                depth += 1
                current.append(char)
            elif char in ">])":
                depth -= 1
                current.append(char)
            elif char == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            parts.append("".join(current).strip())
        return [p for p in parts if p]

    def _extract_docstring(self, code: str) -> Optional[str]:
        """Extracts javadoc docstring if present at beginning."""
        match = re.match(r"\s*(/\*\*.*?\*/)", code, re.DOTALL)
        return match.group(1).strip() if match else None

    def _extract_body(self, code: str) -> str:
        """Extracts content inside the outer curly braces of the method body."""
        start_idx = code.find("{")
        end_idx = code.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return code[start_idx + 1:end_idx].strip()
        return code
