from __future__ import annotations

from pathlib import Path
from typing import Any

from synapse.context.markdown import MarkdownContextExtractor
from synapse.context.objects import (
    Confidence,
    EvidenceSpan,
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelation,
    Provenance,
    SemanticKind,
    SemanticObject,
    SourceType,
    Validity,
)
from synapse.context.parsers import CodeParserRegistry
from synapse.context.scanner import FileObservation, RepositoryScan
from synapse.git.state import GitState


class RepositoryContextBuilder:
    """Builds bounded semantic objects from repository structure and Markdown."""

    def __init__(self) -> None:
        self.markdown = MarkdownContextExtractor()
        self.parsers = CodeParserRegistry()

    def build_from_scan(
        self,
        *,
        scan: RepositoryScan,
        git_state: GitState,
    ) -> tuple[tuple[SemanticObject, ...], tuple[GraphNode, ...], tuple[GraphEdge, ...]]:
        from synapse.serialization import stable_hash

        objects: list[SemanticObject] = []
        objects.append(self._repository_summary(scan, git_state))
        objects.extend(self._manifest_objects(scan, git_state))
        objects.extend(self._code_structure_objects(scan, git_state))

        md_objects = self.markdown.extract_scan(scan)
        objects.extend(md_objects)

        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}
        parsed_files = {
            file.relative_path: self.parsers.parse(
                Path(file.path), relative_path=file.relative_path
            )
            for file in scan.files
            if file.language in {"python", "typescript", "javascript"}
        }

        def default_provenance(
            path: str, src_type: SourceType, content_hash: str | None = None
        ) -> Provenance:
            return Provenance(
                source_uri=path,
                source_type=src_type,
                source_hash=content_hash,
                git_commit=git_state.head_commit,
                branch=git_state.effective_branch,
            )

        def default_confidence(score: float, rationale: str) -> Confidence:
            return Confidence(score=score, rationale=rationale, evidence_count=1)

        folders = {
            parent.as_posix()
            for file in scan.files
            for parent in Path(file.relative_path).parents
            if parent.as_posix() not in {".", ""}
        }
        for folder in sorted(folders):
            folder_id = stable_hash({"kind": "node_package", "path": folder})
            nodes[folder_id] = GraphNode(
                stable_id=folder_id,
                node_type=GraphNodeType.PACKAGE,
                labels=(folder,),
                provenance=default_provenance(folder, SourceType.SYSTEM),
                confidence=default_confidence(0.9, "repository folder boundary"),
                metadata={"source_uri": folder},
            )

        file_id_map: dict[str, str] = {}
        for file in scan.files:
            file_path = file.relative_path
            is_markdown = file.language == "markdown"
            node_type = GraphNodeType.DOCUMENT if is_markdown else GraphNodeType.MODULE
            kind_str = "node_document" if is_markdown else "node_module"
            src_type = SourceType.MARKDOWN if is_markdown else SourceType.CODE

            node_id = stable_hash({"kind": kind_str, "path": file_path})
            file_id_map[file_path] = node_id
            nodes[node_id] = GraphNode(
                stable_id=node_id,
                node_type=node_type,
                labels=(file.path.name, file_path),
                provenance=default_provenance(file_path, src_type, file.content_hash),
                confidence=default_confidence(0.85, f"repository file scan: {file_path}"),
                metadata={"language": file.language, "size_bytes": file.size_bytes},
            )

            parent_dir = Path(file_path).parent.as_posix()
            if parent_dir not in {".", ""}:
                parent_id = stable_hash({"kind": "node_package", "path": parent_dir})
                self._add_edge(
                    edges,
                    from_id=parent_id,
                    to_id=node_id,
                    relation=GraphRelation.OWNS,
                    provenance=default_provenance(file_path, SourceType.SYSTEM),
                    confidence=default_confidence(0.95, "folder contains file"),
                )

        for file in scan.files:
            parse = parsed_files.get(file.relative_path)
            file_node_id = file_id_map.get(file.relative_path)
            if parse is None or file_node_id is None:
                continue
            for symbol in parse.symbols[:200]:
                node_type = (
                    GraphNodeType.CLASS if symbol.kind == "class" else GraphNodeType.FUNCTION
                )
                nodes[symbol.stable_id] = GraphNode(
                    stable_id=symbol.stable_id,
                    node_type=node_type,
                    labels=(symbol.name, f"{file.relative_path}:{symbol.line or 1}"),
                    provenance=default_provenance(
                        file.relative_path, SourceType.CODE, file.content_hash
                    ),
                    confidence=default_confidence(0.82, "code parser symbol extraction"),
                    metadata={
                        "name": symbol.name,
                        "symbol_kind": symbol.kind,
                        "source_path": file.relative_path,
                        "line": symbol.line,
                    },
                )
                self._add_edge(
                    edges,
                    from_id=file_node_id,
                    to_id=symbol.stable_id,
                    relation=GraphRelation.OWNS,
                    provenance=default_provenance(
                        file.relative_path, SourceType.CODE, file.content_hash
                    ),
                    confidence=default_confidence(0.9, "file owns parsed symbol"),
                )

        module_index = self._module_index(file_id_map)
        for file in scan.files:
            parse = parsed_files.get(file.relative_path)
            file_node_id = file_id_map.get(file.relative_path)
            if parse is None or file_node_id is None:
                continue
            for imported in parse.imports[:100]:
                target_node_id = self._resolve_import_target(
                    imported,
                    source_path=file.relative_path,
                    module_index=module_index,
                )
                if target_node_id and target_node_id != file_node_id:
                    self._add_edge(
                        edges,
                        from_id=file_node_id,
                        to_id=target_node_id,
                        relation=GraphRelation.DEPENDS_ON,
                        provenance=default_provenance(
                            file.relative_path, SourceType.CODE, file.content_hash
                        ),
                        confidence=default_confidence(0.75, f"code import dependency: {imported}"),
                    )

        return tuple(objects), tuple(nodes.values()), tuple(edges.values())

    def _add_edge(
        self,
        edges: dict[str, GraphEdge],
        *,
        from_id: str,
        to_id: str,
        relation: GraphRelation,
        provenance: Provenance,
        confidence: Confidence,
    ) -> None:
        edge_id = GraphEdge.derive_id(from_id=from_id, to_id=to_id, relation=relation)
        edges[edge_id] = GraphEdge(
            stable_id=edge_id,
            from_id=from_id,
            to_id=to_id,
            relation=relation,
            provenance=provenance,
            confidence=confidence,
        )

    def _module_index(self, file_id_map: dict[str, str]) -> dict[str, str]:
        index: dict[str, str] = {}
        for relative_path, node_id in file_id_map.items():
            path = Path(relative_path)
            if path.suffix.lower() not in {".py", ".js", ".jsx", ".ts", ".tsx"}:
                continue
            parts = path.with_suffix("").parts
            dotted = ".".join(parts)
            index.setdefault(dotted, node_id)
            index.setdefault(path.stem, node_id)
            index.setdefault(path.with_suffix("").as_posix(), node_id)
        return index

    def _resolve_import_target(
        self,
        imported: str,
        *,
        source_path: str,
        module_index: dict[str, str],
    ) -> str | None:
        cleaned = imported.strip().strip("\"'")
        if not cleaned:
            return None
        if cleaned.startswith("."):
            source_dir = Path(source_path).parent
            candidate = (source_dir / cleaned).as_posix().replace("/./", "/")
            return module_index.get(candidate) or module_index.get(candidate.lstrip("./"))
        normalized = cleaned.replace("/", ".").removesuffix(".py")
        return module_index.get(normalized) or module_index.get(normalized.split(".", 1)[0])

    def manual_note(
        self,
        *,
        message: str,
        branch: str | None,
        git_commit_hash: str | None,
        actor: str = "human",
    ) -> SemanticObject:
        source_uri = "manual://note"
        provenance = Provenance(
            source_uri=source_uri,
            source_type=SourceType.MANUAL_NOTE,
            git_commit=git_commit_hash,
            branch=branch,
            actor=actor,
        )
        return SemanticObject(
            stable_id=SemanticObject.derive_id(
                kind=SemanticKind.NOTE,
                source_uri=source_uri,
                source_hash=None,
                content=message,
            ),
            kind=SemanticKind.NOTE,
            summary=message.strip(),
            tags=("manual", "note"),
            metadata={"actor": actor},
            provenance=provenance,
            confidence=Confidence(score=0.9, rationale="explicit manual note", evidence_count=1),
        )

    def _repository_summary(self, scan: RepositoryScan, git_state: GitState) -> SemanticObject:
        summary = (
            f"Repository has {len(scan.files)} indexed files, "
            f"languages={scan.language_counts}, folders={scan.folder_counts}, "
            f"manifests={[manifest.path for manifest in scan.manifests]}"
        )
        provenance = Provenance(
            source_uri=scan.repository_path.as_posix(),
            source_type=SourceType.SYSTEM,
            git_commit=git_state.head_commit,
            branch=git_state.branch,
            evidence=(),
        )
        return SemanticObject(
            stable_id=SemanticObject.derive_id(
                kind=SemanticKind.ARCHITECTURE,
                source_uri=scan.repository_path.as_posix(),
                source_hash=None,
                content=summary,
            ),
            kind=SemanticKind.ARCHITECTURE,
            summary=summary,
            tags=("repository", "topology"),
            metadata={
                "language_counts": scan.language_counts,
                "folder_counts": scan.folder_counts,
                "file_count": len(scan.files),
            },
            provenance=provenance,
            confidence=Confidence(
                score=0.82,
                rationale="repository structural scan",
                evidence_count=1,
            ),
        )

    def _manifest_objects(
        self,
        scan: RepositoryScan,
        git_state: GitState,
    ) -> tuple[SemanticObject, ...]:
        objects: list[SemanticObject] = []
        by_path = {file.relative_path: file for file in scan.files}
        for manifest in scan.manifests:
            file = by_path.get(manifest.path)
            source_hash = file.content_hash if file else None
            summary = (
                f"{manifest.kind} manifest {manifest.path} declares "
                f"{len(manifest.dependencies)} dependencies"
            )
            if manifest.dependencies:
                summary = f"{summary}: {', '.join(manifest.dependencies[:40])}"
            provenance = Provenance(
                source_uri=manifest.path,
                source_type=SourceType.CODE,
                source_hash=source_hash,
                git_commit=git_state.head_commit,
                branch=git_state.branch,
                evidence=(EvidenceSpan(source_uri=manifest.path, source_hash=source_hash),),
            )
            objects.append(
                SemanticObject(
                    stable_id=SemanticObject.derive_id(
                        kind=SemanticKind.DEPENDENCY,
                        source_uri=manifest.path,
                        source_hash=source_hash,
                        content=summary,
                    ),
                    kind=SemanticKind.DEPENDENCY,
                    summary=summary,
                    tags=("dependency", manifest.kind),
                    metadata={
                        "dependencies": manifest.dependencies,
                        "manifest_kind": manifest.kind,
                    },
                    provenance=provenance,
                    confidence=Confidence(
                        score=0.86,
                        rationale="manifest dependency scan",
                        evidence_count=1,
                    ),
                )
            )
        return tuple(objects)

    def _code_structure_objects(
        self,
        scan: RepositoryScan,
        git_state: GitState,
    ) -> tuple[SemanticObject, ...]:
        objects: list[SemanticObject] = []
        for file in scan.files:
            if file.language not in {"python", "typescript", "javascript"}:
                continue
            objects.append(self._code_object(file, git_state))
        return tuple(objects)

    def _code_object(self, file: FileObservation, git_state: GitState) -> SemanticObject:
        parse = self.parsers.parse(Path(file.path), relative_path=file.relative_path)
        symbol_names = tuple(symbol.name for symbol in parse.symbols[:50])
        symbol_payload = tuple(symbol.__dict__ for symbol in parse.symbols[:200])
        summary = (
            f"{parse.language} module {file.relative_path} imports={list(parse.imports[:30])} "
            f"symbols={list(symbol_names)}"
        )
        if parse.syntax_error:
            summary = f"{summary} syntax_error={parse.syntax_error}"
        provenance = Provenance(
            source_uri=file.relative_path,
            source_type=SourceType.CODE,
            source_hash=file.content_hash,
            git_commit=git_state.head_commit,
            branch=git_state.branch,
            evidence=(EvidenceSpan(source_uri=file.relative_path, source_hash=file.content_hash),),
        )
        return SemanticObject(
            stable_id=SemanticObject.derive_id(
                kind=SemanticKind.MODULE,
                source_uri=file.relative_path,
                source_hash=file.content_hash,
                content=summary,
            ),
            kind=SemanticKind.MODULE,
            summary=summary,
            tags=("code", parse.language, "module"),
            metadata={
                "imports": parse.imports,
                "symbols": symbol_payload,
                "syntax_error": parse.syntax_error,
            },
            provenance=provenance,
            confidence=Confidence(
                score=0.76,
                rationale="safe structural code parse",
                evidence_count=1,
            ),
        )

    def build_incremental_scan(
        self,
        *,
        scan: RepositoryScan,
        git_state: GitState,
        active_nodes: dict[str, dict[str, Any]],
        active_semantics: dict[str, dict[str, Any]],
        active_edges: dict[str, dict[str, Any]],
    ) -> tuple[tuple[SemanticObject, ...], tuple[GraphNode, ...], tuple[GraphEdge, ...]]:
        import json

        from synapse.serialization import stable_hash

        # Map active file paths (source_uri) to their active semantic objects representing modules/documents
        # and their content hashes (source_hash)
        old_file_hashes = {}
        old_file_semantics = {}
        for stable_id, sem in active_semantics.items():
            if sem.get("kind") in (
                SemanticKind.MODULE.value,
                SemanticKind.DEPENDENCY.value,
            ) or sem.get("source_hash"):
                uri = sem.get("source_uri")
                if uri:
                    old_file_hashes[uri] = sem.get("source_hash")
                    old_file_semantics[uri] = sem

        # Compute new scan files
        new_files = {f.relative_path: f for f in scan.files}

        # 1. Change detection
        added_paths = set(new_files.keys()) - set(old_file_hashes.keys())
        deleted_paths = set(old_file_hashes.keys()) - set(new_files.keys())
        modified_paths = set()
        for path in set(new_files.keys()) & set(old_file_hashes.keys()):
            if new_files[path].content_hash != old_file_hashes[path]:
                modified_paths.add(path)

        # Detect moves/renames
        # If a path in deleted_paths has same hash as a path in added_paths:
        renamed_from_to = {}
        for dp in list(deleted_paths):
            old_hash = old_file_hashes[dp]
            for ap in list(added_paths):
                if new_files[ap].content_hash == old_hash:
                    renamed_from_to[dp] = ap
                    deleted_paths.remove(dp)
                    added_paths.remove(ap)
                    break

        # Accumulate changes
        to_invalidate_node_ids = set()
        to_invalidate_edge_ids = set()
        to_invalidate_semantic_ids = set()

        # Files to parse fully (newly added, modified, renamed destination)
        files_to_parse = list(added_paths) + list(modified_paths) + list(renamed_from_to.values())
        # Files to invalidate (deleted, modified, renamed source)
        files_to_invalidate = (
            list(deleted_paths) + list(modified_paths) + list(renamed_from_to.keys())
        )

        # For files to invalidate, collect their nodes, symbols, edges, and semantic objects
        for path in files_to_invalidate:
            # Invalidate file node.
            doc_node_id = stable_hash({"kind": "node_document", "path": path})
            mod_node_id = stable_hash({"kind": "node_module", "path": path})
            if doc_node_id in active_nodes:
                to_invalidate_node_ids.add(doc_node_id)
            if mod_node_id in active_nodes:
                to_invalidate_node_ids.add(mod_node_id)

            # Invalidate symbols inside the file from the previous module summary.
            old_sem = old_file_semantics.get(path)
            if old_sem:
                to_invalidate_semantic_ids.add(str(old_sem["stable_id"]))
                metadata = old_sem.get("metadata_json")
                if metadata:
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except Exception:
                            metadata = {}
                    symbols = metadata.get("symbols", [])
                    for sym in symbols:
                        sym_id = sym.get("stable_id")
                        if sym_id and sym_id in active_nodes:
                            to_invalidate_node_ids.add(sym_id)

            # Also find all active semantic objects whose source_uri is path
            for sem_id, sem_data in active_semantics.items():
                if sem_data.get("source_uri") == path:
                    to_invalidate_semantic_ids.add(sem_id)

            # Find any overlays targeting these nodes
            target_ids = to_invalidate_node_ids | to_invalidate_semantic_ids
            for sem_id, sem_data in active_semantics.items():
                meta_str = sem_data.get("metadata_json")
                if meta_str:
                    try:
                        meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
                    except Exception:
                        meta = {}
                    if meta.get("target_stable_id") in target_ids:
                        to_invalidate_semantic_ids.add(sem_id)

        # Invalidate edges connected to any invalidated node
        for edge_id, edge in active_edges.items():
            if edge["from_id"] in to_invalidate_node_ids or edge["to_id"] in to_invalidate_node_ids:
                to_invalidate_edge_ids.add(edge_id)

        # 3. Parse newly added or modified files, adding their fresh elements to the delta
        incremental_scan = RepositoryScan(
            repository_path=scan.repository_path,
            files=tuple(new_files[p] for p in files_to_parse if p in new_files),
            manifests=tuple(m for m in scan.manifests if m.path in files_to_parse),
        )

        fresh_sems, fresh_nodes, fresh_edges = self.build_from_scan(
            scan=incremental_scan,
            git_state=git_state,
        )

        # Filter out fresh elements from invalidations to avoid primary key conflicts
        fresh_node_ids = {node.stable_id for node in fresh_nodes}
        fresh_sem_ids = {sem.stable_id for sem in fresh_sems}
        fresh_edge_ids = {edge.stable_id for edge in fresh_edges}

        to_invalidate_node_ids -= fresh_node_ids
        to_invalidate_semantic_ids -= fresh_sem_ids
        to_invalidate_edge_ids -= fresh_edge_ids

        # Now, create the actual output lists
        out_semantics = []
        out_nodes = []
        out_edges = []

        # 2. Add invalidations to delta (setting valid_to_context = "__CURRENT_CONTEXT__")
        for nid in to_invalidate_node_ids:
            ndata = active_nodes[nid]
            out_nodes.append(
                GraphNode(
                    stable_id=nid,
                    node_type=GraphNodeType(ndata["node_type"]),
                    labels=tuple(json.loads(ndata["labels_json"])),
                    metadata=json.loads(ndata["metadata_json"]),
                    confidence=Confidence(
                        score=0.0, rationale="invalidated during scan", evidence_count=0
                    ),
                    provenance=Provenance(
                        source_uri=ndata["source_uri"],
                        source_type=SourceType.SYSTEM,
                    ),
                    validity=Validity(
                        valid_from_context=ndata["valid_from_context"],
                        valid_to_context="__CURRENT_CONTEXT__",
                    ),
                )
            )

        for eid in to_invalidate_edge_ids:
            edata = active_edges[eid]
            out_edges.append(
                GraphEdge(
                    stable_id=eid,
                    from_id=edata["from_id"],
                    to_id=edata["to_id"],
                    relation=GraphRelation(edata["relation"]),
                    metadata=json.loads(edata["metadata_json"]),
                    confidence=Confidence(
                        score=0.0, rationale="invalidated during scan", evidence_count=0
                    ),
                    provenance=Provenance(
                        source_uri=edata["source_uri"],
                        source_type=SourceType.SYSTEM,
                    ),
                    validity=Validity(
                        valid_from_context=edata["valid_from_context"],
                        valid_to_context="__CURRENT_CONTEXT__",
                    ),
                )
            )

        for sid in to_invalidate_semantic_ids:
            sdata = active_semantics[sid]
            out_semantics.append(
                SemanticObject(
                    stable_id=sid,
                    kind=SemanticKind(sdata["kind"]),
                    summary=sdata["summary"],
                    tags=tuple(json.loads(sdata["tags_json"])),
                    metadata=json.loads(sdata["metadata_json"]),
                    confidence=Confidence(
                        score=0.0, rationale="invalidated during scan", evidence_count=0
                    ),
                    provenance=Provenance(
                        source_uri=sdata["source_uri"],
                        source_type=SourceType.SYSTEM,
                    ),
                    validity=Validity(
                        valid_from_context=sdata["valid_from_context"],
                        valid_to_context="__CURRENT_CONTEXT__",
                    ),
                )
            )

        # Set valid_from_context = "__CURRENT_CONTEXT__" for the fresh objects
        for f_sem in fresh_sems:
            # Skip repository summary object to prevent duplicate global summaries
            if f_sem.kind == SemanticKind.ARCHITECTURE and f_sem.tags == ("repository", "topology"):
                continue
            out_semantics.append(
                f_sem.model_copy(
                    update={"validity": Validity(valid_from_context="__CURRENT_CONTEXT__")}
                )
            )
        for f_node in fresh_nodes:
            out_nodes.append(
                f_node.model_copy(
                    update={"validity": Validity(valid_from_context="__CURRENT_CONTEXT__")}
                )
            )
        for f_edge in fresh_edges:
            out_edges.append(
                f_edge.model_copy(
                    update={"validity": Validity(valid_from_context="__CURRENT_CONTEXT__")}
                )
            )

        return tuple(out_semantics), tuple(out_nodes), tuple(out_edges)
