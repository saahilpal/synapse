from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TraceStore:
    """Manages recording and retrieving the latest operational trace."""

    def __init__(self, repository_path: Path) -> None:
        self.repo_path = repository_path
        self.trace_file = repository_path / ".synap" / "trace_latest.json"

    def record_trace(
        self,
        trace_type: str,
        summary: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        """Save a new trace event as the latest trace."""
        import uuid

        trace_id = str(uuid.uuid4())
        trace_data = {
            "trace_id": trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": trace_type,
            "summary": summary,
            "details": details,
        }

        try:
            self.trace_file.parent.mkdir(parents=True, exist_ok=True)
            self.trace_file.write_text(json.dumps(trace_data, indent=2), encoding="utf-8")
        except Exception:
            # Operational stability: do not crash the app if trace file cannot be written
            pass

        return trace_data

    def get_latest(self) -> dict[str, Any]:
        """Retrieve the latest trace event."""
        if not self.trace_file.exists():
            return {
                "trace_id": "none",
                "timestamp": datetime.now(UTC).isoformat(),
                "type": "system",
                "summary": "No traces recorded yet",
                "details": {
                    "status": "ready",
                    "message": "Tracing system initialized. Waiting for retrieval/indexing activity.",
                },
            }

        try:
            data = json.loads(self.trace_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {"error": "Invalid trace structure"}
        except (OSError, json.JSONDecodeError) as e:
            return {
                "trace_id": "error",
                "timestamp": datetime.now(UTC).isoformat(),
                "type": "error",
                "summary": "Failed to read latest trace",
                "details": {"error": str(e)},
            }
