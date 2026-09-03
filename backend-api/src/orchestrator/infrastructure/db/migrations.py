"""Bring the schema to head, once, before the process serves anything.

**This module is the canonical statement of when migrations run.** `main()` wires
`run_migrations` in as the application's start-up step — `create_app(settings,
lifespan=migrating_lifespan(settings))` — and uvicorn awaits start-up before it creates the
listening socket. So: exactly one upgrade and one `migrations applied` line per process,
the schema current before the first request, and a failed upgrade aborting start-up instead
of being retried behind a listening port.

The wiring lives in `main()` and not in `create_app` for a reason worth keeping: an
application a test builds carries no start-up step at all, which is what keeps the whole
unit suite free of a database (AD-18). `tests/unit/test_logging.py` calls `main()` itself
with only `uvicorn.run` stubbed, so the migration must not be a side effect of that call
either.

The URL is not passed through `alembic.ini` — the `Settings` object the process already
built is handed to `env.py` through `config.attributes`, so the environment is read exactly
once (AD-20) and no credential enters a committed file (hard rule 5).
"""

from __future__ import annotations

from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from orchestrator.infrastructure.settings import Settings

#: The first revision. Later stories add revisions; this one stays the root of the chain.
BASELINE_REVISION = "0001_baseline"

CONFIG_FILENAME = "alembic.ini"
SCRIPT_DIRNAME = "alembic"

log = structlog.get_logger(__name__)


def migration_root() -> Path:
    """The directory holding `alembic.ini` and `alembic/`.

    Searched upward from this module rather than hard-coded, so the same code works from a
    source checkout and from the image layout 1.6 builds.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / CONFIG_FILENAME).is_file() and (candidate / SCRIPT_DIRNAME).is_dir():
            return candidate
    raise RuntimeError(f"{CONFIG_FILENAME} not found above {__file__}")


def alembic_config(settings: Settings) -> Config:
    """Alembic's configuration, with the script directory pinned and the settings attached."""
    root = migration_root()
    config = Config(str(root / CONFIG_FILENAME))
    # `script_location` in the file is relative to the working directory; make it absolute
    # so `run_migrations` works whatever directory the process was started from
    config.set_main_option("script_location", str(root / SCRIPT_DIRNAME))
    config.attributes["settings"] = settings
    return config


def head_revision(config: Config) -> str:
    """The single revision the committed migration tree ends at.

    `get_heads()` rather than `get_current_head()`: the latter raises `MultipleHeads` from
    inside Alembic before any check here could run, and two parallel branches reaching main
    is a merge mistake that deserves a message naming them, at the moment start-up fails.
    """
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            f"the migration tree must have exactly one head, found {len(heads)}: "
            f"{', '.join(heads) or 'none'} — merge the branches with `alembic merge`"
        )
    return heads[0]


def run_migrations(settings: Settings) -> str:
    """Run `alembic upgrade head` and return the revision now applied.

    Raises whatever Alembic raises: an upgrade that failed must stop the process, not be
    logged and stepped over.
    """
    config = alembic_config(settings)
    command.upgrade(config, "head")
    head = head_revision(config)
    log.info("migrations applied", revision=head)
    return head
