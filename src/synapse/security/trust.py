from __future__ import annotations

from synapse.cognition.objects import TrustLevel
from synapse.storage.sqlite import SQLiteEventStore


class TrustClassifier:
    """Evaluates the trust level of context sources based on database records."""

    def __init__(self, event_store: SQLiteEventStore) -> None:
        self.event_store = event_store

    def get_source_trust(self, source_uri: str) -> TrustLevel:
        """Determines the trust level of a given source. Defaults to LOW."""
        with self.event_store.connect() as conn:
            row = conn.execute(
                "SELECT trust_level FROM trust_records WHERE source = ?",
                (source_uri,),
            ).fetchone()

        if row is None:
            # Check for general patterns (e.g., system commands vs untrusted code files)
            if source_uri.startswith("system://") or source_uri.startswith("manual://"):
                return TrustLevel.HIGH
            return TrustLevel.LOW

        return TrustLevel(str(row["trust_level"]))
