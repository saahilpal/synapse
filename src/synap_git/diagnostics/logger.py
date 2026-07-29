from __future__ import annotations

import contextlib
import logging
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

import structlog

from synap_git.config import LoggingMode, SynapSettings


@dataclass(frozen=True)
class TraceResult:
    correlation_id: str
    latency_ms: float


def configure_logging(settings: SynapSettings) -> None:
    from logging.handlers import RotatingFileHandler

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
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

    # Set up rotating file handler (5MB, 5 backups)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(file_handler)

    # Set up stream handler (stderr)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    if settings.log_level.upper() == "DEBUG":
        stream_handler.setLevel(logging.DEBUG)
    else:
        stream_handler.setLevel(logging.WARNING)
    root_logger.addHandler(stream_handler)

    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(subsystem: str) -> structlog.stdlib.BoundLogger:
    logger = structlog.get_logger("synap").bind(subsystem=subsystem)
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
