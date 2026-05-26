from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from synapse.indexer.engine import SynapseRuntime


def create_app(runtime: SynapseRuntime) -> FastAPI:
    app = FastAPI(
        title="Synapse Context Diagnostics",
        description="Deterministic structural context infrastructure for AI coding agents.",
        version="0.2.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve static UI files
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def get_index() -> str:
        index_file = static_dir / "index.html"
        if index_file.exists():
            return index_file.read_text(encoding="utf-8")
        return "<h1>Synapse Diagnostic UI is ready.</h1>"

    @app.get("/api/v1/status")
    async def get_status() -> dict[str, Any]:
        try:
            status = runtime.status()
            return {
                "repository_path": status.repository_path,
                "branch": status.branch,
                "git_commit": status.git_commit,
                "active_commit": status.active_commit,
                "symbols": status.symbols,
                "files": status.files,
                "mode": status.mode,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/trace/latest")
    async def get_latest_trace() -> dict[str, Any]:
        try:
            return runtime.trace_store.get_latest()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/events")
    async def get_events() -> StreamingResponse:
        from collections.abc import AsyncGenerator

        async def event_generator() -> AsyncGenerator[str, None]:
            while True:
                status = runtime.status()
                yield f"data: {json.dumps(status.__dict__)}\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.get("/wiki/{filepath:path}")
    async def get_wiki_page(filepath: str) -> dict[str, Any]:
        wiki_path = runtime.wiki.wiki_dir / f"{filepath}.md"
        if wiki_path.exists():
            return {"status": "ok", "content": wiki_path.read_text(encoding="utf-8")}
        return {"status": "error", "message": "Wiki not found"}

    @app.get("/api/v1/memory")
    async def get_memory_page() -> dict[str, Any]:
        approved = runtime.store.get_lessons("approved")
        pending = runtime.store.get_lessons("pending")
        return {"status": "ok", "approved": approved, "pending": pending}

    @app.get("/api/v1/cost")
    async def get_cost_page() -> dict[str, Any]:
        with runtime.store.connect() as conn:
            rows = conn.execute("SELECT * FROM llm_calls ORDER BY created_at DESC").fetchall()
            calls = [dict(r) for r in rows]
        return {"status": "ok", "calls": calls}

    @app.get("/api/v1/checkpoints")
    async def get_checkpoints_page() -> dict[str, Any]:
        with runtime.store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM checkpoints ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            cps = [dict(r) for r in rows]
        return {"status": "ok", "checkpoints": cps}

    return app
