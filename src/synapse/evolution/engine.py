from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from synapse.cognition.dag import ContextDag
from synapse.cognition.objects import SemanticKind
from synapse.evolution.models import (
    BranchDivergence,
    CognitiveReplayState,
    ConfidenceEvolution,
    EvolutionKind,
    SemanticDiff,
    SemanticDiffItem,
    TimelineEvent,
)
from synapse.storage.sqlite import SQLiteEventStore


class CognitiveEvolutionEngine:
    """Computes semantic evolution over context DAG history.

    This is the center of Synapse's differentiation: the graph/store layer records
    facts, while this engine explains how understanding changed through time.
    """

    def __init__(self, *, event_store: SQLiteEventStore, dag: ContextDag) -> None:
        self.event_store = event_store
        self.dag = dag

    def semantic_diff(self, left_context: str, right_context: str) -> SemanticDiff:
        left = _by_stable_id(self.event_store.semantic_objects_for_context(left_context))
        right = _by_stable_id(self.event_store.semantic_objects_for_context(right_context))
        added: list[SemanticDiffItem] = []
        removed: list[SemanticDiffItem] = []
        changed: list[SemanticDiffItem] = []
        confidence_changed: list[SemanticDiffItem] = []
        unchanged = 0

        for stable_id in sorted(right.keys() - left.keys()):
            added.append(_item(stable_id, EvolutionKind.ADDED, after=right[stable_id]))
        for stable_id in sorted(left.keys() - right.keys()):
            removed.append(_item(stable_id, EvolutionKind.REMOVED, before=left[stable_id]))
        for stable_id in sorted(left.keys() & right.keys()):
            before = left[stable_id]
            after = right[stable_id]
            if str(before["summary"]) != str(after["summary"]):
                changed.append(_item(stable_id, EvolutionKind.CHANGED, before=before, after=after))
            elif abs(float(before["confidence"]) - float(after["confidence"])) >= 0.05:
                confidence_changed.append(
                    _item(stable_id, EvolutionKind.CONFIDENCE_CHANGED, before=before, after=after)
                )
            else:
                unchanged += 1

        headline = _headline(
            added_count=len(added),
            removed_count=len(removed),
            changed_count=len(changed),
            confidence_count=len(confidence_changed),
        )
        return SemanticDiff(
            left_context=left_context,
            right_context=right_context,
            headline=headline,
            added=tuple(added),
            removed=tuple(removed),
            changed=tuple(changed),
            confidence_changed=tuple(confidence_changed),
            unchanged_count=unchanged,
        )

    def timeline(self, *, branch: str | None = None, limit: int = 100) -> tuple[TimelineEvent, ...]:
        rows = self.event_store.list_context_commits(limit=limit)
        events: list[TimelineEvent] = []
        for row in reversed(rows):
            if branch and row["branch"] != branch:
                continue
            context_hash = str(row["context_hash"])
            semantic_counts = Counter(
                str(semantic["kind"])
                for semantic in self.event_store.semantic_objects_for_context(context_hash)
            )
            events.append(
                TimelineEvent(
                    context_hash=context_hash,
                    event_sequence=row["event_sequence"],
                    git_commit_hash=row["git_commit_hash"],
                    branch=row["branch"],
                    summary=str(row["summary"]),
                    confidence=float(row["confidence"]),
                    created_at=datetime.fromisoformat(str(row["created_at"])),
                    semantic_counts=dict(sorted(semantic_counts.items())),
                )
            )
        return tuple(events)

    def confidence_evolution(self, stable_id: str) -> ConfidenceEvolution:
        rows = self.event_store.semantic_history(stable_id)
        samples: list[dict[str, Any]] = []
        for row in rows:
            samples.append(
                {
                    "context_hash": row["context_hash"],
                    "git_commit_hash": row["git_commit_hash"],
                    "branch": row["branch"],
                    "confidence": float(row["confidence"]),
                    "created_at": row["created_at"],
                    "summary": row["summary"],
                }
            )
        trend = "flat"
        if len(samples) >= 2:
            first = float(samples[0]["confidence"])
            last = float(samples[-1]["confidence"])
            if last > first + 0.05:
                trend = "rising"
            elif last < first - 0.05:
                trend = "falling"
        return ConfidenceEvolution(stable_id=stable_id, samples=tuple(samples), trend=trend)

    def branch_divergence(self, *, left_branch: str, right_branch: str) -> BranchDivergence:
        left_head = self.event_store.get_active_head(left_branch)
        right_head = self.event_store.get_active_head(right_branch)
        common = None
        if left_head and right_head:
            common = self.dag.divergence(left_head, right_head)
        return BranchDivergence(
            left_branch=left_branch,
            right_branch=right_branch,
            left_head=left_head,
            right_head=right_head,
            common_context=common,
            diverged=bool(left_head and right_head and left_head != right_head),
        )

    def replay_cognition(
        self,
        *,
        context_hash: str | None = None,
        branch: str | None = None,
    ) -> CognitiveReplayState:
        events = self.timeline(branch=branch)
        if context_hash:
            ancestry = set(self.dag.ancestry(context_hash))
            events = tuple(event for event in events if event.context_hash in ancestry)
        latest_context = context_hash or (events[-1].context_hash if events else None)
        active_assumptions: list[str] = []
        invalidated_assumptions: list[str] = []
        confidence_samples: list[dict[str, Any]] = []
        if latest_context:
            for row in self.event_store.semantic_objects_for_context(latest_context):
                if row["kind"] == SemanticKind.ASSUMPTION.value:
                    if row["valid_to_context"]:
                        invalidated_assumptions.append(str(row["stable_id"]))
                    else:
                        active_assumptions.append(str(row["stable_id"]))
                confidence_samples.append(
                    {
                        "stable_id": row["stable_id"],
                        "confidence": float(row["confidence"]),
                        "kind": row["kind"],
                    }
                )
        return CognitiveReplayState(
            context_hash=latest_context,
            branch=branch,
            events=events,
            active_assumptions=tuple(sorted(active_assumptions)),
            invalidated_assumptions=tuple(sorted(invalidated_assumptions)),
            confidence_samples=tuple(confidence_samples),
        )


def _by_stable_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["stable_id"]): row for row in rows}


def _item(
    stable_id: str,
    change: EvolutionKind,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> SemanticDiffItem:
    representative = after or before or {}
    return SemanticDiffItem(
        stable_id=stable_id,
        kind=str(representative.get("kind", "unknown")),
        change=change,
        before_summary=str(before["summary"]) if before else None,
        after_summary=str(after["summary"]) if after else None,
        before_confidence=float(before["confidence"]) if before else None,
        after_confidence=float(after["confidence"]) if after else None,
        source_uri=str(representative.get("source_uri")) if representative else None,
        metadata=_metadata(representative),
    )


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(str(row.get("metadata_json", "{}")))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _headline(
    *,
    added_count: int,
    removed_count: int,
    changed_count: int,
    confidence_count: int,
) -> str:
    pieces: list[str] = []
    if added_count:
        pieces.append(f"{added_count} cognition objects added")
    if removed_count:
        pieces.append(f"{removed_count} cognition objects removed")
    if changed_count:
        pieces.append(f"{changed_count} cognition objects changed")
    if confidence_count:
        pieces.append(f"{confidence_count} confidence shifts")
    return "; ".join(pieces) if pieces else "No semantic cognition change detected"
