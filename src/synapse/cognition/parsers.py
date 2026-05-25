from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from synapse.serialization import stable_hash

PYTHON_SUFFIXES = {".py"}
JAVASCRIPT_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}


@dataclass(frozen=True)
class CodeSymbol:
    stable_id: str
    kind: str
    name: str
    source_path: str
    line: int | None = None
    metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class CodeParseResult:
    path: str
    language: str
    imports: tuple[str, ...]
    symbols: tuple[CodeSymbol, ...]
    syntax_error: str | None = None


class CodeParserRegistry:
    """Parser abstraction with Tree-sitter-ready boundaries and safe fallbacks."""

    def parse(self, path: Path, *, relative_path: str) -> CodeParseResult:
        suffix = path.suffix.lower()
        if suffix in PYTHON_SUFFIXES:
            return self._parse_python(path, relative_path)
        if suffix in JAVASCRIPT_SUFFIXES:
            return self._parse_javascript(path, relative_path)
        return CodeParseResult(path=relative_path, language="unknown", imports=(), symbols=())

    def _parse_python(self, path: Path, relative_path: str) -> CodeParseResult:
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text, filename=relative_path)
        except SyntaxError as exc:
            return CodeParseResult(
                path=relative_path,
                language="python",
                imports=(),
                symbols=(),
                syntax_error=str(exc),
            )
        imports: set[str] = set()
        symbols: list[CodeSymbol] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.ClassDef):
                symbols.append(_symbol("class", node.name, relative_path, node.lineno))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                symbols.append(_symbol("function", node.name, relative_path, node.lineno))
        return CodeParseResult(
            path=relative_path,
            language="python",
            imports=tuple(sorted(imports)),
            symbols=tuple(symbols),
        )

    def _parse_javascript(self, path: Path, relative_path: str) -> CodeParseResult:
        text = path.read_text(encoding="utf-8", errors="replace")
        imports = set(re.findall(r"from\s+['\"]([^'\"]+)['\"]", text))
        imports.update(re.findall(r"import\s+['\"]([^'\"]+)['\"]", text))
        imports.update(re.findall(r"require\(['\"]([^'\"]+)['\"]\)", text))
        symbols: list[CodeSymbol] = []
        for match in re.finditer(r"\b(class|function)\s+([A-Za-z_$][\w$]*)", text):
            line = text.count("\n", 0, match.start()) + 1
            symbols.append(_symbol(match.group(1), match.group(2), relative_path, line))
        for match in re.finditer(r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", text):
            line = text.count("\n", 0, match.start()) + 1
            symbols.append(_symbol("function", match.group(1), relative_path, line))
        language = "typescript" if path.suffix.lower() in {".ts", ".tsx"} else "javascript"
        return CodeParseResult(
            path=relative_path,
            language=language,
            imports=tuple(sorted(imports)),
            symbols=tuple(symbols),
        )


def _symbol(kind: str, name: str, source_path: str, line: int | None) -> CodeSymbol:
    return CodeSymbol(
        stable_id=stable_hash(
            {"kind": kind, "name": name, "source_path": source_path, "line": line}
        ),
        kind=kind,
        name=name,
        source_path=source_path,
        line=line,
    )
