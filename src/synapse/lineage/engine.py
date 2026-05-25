from __future__ import annotations

from synapse.lineage.models import LineageFinding, LineageFindingKind, LineageReport
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore


class LineageVerifier:
    """git fsck equivalent for cognition lineage."""

    def __init__(self, *, event_store: SQLiteEventStore, object_store: ObjectStore) -> None:
        self.event_store = event_store
        self.object_store = object_store

    def verify(self) -> LineageReport:
        context_rows = self.event_store.list_context_rows()
        edge_rows = self.event_store.list_context_edges()
        active_heads = self.event_store.list_active_heads()
        context_hashes = {str(row["context_hash"]) for row in context_rows}
        findings: list[LineageFinding] = []

        for row in context_rows:
            context_hash = str(row["context_hash"])
            try:
                self.object_store.verify(context_hash)
            except FileNotFoundError:
                findings.append(
                    LineageFinding(
                        kind=LineageFindingKind.MISSING_OBJECT,
                        severity="critical",
                        object_id=context_hash,
                        summary="context row references missing object-store payload",
                    )
                )
            except Exception as exc:
                findings.append(
                    LineageFinding(
                        kind=LineageFindingKind.CORRUPT_OBJECT,
                        severity="critical",
                        object_id=context_hash,
                        summary=f"context object failed integrity verification: {exc}",
                    )
                )

        graph: dict[str, set[str]] = {context_hash: set() for context_hash in context_hashes}
        for edge in edge_rows:
            child = str(edge["child_hash"])
            parent = str(edge["parent_hash"])
            if child not in context_hashes:
                findings.append(
                    LineageFinding(
                        kind=LineageFindingKind.MISSING_PARENT,
                        severity="critical",
                        object_id=child,
                        summary="edge child is missing from context table",
                    )
                )
                continue
            if parent not in context_hashes:
                findings.append(
                    LineageFinding(
                        kind=LineageFindingKind.MISSING_PARENT,
                        severity="critical",
                        object_id=child,
                        summary=f"parent context is missing: {parent}",
                    )
                )
                continue
            graph[child].add(parent)

        findings.extend(self._cycle_findings(graph))

        for head in active_heads:
            context_hash = str(head["context_hash"])
            if context_hash not in context_hashes:
                findings.append(
                    LineageFinding(
                        kind=LineageFindingKind.INVALID_ACTIVE_HEAD,
                        severity="critical",
                        object_id=str(head["branch"]),
                        summary=f"active head points to missing context: {context_hash}",
                    )
                )

        return LineageReport(
            ok=not findings,
            context_count=len(context_rows),
            edge_count=len(edge_rows),
            active_head_count=len(active_heads),
            findings=tuple(findings),
        )

    def _cycle_findings(self, graph: dict[str, set[str]]) -> tuple[LineageFinding, ...]:
        visiting: set[str] = set()
        visited: set[str] = set()
        stack: list[str] = []
        findings: list[LineageFinding] = []

        def visit(node: str) -> None:
            visiting.add(node)
            stack.append(node)
            for parent in sorted(graph[node]):
                if parent in visiting:
                    cycle = stack[stack.index(parent) :] + [parent]
                    findings.append(
                        LineageFinding(
                            kind=LineageFindingKind.CYCLE,
                            severity="critical",
                            object_id=node,
                            summary="context lineage cycle detected: " + " -> ".join(cycle),
                        )
                    )
                elif parent not in visited:
                    visit(parent)
            stack.pop()
            visiting.remove(node)
            visited.add(node)

        for node in sorted(graph):
            if node not in visited:
                visit(node)
        return tuple(findings)
