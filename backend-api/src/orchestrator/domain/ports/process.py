"""The `ProcessRunner` port (AD-14, FR-10): every command a Run executes, timed and grouped.

Three rules make this the one place a hung command can be stopped:

- **Every process gets its own session and process group.** `start` is the only way one is
  created, so `kill_group` can always reach the whole tree a command spawned — a shell that
  forked a compiler, that forked a linker — with one signal to the group rather than one to
  a pid that may not be the one still running.
- **The runner owns the deadline, never the engine (AD-6).** `wait` enforces `timeout_min`
  itself: the engine never times a step, because a wall-clock wait inside a durable step
  would be exactly the branching-outside-a-step AD-6 forbids.
- **`kill_group` is idempotent.** A group that is already gone is not an error — cancelling
  a Run and a timeout racing each other must both be able to call it and both get back
  cleanly (AD-13).

`Handle` carries only what identifies the process to a later call — `pid` for the record,
`pgid` for every signal — never the operating-system object itself, so nothing outside
`infrastructure/process/` holds a `subprocess.Popen`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Handle:
    """What `start` hands back: enough to wait on the process or to kill its group."""

    pid: int
    pgid: int


@dataclass(frozen=True)
class Outcome:
    """What `wait` hands back: the exit code, or that the deadline is why there is none."""

    #: `None` only when the process was killed before it could report one.
    exit_code: int | None
    #: True when `timeout_min` expired and the runner killed the group itself.
    timed_out: bool
    #: True when the stall detector found no filesystem activity for `stall_min` minutes.
    stalled: bool = False


@runtime_checkable
class ProcessRunner(Protocol):
    """Runs one command, in its own process group, under an activity-based stall detector."""

    def start(  # noqa: PLR0913 — the port's own signature
        self,
        cmd: Sequence[str] | str,
        *,
        cwd: Path | None,
        env: Mapping[str, str],
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
    ) -> Handle:
        """Start `cmd` in its own session, stdout and stderr appended to `log_path`.

        `env` is exactly what the caller passes, plus the runner's own `PATH`, `HOME`,
        `LANG`, `TERM` and `GIT_TERMINAL_PROMPT` — the orchestrator's own environment is
        never inherited beyond those five names.

        `timeout_min=None` means no wall-clock deadline; the process runs until it exits
        naturally or `stall_min` fires.  `stall_min=None` means no stall detection.
        """
        ...

    def wait(self, handle: Handle) -> Outcome:
        """Block until the process ends, `timeout_min` expires, or a stall is detected.

        On wall-clock expiry: `SIGTERM` to the group, ten seconds to leave on its own,
        then `SIGKILL` — outcome has `timed_out=True`.  On stall: same kill sequence —
        outcome has `stalled=True`.  Both flags are mutually exclusive.
        """
        ...

    def kill_group(self, pgid: int) -> None:
        """`SIGTERM`, ten seconds, `SIGKILL` — the same sequence `wait` uses on expiry.

        A group that is already gone is not a failure: this returns cleanly either way,
        which is what lets `cancel` and a timeout race each other safely (AD-13).
        """
        ...
