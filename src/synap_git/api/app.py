from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from synap_git import __version__
from synap_git.diagnostics.logger import get_logger
from synap_git.indexer.engine import SynapRuntime

logger = get_logger("api")


def _read_daemon_heartbeat(repository_path: Path) -> dict[str, Any] | None:
    heartbeat_path = repository_path / ".synap" / "daemon_heartbeat.json"
    if not heartbeat_path.exists():
        return None
    try:
        data = json.loads(heartbeat_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        mtime = heartbeat_path.stat().st_mtime
        if time.time() - mtime > 10.0:
            data["status"] = "stale"
        return data
    except Exception:
        return None


class StatusSnapshotCache:
    """Shared status snapshot cache with freshness TTL to prevent redundant subprocesses and DB counts."""

    def __init__(self, runtime: SynapRuntime, ttl: float = 2.0) -> None:
        self.runtime = runtime
        self.ttl = ttl
        self._cached_snapshot: dict[str, Any] | None = None
        self._last_fetch_monotonic: float = 0.0
        self._lock = asyncio.Lock()
        self.logger = get_logger("api.status_cache")

    async def get_status(self, force_refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if (
            not force_refresh
            and self._cached_snapshot is not None
            and (now - self._last_fetch_monotonic) < self.ttl
        ):
            return self._cached_snapshot

        async with self._lock:
            # Double check after acquiring lock to prevent dog-piling
            now = time.monotonic()
            if (
                not force_refresh
                and self._cached_snapshot is not None
                and (now - self._last_fetch_monotonic) < self.ttl
            ):
                return self._cached_snapshot

            status = await asyncio.to_thread(self.runtime.status)
            daemon_info = await asyncio.to_thread(
                _read_daemon_heartbeat, Path(status.repository_path)
            )

            daemon_status = daemon_info.get("status") if isinstance(daemon_info, dict) else None
            daemon_pid = daemon_info.get("pid") if isinstance(daemon_info, dict) else None

            raw_fp = (
                f"{status.branch}:{status.git_commit}:{status.active_commit}:"
                f"{status.symbols}:{status.files}:{status.is_dirty}:{status.mode}:"
                f"{daemon_status}:{daemon_pid}"
            )
            fingerprint = hashlib.sha256(raw_fp.encode("utf-8")).hexdigest()[:16]

            now_wall = time.time()
            snapshot: dict[str, Any] = {
                "repository_path": status.repository_path,
                "branch": status.branch,
                "git_commit": status.git_commit,
                "active_commit": status.active_commit,
                "symbols": status.symbols,
                "files": status.files,
                "mode": status.mode,
                "is_dirty": status.is_dirty,
                "daemon": daemon_info,
                "timestamp": now_wall,
                "cached_at": now_wall,
                "freshness_ttl": self.ttl,
                "fingerprint": fingerprint,
            }
            self._cached_snapshot = snapshot
            self._last_fetch_monotonic = now
            return snapshot

    def invalidate(self) -> None:
        self._cached_snapshot = None
        self._last_fetch_monotonic = 0.0


class LessonActionRequest(BaseModel):
    lesson_id: str
    why_failed: str = ""


def create_app(
    runtime: SynapRuntime,
    status_cache: StatusSnapshotCache | None = None,
    cache_ttl: float = 2.0,
) -> FastAPI:
    app = FastAPI(
        title="Synap Context Diagnostics",
        description="Deterministic structural context infrastructure for AI coding agents.",
        version=__version__,
    )

    if status_cache is None:
        status_cache = StatusSnapshotCache(runtime, ttl=cache_ttl)
    app.state.status_cache = status_cache

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:9876",
            "http://localhost:9876",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
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
    @app.get("/api/status")
    @app.get("/health")
    @app.get("/healthz")
    async def get_status() -> dict[str, Any]:
        try:
            assert status_cache is not None
            return await status_cache.get_status()
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
    async def get_events(request: Request) -> StreamingResponse:
        async def event_generator() -> AsyncGenerator[str, None]:
            last_fingerprint: str | None = None
            try:
                while True:
                    if await request.is_disconnected():
                        break

                    try:
                        assert status_cache is not None
                        snapshot = await status_cache.get_status()
                        fingerprint = str(snapshot.get("fingerprint", ""))
                        if fingerprint != last_fingerprint:
                            last_fingerprint = fingerprint
                            yield f"data: {json.dumps(snapshot)}\n\n"
                        else:
                            yield ": keepalive\n\n"
                    except Exception as e:
                        logger.warning("events_stream_error", error=str(e))

                    for _ in range(20):
                        if await request.is_disconnected():
                            return
                        await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

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
        try:
            await asyncio.to_thread(runtime.initialize_storage)
            approved = await asyncio.to_thread(runtime.store.get_lessons, "approved")
            pending = await asyncio.to_thread(runtime.store.get_lessons, "pending")
            return {"status": "ok", "approved": approved, "pending": pending}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "approved": [], "pending": []}

    @app.get("/api/v1/usage")
    async def get_usage_page() -> dict[str, Any]:
        calls = await asyncio.to_thread(runtime.store.get_llm_calls)
        return {"status": "ok", "calls": calls}

    @app.get("/api/v1/checkpoints")
    async def get_checkpoints_page() -> dict[str, Any]:
        cps = await asyncio.to_thread(runtime.store.get_checkpoints, None, 20)
        return {"status": "ok", "checkpoints": cps}

    @app.get("/api/v1/blast")
    async def get_blast() -> dict[str, Any]:
        try:
            from synap_git.mcp.server import SynapMCPFacade

            facade = SynapMCPFacade(runtime)
            blast = await asyncio.to_thread(facade.get_blast_radius)
            return {"status": "ok", "blast": blast}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "blast": {}}

    @app.get("/api/v1/hubs")
    async def get_hubs(limit: int = 10) -> dict[str, Any]:
        try:

            def _calc_hubs() -> list[dict[str, Any]]:
                active_files = list(runtime.git.get_dirty_diff_ranges().keys())
                return runtime.store.compute_pagerank(active_files=active_files, limit=limit)

            hubs = await asyncio.to_thread(_calc_hubs)
            return {"status": "ok", "hubs": hubs}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "hubs": []}

    @app.get("/api/v1/search")
    async def search(q: str, max_tokens: int = 2000) -> dict[str, Any]:
        try:
            from synap_git.mcp.server import SynapMCPFacade

            facade = SynapMCPFacade(runtime)
            res = await asyncio.to_thread(facade.search, q, max_tokens, summary_only=True)
            return {"status": "ok", "query": q, "results": res}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "results": {}}

    @app.get("/api/v1/symbol")
    async def get_symbol(name: str, file_path: str = "") -> dict[str, Any]:
        try:
            from synap_git.mcp.server import SynapMCPFacade

            facade = SynapMCPFacade(runtime)
            sym = await asyncio.to_thread(facade.read_symbol, name, file_path or None)
            callers = await asyncio.to_thread(
                facade.get_neighborhood, name, file_path or None, "upstream", 1
            )
            callees = await asyncio.to_thread(
                facade.get_neighborhood, name, file_path or None, "downstream", 1
            )
            return {"status": "ok", "symbol": sym, "callers": callers, "callees": callees}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @app.get("/api/v1/memories")
    async def get_memories(key: str = "", limit: int = 20) -> dict[str, Any]:
        try:
            from synap_git.mcp.server import SynapMCPFacade

            facade = SynapMCPFacade(runtime)
            res = await asyncio.to_thread(facade.recall, key, limit)
            return {"status": "ok", "memories": res.get("memories", [])}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "memories": []}

    @app.post("/api/v1/memory/approve")
    async def approve_lesson(req: LessonActionRequest) -> dict[str, Any]:
        try:
            await asyncio.to_thread(
                runtime.store.update_lesson,
                req.lesson_id,
                req.why_failed or "Approved via Web UI",
                "approved",
                "web_ui",
            )
            return {"status": "ok", "lesson_id": req.lesson_id}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @app.post("/api/v1/memory/reject")
    async def reject_lesson(req: LessonActionRequest) -> dict[str, Any]:
        try:
            await asyncio.to_thread(
                runtime.store.update_lesson,
                req.lesson_id,
                req.why_failed or "Rejected via Web UI",
                "rejected",
                "web_ui",
            )
            return {"status": "ok", "lesson_id": req.lesson_id}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    return app
