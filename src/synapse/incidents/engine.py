from __future__ import annotations

from datetime import datetime

from synapse.assumptions import AssumptionEngine
from synapse.evolution import CognitiveEvolutionEngine
from synapse.incidents.models import IncidentRecord, IncidentReplay
from synapse.serialization import stable_hash
from synapse.storage.sqlite import SQLiteEventStore


class IncidentEngine:
    """Links incidents to the cognition state Synapse believed at the time."""

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

    def record(
        self,
        *,
        title: str,
        summary: str,
        branch: str,
        git_commit_hash: str | None,
        occurred_at: datetime,
    ) -> IncidentRecord:
        context_hash = self.event_store.get_active_head(branch)
        assumption_ids = tuple(
            assumption.stable_id
            for assumption in self.assumptions.list_assumptions(context_hash=context_hash)
        )
        incident_id = stable_hash(
            {
                "title": title,
                "summary": summary,
                "context_hash": context_hash,
                "git_commit_hash": git_commit_hash,
                "occurred_at": occurred_at.isoformat(),
            }
        )
        return IncidentRecord(
            incident_id=incident_id,
            title=title,
            context_hash=context_hash,
            git_commit_hash=git_commit_hash,
            branch=branch,
            occurred_at=occurred_at,
            assumption_ids=assumption_ids,
            summary=summary,
        )

    def replay(self, incident: IncidentRecord) -> IncidentReplay:
        state = self.evolution.replay_cognition(
            context_hash=incident.context_hash,
            branch=incident.branch,
        )
        return IncidentReplay(
            incident=incident,
            active_assumptions=state.active_assumptions,
            invalidated_assumptions=state.invalidated_assumptions,
            confidence_samples=tuple(
                {str(key): value for key, value in sample.items()}
                for sample in state.confidence_samples
            ),
        )
