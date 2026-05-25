from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from synapse.projections.models import ProjectionKind
from synapse.runtime.service import SynapseRuntime
from synapse.security.redaction import SecretRedactor
from synapse.security.sanitization import SafeMarkdownRenderer
from synapse.security.validation import InputValidator


def create_app(runtime: SynapseRuntime) -> FastAPI:
    app = FastAPI(
        title="Synapse Cognition visualizer",
        description="Temporal Cognitive Operating System for Software Systems",
        version="0.1.0",
    )

    # Enable CORS for developer workflows
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store runtime in state
    app.state.runtime = runtime

    # Security classes
    redactor = SecretRedactor()
    validator = InputValidator(runtime.settings.repository_path)
    md_renderer = SafeMarkdownRenderer()

    # Serve static UI files
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def get_index() -> str:
        index_file = static_dir / "index.html"
        if index_file.exists():
            return index_file.read_text(encoding="utf-8")
        return "<h1>Synapse visualizer UI is ready. Place index.html in api/static/</h1>"

    @app.get("/api/v1/status")
    async def get_status() -> dict[str, Any]:
        try:
            status = runtime.status()
            data = {
                "repository_path": status.repository_path,
                "branch": status.branch,
                "git_commit": status.git_commit,
                "active_context": status.active_context,
                "events": status.events,
                "context_objects": status.context_objects,
                "semantic_objects": status.semantic_objects,
                "mode": status.mode,
            }
            return redactor.redact(data)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/timeline")
    async def get_timeline(
        branch: str | None = None,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        try:
            clamped_limit = validator.validate_limit(limit)
            timeline = runtime.timeline(branch=branch, limit=clamped_limit)
            events = [item.model_dump(mode="json") for item in timeline]
            return {"events": redactor.redact(events)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/projection/{context_hash}/{kind}")
    async def get_projection(
        context_hash: str,
        kind: ProjectionKind,
        prefix: str | None = None,
        compare_with: str | None = None,
    ) -> dict[str, Any]:
        try:
            # Validate input safety
            if prefix:
                validator.validate_safe_path(prefix)

            filters = {}
            if prefix:
                filters["prefix"] = prefix
            if compare_with:
                filters["compare_with"] = compare_with

            # Generate projection from engine
            graph = runtime.projection_engine.get_projection(
                context_hash=context_hash,
                kind=kind,
                filters=filters,
            )

            # Redact data safely
            return redactor.redact(graph.model_dump(mode="json"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/assumptions")
    async def get_assumptions(context_hash: str | None = None) -> dict[str, Any]:
        try:
            records = runtime.assumptions(context_hash=context_hash)
            items = []
            for record in records:
                item = record.model_dump(mode="json")
                # Sanitize markdown representation
                if "summary" in item:
                    item["summary_html"] = md_renderer.render(item["summary"])
                items.append(item)
            return {"assumptions": redactor.redact(items)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/incidents")
    async def get_incidents() -> dict[str, Any]:
        try:
            # Select incident objects from SQLite
            with runtime.event_store.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM semantic_objects
                    WHERE kind = 'incident'
                    ORDER BY created_at DESC
                    """
                ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item["summary_html"] = md_renderer.render(str(row["summary"]))
                items.append(item)
            return {"incidents": redactor.redact(items)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/health")
    async def get_health(context_hash: str | None = None) -> dict[str, Any]:
        try:
            report = runtime.analyze_health(context_hash)
            return redactor.redact(report.model_dump(mode="json"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/reasoning")
    async def get_reasoning(context_hash: str | None = None) -> dict[str, Any]:
        try:
            report = runtime.analyze_reasoning(context_hash)
            return redactor.redact(report.model_dump(mode="json"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/search/temporal")
    async def get_temporal_search(query: str) -> dict[str, Any]:
        try:
            result = runtime.query_engine.query_flexible(query)
            return redactor.redact(result.__dict__)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/merge/conflicts")
    async def get_merge_conflicts(left: str, right: str) -> dict[str, Any]:
        try:
            report = runtime.detect_conflicts(left, right)
            return redactor.redact(report.model_dump(mode="json"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/v1/compact")
    async def post_compact() -> dict[str, Any]:
        try:
            result = runtime.compact()
            return redactor.redact(result)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/v1/note")
    async def post_note(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
            message = str(body.get("message", "")).strip()
            if not message:
                raise HTTPException(status_code=400, detail="Note message must not be empty.")

            validator.validate_payload_size(message)
            context_hash = runtime.add_note(message)
            return {"status": "ok", "context_hash": context_hash}
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/v1/incident")
    async def post_incident(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
            title = str(body.get("title", "")).strip()
            summary = str(body.get("summary", "")).strip()
            if not title or not summary:
                raise HTTPException(status_code=400, detail="Title and summary are required.")

            validator.validate_payload_size(title + summary)
            record = runtime.record_incident(title=title, summary=summary)
            return {"status": "ok", "incident_id": str(record.incident_id)}
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return app
