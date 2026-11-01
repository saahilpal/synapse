from __future__ import annotations

from collections import defaultdict
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

    def skeletonize(self, path: Path, *, text: str | None = None) -> str:
        """
        Produce a deterministic structural code skeleton by stripping implementation
        bodies while preserving imports, class structures, method signatures, return types,
        and docstrings via Tree-sitter AST pruning. Yields 80-90% token compression.
        """
        try:
            if text is None:
                text = path.read_text(encoding="utf-8", errors="replace")

            suffix = path.suffix.lower()
            from synap_git.indexer.scanner import LANGUAGE_BY_SUFFIX

            lang_name = LANGUAGE_BY_SUFFIX.get(suffix)
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

            if not lang_name:
                return text

            parser = self._get_parser(lang_name)
            if not parser:
                return text

            text_bytes = bytearray(text, "utf-8")
            tree = parser.parse(bytes(text_bytes))
            replacements: list[tuple[int, int, bytes]] = []

            def walk(n: Node) -> None:
                if lang_name == "python":
                    if n.type == "function_definition":
                        body = n.child_by_field_name("body")
                        if body and body.type == "block":
                            first_stmt = body.children[0] if body.children else None
                            has_doc = (
                                first_stmt
                                and first_stmt.type == "expression_statement"
                                and any(c.type == "string" for c in first_stmt.children)
                            )
                            indent = " " * (n.start_point[1] + 4)
                            if has_doc and first_stmt:
                                replacements.append(
                                    (first_stmt.end_byte, body.end_byte, f"\n{indent}...".encode())
                                )
                            else:
                                replacements.append((body.start_byte, body.end_byte, b"..."))
                            return
                elif lang_name in ("javascript", "typescript", "tsx"):
                    if n.type in ("function_declaration", "method_definition", "arrow_function"):
                        body = n.child_by_field_name("body")
                        if body and body.type == "statement_block":
                            replacements.append((body.start_byte, body.end_byte, b"{ /* ... */ }"))
                            return
                elif lang_name in ("go", "rust"):
                    if n.type in ("function_declaration", "method_declaration", "function_item"):
                        body = n.child_by_field_name("body")
                        if body and body.type == "block":
                            replacements.append((body.start_byte, body.end_byte, b"{ /* ... */ }"))
                            return
                elif lang_name in ("java", "c", "cpp", "c_sharp"):
                    if n.type in ("method_declaration", "function_definition"):
                        body = n.child_by_field_name("body")
                        if body:
                            replacements.append((body.start_byte, body.end_byte, b"{ /* ... */ }"))
                            return

                for child in n.children:
                    walk(child)

            walk(tree.root_node)
            replacements.sort(key=lambda r: r[0], reverse=True)
            for start, end, rep in replacements:
                if 0 <= start <= end <= len(text_bytes):
                    text_bytes[start:end] = rep

            return text_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            import structlog

            structlog.get_logger().warning("skeletonize_failed", path=str(path), error=str(e))
            return text if text is not None else ""

    def _parse_tree_sitter(
        self, text: str, lang_name: str, relative_path: str, parser: Parser
    ) -> CodeParseResult:
        text_bytes = bytes(text, "utf8")
        try:
            tree = parser.parse(text_bytes)
        except Exception as e:
            return CodeParseResult(
                path=relative_path, language=lang_name, symbols=(), syntax_error=str(e)
            )

        if not tree:
            return CodeParseResult(path=relative_path, language=lang_name, symbols=())

        symbols: list[CodeSymbol] = []
        imports: list[str] = []
        symbol_counts: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        has_traversal_error = False

        def extract_text(node: Node | None) -> str | None:
            if not node:
                return None
            try:
                return text_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
            except Exception:
                return None

        # Recursive traversal to extract symbols and imports
        def traverse(node: Node) -> None:
            kind = node.type
            name = None

            # Symbol & import extraction logic per language
            if lang_name == "python":
                if kind in ("class_definition", "function_definition"):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "import_from_statement":
                    mod_name = extract_text(node.child_by_field_name("module_name"))
                    if mod_name:
                        imported_names: list[str] = []
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
                            for n_name in imported_names:
                                imports.append(f"{mod_name}:{n_name}")
                        imports.append(mod_name)
                elif kind == "import_statement":
                    for child in node.children:
                        if child.type == "dotted_name":
                            imp_name = extract_text(child)
                            if imp_name:
                                imports.append(imp_name)
                        elif child.type == "aliased_import":
                            name_node = child.child_by_field_name("name")
                            imp_name = extract_text(name_node)
                            if imp_name:
                                imports.append(imp_name)

            elif lang_name in ("javascript", "tsx", "typescript"):
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
                    elif value_node and value_node.type == "call_expression":
                        fn_node = value_node.child_by_field_name("function")
                        fn_name = extract_text(fn_node)
                        if fn_name in ("require", "import"):
                            args = value_node.child_by_field_name("arguments")
                            if args and args.children:
                                for ac in args.children:
                                    if ac.type in ("string", "string_fragment"):
                                        s_val = extract_text(ac)
                                        if s_val:
                                            s_clean = s_val.strip("'\"`")
                                            imports.append(s_clean)
                                            name_n = node.child_by_field_name("name")
                                            if name_n:
                                                if name_n.type == "identifier":
                                                    id_txt = extract_text(name_n)
                                                    if id_txt:
                                                        imports.append(f"{s_clean}:{id_txt}")
                                                elif name_n.type == "object_pattern":
                                                    for pat in name_n.children:
                                                        if (
                                                            pat.type
                                                            == "shorthand_property_identifier_pattern"
                                                        ):
                                                            p_txt = extract_text(pat)
                                                            if p_txt:
                                                                imports.append(f"{s_clean}:{p_txt}")
                                                        elif pat.type == "pair_pattern":
                                                            key_n = pat.child_by_field_name("key")
                                                            k_txt = extract_text(key_n)
                                                            if k_txt:
                                                                imports.append(f"{s_clean}:{k_txt}")

                elif kind == "import_statement":
                    src = extract_text(node.child_by_field_name("source"))
                    if src:
                        s_clean = src.strip("'\"`")
                        imports.append(s_clean)
                        for c in node.children:
                            if c.type == "import_clause":
                                for sub in c.children:
                                    if sub.type == "identifier":
                                        id_txt = extract_text(sub)
                                        if id_txt:
                                            imports.append(f"{s_clean}:{id_txt}")
                                    elif sub.type == "named_imports":
                                        for spec in sub.children:
                                            if spec.type == "import_specifier":
                                                name_n = spec.child_by_field_name("name")
                                                n_txt = extract_text(name_n)
                                                if n_txt:
                                                    imports.append(f"{s_clean}:{n_txt}")
                                    elif sub.type == "namespace_import":
                                        name_n = sub.child_by_field_name("name")
                                        n_txt = extract_text(name_n)
                                        if n_txt:
                                            imports.append(f"{s_clean}:{n_txt}")

                elif kind == "export_statement":
                    src = extract_text(node.child_by_field_name("source"))
                    if src:
                        s_clean = src.strip("'\"`")
                        imports.append(s_clean)
                        for c in node.children:
                            if c.type == "export_clause":
                                for spec in c.children:
                                    if spec.type == "export_specifier":
                                        name_n = spec.child_by_field_name("name")
                                        n_txt = extract_text(name_n)
                                        if n_txt:
                                            imports.append(f"{s_clean}:{n_txt}")

                elif kind == "call_expression":
                    fn_node = node.child_by_field_name("function")
                    fn_name = extract_text(fn_node)
                    if fn_name in ("require", "import"):
                        args = node.child_by_field_name("arguments")
                        if args and args.children:
                            for ac in args.children:
                                if ac.type in ("string", "string_fragment"):
                                    s_val = extract_text(ac)
                                    if s_val:
                                        imports.append(s_val.strip("'\"`"))

            elif lang_name == "go":
                if kind in ("function_declaration", "method_declaration", "type_spec"):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "import_spec":
                    path_val = extract_text(node.child_by_field_name("path"))
                    if path_val:
                        clean_path = path_val.strip('"')
                        imports.append(clean_path)
                        name_node = node.child_by_field_name("name")
                        if name_node:
                            alias = extract_text(name_node)
                            if alias:
                                imports.append(f"{clean_path}:{alias}")

            elif lang_name == "rust":
                if kind in ("function_item", "struct_item", "enum_item", "trait_item", "impl_item"):
                    name = extract_text(node.child_by_field_name("name"))
                    if not name and kind == "impl_item":
                        t_name = extract_text(node.child_by_field_name("type"))
                        if t_name:
                            name = "impl " + t_name
                elif kind == "use_declaration":
                    txt = extract_text(node)
                    if txt:
                        clean = txt.strip().removeprefix("use").removesuffix(";").strip()
                        if clean:
                            imports.append(clean)
                    for c in node.children:
                        if c.type == "scoped_identifier":
                            full_path = extract_text(c)
                            if full_path and "::" in full_path:
                                mod_p, sym_p = full_path.rsplit("::", 1)
                                imports.append(f"{mod_p}:{sym_p}")
                                imports.append(mod_p)
                        elif c.type == "scoped_use_list":
                            path_node = c.child_by_field_name("path") or (
                                c.children[0] if c.children else None
                            )
                            mod_prefix = extract_text(path_node)
                            list_node = c.child_by_field_name("list") or (
                                c.children[-1] if c.children else None
                            )
                            if mod_prefix and list_node:
                                imports.append(mod_prefix)
                                for item in list_node.children:
                                    if item.type == "identifier":
                                        i_txt = extract_text(item)
                                        if i_txt:
                                            imports.append(f"{mod_prefix}:{i_txt}")
                                    elif item.type == "use_as_clause":
                                        orig = (
                                            extract_text(item.children[0])
                                            if item.children
                                            else None
                                        )
                                        if orig:
                                            imports.append(f"{mod_p}:{orig}")
                elif kind == "mod_item":
                    name_n = node.child_by_field_name("name")
                    body_n = node.child_by_field_name("body")
                    if name_n and not body_n:
                        mod_name = extract_text(name_n)
                        if mod_name:
                            imports.append(mod_name)

            elif lang_name == "java":
                if kind in (
                    "class_declaration",
                    "method_declaration",
                    "interface_declaration",
                    "enum_declaration",
                ):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "import_declaration":
                    txt = extract_text(node)
                    if txt:
                        clean = (
                            txt.strip()
                            .removeprefix("import")
                            .strip()
                            .removeprefix("static")
                            .strip()
                            .removesuffix(";")
                            .strip()
                        )
                        if clean:
                            imports.append(clean)
                            if "." in clean:
                                pkg_part, sym_part = clean.rsplit(".", 1)
                                if sym_part != "*":
                                    imports.append(f"{pkg_part}:{sym_part}")
                                imports.append(pkg_part)

            elif lang_name == "cpp":
                if kind in (
                    "function_definition",
                    "class_specifier",
                    "struct_specifier",
                    "enum_specifier",
                ):
                    name = extract_text(node.child_by_field_name("name"))
                    if not name:
                        declarator = node.child_by_field_name("declarator")
                        if declarator:
                            d_name = declarator.child_by_field_name("declarator")
                            name = extract_text(d_name) if d_name else extract_text(declarator)
                elif kind in ("declaration", "field_declaration"):
                    decl = node.child_by_field_name("declarator")
                    if decl:
                        if decl.type == "function_declarator":
                            ident = decl.child_by_field_name("declarator") or (
                                decl.children[0] if decl.children else None
                            )
                            name = extract_text(ident)
                            if name:
                                kind = "function"
                elif kind == "preproc_include":
                    for child in node.children:
                        if child.type in ("system_lib_string", "string_literal"):
                            inc_text = extract_text(child)
                            if inc_text:
                                imports.append(inc_text.strip("<\">'"))

            elif lang_name == "c":
                if kind in ("function_definition", "struct_specifier", "enum_specifier"):
                    name = extract_text(node.child_by_field_name("name"))
                    if not name:
                        declarator = node.child_by_field_name("declarator")
                        if declarator:
                            d_name = declarator.child_by_field_name("declarator")
                            name = extract_text(d_name) if d_name else extract_text(declarator)
                elif kind == "declaration":
                    decl = node.child_by_field_name("declarator")
                    if decl and decl.type == "function_declarator":
                        ident = decl.child_by_field_name("declarator") or (
                            decl.children[0] if decl.children else None
                        )
                        name = extract_text(ident)
                        if name:
                            kind = "function"
                elif kind == "preproc_include":
                    for child in node.children:
                        if child.type in ("system_lib_string", "string_literal"):
                            inc_text = extract_text(child)
                            if inc_text:
                                imports.append(inc_text.strip("<\">'"))

            elif lang_name == "ruby":
                if kind in ("class", "module", "method"):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "call":
                    fn = extract_text(node.child_by_field_name("name")) or extract_text(
                        node.child_by_field_name("method")
                    )
                    if not fn and node.children:
                        fn = extract_text(node.children[0])
                    if fn in ("require", "require_relative"):
                        args = node.child_by_field_name("arguments") or (
                            node.children[1] if len(node.children) > 1 else None
                        )
                        if args:
                            arg_text = extract_text(args)
                            if arg_text:
                                imports.append(arg_text.strip("() \"'"))

            elif lang_name == "c_sharp":
                if kind in (
                    "class_declaration",
                    "method_declaration",
                    "interface_declaration",
                    "struct_declaration",
                    "enum_declaration",
                ):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "using_directive":
                    txt = extract_text(node)
                    if txt:
                        clean = (
                            txt.strip()
                            .removeprefix("using")
                            .strip()
                            .removeprefix("static")
                            .strip()
                            .removesuffix(";")
                            .strip()
                        )
                        if clean:
                            imports.append(clean)

            elif lang_name == "php":
                if kind in (
                    "class_declaration",
                    "function_definition",
                    "method_declaration",
                    "interface_declaration",
                    "trait_declaration",
                ):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind in ("namespace_use_declaration", "use_declaration"):
                    has_clause = False
                    for clause in node.children:
                        if clause.type == "namespace_use_clause":
                            has_clause = True
                            u_text = extract_text(clause)
                            if u_text:
                                imports.append(u_text.strip("\\;"))
                    if not has_clause:
                        txt = extract_text(node)
                        if txt:
                            clean = (
                                txt.strip()
                                .removeprefix("use")
                                .strip()
                                .removeprefix("function")
                                .strip()
                                .removesuffix(";")
                                .strip()
                            )
                            if clean:
                                imports.append(clean.strip("\\"))

            elif lang_name == "kotlin":
                if kind in (
                    "class_declaration",
                    "function_declaration",
                    "object_declaration",
                    "interface_declaration",
                ):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "import_header":
                    txt = extract_text(node)
                    if txt:
                        clean = txt.strip().removeprefix("import").strip()
                        if clean:
                            imports.append(clean)

            elif lang_name == "scala":
                if kind in (
                    "class_definition",
                    "object_definition",
                    "function_definition",
                    "trait_definition",
                ):
                    name = extract_text(node.child_by_field_name("name"))
                elif kind == "import_declaration":
                    txt = extract_text(node)
                    if txt:
                        clean = txt.strip().removeprefix("import").strip()
                        if clean:
                            imports.append(clean)

            if name:
                # Compute hash of the node's subtree for change detection
                ast_content = extract_text(node) or ""
                ast_hash = stable_hash(ast_content)

                # Deterministic disambiguation across same name+kind without coupling to volatile line numbers
                sym_key = (relative_path, name, kind)
                symbol_counts[sym_key] += 1
                sym_id = stable_hash(
                    {
                        "path": relative_path,
                        "name": name,
                        "kind": kind,
                        "index": symbol_counts[sym_key],
                    }
                )

                # Extract identifier references within this symbol
                refs: set[str] = set()

                def collect_refs(n: Node) -> None:
                    if n.type in (
                        "identifier",
                        "type_identifier",
                        "scoped_identifier",
                        "property_identifier",
                        "field_identifier",
                    ):
                        txt = extract_text(n)
                        if txt and txt != name:
                            refs.add(txt)
                    for c in n.children:
                        collect_refs(c)

                collect_refs(node)

                symbols.append(
                    CodeSymbol(
                        stable_id=sym_id,
                        kind=kind,
                        name=name,
                        source_path=relative_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        ast_hash=ast_hash,
                        metadata={"refs": sorted(refs)},
                    )
                )

            for child in node.children:
                traverse(child)

        try:
            traverse(tree.root_node)
        except Exception:
            has_traversal_error = True

        has_err = bool(tree.root_node.has_error or has_traversal_error)
        return CodeParseResult(
            path=relative_path,
            language=lang_name,
            symbols=tuple(symbols),
            imports=tuple(sorted(set(imports))),
            syntax_error="syntax_error_detected" if has_err else None,
        )
