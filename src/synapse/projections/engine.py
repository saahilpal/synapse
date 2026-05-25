from __future__ import annotations

import json
from typing import Any

from synapse.cognition.dag import ContextDag
from synapse.projections.models import (
    ProjectionEdge,
    ProjectionGraph,
    ProjectionKind,
    ProjectionNode,
)
from synapse.serialization import stable_hash
from synapse.storage.sqlite import SQLiteEventStore
from synapse.temporal.graph import TemporalGraphEngine


class ProjectionEngine:
    """Slices the temporal cognition graph into secure, bounded visual views."""

    def __init__(
        self,
        *,
        event_store: SQLiteEventStore,
        dag: ContextDag,
        temporal_graph: TemporalGraphEngine,
        max_nodes: int = 150,
    ) -> None:
        self.event_store = event_store
        self.dag = dag
        self.temporal_graph = temporal_graph
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
                data = json.loads(cached)
                return ProjectionGraph.model_validate(data)

        # Generate fresh projection
        graph = self._generate(context_hash, kind, filters_clean)

        # Cache it
        serialized = graph.model_dump_json()
        self.event_store.cache_projection(
            context_hash=context_hash,
            projection_kind=kind.value,
            filters_hash=filters_hash,
            graph_json=serialized,
        )

        return graph

    def _generate(
        self,
        context_hash: str,
        kind: ProjectionKind,
        filters: dict[str, Any],
    ) -> ProjectionGraph:
        # Reconstruct active graph nodes & edges
        nodes_map, edges_map = self._reconstruct_graph(context_hash)

        # Build clean projection structures
        proj_nodes: dict[str, ProjectionNode] = {}
        proj_edges: list[ProjectionEdge] = []

        if kind == ProjectionKind.OVERVIEW:
            # High-level overview: show decisions, assumptions, services, and packages, filtering out code modules
            allowed_kinds = {"decision", "assumption", "service", "package", "incident", "document"}
            for nid, ndata in nodes_map.items():
                node_type = str(ndata["node_type"])
                if node_type in allowed_kinds:
                    proj_nodes[nid] = self._to_proj_node(ndata)

            # Keep edges between the overview nodes
            for eid, edata in edges_map.items():
                if edata["from_id"] in proj_nodes and edata["to_id"] in proj_nodes:
                    proj_edges.append(self._to_proj_edge(edata))

        elif kind == ProjectionKind.SUBSYSTEM:
            # Filters by a specific folder prefix (default to root if not specified)
            path_prefix = str(filters.get("prefix", "")).strip()
            for nid, ndata in nodes_map.items():
                source_uri = str(ndata.get("source_uri", ""))
                # If module or package matching prefix
                if not path_prefix or source_uri.startswith(path_prefix):
                    proj_nodes[nid] = self._to_proj_node(ndata)

            for eid, edata in edges_map.items():
                if edata["from_id"] in proj_nodes and edata["to_id"] in proj_nodes:
                    proj_edges.append(self._to_proj_edge(edata))

        elif kind == ProjectionKind.REPLAY:
            # Visualise context commit lineage DAG up to context_hash
            ordered_ancestry = self.dag.ancestry(context_hash)
            # Create nodes for the contexts themselves
            for c_hash in ordered_ancestry:
                row = self.event_store.get_context_row(c_hash)
                summary = str(row["summary"]) if row else f"Context {c_hash[:8]}"
                conf_val = float(row["confidence"]) if row else 1.0
                val_state = "validated" if conf_val >= 0.85 else "assumed"
                proj_nodes[c_hash] = ProjectionNode(
                    id=c_hash,
                    label=summary,
                    kind="context_commit",
                    confidence=conf_val,
                    status="active" if c_hash == context_hash else "historical",
                    validation_state=val_state,
                    metadata={
                        "git_commit": row["git_commit_hash"] if row else None,
                        "branch": row["branch"] if row else None,
                        "created_at": row["created_at"] if row else None,
                    },
                )

            # Create edges between child -> parent
            for c_hash in ordered_ancestry:
                parents = self.event_store.parent_hashes(c_hash)
                for p_hash in parents:
                    if p_hash in proj_nodes:
                        edge_id = f"{c_hash}->{p_hash}"
                        proj_edges.append(
                            ProjectionEdge(
                                id=edge_id,
                                from_id=c_hash,
                                to_id=p_hash,
                                relation="parent",
                                confidence=1.0,
                            )
                        )

        elif kind == ProjectionKind.DRIFT:
            # Highlighting drifted modules (git changes compared to scanned code state)
            for nid, ndata in nodes_map.items():
                pnode = self._to_proj_node(ndata)
                # Check metadata or validity for drift flags
                is_drifted = ndata.get("metadata_json") and "drift" in str(ndata["metadata_json"])
                if is_drifted:
                    pnode.status = "drifted"
                proj_nodes[nid] = pnode

            for eid, edata in edges_map.items():
                if edata["from_id"] in proj_nodes and edata["to_id"] in proj_nodes:
                    proj_edges.append(self._to_proj_edge(edata))

        elif kind == ProjectionKind.ASSUMPTION:
            # Focus on assumptions and constraints
            allowed_kinds = {"assumption", "decision", "risk"}
            for nid, ndata in nodes_map.items():
                node_type = str(ndata["node_type"])
                if node_type in allowed_kinds:
                    pnode = self._to_proj_node(ndata)
                    # Check invalidation flag
                    metadata = (
                        json.loads(ndata["metadata_json"])
                        if isinstance(ndata["metadata_json"], str)
                        else ndata["metadata_json"]
                    )
                    if metadata and metadata.get("invalidated"):
                        pnode.status = "invalidated"
                    proj_nodes[nid] = pnode

            for eid, edata in edges_map.items():
                if edata["from_id"] in proj_nodes and edata["to_id"] in proj_nodes:
                    proj_edges.append(self._to_proj_edge(edata))

        elif kind == ProjectionKind.INCIDENT:
            # Highlight incident nodes and components connected to incidents
            incident_nodes = set()
            for nid, ndata in nodes_map.items():
                node_type = str(ndata["node_type"])
                if node_type == "incident":
                    proj_nodes[nid] = self._to_proj_node(ndata)
                    incident_nodes.add(nid)

            # Add connected nodes
            for eid, edata in edges_map.items():
                from_id = edata["from_id"]
                to_id = edata["to_id"]
                if from_id in incident_nodes or to_id in incident_nodes:
                    if from_id not in proj_nodes and from_id in nodes_map:
                        proj_nodes[from_id] = self._to_proj_node(nodes_map[from_id])
                    if to_id not in proj_nodes and to_id in nodes_map:
                        proj_nodes[to_id] = self._to_proj_node(nodes_map[to_id])
                    proj_edges.append(self._to_proj_edge(edata))

        elif kind == ProjectionKind.BRANCH:
            # branch comparison: compare this context hash with another
            other_hash = str(filters.get("compare_with", ""))
            if other_hash:
                other_nodes, other_edges = self._reconstruct_graph(other_hash)

                # Find differences
                all_node_ids = set(nodes_map.keys()) | set(other_nodes.keys())
                for nid in all_node_ids:
                    if nid in nodes_map and nid not in other_nodes:
                        # Present in left (current), absent in right (other) -> modified or deleted in other
                        pnode = self._to_proj_node(nodes_map[nid])
                        pnode.status = "deleted"
                        proj_nodes[nid] = pnode
                    elif nid in other_nodes and nid not in nodes_map:
                        # Present in right, absent in left -> added in other
                        pnode = self._to_proj_node(other_nodes[nid])
                        pnode.status = "added"
                        proj_nodes[nid] = pnode
                    else:
                        # Present in both -> check if metadata or confidence changed
                        left_node = nodes_map[nid]
                        right_node = other_nodes[nid]
                        pnode = self._to_proj_node(left_node)
                        if left_node["confidence"] != right_node["confidence"]:
                            pnode.status = "modified"
                        proj_nodes[nid] = pnode

                # Edges comparison
                all_edge_ids = set(edges_map.keys()) | set(other_edges.keys())
                for eid in all_edge_ids:
                    if (
                        eid in edges_map
                        and edges_map[eid]["from_id"] in proj_nodes
                        and edges_map[eid]["to_id"] in proj_nodes
                    ):
                        proj_edges.append(self._to_proj_edge(edges_map[eid]))
                    elif (
                        eid in other_edges
                        and other_edges[eid]["from_id"] in proj_nodes
                        and other_edges[eid]["to_id"] in proj_nodes
                    ):
                        proj_edges.append(self._to_proj_edge(other_edges[eid]))
            else:
                # Fallback to standard node mapping if compare_with not specified
                for nid, ndata in nodes_map.items():
                    proj_nodes[nid] = self._to_proj_node(ndata)
                for eid, edata in edges_map.items():
                    if edata["from_id"] in proj_nodes and edata["to_id"] in proj_nodes:
                        proj_edges.append(self._to_proj_edge(edata))

        # Graph clustering: if projection nodes exceed 80, collapse module nodes under their parent package nodes
        if len(proj_nodes) > 80:
            packages = {nid: n for nid, n in proj_nodes.items() if n.kind in ("package", "service")}
            modules = {nid: n for nid, n in proj_nodes.items() if n.kind == "module"}

            module_to_package: dict[str, str] = {}

            # 1. Map module -> parent package ID based on owns relationship
            for edge in proj_edges:
                if edge.relation in ("owns", "owns_module"):
                    if edge.from_id in packages and edge.to_id in modules:
                        module_to_package[edge.to_id] = edge.from_id

            # 2. Fallback to source_uri prefix matching for directory clustering
            for mid, mnode in modules.items():
                if mid not in module_to_package:
                    m_uri = mnode.metadata.get("source_uri", "") if mnode.metadata else ""
                    best_pkg = None
                    best_len = -1
                    for pid, pnode in packages.items():
                        p_uri = pnode.metadata.get("source_uri", "") if pnode.metadata else ""
                        if p_uri and m_uri.startswith(p_uri) and len(p_uri) > best_len:
                            best_pkg = pid
                            best_len = len(p_uri)
                    if best_pkg:
                        module_to_package[mid] = best_pkg

            # 3. Collapse nodes and re-route edges
            if module_to_package:
                for mid in module_to_package:
                    proj_nodes.pop(mid, None)

                new_edges: dict[str, ProjectionEdge] = {}
                for edge in proj_edges:
                    from_id = module_to_package.get(edge.from_id, edge.from_id)
                    to_id = module_to_package.get(edge.to_id, edge.to_id)

                    if from_id == to_id:
                        continue
                    if edge.relation in ("owns", "owns_module") and edge.to_id in module_to_package:
                        continue

                    edge_key = f"{from_id}->{to_id}:{edge.relation}"
                    if edge_key in new_edges:
                        if edge.confidence > new_edges[edge_key].confidence:
                            new_edges[edge_key] = ProjectionEdge(
                                id=edge_key,
                                from_id=from_id,
                                to_id=to_id,
                                relation=edge.relation,
                                confidence=edge.confidence,
                                metadata=edge.metadata,
                            )
                    else:
                        new_edges[edge_key] = ProjectionEdge(
                            id=edge_key,
                            from_id=from_id,
                            to_id=to_id,
                            relation=edge.relation,
                            confidence=edge.confidence,
                            metadata=edge.metadata,
                        )
                proj_edges = list(new_edges.values())

        # Enforce max node bounds to keep rendering secure and performant
        if len(proj_nodes) > self.max_nodes:
            # Sort by confidence / importance and keep top max_nodes
            sorted_nodes = sorted(proj_nodes.values(), key=lambda n: n.confidence, reverse=True)
            proj_nodes = {n.id: n for n in sorted_nodes[: self.max_nodes]}
            # Keep only edges connecting remaining nodes
            proj_edges = [
                edge
                for edge in proj_edges
                if edge.from_id in proj_nodes and edge.to_id in proj_nodes
            ]

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

    def _to_proj_node(self, row: dict[str, Any]) -> ProjectionNode:
        labels = (
            json.loads(row["labels_json"])
            if isinstance(row["labels_json"], str)
            else row["labels_json"]
        )
        metadata = (
            json.loads(row["metadata_json"])
            if isinstance(row["metadata_json"], str)
            else row["metadata_json"]
        )
        label = labels[0] if labels else row["stable_id"]

        valid_to = row.get("valid_to_context")
        conf_val = float(row["confidence"])
        if valid_to is not None:
            val_state = "invalidated"
        elif conf_val >= 0.85:
            val_state = "validated"
        else:
            val_state = "assumed"

        return ProjectionNode(
            id=str(row["stable_id"]),
            label=str(label),
            kind=str(row["node_type"]),
            confidence=conf_val,
            validation_state=val_state,
            metadata={
                "source_uri": row["source_uri"],
                "labels": labels,
                "metadata": metadata,
            },
        )

    def _to_proj_edge(self, row: dict[str, Any]) -> ProjectionEdge:
        metadata = (
            json.loads(row["metadata_json"])
            if isinstance(row["metadata_json"], str)
            else row["metadata_json"]
        )
        valid_to = row.get("valid_to_context")
        conf_val = float(row["confidence"])
        if valid_to is not None:
            val_state = "invalidated"
        elif conf_val >= 0.85:
            val_state = "validated"
        else:
            val_state = "assumed"

        return ProjectionEdge(
            id=str(row["stable_id"]),
            from_id=str(row["from_id"]),
            to_id=str(row["to_id"]),
            relation=str(row["relation"]),
            confidence=conf_val,
            validation_state=val_state,
            metadata=metadata or {},
        )
