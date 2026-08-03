from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter_languages  # type: ignore
from tree_sitter import Node, Parser

from synap_git.utils.serialization import stable_hash


@dataclass(frozen=True)
class CodeSymbol:
    stable_id: str
    kind: str
    name: str
    source_path: str
    start_line: int
    end_line: int
    ast_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


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
        self._parsers: dict[str, Parser | None] = {}

    def _get_parser(self, lang_name: str) -> Parser | None:
        if lang_name not in self._parsers:
            try:
                lang = tree_sitter_languages.get_language(lang_name)
                parser = Parser()
                parser.set_language(lang)
                self._parsers[lang_name] = parser
            except Exception:
                self._parsers[lang_name] = None
        return self._parsers[lang_name]

    def parse(self, path: Path, *, relative_path: str, text: str | None = None) -> CodeParseResult:
        try:
            suffix = path.suffix.lower()
            if text is None:
                text = path.read_text(encoding="utf-8", errors="replace")

            from synap_git.indexer.scanner import LANGUAGE_BY_SUFFIX

            lang_name = LANGUAGE_BY_SUFFIX.get(suffix)

            # Shebang detection for files without extension
            if not lang_name and text.startswith("#!"):
                first_line = text.split("\n", 1)[0].lower()
                if "python" in first_line:
                    lang_name = "python"
                elif "node" in first_line:
                    lang_name = "javascript"
                elif "bash" in first_line or "sh" in first_line:
                    lang_name = "bash"
                elif "ruby" in first_line:
                    lang_name = "ruby"

            if lang_name:
                parser = self._get_parser(lang_name)
                if parser:
                    return self._parse_tree_sitter(text, lang_name, relative_path, parser)

            return CodeParseResult(path=relative_path, language="unknown", symbols=())
        except Exception as e:
            import structlog

            structlog.get_logger().warning("parser_failed", path=relative_path, error=str(e))
            return CodeParseResult(
                path=relative_path, language="unknown", symbols=(), syntax_error=str(e)
            )

    def _parse_tree_sitter(
        self, text: str, lang_name: str, relative_path: str, parser: Parser
    ) -> CodeParseResult:
        text_bytes = bytes(text, "utf8")
        tree = parser.parse(text_bytes)

        symbols: list[CodeSymbol] = []
        imports: list[str] = []

        def extract_text(node: Node | None) -> str | None:
            if not node:
                return None
            return text_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

        # Simple recursive traversal to extract symbols
        def traverse(node: Node) -> None:
            kind = node.type
            name = None

            # Basic symbol extraction logic per language
            if lang_name == "python":
                if kind in ("class_definition", "function_definition"):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "import_from_statement":
                    mod_name = extract_text(node.child_by_field_name("module_name"))
                    if mod_name:
                        imported_names = []
                        import_found = False
                        for child in node.children:
                            if child.type == "import":
                                import_found = True
                                continue
                            if not import_found:
                                continue
                            if child.type == "dotted_name":
                                t_val = extract_text(child)
                                if t_val:
                                    imported_names.append(t_val)
                            elif child.type == "aliased_import":
                                name_node = child.child_by_field_name("name")
                                t_val = extract_text(name_node)
                                if t_val:
                                    imported_names.append(t_val)
                            elif child.type == "import_list":

                                def find_names(n: Node) -> None:
                                    if n.type == "dotted_name":
                                        t_val = extract_text(n)
                                        if t_val:
                                            imported_names.append(t_val)
                                    elif n.type == "aliased_import":
                                        name_node = n.child_by_field_name("name")
                                        t_val = extract_text(name_node)
                                        if t_val:
                                            imported_names.append(t_val)
                                    for c in n.children:
                                        find_names(c)

                                find_names(child)
                        if imported_names:
                            for name in imported_names:
                                imports.append(f"{mod_name}:{name}")
                        else:
                            imports.append(mod_name)
                elif kind == "import_statement":
                    for child in node.children:
                        if child.type == "dotted_name":
                            imp_name = extract_text(child)
                            if imp_name:
                                imports.append(imp_name)

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
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "variable_declarator":
                    # Catch const foo = () => ...
                    value_node = node.child_by_field_name("value")
                    if value_node and value_node.type in ("arrow_function", "function_expression"):
                        name = extract_text(node.child_by_field_name("name"))
                        if name:
                            kind = "function_definition"

                elif kind == "import_statement":
                    src = extract_text(node.child_by_field_name("source"))
                    if src:
                        imports.append(src.strip("'\""))

            elif lang_name == "go":
                if kind in ("function_declaration", "method_declaration", "type_spec"):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "import_spec":
                    path_val = extract_text(node.child_by_field_name("path"))
                    if path_val:
                        imports.append(path_val.strip('"'))

            elif lang_name == "rust":
                if kind in ("function_item", "struct_item", "enum_item", "trait_item", "impl_item"):
                    name = extract_text(node.child_by_field_name("name"))
                    if not name and kind == "impl_item":
                        t_name = extract_text(node.child_by_field_name("type"))
                        if t_name:
                            name = "impl " + t_name

            elif lang_name == "java":
                if kind in (
                    "class_declaration",
                    "method_declaration",
                    "interface_declaration",
                    "enum_declaration",
                ):
                    name = extract_text(node.child_by_field_name("name"))

            elif lang_name == "cpp":
                if kind in ("function_definition", "class_specifier", "struct_specifier"):
                    name = extract_text(node.child_by_field_name("name"))
                    if not name:
                        # Fallback to declarator
                        declarator = node.child_by_field_name("declarator")
                        if declarator:
                            name = extract_text(declarator.child_by_field_name("declarator"))

            elif lang_name == "ruby":
                if kind in ("class", "module", "method"):
                    name = extract_text(node.child_by_field_name("name"))

            elif lang_name == "c_sharp":
                if kind in (
                    "class_declaration",
                    "method_declaration",
                    "interface_declaration",
                    "struct_declaration",
                    "enum_declaration",
                ):
                    name = extract_text(node.child_by_field_name("name"))

            elif lang_name == "php":
                if kind in (
                    "class_declaration",
                    "function_definition",
                    "method_declaration",
                    "interface_declaration",
                    "trait_declaration",
                ):
                    name = extract_text(node.child_by_field_name("name"))

            elif lang_name == "kotlin":
                if kind in (
                    "class_declaration",
                    "function_declaration",
                    "object_declaration",
                    "interface_declaration",
                ):
                    name = extract_text(node.child_by_field_name("name"))

            elif lang_name == "scala":
                if kind in (
                    "class_definition",
                    "object_definition",
                    "function_definition",
                    "trait_definition",
                ):
                    name = extract_text(node.child_by_field_name("name"))

            elif lang_name == "c":
                if kind in ("function_definition", "struct_specifier", "enum_specifier"):
                    name = extract_text(node.child_by_field_name("name"))
                    if not name:
                        declarator = node.child_by_field_name("declarator")
                        if declarator:
                            name = extract_text(declarator.child_by_field_name("declarator"))

            if name:
                # Compute hash of the node's subtree for change detection
                ast_content = extract_text(node) or ""
                ast_hash = stable_hash(ast_content)

                # Ensure uniqueness by appending start/end lines if needed, but for now we rely on name/kind
                # since stable_id uses path, name, kind. Wait, if multiple methods have same name (e.g. overloads)
                # it will duplicate. Let's include start_line in stable_id to prevent IntegrityError!
                sym_id = stable_hash(
                    {"path": relative_path, "name": name, "kind": kind, "line": node.start_point[0]}
                )

                symbols.append(
                    CodeSymbol(
                        stable_id=sym_id,
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
