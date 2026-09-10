"""The `Harness` port (AD-10, FR-14, FR-21): starting a coding agent, and what comes back.

One port, one adapter per harness, and a registry keyed by the name a Template writes. The
rule the port exists to hold is stated by what `HarnessResult` *does not* have: an adapter
returns the session it ran under, the exit code, the log it wrote, the usage the harness
reported, and the result object exactly as the harness printed it — and nothing it has
interpreted. Whether an exit was the budget cap, whether a story is blocked, whether a test
failed: every one of those is read from the repository or from the JSON by a use case, so
adding a harness never means adding a second place that decides what an attempt meant.

Three things follow from that and are worth naming here rather than in each adapter:

- **`capabilities` is asked, never assumed.** `preassign_session` is what lets the caller
  allocate a session id before the process starts, so an attempt can be resumed by a row
  that never saw the harness's own output; `resume` is what makes `retry` a continuation
  rather than a fresh dispatch; `native_tracing` says the harness exports its own OTLP
  spans and parents them under the `TRACEPARENT` it is given (AD-11). Each defaults to
  `False`, so a caller that asks gets a claim the adapter made rather than one this port
  assumed. What the flags do *not* gate is the environment: `TRACEPARENT` is a contract
  name for every harness (`scripts/harness/_common.sh`), and a harness without
  `native_tracing` still receives it and simply exports nothing under it.
- **`usage` is optional and provisional.** It is the harness's own estimate. AD-11 replaces
  it with the Gateway's settled spend when `/spend/logs/v2` answers, so `None` here is an
  ordinary outcome — a harness that printed no JSON at all — and never an error.
- **The process is the `ProcessRunner`'s (AD-14).** An adapter starts nothing itself, so
  every harness process gets its own process group and its own deadline from the one place
  that can kill it. `pgid` is on the result for the record; AD-14 wants it stored *before*
  the process is awaited, which `run` — one call that starts and waits — could not give.
  5.4 closed that seam by splitting the call in two: `start` hands back a `HarnessHandle`
  carrying the `pgid`, the caller commits it, and `wait` blocks on the handle. `run` stays
  on the port and is exactly `wait(start(...))`, so nothing that only dispatches has to
  know the halves exist.

`HarnessEnv` is the other seam this port names: the callable that builds one attempt's
environment. It is declared here, in `domain/`, because `application/steps/agent.py` hands
the harness "exactly what the environment builder returned" (AD-5, AD-10) and may not
import the builder itself — `infrastructure/harness/env.py` takes `Settings`. The
composition root binds those and passes the closure down as a port.

`resume_command` is the operator's escape hatch (FR-21): a line to paste into a terminal,
not a command this system runs. The read model prefixes it with the container's own `docker
compose exec`, which is why it returns text and not an argv.

`TerminalEnv` is the other half of that escape hatch, and it is a *separate* port from
`HarnessEnv` for one reason: AD-5. `HarnessEnv` returns the real environment, credentials
included, and hands it straight to a child process that nobody reads. What the read model
publishes is a command *string* on a screen, so it may carry identifiers and nothing else —
the credentials are named there and resolved inside the container. Two ports rather than one
filtered result: a filter can be forgotten, whereas a builder that was never given a secret
cannot leak one, and `TerminalEnvironment` is what that builder returns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run


@dataclass(frozen=True)
class HarnessUsage:
    """What one attempt cost, as the harness itself reported it (AD-11).

    Provisional by nature: `Gateway.spend_for_attempt` replaces these three numbers with the
    Gateway's own once the spend log holds the attempt's rows.
    """

    tokens_in: int
    tokens_out: int
    #: USD. A `Decimal` because money is never a float in this system.
    cost_usd: Decimal


@dataclass(frozen=True)
class HarnessCapabilities:
    """What a harness can do, declared by the adapter and asked by the caller.

    Every field defaults to `False`: a capability is claimed, never acquired by omission.
    """

    #: The caller may choose the session id before the process starts.
    preassign_session: bool = False
    #: A finished session can be continued with a further message.
    resume: bool = False
    #: The harness exports its own OTLP spans and parents them under `TRACEPARENT` (AD-11).
    native_tracing: bool = False


@dataclass(frozen=True)
class HarnessResult:
    """What one dispatch produced. Nothing here is interpreted by the adapter (AD-10)."""

    #: The session this attempt ran under — pre-assigned when the harness allows it, so the
    #: value is known even when the harness printed nothing.
    #:
    #: `None` is the answer of a harness that names its own session and then did not print it:
    #: `capabilities.preassign_session = False` means the caller's id was never used, so an
    #: output with no session event leaves the attempt with none at all. `Attempt.session_id`
    #: is `str | None` for the same reason, and `agent_tail.finish` writes this straight onto
    #: it — the absence is recorded as an absence rather than as an empty string a later
    #: `resume` would try to continue.
    session_id: str | None
    #: `None` only when the process was killed before it could report one (AD-14).
    exit_code: int | None
    #: Where stdout and stderr went. The prompt is beside it, at `{log_path}.prompt`.
    log_path: Path
    #: The harness's own figures, or `None` when it printed none this system could read.
    usage: HarnessUsage | None = None
    #: True when the `ProcessRunner`'s deadline expired and it killed the group.
    timed_out: bool = False
    #: The process group the harness ran in, for the record and for a later `kill_group`.
    pgid: int | None = None
    #: The harness's JSON result object, verbatim. 5.7 reads the budget-cap field out of it;
    #: this port names no field of it at all.
    raw_result: dict[str, Any] | None = None


@dataclass(frozen=True)
class HarnessHandle:
    """A harness process that has started and not yet been awaited (AD-14).

    `pid` and `pgid` both, because `ProcessRunner.wait` takes a `Handle(pid, pgid)` and an
    adapter must be able to rebuild one without holding an opaque object of its own.
    `session_id` and `log_path` travel with it so `wait` needs no second copy of what
    `start` was told.
    """

    session_id: str
    log_path: Path
    pid: int
    pgid: int
    #: The directory the dispatch ran in, for an adapter whose `wait` needs it.
    #:
    #: Defaulted, because only one harness does: `local` names no session on the command line
    #: and may have to ask OpenCode's own session store which session was opened in this
    #: worktree (7.3). `start` is the half that was told the path and `wait` is the half that
    #: reads, so without this the lookup would have to accept any session on the host — or the
    #: adapter would have to keep state between the two halves, which is exactly what handing
    #: a handle back exists to avoid.
    cwd: Path | None = None


@runtime_checkable
class HarnessEnv(Protocol):
    """Builds the environment one attempt's harness process receives, and nothing else."""

    def __call__(  # noqa: PLR0913 — one argument per fact; AD-5 fixes the list
        self,
        attempt: Attempt,
        *,
        run: Run,
        project_slug: str,
        project_env: Mapping[str, str],
        log_content: bool,
        story_id: str | None,
        traceparent: str,
    ) -> dict[str, str]:
        """Exactly `HARNESS_ENV_CONTRACT`, the harness's aliases, and the Project's own."""
        ...


