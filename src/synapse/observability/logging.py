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

from synapse.config import LoggingMode, SynapseSettings


@dataclass(frozen=True)
class TraceResult:
    correlation_id: str
    latency_ms: float


def configure_logging(settings: SynapseSettings) -> None:
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

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(subsystem: str) -> structlog.stdlib.BoundLogger:
    logger = structlog.get_logger("synapse").bind(subsystem=subsystem)
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
