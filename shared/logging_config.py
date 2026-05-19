"""
Structured JSON logging configuration for IVGS v5 (§13.4).

Every log entry includes: timestamp, service_name, node_hostname,
severity, message, and optional job_id / trace_id fields.
"""
import logging
import sys
from typing import Optional

import structlog

from .config import settings


def setup_logging(
    service_name: str = "ivgs",
    node_hostname: Optional[str] = None,
) -> None:
    """
    Configure structured logging for a service.

    Args:
        service_name: Identifier for the service (ivgs-api, ivgs-workers, etc.).
        node_hostname: Hostname override (defaults to settings.NODE_HOSTNAME).
    """
    hostname = node_hostname or settings.NODE_HOSTNAME
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Shared processors injected into every log entry
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.LOG_FORMAT.lower() == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Suppress noisy third-party loggers
    for noisy in ("urllib3", "httpx", "httpcore", "PIL", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Bind service-level context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        service=service_name,
        node=hostname,
    )

    root.info(
        f"Logging configured: service={service_name}, node={hostname}, "
        f"level={settings.LOG_LEVEL}, format={settings.LOG_FORMAT}"
    )
