"""FR-21's second path: the command an Operator pastes to take a parked Story's session over.

One `docker compose exec` line, assembled here and published on the Run detail
(`run_views.py::run_detail`). What it looks like is the brief's, verbatim:

    docker compose exec -e ORCH_RUN_ID=… … -e TRACEPARENT=… backend-api sh -c \\
      'export ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY" ANTHROPIC_CUSTOM_HEADERS="…"; \\
       cd {worktree} && claude --resume {session}'

**AD-5 is the shape of this module, not a check inside it.** Nothing here is given a
`Settings`, a `SecretStr` or the real harness environment. `TerminalEnv` (the port) answers
with identifiers by value and every credential as the shell reference `$NAME`, so the string
built below cannot contain a secret — the container the Operator execs into resolves the
names from its own environment when the line runs. `GITHUB_TOKEN` is in neither list, because
it is in no harness environment at all (`infrastructure/harness/env.py::FORBIDDEN_NAMES`).

**The exports are the harness's own aliases, and only quoting is decided here.** Which names
are exported comes from `HARNESS_ENV_ALIASES` through the `AliasBuilder`
`infrastructure/harness/registry.py::build_terminal_env` binds; this module writes them as
`NAME="value"` in the order that array declares them, and nothing else.

**Why a Run may have no terminal at all.** A `terminal: null` is the ordinary answer for
every stop the escape hatch does not apply to, and there are five of them: a park row that is
not an `agent` row, a Run with no worktree, an attempt that never got a session id, a harness
the registry does not hold (Epic 7's `codex` and `local`), and a harness whose
`capabilities.resume` is `False`. Each is asked in that order, and each answers `None` rather
than raising: a read model that 500s because a Run parked somewhere unusual would be worse
than one that hides an optional section.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from orchestrator.application.steps import AGENT_KIND
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.harness import Harness, TerminalEnv, TerminalEnvironment

#: The container the command execs into — the service name `docker-compose.yml` gives the
#: backend, which is also the container holding the worktree and the harness CLIs (AD-14).
SERVICE = "backend-api"
COMPOSE_EXEC = "docker compose exec"
#: The shell the exported names and the harness invocation run under, inside the container.
SHELL = "sh -c"

#: `ORCH_LANGFUSE_TAGS` is a JSON array, so its value holds `[`, `"` and spaces; the other
#: seven identifiers are ids, a slug or a comma-joined tag list. Quoting only what needs it
#: keeps the line readable, which matters for something a person reads before pasting.
QUOTED_IDENTIFIERS = frozenset({"ORCH_LANGFUSE_TAGS"})

#: What a `\` must become inside the inner shell's double quotes, first, so the escapes added
#: after it are not themselves escaped.
BACKSLASH = "\\"
#: The characters a double-quoted shell word still interprets, and that therefore have to be
#: escaped inside an export value. **`$` is deliberately absent**: the whole mechanism of
#: this command is that `$LITELLM_API_KEY` is expanded by the container, so escaping it would
#: hand the harness the literal seven characters instead of the Gateway key. Nothing else can
#: carry a `$` — every value here is a UUID, a slug, a tag list, a traceparent or a JSON array
#: of those (`infrastructure/harness/env.py::identifiers`).
DOUBLE_QUOTED_SPECIALS = ('"', "`")

#: The one way to put a `'` inside a single-quoted shell word: close it, escape the quote,
#: reopen. No value below can contain one today; writing it anyway is what keeps that from
#: becoming a silent breakage the day one can.
SINGLE_QUOTE = "'"
SINGLE_QUOTE_ESCAPE = "'\\''"

#: How long a session stays resumable, per harness. A duration is not a capability — the
#: `HarnessCapabilities` fields are all booleans and default to `False`, and "30 days" is
#: neither — so it is a name-keyed table beside the one rule that reads it, the shape
#: `run_views.py::_KIND_LABELS` already uses. Epic 7 adds `codex`'s own figure here; a
#: harness with no entry answers `None`, which is the brief's "null for others".
SESSION_LIFETIME_DAYS: dict[str, int] = {"claude": 30}


@dataclass(frozen=True)
class Terminal:
    """The `terminal` block of the Run detail read model (FR-21, UX-DR5)."""

    #: The whole line, ready to paste. Identifiers inline, credentials by name.
    command: str
    #: When the harness stops being able to resume this session, or `None` when the harness
    #: states no lifetime. Read off the attempt's own start, not the Run's.
    session_lifetime_ends_at: datetime | None
    #: `run.terminal_session` — whether the Operator has already marked a session open.
    in_progress: bool


@dataclass(frozen=True)
class TerminalPorts:
    """What the command needs beyond the Run's own rows: the identifiers and the registry."""

    env: TerminalEnv
    #: The harness registry, for `capabilities.resume` and the harness's own resume line.
    #: The same mapping `build_harnesses` returns, so a harness that is not enabled on this
    #: instance is simply absent and answers `None`.
    harnesses: Mapping[str, Harness]


