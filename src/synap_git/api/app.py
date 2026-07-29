from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from synap_git import __version__
from synap_git.indexer.engine import SynapRuntime


def create_app(runtime: SynapRuntime) -> FastAPI:
    app = FastAPI(
        title="Synap Context Diagnostics",
        description="Deterministic structural context infrastructure for AI coding agents.",
        version=__version__,
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
        exists = await asyncio.to_thread(index_file.exists)
        if exists:
            return await asyncio.to_thread(index_file.read_text, encoding="utf-8")
        return "<h1>Synap Diagnostic UI is ready.</h1>"

    @app.get("/api/v1/status")
    async def get_status() -> dict[str, Any]:
        try:
            status = await asyncio.to_thread(runtime.status)
            from synap_git.cli.main import _read_daemon_heartbeat

            daemon_info = await asyncio.to_thread(
                _read_daemon_heartbeat, Path(status.repository_path)
            )
            return {
                "repository_path": status.repository_path,
                "branch": status.branch,
                "git_commit": status.git_commit,
                "active_commit": status.active_commit,
                "symbols": status.symbols,
                "files": status.files,
                "mode": status.mode,
                "daemon": daemon_info,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/trace/latest")
    async def get_latest_trace() -> dict[str, Any]:
        try:
            if runtime.trace_store:
                return await asyncio.to_thread(runtime.trace_store.get_latest)
            return {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/v1/events")
    async def get_events() -> StreamingResponse:
        from collections.abc import AsyncGenerator

        async def event_generator() -> AsyncGenerator[str, None]:
            while True:
                status = await asyncio.to_thread(runtime.status)
                yield f"data: {json.dumps(status.__dict__)}\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.get("/wiki/{filepath:path}")
    async def get_wiki_page(filepath: str) -> dict[str, Any]:
        base_dir = runtime.wiki.wiki_dir.resolve()
        try:
            target_path = (base_dir / filepath).resolve()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid path")

        if not target_path.is_relative_to(base_dir):
            raise HTTPException(status_code=403, detail="Path traversal detected")

        target = filepath
        if target.endswith(".md"):
            target = target[:-3]
        try:
            await asyncio.to_thread(runtime.wiki.ensure_wiki_page, target)
        except Exception as e:
            import structlog

            structlog.get_logger().error("suppressed_error_caught", error=str(e))

        wiki_path = runtime.wiki.wiki_dir / f"{target}.md"
        exists = await asyncio.to_thread(wiki_path.exists)
        if exists:
            content = await asyncio.to_thread(wiki_path.read_text, encoding="utf-8")
            return {"status": "ok", "content": content}
        return {"status": "error", "message": "Wiki not found"}

    @app.get("/api/v1/memory")
    async def get_memory_page() -> dict[str, Any]:
        approved = await asyncio.to_thread(runtime.store.get_lessons, "approved")
        pending = await asyncio.to_thread(runtime.store.get_lessons, "pending")
        return {"status": "ok", "approved": approved, "pending": pending}

    def _fetch_calls() -> list[dict[str, Any]]:
        with runtime.store.connect() as conn:
            rows = conn.execute("SELECT * FROM llm_calls ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/v1/usage")
    async def get_usage_page() -> dict[str, Any]:
        calls = await asyncio.to_thread(_fetch_calls)
        return {"status": "ok", "calls": calls}

    def _fetch_checkpoints() -> list[dict[str, Any]]:
        with runtime.store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM checkpoints ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/v1/checkpoints")
    async def get_checkpoints_page() -> dict[str, Any]:
        cps = await asyncio.to_thread(_fetch_checkpoints)
        return {"status": "ok", "checkpoints": cps}

    return app