@dataclass(frozen=True)
class TerminalEnvironment:
    """What one attempt's paste-able resume command may state (AD-5, FR-21).

    Two ordered lists rather than two mappings, because both are rendered into a shell line
    and the order is the line: `identifiers` is the `-e NAME=value` list, in
    `HARNESS_ENV_CONTRACT`'s own order, and `exports` is the harness's own
    `HARNESS_ENV_ALIASES`, in the order that array declares them.

    **Neither list ever holds a secret value.** `identifiers` carries this attempt's own ids —
    the Run, the Attempt, the Story, the harness, the Project, the tags and the traceparent —
    and `exports` carries alias names against *shell references* (`$LITELLM_API_KEY`), which
    the container resolves from its own environment when the Operator pastes the line.
    `GITHUB_TOKEN` is in neither, as it is in no harness environment at all.
    """

    identifiers: tuple[tuple[str, str], ...]
    exports: tuple[tuple[str, str], ...]


@runtime_checkable
class TerminalEnv(Protocol):
    """Builds the identifiers and alias exports one attempt's terminal command carries."""

    def __call__(
        self,
        attempt: Attempt,
        *,
        run: Run,
        project_slug: str,
        story_id: str | None,
        traceparent: str,
    ) -> TerminalEnvironment:
        """Identifiers by value, every other contract name by shell reference (AD-5)."""
        ...


@runtime_checkable
class Harness(Protocol):
    """One coding-agent harness: dispatch, resume, and the line an operator can paste."""

    #: The registry key and the `attempt.harness` value: `claude`, `codex` or `local`.
    name: str
    capabilities: HarnessCapabilities

    def run(  # noqa: PLR0913 — AD-10 fixes this argument list; a bundle would hide it
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        model: str | None,
        session_id: str,
        budget_usd_remaining: Decimal,
        timeout_min: float,
        log_path: Path,
    ) -> HarnessResult:
        """Dispatch `prompt` in `cwd`, with exactly `env` and nothing of this process's own.

        `env` is what `infrastructure/harness/env.py` built (AD-5): the adapter adds no
        name to it and reads no credential of its own. `model` is `None` when the Template
        bound none, and the harness's configured default then decides.

        Exactly `wait(start(...))`: a caller with nothing to do between the two halves
        calls this and never sees a handle.
        """
        ...

    def start(  # noqa: PLR0913 — the same list `run` takes, for the same reason
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        model: str | None,
        session_id: str,
        budget_usd_remaining: Decimal,
        timeout_min: float,
        log_path: Path,
    ) -> HarnessHandle:
        """Start the dispatch and hand back its handle, without waiting for it.

        The half AD-14 needs: `attempt.pgid` is stored from this handle, in its own unit of
        work, before `wait` blocks — so a backend killed mid-attempt knows which process
        group to reap.
        """
        ...

    def wait(self, handle: HarnessHandle) -> HarnessResult:
        """Block until the process `start` returned ends, and read its log.

        The group is killed if this raises: the handle is the only thing that knows the
        `pgid`, so an exception escaping here without a kill is the orphan AD-14 forbids.
        """
        ...

    def resume(  # noqa: PLR0913 — AD-10 fixes this argument list too
        self,
        *,
        cwd: Path,
        session_id: str,
        message: str,
        env: Mapping[str, str],
        timeout_min: float,
        log_path: Path,
    ) -> HarnessResult:
        """Continue `session_id` with `message`. Only `retry` on the same row uses this, and
        no row ever resumes another row's session (AD-10)."""
        ...

    def resume_command(self, cwd: str, session_id: str) -> str | None:
        """The shell line an operator can paste to take the session over by hand (FR-21).

        `None` is the answer of a harness that has no resume form at all — `local`, whose
        `capabilities.resume` is `False` (7.3). The read model already hides the terminal
        block for such a harness, so this is belt and braces rather than a second rule: a
        plausible-looking line for a session that cannot be continued would be worse than
        no line, and an adapter should be able to say so in the return value.
        """
        ...