def resume_command(
    ports: TerminalPorts,
    run: Run,
    park_row: StepRun | None,
    attempt: Attempt | None,
    *,
    project_slug: str,
) -> Terminal | None:
    """The `terminal` block for this Run, or `None` — see the module docstring's five cases."""
    harness = _resumable_harness(ports, park_row, attempt)
    if harness is None or attempt is None or park_row is None or run.worktree_path is None:
        return None
    environment = ports.env(
        attempt,
        run=run,
        project_slug=project_slug,
        story_id=park_row.story_id,
        traceparent=run.trace_id or "",
    )
    inner = harness.resume_command(run.worktree_path, attempt.session_id or "")
    return Terminal(
        command=_command(environment, inner),
        session_lifetime_ends_at=_lifetime_ends_at(harness.name, attempt.started_at),
        in_progress=run.terminal_session,
    )


def _resumable_harness(
    ports: TerminalPorts, park_row: StepRun | None, attempt: Attempt | None
) -> Harness | None:
    """The harness this attempt ran under, if a terminal can resume it at all."""
    if park_row is None or park_row.kind != AGENT_KIND:
        return None
    if attempt is None or not attempt.session_id:
        return None
    harness = ports.harnesses.get(attempt.harness or "")
    if harness is None or not harness.capabilities.resume:
        return None
    return harness


def _command(environment: TerminalEnvironment, inner: str) -> str:
    """`docker compose exec {-e …} backend-api sh -c '{exports}; {resume}'`.

    The inner script is single-quoted so `$LITELLM_API_KEY` survives the Operator's own shell
    and is expanded by the container's instead — which is the entire mechanism by which a
    credential reaches the harness without ever being on screen.
    """
    flags = " ".join(f"-e {_identifier(name, value)}" for name, value in environment.identifiers)
    script = _script(environment.exports, inner)
    return f"{COMPOSE_EXEC} {flags} {SERVICE} {SHELL} '{_single_quoted(script)}'"


def _single_quoted(script: str) -> str:
    """The script as it goes inside `sh -c '…'` — every `'` closed, escaped and reopened."""
    return script.replace(SINGLE_QUOTE, SINGLE_QUOTE_ESCAPE)


def _escaped(value: str) -> str:
    """One export value, as the *inner* shell must read it back.

    `ANTHROPIC_CUSTOM_HEADERS` is why this exists rather than being an interpolation. Its
    value carries `ORCH_LANGFUSE_TAGS`, which is a JSON array — `["run:…", "attempt:…"]` —
    and every one of those double quotes would otherwise close the double-quoted export a
    character early. The inner shell would then hand Claude Code
    `langfuse_tags: [run:…, attempt:…]`, which is not JSON, and AD-11's attribution would be
    silently wrong for every Gateway call the Operator made from the terminal: exactly the
    spend the brief wants landing on the attempt.
    """
    escaped = value.replace(BACKSLASH, BACKSLASH + BACKSLASH)
    for special in DOUBLE_QUOTED_SPECIALS:
        escaped = escaped.replace(special, BACKSLASH + special)
    return escaped


def _identifier(name: str, value: str) -> str:
    """`NAME=value`, single-quoted where the value is JSON and would otherwise split."""
    if name in QUOTED_IDENTIFIERS:
        return f"{name}='{value}'"
    return f"{name}={value}"


def _script(exports: Sequence[tuple[str, str]], inner: str) -> str:
    """`export A="…" B="…"; {resume}` — or just the resume line for a harness with no aliases.

    Double quotes around each value, inside the single-quoted script: that is what lets
    `$LITELLM_API_KEY` expand in the container and what keeps a header block's own newlines
    together as one argument. `_escaped` is what keeps everything *else* the inner shell would
    have interpreted from being interpreted.
    """
    if not exports:
        return inner
    names = " ".join(f'{name}="{_escaped(value)}"' for name, value in exports)
    return f"export {names}; {inner}"


def _lifetime_ends_at(harness_name: str, started_at: datetime | None) -> datetime | None:
    """Attempt start plus the harness's own session lifetime, or `None` when either is unknown."""
    days = SESSION_LIFETIME_DAYS.get(harness_name)
    if days is None or started_at is None:
        return None
    return started_at + timedelta(days=days)
