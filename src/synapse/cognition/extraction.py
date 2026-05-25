from __future__ import annotations

from pathlib import Path

from synapse.cognition.markdown import MarkdownCognitionExtractor
from synapse.cognition.objects import (
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
)
from synapse.cognition.parsers import CodeParserRegistry
from synapse.cognition.scanner import FileObservation, RepositoryScan
from synapse.git.state import GitState


class RepositoryCognitionBuilder:
    """Builds bounded semantic objects from repository structure and Markdown."""

    def __init__(self) -> None:
        self.markdown = MarkdownCognitionExtractor()
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
        edges: list[GraphEdge] = []

        # Helper to create default confidence/provenance
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

        # 1. Add Package / Directory Nodes
        folders = set()
        for file in scan.files:
            p = Path(file.relative_path)
            for parent in p.parents:
                if parent.as_posix() not in {".", ""}:
                    folders.add(parent.as_posix())

        for folder in folders:
            folder_id = stable_hash({"kind": "node_package", "path": folder})
            nodes[folder_id] = GraphNode(
                stable_id=folder_id,
                node_type=GraphNodeType.PACKAGE,
                labels=(folder,),
                provenance=default_provenance(folder, SourceType.SYSTEM),
                confidence=default_confidence(0.9, "repository folder structure"),
            )

        # 2. Add Code File Nodes and Markdown Document Nodes
        file_id_map: dict[str, str] = {}  # relative_path -> node stable_id
        for file in scan.files:
            file_path = file.relative_path
            is_md = file_path.endswith(".md")

            node_type = GraphNodeType.DOCUMENT if is_md else GraphNodeType.MODULE
            kind_str = "node_document" if is_md else "node_module"
            src_type = SourceType.MARKDOWN if is_md else SourceType.CODE

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

            # Owner edge from parent folder to file
            parent_dir = Path(file_path).parent.as_posix()
            if parent_dir not in {".", ""}:
                parent_id = stable_hash({"kind": "node_package", "path": parent_dir})
                if parent_id in nodes:
                    edge_id = GraphEdge.derive_id(
                        from_id=parent_id,
                        to_id=node_id,
                        relation=GraphRelation.OWNS,
                    )
                    edges.append(
                        GraphEdge(
                            stable_id=edge_id,
                            from_id=parent_id,
                            to_id=node_id,
                            relation=GraphRelation.OWNS,
                            provenance=default_provenance(file_path, SourceType.SYSTEM),
                            confidence=default_confidence(0.95, "folder hierarchy containment"),
                        )
                    )

        # 3. Add Dependency Nodes (from Manifests)
        for manifest in scan.manifests:
            manifest_id = stable_hash({"kind": "node_dependency", "path": manifest.path})
            nodes[manifest_id] = GraphNode(
                stable_id=manifest_id,
                node_type=GraphNodeType.DEPENDENCY,
                labels=(f"manifest:{manifest.kind}", manifest.path),
                provenance=default_provenance(manifest.path, SourceType.CODE),
                confidence=default_confidence(0.88, f"manifest file scan: {manifest.path}"),
                metadata={"manifest_kind": manifest.kind, "dependencies": manifest.dependencies},
            )

        # 4. Map Markdown Decisions and Assumptions
        for sem in md_objects:
            node_type = GraphNodeType.DOCUMENT
            if sem.kind == SemanticKind.DECISION:
                node_type = GraphNodeType.DECISION
            elif sem.kind == SemanticKind.ASSUMPTION:
                node_type = GraphNodeType.ASSUMPTION
            elif sem.kind == SemanticKind.RISK:
                node_type = GraphNodeType.RISK
            elif sem.kind == SemanticKind.INCIDENT:
                node_type = GraphNodeType.INCIDENT
            else:
                continue

            title = sem.metadata.get("title") or sem.summary[:50]
            nodes[sem.stable_id] = GraphNode(
                stable_id=sem.stable_id,
                node_type=node_type,
                labels=(title,),
                provenance=sem.provenance,
                confidence=sem.confidence,
                metadata=sem.metadata,
            )

            # Link document node to decision/assumption node
            doc_path = sem.provenance.source_uri
            doc_node_id = file_id_map.get(doc_path)
            if doc_node_id:
                edge_id = GraphEdge.derive_id(
                    from_id=doc_node_id,
                    to_id=sem.stable_id,
                    relation=GraphRelation.DOCUMENTS,
                )
                edges.append(
                    GraphEdge(
                        stable_id=edge_id,
                        from_id=doc_node_id,
                        to_id=sem.stable_id,
                        relation=GraphRelation.DOCUMENTS,
                        provenance=sem.provenance,
                        confidence=sem.confidence,
                    )
                )

        # 5. Build code imports links (Depends On)
        for file in scan.files:
            if file.language not in {"python", "typescript", "javascript"}:
                continue
            parse = self.parsers.parse(Path(file.path), relative_path=file.relative_path)
            file_node_id = file_id_map.get(file.relative_path)
            if not file_node_id:
                continue

            for imp in parse.imports:
                # Find matching target file inside workspace
                for other_file in scan.files:
                    other_path_clean = other_file.relative_path.replace("\\", "/").lower()
                    imp_clean = imp.lower()
                    if (
                        imp_clean in other_path_clean
                        and other_file.relative_path != file.relative_path
                    ):
                        other_node_id = file_id_map.get(other_file.relative_path)
                        if other_node_id:
                            edge_id = GraphEdge.derive_id(
                                from_id=file_node_id,
                                to_id=other_node_id,
                                relation=GraphRelation.DEPENDS_ON,
                            )
                            edges.append(
                                GraphEdge(
                                    stable_id=edge_id,
                                    from_id=file_node_id,
                                    to_id=other_node_id,
                                    relation=GraphRelation.DEPENDS_ON,
                                    provenance=default_provenance(
                                        file.relative_path, SourceType.CODE, file.content_hash
                                    ),
                                    confidence=default_confidence(
                                        0.75, f"code import dependency: {imp}"
                                    ),
                                )
                            )
                            break

        # 6. Build Markdown reference links
        for sem in md_objects:
            links = sem.metadata.get("links", ())
            for link in links:
                # Check if it links to a file in the workspace
                target_node_id = None
                for file_path, node_id in file_id_map.items():
                    if link in file_path or file_path in link:
                        target_node_id = node_id
                        break

                # Check if it links to another decision/assumption by heading/ID
                if not target_node_id:
                    for other_sem in md_objects:
                        title_clean = str(other_sem.metadata.get("title", "")).lower()
                        if link.lower() in title_clean or title_clean in link.lower():
                            target_node_id = other_sem.stable_id
                            break

                if target_node_id and target_node_id != sem.stable_id:
                    edge_id = GraphEdge.derive_id(
                        from_id=sem.stable_id,
                        to_id=target_node_id,
                        relation=GraphRelation.REFERENCES,
                    )
                    edges.append(
                        GraphEdge(
                            stable_id=edge_id,
                            from_id=sem.stable_id,
                            to_id=target_node_id,
                            relation=GraphRelation.REFERENCES,
                            provenance=sem.provenance,
                            confidence=sem.confidence,
                        )
                    )

        return tuple(objects), tuple(nodes.values()), tuple(edges)

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
                "symbols": tuple(symbol.__dict__ for symbol in parse.symbols),
                "syntax_error": parse.syntax_error,
            },
            provenance=provenance,
            confidence=Confidence(
                score=0.76,
                rationale="safe structural code parse",
                evidence_count=1,
            ),
        )
