"""structlog JSON to stdout. There is no `print` in this codebase.

Records reaching stdlib `logging` — uvicorn's and FastAPI's — are routed through the same
structlog processor chain, so the stream is JSON end to end rather than half plain text.

Every line emitted inside a Run carries `run_id`, `path` and `attempt`; those are bound by
the caller, not here. This module only decides the renderer and the level.
"""

from __future__ import annotations

import logging
import sys

import structlog

SHARED_PROCESSORS: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


def _level_number(level: str) -> int:
    """Resolve a level name, refusing an unknown one rather than quietly using INFO."""
    number = logging.getLevelNamesMapping().get(level.upper())
    if number is None:
        raise ValueError(f"unknown log level {level!r}")
    return number


def configure_logging(level: str) -> None:
    """Send structured JSON logs to stdout at `level` (a name such as `info`)."""
    level_number = _level_number(level)

    structlog.configure(
        processors=[
            *SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_number),
        logger_factory=structlog.stdlib.LoggerFactory(),
        # tests reconfigure the process; caching would pin the first level chosen
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level_number)
