from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from synapse.storage.sqlite import SQLiteEventStore


class GraphProjectionError(RuntimeError):
    """Raised when graph projection cannot be built."""


@dataclass(frozen=True)
class GraphProjectionSummary:
    context_hash: str
    node_count: int
    edge_count: int


class NetworkXGraphProjection:
    """NetworkX derived graph projection rebuilt from SQLite/object truth."""

    def __init__(self, event_store: SQLiteEventStore) -> None:
        self.event_store = event_store

    def rebuild_context(self, context_hash: str) -> GraphProjectionSummary:
        try:
            import networkx as nx
        except ImportError as exc:
            raise GraphProjectionError("NetworkX is not installed") from exc

        graph: Any = nx.MultiDiGraph()
        for node in self.event_store.graph_nodes_for_context(context_hash):
            graph.add_node(
                str(node["stable_id"]),
                node_type=str(node["node_type"]),
                labels=json.loads(str(node["labels_json"])),
                metadata=json.loads(str(node["metadata_json"])),
                confidence=float(node["confidence"]),
                source_uri=str(node["source_uri"]),
            )
        for edge in self.event_store.graph_edges_for_context(context_hash):
            graph.add_edge(
                str(edge["from_id"]),
                str(edge["to_id"]),
                key=str(edge["stable_id"]),
                relation=str(edge["relation"]),
                metadata=json.loads(str(edge["metadata_json"])),
                confidence=float(edge["confidence"]),
                source_uri=str(edge["source_uri"]),
            )
        return GraphProjectionSummary(
            context_hash=context_hash,
            node_count=int(graph.number_of_nodes()),
            edge_count=int(graph.number_of_edges()),
        )


GraphMemoryError = GraphProjectionError
NetworkXGraphMemory = NetworkXGraphProjection
