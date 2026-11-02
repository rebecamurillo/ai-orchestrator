"""Pre-flight's `docker` line: a Run whose commands look like they need a Docker daemon.

The daemon is the optional `docker` service (`Settings.verify_docker`); without it, a
`docker compose` in a verify row exits `Cannot connect to the Docker daemon` after the agent
has already spent its attempt. Pre-flight cannot run a command, so it reads two signs, in
order, and reports the first it finds:

- a planned `shell` row whose command names `docker` or `docker-compose`;
- a compose file at the repository root, at the commit the plan was built from — the
  common case being a quality gate that runs a script which runs `docker compose`, which no
  command text shows.

Both are guesses, so the line is at most `warn` and never blocks a start. It is absent when
neither sign is there: a repository with no use for Docker sees no new line. A compose file
that cannot be read (a git failure) counts as no sign — origin and base-branch lines already
report the git failure itself.
"""

from __future__ import annotations

import re

from orchestrator.application.preflight.checks import STEP_FAILURES, Context
from orchestrator.application.preflight.model import CHECK_DOCKER, Line
from orchestrator.application.steps import SHELL_KIND
from orchestrator.application.templates.rows import COMMAND_KEY

#: The names `docker compose` looks for at a project root, in its own order.
COMPOSE_FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")

#: `docker` or `docker-compose` as a word: not `dockerfile-lint`, not `my-docker-thing`.
DOCKER_WORD = re.compile(r"(?<![\w-])docker(?:-compose)?(?![\w-])")

ON = "the docker service serves this Run's docker commands (VERIFY_DOCKER)"
OFF = (
    "no Docker daemon on this instance: a docker command exits "
    "'Cannot connect to the Docker daemon' — set VERIFY_DOCKER=true "
    "(./install.sh start --with-docker) if this Run's commands need one"
)


def docker_line(ctx: Context, verify_docker: bool) -> Line | None:
    """`ok` when the daemon is on, `warn` when it is off, `None` when nothing needs it."""
    sign = _sign(ctx)
    if sign is None:
        return None
    if verify_docker:
        return Line(CHECK_DOCKER, "ok", f"{sign} · {ON}")
    return Line(CHECK_DOCKER, "warn", f"{sign} · {OFF}")


def _sign(ctx: Context) -> str | None:
    if ctx.plan is None:
        return None
    for row in ctx.plan.rows:
        if row.kind == SHELL_KIND and DOCKER_WORD.search(str(row.with_resolved.get(COMMAND_KEY))):
            return f"{row.path} runs docker"
    for name in COMPOSE_FILES:
        try:
            found = ctx.git.read_file(ctx.base_dir, ctx.plan.plan_ref, name)
        except STEP_FAILURES:
            return None
        if found is not None:
            return f"{name} at the repository root"
    return None
