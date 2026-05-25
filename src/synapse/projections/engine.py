from __future__ import annotations

import json
from typing import Any

from synapse.context.dag import ContextDag
from synapse.projections.models import (
    ProjectionEdge,
    ProjectionGraph,
    ProjectionKind,
    ProjectionNode,
)
from synapse.serialization import stable_hash
from synapse.storage.sqlite import SQLiteEventStore


class ProjectionEngine:
    """Builds bounded structural views for the local UI."""

    def __init__(
        self,
        *,
        event_store: SQLiteEventStore,
        dag: ContextDag,
        max_nodes: int = 150,
    ) -> None:
        self.event_store = event_store
        self.dag = dag
        self.max_nodes = max_nodes

    def get_projection(
        self,
        context_hash: str,
        kind: ProjectionKind,
        filters: dict[str, Any] | None = None,
        bypass_cache: bool = False,
    ) -> ProjectionGraph:
        filters_clean = filters or {}
        filters_hash = stable_hash(filters_clean)

        if not bypass_cache:
            cached = self.event_store.get_cached_projection(
                context_hash=context_hash,
                projection_kind=kind.value,
                filters_hash=filters_hash,
            )
            if cached:
                return ProjectionGraph.model_validate(json.loads(cached))

        graph = self._generate(context_hash, kind, filters_clean)
        self.event_store.cache_projection(
            context_hash=context_hash,
            projection_kind=kind.value,
            filters_hash=filters_hash,
            graph_json=graph.model_dump_json(),
        )
        return graph

    def _generate(
        self,
        context_hash: str,
        kind: ProjectionKind,
        filters: dict[str, Any],
    ) -> ProjectionGraph:
        if kind is ProjectionKind.HISTORY:
            return self._history_projection(context_hash, kind)

        nodes_map, edges_map = self._reconstruct_graph(context_hash)
        if kind is ProjectionKind.COMPARE:
            compare_with = str(filters.get("compare_with", ""))
            if compare_with:
                return self._compare_projection(context_hash, compare_with, kind)

        prefix = str(filters.get("prefix", "")).strip()
        proj_nodes: dict[str, ProjectionNode] = {}
        for node_id, row in nodes_map.items():
            source_uri = str(row.get("source_uri", ""))
            node_type = str(row.get("node_type", ""))
            if kind is ProjectionKind.OVERVIEW and node_type not in {
                "package",
                "module",
                "document",
                "class",
                "function",
            }:
                continue
            if kind is ProjectionKind.SUBSYSTEM and prefix and not source_uri.startswith(prefix):
                continue
            proj_nodes[node_id] = self._to_proj_node(row)

        proj_edges = [
            self._to_proj_edge(row)
            for row in edges_map.values()
            if row["from_id"] in proj_nodes and row["to_id"] in proj_nodes
        ]
        proj_nodes, proj_edges = self._bound(proj_nodes, proj_edges)
        return ProjectionGraph(
            context_hash=context_hash,
            kind=kind,
            nodes=tuple(proj_nodes.values()),
            edges=tuple(proj_edges),
        )

    def _history_projection(self, context_hash: str, kind: ProjectionKind) -> ProjectionGraph:
        nodes: dict[str, ProjectionNode] = {}
        edges: list[ProjectionEdge] = []
        for commit_hash in self.dag.ancestry(context_hash):
            row = self.event_store.get_context_row(commit_hash)
            summary = str(row["summary"]) if row else f"Context {commit_hash[:8]}"
            nodes[commit_hash] = ProjectionNode(
                id=commit_hash,
                label=summary,
                kind="context",
                status="active" if commit_hash == context_hash else "historical",
                validation_state="validated",
                metadata={
                    "git_commit": row["git_commit_hash"] if row else None,
                    "branch": row["branch"] if row else None,
                    "created_at": row["created_at"] if row else None,
                },
            )
        for commit_hash in nodes:
            for parent_hash in self.event_store.parent_hashes(commit_hash):
                if parent_hash in nodes:
                    edge_id = f"{commit_hash}->{parent_hash}"
                    edges.append(
                        ProjectionEdge(
                            id=edge_id,
                            from_id=commit_hash,
                            to_id=parent_hash,
                            relation="parent",
                        )
                    )
        return ProjectionGraph(
            context_hash=context_hash,
            kind=kind,
            nodes=tuple(nodes.values()),
            edges=tuple(edges),
        )

    def _compare_projection(
        self,
        context_hash: str,
        other_hash: str,
        kind: ProjectionKind,
    ) -> ProjectionGraph:
        left_nodes, left_edges = self._reconstruct_graph(context_hash)
        right_nodes, right_edges = self._reconstruct_graph(other_hash)
        proj_nodes: dict[str, ProjectionNode] = {}

        for node_id in sorted(set(left_nodes) | set(right_nodes)):
            if node_id in left_nodes and node_id not in right_nodes:
                node = self._to_proj_node(left_nodes[node_id])
                node.status = "added"
            elif node_id in right_nodes and node_id not in left_nodes:
                node = self._to_proj_node(right_nodes[node_id])
                node.status = "removed"
            else:
                node = self._to_proj_node(left_nodes[node_id])
            proj_nodes[node_id] = node

        proj_edges = [
            self._to_proj_edge(row)
            for row in {**right_edges, **left_edges}.values()
            if row["from_id"] in proj_nodes and row["to_id"] in proj_nodes
        ]
        proj_nodes, proj_edges = self._bound(proj_nodes, proj_edges)
        return ProjectionGraph(
            context_hash=context_hash,
            kind=kind,
            nodes=tuple(proj_nodes.values()),
            edges=tuple(proj_edges),
        )

    def _reconstruct_graph(
        self, context_hash: str
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        ordered_ancestry = self.dag.ancestry(context_hash)
        ancestry = set(ordered_ancestry)

        node_rows = self.event_store.graph_nodes_for_contexts(ordered_ancestry)
        edge_rows = self.event_store.graph_edges_for_contexts(ordered_ancestry)

        nodes_by_context: dict[str, list[dict[str, Any]]] = {}
        for row in node_rows:
            nodes_by_context.setdefault(str(row["context_hash"]), []).append(row)

        edges_by_context: dict[str, list[dict[str, Any]]] = {}
        for row in edge_rows:
            edges_by_context.setdefault(str(row["context_hash"]), []).append(row)

        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        for context in reversed(ordered_ancestry):
            for row in nodes_by_context.get(context, []):
                valid_to = row.get("valid_to_context")
                if valid_to and str(valid_to) in ancestry:
                    nodes.pop(str(row["stable_id"]), None)
                else:
                    nodes[str(row["stable_id"])] = dict(row)
            for row in edges_by_context.get(context, []):
                valid_to = row.get("valid_to_context")
                if valid_to and str(valid_to) in ancestry:
                    edges.pop(str(row["stable_id"]), None)
                else:
                    edges[str(row["stable_id"])] = dict(row)
        return nodes, edges

    def _bound(
        self,
        nodes: dict[str, ProjectionNode],
        edges: list[ProjectionEdge],
    ) -> tuple[dict[str, ProjectionNode], list[ProjectionEdge]]:
        if len(nodes) <= self.max_nodes:
            return nodes, edges
        selected = dict(sorted(nodes.items(), key=lambda item: item[1].label)[: self.max_nodes])
        selected_edges = [
            edge for edge in edges if edge.from_id in selected and edge.to_id in selected
        ]
        return selected, selected_edges

    def _to_proj_node(self, row: dict[str, Any]) -> ProjectionNode:
        labels = self._loads(row["labels_json"])
        metadata = self._loads(row["metadata_json"])
        label = labels[0] if labels else row["stable_id"]

        valid_to = row.get("valid_to_context")
        validation_state = "invalidated" if valid_to is not None else "validated"
        return ProjectionNode(
            id=str(row["stable_id"]),
            label=str(label),
            kind=str(row["node_type"]),
            status="invalidated" if valid_to is not None else "active",
            validation_state=validation_state,
            metadata={
                "source_uri": row["source_uri"],
                "labels": labels,
                "metadata": metadata,
            },
        )

    def _to_proj_edge(self, row: dict[str, Any]) -> ProjectionEdge:
        metadata = self._loads(row["metadata_json"])
        valid_to = row.get("valid_to_context")
        return ProjectionEdge(
            id=str(row["stable_id"]),
            from_id=str(row["from_id"]),
            to_id=str(row["to_id"]),
            relation=str(row["relation"]),
            validation_state="invalidated" if valid_to is not None else "validated",
            metadata=metadata or {},
        )

    def _loads(self, value: object) -> Any:
        if isinstance(value, str):
            return json.loads(value)
        return value
