from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from synapse.cognition.scanner import RepositoryScan
from synapse.storage.sqlite import SQLiteEventStore


class DriftKind(StrEnum):
    MISSING_SOURCE = "missing_source"
    MISSING_LINK_TARGET = "missing_link_target"
    OUTDATED_DEPENDENCY = "outdated_dependency"


@dataclass(frozen=True)
class DriftFinding:
    kind: DriftKind
    severity: str
    source_uri: str
    summary: str
    score: float
    context_hash: str | None = None


class DriftDetector:
    """Initial confidence-aware drift checks against current repository evidence."""

    def __init__(self, *, event_store: SQLiteEventStore, repository_path: Path) -> None:
        self.event_store = event_store
        self.repository_path = repository_path

    def detect(self, *, scan: RepositoryScan, context_hash: str | None) -> tuple[DriftFinding, ...]:
        findings: list[DriftFinding] = []
        if context_hash is None:
            return ()
        rows = self.event_store.semantic_objects_for_context(context_hash)
        current_paths = {file.relative_path for file in scan.files}
        current_dependencies = set(scan.dependencies)
        for row in rows:
            source_uri = str(row["source_uri"])
            if _is_local_path(source_uri) and source_uri not in current_paths:
                findings.append(
                    DriftFinding(
                        kind=DriftKind.MISSING_SOURCE,
                        severity="high",
                        source_uri=source_uri,
                        summary=f"Stored cognition references missing source {source_uri}",
                        score=0.9,
                        context_hash=context_hash,
                    )
                )
            metadata = _metadata(row)
            for link in metadata.get("links", []):
                if isinstance(link, str) and _is_local_path(link):
                    normalized = link.split("#", 1)[0].lstrip("./")
                    if normalized and normalized not in current_paths:
                        findings.append(
                            DriftFinding(
                                kind=DriftKind.MISSING_LINK_TARGET,
                                severity="medium",
                                source_uri=source_uri,
                                summary=f"Markdown link target is missing: {link}",
                                score=0.65,
                                context_hash=context_hash,
                            )
                        )
            dependencies = metadata.get("dependencies", [])
            if isinstance(dependencies, list):
                missing = sorted(
                    str(dep) for dep in dependencies if dep not in current_dependencies
                )
                if missing and source_uri not in current_paths:
                    findings.append(
                        DriftFinding(
                            kind=DriftKind.OUTDATED_DEPENDENCY,
                            severity="low",
                            source_uri=source_uri,
                            summary=f"Dependency cognition may be stale: {', '.join(missing[:10])}",
                            score=0.4,
                            context_hash=context_hash,
                        )
                    )
        return tuple(findings)


def _is_local_path(uri: str) -> bool:
    return "://" not in uri and not uri.startswith("/")


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    import json

    try:
        value = json.loads(str(row["metadata_json"]))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}
