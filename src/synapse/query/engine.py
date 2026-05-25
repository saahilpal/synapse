from __future__ import annotations

import re
from datetime import datetime

from synapse.assumptions import AssumptionEngine
from synapse.evolution import CognitiveEvolutionEngine
from synapse.query.models import TemporalQueryKind, TemporalQueryResult
from synapse.storage.sqlite import SQLiteEventStore


class TemporalQueryEngine:
    """Typed temporal cognition queries over context lineage and semantic history."""

    def __init__(
        self,
        *,
        event_store: SQLiteEventStore,
        evolution: CognitiveEvolutionEngine,
        assumptions: AssumptionEngine,
    ) -> None:
        self.event_store = event_store
        self.evolution = evolution
        self.assumptions = assumptions

    def cognition_before_commit(self, git_commit_hash: str) -> TemporalQueryResult:
        rows = self.event_store.list_context_rows()
        before: dict[str, object] | None = None
        matched = False
        for row in rows:
            if row.get("git_commit_hash") == git_commit_hash:
                matched = True
                break
            before = row
        context_hash = str(before["context_hash"]) if matched and before else None
        semantic_rows = (
            tuple(self.event_store.semantic_objects_for_context(context_hash))
            if context_hash
            else ()
        )
        return TemporalQueryResult(
            query=TemporalQueryKind.COGNITION_BEFORE_COMMIT,
            context_hash=context_hash,
            rows=semantic_rows,
            summary=f"{len(semantic_rows)} cognition objects before commit {git_commit_hash}",
        )

    def evolution_between_dates(self, start: datetime, end: datetime) -> TemporalQueryResult:
        rows = tuple(
            row
            for row in self.event_store.list_context_rows()
            if start <= datetime.fromisoformat(str(row["created_at"])) <= end
        )
        return TemporalQueryResult(
            query=TemporalQueryKind.EVOLUTION_BETWEEN_DATES,
            rows=rows,
            summary=(
                f"{len(rows)} context commits between {start.isoformat()} and {end.isoformat()}"
            ),
        )

    def assumptions_invalidated_after(self, context_hash: str) -> TemporalQueryResult:
        rows = tuple(
            assumption.model_dump(mode="json")
            for assumption in self.assumptions.list_assumptions()
            if assumption.invalidated_by_context == context_hash
        )
        return TemporalQueryResult(
            query=TemporalQueryKind.INVALIDATED_ASSUMPTIONS_AFTER,
            context_hash=context_hash,
            rows=rows,
            summary=f"{len(rows)} assumptions invalidated by context {context_hash}",
        )

    def confidence_decay_for(self, stable_id: str) -> TemporalQueryResult:
        evolution = self.evolution.confidence_evolution(stable_id)
        rows = evolution.samples
        decays = [
            (before, after)
            for before, after in zip(rows, rows[1:], strict=False)
            if float(after["confidence"]) < float(before["confidence"])
        ]
        return TemporalQueryResult(
            query=TemporalQueryKind.CONFIDENCE_DECAY_FOR,
            rows=rows,
            summary=f"{len(decays)} confidence decay steps for {stable_id}",
        )

    def query_flexible(self, query_string: str) -> TemporalQueryResult:
        """Flexible temporal search supporting date, commit, incident, drift, and confidence queries."""
        query_string_lower = query_string.lower().strip()

        # 1. Date: after YYYY-MM-DD / before YYYY-MM-DD
        date_match = re.search(r"(after|before)\s+(\d{4}-\d{2}-\d{2})", query_string_lower)
        if date_match:
            modifier = date_match.group(1)
            date_val = datetime.strptime(date_match.group(2), "%Y-%m-%d")
            context_rows = self.event_store.list_context_rows()
            matched_hashes = []
            for row in context_rows:
                row_date = datetime.fromisoformat(str(row["created_at"]))
                if row_date.tzinfo is not None:
                    row_date = row_date.replace(tzinfo=None)
                if modifier == "after" and row_date > date_val:
                    matched_hashes.append(str(row["context_hash"]))
                elif modifier == "before" and row_date < date_val:
                    matched_hashes.append(str(row["context_hash"]))

            rows = self.event_store.semantic_objects_for_contexts(matched_hashes)
            return TemporalQueryResult(
                query=TemporalQueryKind.FLEXIBLE_SEARCH,
                rows=tuple(rows),
                summary=f"Found {len(rows)} semantic objects {modifier} date {date_match.group(2)}",
            )

        # 2. Commit: after commit <hash> / before commit <hash>
        commit_match = re.search(r"(after|before)\s+commit\s+([a-fA-F0-9]+)", query_string_lower)
        if commit_match:
            modifier = commit_match.group(1)
            commit_hash = commit_match.group(2)
            context_rows = self.event_store.list_context_rows()

            target_seq = None
            for row in context_rows:
                c_hash = row.get("git_commit_hash")
                if c_hash and c_hash.startswith(commit_hash):
                    target_seq = row.get("event_sequence")
                    break

            if target_seq is None:
                return TemporalQueryResult(
                    query=TemporalQueryKind.FLEXIBLE_SEARCH,
                    rows=(),
                    summary=f"Commit '{commit_hash}' not found in context history.",
                )

            matched_hashes = []
            for row in context_rows:
                seq = row.get("event_sequence")
                if seq is not None:
                    if modifier == "after" and seq > target_seq:
                        matched_hashes.append(str(row["context_hash"]))
                    elif modifier == "before" and seq < target_seq:
                        matched_hashes.append(str(row["context_hash"]))

            rows = self.event_store.semantic_objects_for_contexts(matched_hashes)
            return TemporalQueryResult(
                query=TemporalQueryKind.FLEXIBLE_SEARCH,
                rows=tuple(rows),
                summary=f"Found {len(rows)} semantic objects {modifier} commit {commit_hash}",
            )

        # 3. Incident: after incident <title> / before incident <title>
        incident_match = re.search(r"(after|before)\s+incident\s+(.+)", query_string_lower)
        if incident_match:
            modifier = incident_match.group(1)
            incident_title = incident_match.group(2)

            incident_objects = self.event_store.semantic_objects_by_kind(kind="incident")
            target_date = None
            for obj in incident_objects:
                if incident_title in str(obj.get("summary", "")).lower():
                    target_date = datetime.fromisoformat(str(obj["created_at"]))
                    if target_date.tzinfo is not None:
                        target_date = target_date.replace(tzinfo=None)
                    break

            if not target_date:
                return TemporalQueryResult(
                    query=TemporalQueryKind.FLEXIBLE_SEARCH,
                    rows=(),
                    summary=f"Incident '{incident_title}' not found.",
                )

            context_rows = self.event_store.list_context_rows()
            matched_hashes = []
            for row in context_rows:
                row_date = datetime.fromisoformat(str(row["created_at"]))
                if row_date.tzinfo is not None:
                    row_date = row_date.replace(tzinfo=None)
                if modifier == "after" and row_date > target_date:
                    matched_hashes.append(str(row["context_hash"]))
                elif modifier == "before" and row_date < target_date:
                    matched_hashes.append(str(row["context_hash"]))

            rows = self.event_store.semantic_objects_for_contexts(matched_hashes)
            return TemporalQueryResult(
                query=TemporalQueryKind.FLEXIBLE_SEARCH,
                rows=tuple(rows),
                summary=f"Found {len(rows)} semantic objects {modifier} incident '{incident_title}'",
            )

        # 4. Drift: drift in <subsystem>
        drift_match = re.search(r"drift\s+in\s+(\S+)", query_string_lower)
        if drift_match:
            subsystem = drift_match.group(1)
            all_semantics = self.event_store.search_semantic_objects(subsystem)
            drift_rows = []
            for sem in all_semantics:
                metadata = sem.get("metadata_json")
                is_drifted = metadata and "drift" in str(metadata)
                if (
                    is_drifted
                    or sem.get("kind") == "drift"
                    or "drift" in str(sem.get("summary", "")).lower()
                ):
                    drift_rows.append(sem)

            return TemporalQueryResult(
                query=TemporalQueryKind.FLEXIBLE_SEARCH,
                rows=tuple(drift_rows),
                summary=f"Found {len(drift_rows)} drift records in subsystem '{subsystem}'",
            )

        # 5. Low confidence or Confidence collapse
        if "confidence collapse" in query_string_lower or "low confidence" in query_string_lower:
            with self.event_store.connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM semantic_objects WHERE confidence < 0.5 ORDER BY confidence ASC"
                ).fetchall()
            res_rows = [dict(r) for r in rows]
            return TemporalQueryResult(
                query=TemporalQueryKind.FLEXIBLE_SEARCH,
                rows=tuple(res_rows),
                summary=f"Found {len(res_rows)} low confidence semantic objects",
            )

        # Fallback to general keyword search
        rows = self.event_store.search_semantic_objects(query_string)
        return TemporalQueryResult(
            query=TemporalQueryKind.FLEXIBLE_SEARCH,
            rows=tuple(rows),
            summary=f"Keyword search for '{query_string}' matched {len(rows)} objects",
        )
