from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter_languages  # type: ignore
from tree_sitter import Node, Parser

from synapse.utils.serialization import stable_hash

PYTHON_SUFFIXES = {".py"}
JAVASCRIPT_SUFFIXES = {".js", ".jsx"}
TYPESCRIPT_SUFFIXES = {".ts", ".tsx"}
GO_SUFFIXES = {".go"}
RUST_SUFFIXES = {".rs"}
JAVA_SUFFIXES = {".java"}
CPP_SUFFIXES = {".cpp", ".cc", ".cxx", ".hpp", ".h"}
RUBY_SUFFIXES = {".rb"}


@dataclass(frozen=True)
class CodeSymbol:
    stable_id: str
    kind: str
    name: str
    source_path: str
    start_line: int
    end_line: int
    ast_hash: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CodeParseResult:
    path: str
    language: str
    symbols: tuple[CodeSymbol, ...]
    imports: tuple[str, ...] = ()
    syntax_error: str | None = None


class CodeParserRegistry:
    """Deterministic AST parser using Tree-sitter for structural grounding."""

    def __init__(self) -> None:
        self._parsers: dict[str, Parser] = {}

    def _get_parser(self, lang_name: str) -> Parser:
        if lang_name not in self._parsers:
            lang = tree_sitter_languages.get_language(lang_name)
            parser = Parser()
            parser.set_language(lang)
            self._parsers[lang_name] = parser
        return self._parsers[lang_name]

    def parse(self, path: Path, *, relative_path: str) -> CodeParseResult:
        suffix = path.suffix.lower()
        text = path.read_text(encoding="utf-8", errors="replace")

        if suffix in PYTHON_SUFFIXES:
            return self._parse_tree_sitter(text, "python", relative_path)
        if suffix in JAVASCRIPT_SUFFIXES:
            return self._parse_tree_sitter(text, "javascript", relative_path)
        if suffix in TYPESCRIPT_SUFFIXES:
            return self._parse_tree_sitter(text, "tsx", relative_path)
        if suffix in GO_SUFFIXES:
            return self._parse_tree_sitter(text, "go", relative_path)
        if suffix in RUST_SUFFIXES:
            return self._parse_tree_sitter(text, "rust", relative_path)
        if suffix in JAVA_SUFFIXES:
            return self._parse_tree_sitter(text, "java", relative_path)
        if suffix in CPP_SUFFIXES:
            return self._parse_tree_sitter(text, "cpp", relative_path)
        if suffix in RUBY_SUFFIXES:
            return self._parse_tree_sitter(text, "ruby", relative_path)

        return CodeParseResult(path=relative_path, language="unknown", symbols=())

    def _parse_tree_sitter(self, text: str, lang_name: str, relative_path: str) -> CodeParseResult:
        parser = self._get_parser(lang_name)
        tree = parser.parse(bytes(text, "utf8"))

        symbols: list[CodeSymbol] = []
        imports: list[str] = []

        # Simple recursive traversal to extract symbols
        def traverse(node: Node) -> None:
            kind = node.type
            name = None

            # Basic symbol extraction logic per language
            if lang_name == "python":
                if kind in ("class_definition", "function_definition"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = text[name_node.start_byte : name_node.end_byte]
                elif kind == "import_from_statement":
                    module_node = node.child_by_field_name("module_name")
                    if module_node:
                        imports.append(text[module_node.start_byte : module_node.end_byte])
                elif kind == "import_statement":
                    for child in node.children:
                        if child.type == "dotted_name":
                            imports.append(text[child.start_byte : child.end_byte])

            elif lang_name in ("javascript", "tsx"):
                # Capturing classes, functions, methods, interfaces, and types
                if kind in (
                    "class_declaration",
                    "function_declaration",
                    "method_definition",
                    "interface_declaration",
                    "type_alias_declaration",
                    "class",
                ):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = text[name_node.start_byte : name_node.end_byte]
                elif kind == "variable_declarator":
                    # Catch const foo = () => ...
                    name_node = node.child_by_field_name("name")
                    value_node = node.child_by_field_name("value")
                    if (
                        name_node
                        and value_node
                        and value_node.type in ("arrow_function", "function_expression")
                    ):
                        name = text[name_node.start_byte : name_node.end_byte]
                        kind = "function_definition"

                elif kind == "import_statement":
                    source_node = node.child_by_field_name("source")
                    if source_node:
                        imports.append(
                            text[source_node.start_byte : source_node.end_byte].strip("'\"")
                        )

            elif lang_name == "go":
                if kind in ("function_declaration", "method_declaration", "type_spec"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = text[name_node.start_byte : name_node.end_byte]
                elif kind == "import_spec":
                    path_node = node.child_by_field_name("path")
                    if path_node:
                        imports.append(text[path_node.start_byte : path_node.end_byte].strip('"'))

            elif lang_name == "rust":
                if kind in ("function_item", "struct_item", "enum_item", "trait_item", "impl_item"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = text[name_node.start_byte : name_node.end_byte]
                    elif kind == "impl_item":
                        type_node = node.child_by_field_name("type")
                        if type_node:
                            name = "impl " + text[type_node.start_byte : type_node.end_byte]

            elif lang_name == "java":
                if kind in (
                    "class_declaration",
                    "method_declaration",
                    "interface_declaration",
                    "enum_declaration",
                ):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = text[name_node.start_byte : name_node.end_byte]

            elif lang_name == "cpp":
                if kind in ("function_definition", "class_specifier", "struct_specifier"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = text[name_node.start_byte : name_node.end_byte]
                    else:
                        # Fallback to declarator
                        declarator = node.child_by_field_name("declarator")
                        if declarator:
                            name_node = declarator.child_by_field_name("declarator")
                            if name_node:
                                name = text[name_node.start_byte : name_node.end_byte]

            elif lang_name == "ruby":
                if kind in ("class", "module", "method"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = text[name_node.start_byte : name_node.end_byte]

            if name:
                # Compute hash of the node's subtree for change detection
                ast_content = text[node.start_byte : node.end_byte]
                ast_hash = stable_hash(ast_content)

                symbols.append(
                    CodeSymbol(
                        stable_id=stable_hash({"path": relative_path, "name": name, "kind": kind}),
                        kind=kind,
                        name=name,
                        source_path=relative_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        ast_hash=ast_hash,
                    )
                )

            for child in node.children:
                traverse(child)

        traverse(tree.root_node)

        return CodeParseResult(
            path=relative_path,
            language=lang_name,
            symbols=tuple(symbols),
            imports=tuple(sorted(set(imports))),
        )
