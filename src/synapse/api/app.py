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
from synapse.security.validation import InputValidator


def create_app(runtime: SynapseRuntime) -> FastAPI:
    app = FastAPI(
        title="Synapse Context Visualizer",
        description="Persistent structural context infrastructure for AI coding agents.",
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
            commits = runtime.list_context_commits(limit=clamped_limit)
            # Reconstruct dummy events for UI compatibility representing context creations
            events = []
            for item in commits:
                events.append(
                    {
                        "summary": item.get("summary", "Context Commit"),
                        "git_commit_hash": item.get("git_commit_hash"),
                        "branch": item.get("branch", branch or "main"),
                        "event_type": "context.object_created",
                        "payload": {"context_hash": item.get("context_hash")},
                    }
                )
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

    @app.post("/api/v1/overlay")
    async def post_overlay(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
            target_id = str(body.get("target_id", "")).strip()
            instruction = str(body.get("instruction", "Explain this module.")).strip()

            if not target_id:
                raise HTTPException(status_code=400, detail="Target ID is required.")

            context_hash = runtime.add_overlay(
                target_stable_id=target_id, prompt_instruction=instruction
            )
            return {"status": "ok", "context_hash": context_hash}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return app
