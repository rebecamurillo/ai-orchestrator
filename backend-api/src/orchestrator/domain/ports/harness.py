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
  the process is awaited, which `run` — one call that starts and waits — cannot give. That
  seam is 5.4's to close.

`resume_command` is the operator's escape hatch (FR-21): a line to paste into a terminal,
not a command this system runs. The read model prefixes it with the container's own `docker
compose exec`, which is why it returns text and not an argv.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


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
    session_id: str
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

    def resume_command(self, cwd: str, session_id: str) -> str:
        """The shell line an operator can paste to take the session over by hand (FR-21)."""
        ...
