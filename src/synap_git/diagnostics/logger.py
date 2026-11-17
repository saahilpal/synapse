from __future__ import annotations

import atexit
import contextlib
import logging
import queue
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from typing import cast
from uuid import uuid4

import structlog

from synap_git.config import LoggingMode, SynapSettings

_queue_listener: QueueListener | None = None
_log_queue: queue.Queue[logging.LogRecord] | None = None

_COMPONENT_MAP: dict[str, str] = {
    "wiki": "wiki",
    "wiki_engine": "wiki",
    "wiki_worker": "wiki",
    "daemon": "daemon",
    "runtime_daemon": "daemon",
    "watcher": "daemon",
    "indexer": "indexer",
    "engine": "indexer",
    "scanner": "indexer",
    "parser": "indexer",
    "ast": "indexer",
    "storage": "storage",
    "store": "storage",
    "sqlite": "storage",
    "db": "storage",
    "database": "storage",
    "cli": "cli",
    "main": "cli",
    "command": "cli",
}


def _normalize_component(name: str) -> str:
    cleaned = name.lower().strip()
    if cleaned in _COMPONENT_MAP:
        return _COMPONENT_MAP[cleaned]
    if any(cleaned.startswith(prefix) for prefix in ("wiki", "doc")):
        return "wiki"
    if any(cleaned.startswith(prefix) for prefix in ("daemon", "watch")):
        return "daemon"
    if any(cleaned.startswith(prefix) for prefix in ("index", "scan", "parse")):
        return "indexer"
    if any(cleaned.startswith(prefix) for prefix in ("store", "sql", "db")):
        return "storage"
    if any(cleaned.startswith(prefix) for prefix in ("cli", "cmd")):
        return "cli"
    return cleaned


def _ensure_component_processor(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    if "component" not in event_dict:
        subsystem = event_dict.get("subsystem", "daemon")
        event_dict["component"] = _normalize_component(str(subsystem))
    return event_dict


class FlushingRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that immediately flushes every record to disk."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def stop_logging() -> None:
    """Stop the global QueueListener and flush pending log records."""
    global _queue_listener, _log_queue
    if _queue_listener is not None:
        try:
            _queue_listener.stop()
        except Exception:
            pass
        _queue_listener = None
    _log_queue = None


@dataclass(frozen=True)
class TraceResult:
    correlation_id: str
    latency_ms: float


def configure_logging(settings: SynapSettings) -> None:
    global _queue_listener, _log_queue

    stop_logging()

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        _ensure_component_processor,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.typing.Processor
    if settings.logging_mode is LoggingMode.JSON:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    log_dir = settings.log_path
    assert log_dir is not None
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "daemon.log"

    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    # Set up rotating file handler (5MB, 5 backups) with immediate flush
    file_handler = FlushingRotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    file_handler.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Set up stream handler (stderr)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    if settings.log_level.upper() == "DEBUG":
        stream_handler.setLevel(logging.DEBUG)
    else:
        stream_handler.setLevel(logging.WARNING)

    # Centralized QueueHandler + QueueListener for thread and process safety
    log_queue: queue.Queue[logging.LogRecord] = queue.Queue(-1)
    queue_handler = QueueHandler(log_queue)
    queue_handler.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root_logger.addHandler(queue_handler)

    _queue_listener = QueueListener(
        log_queue,
        file_handler,
        stream_handler,
        respect_handler_level=True,
    )
    _queue_listener.start()
    _log_queue = log_queue

    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    for quiet_logger in ("markdown_it", "asyncio", "httpcore", "httpx"):
        logging.getLogger(quiet_logger).setLevel(logging.WARNING)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    atexit.register(stop_logging)


def get_logger(
    subsystem: str = "daemon",
    *,
    component: str | None = None,
) -> structlog.stdlib.BoundLogger:
    comp = component or _normalize_component(subsystem)
    logger = structlog.get_logger("synap").bind(component=comp, subsystem=subsystem)
    return cast(structlog.stdlib.BoundLogger, logger)


@contextlib.contextmanager
def traced_operation(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    *,
    object_id: str | None = None,
    correlation_id: str | None = None,
    **fields: object,
) -> Iterator[TraceResult]:
    correlation = correlation_id or str(uuid4())
    start = time.perf_counter()
    bound = logger.bind(
        operation=operation,
        object_id=object_id,
        correlation_id=correlation,
        **fields,
    )
    bound.info("operation_started", status="started")
    try:
        yield TraceResult(correlation_id=correlation, latency_ms=0.0)
    except Exception:
        latency_ms = (time.perf_counter() - start) * 1000
        bound.exception("operation_failed", status="error", latency=latency_ms)
        raise
    else:
        latency_ms = (time.perf_counter() - start) * 1000
        bound.info("operation_finished", status="ok", latency=latency_ms)
