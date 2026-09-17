"""In-memory `ProcessRunner` — the one fake for that port (AD-18). Reuse it; do not write
another.

Outcomes are scripted **per command**, keyed by the exact `cmd` a caller starts, because a
`shell` row is testing what it does with an exit code and a timeout, not what a real process
would print. A command not in the script answers with `default`, so a test that only cares
about one row's command need not script every other one it never asks about.

Every call is recorded — `start`'s arguments and `kill_group`'s — for the same reason
`FakeGit.calls` exists: "the redispatch row's command ran with this `cwd`" is a rule only a
call log can settle.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.process import Handle, Outcome

#: What an unscripted `start` answers with: a clean exit, no timeout, no stall.
DEFAULT_OUTCOME = Outcome(exit_code=0, timed_out=False, stalled=False)


class FakeProcessRunner:
    """Scripted outcomes by command, a call log, and process groups that never really run."""

    def __init__(
        self,
        *,
        outcomes: Mapping[str, Outcome] | None = None,
        default: Outcome = DEFAULT_OUTCOME,
    ) -> None:
        self._outcomes = dict(outcomes or {})
        self._default = default
        self.calls: list[dict[str, Any]] = []
        self._pending: dict[int, Outcome] = {}
        self._next_pgid = 1

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
        self.calls.append(
            {
                "method": "start",
                "cmd": cmd,
                "cwd": cwd,
                "env": dict(env),
                "timeout_min": timeout_min,
                "stall_min": stall_min,
                "log_path": log_path,
            }
        )
        pgid = self._next_pgid
        self._next_pgid += 1
        key = cmd if isinstance(cmd, str) else " ".join(cmd)
        self._pending[pgid] = self._outcomes.get(key, self._default)
        return Handle(pid=pgid, pgid=pgid)

    def wait(self, handle: Handle) -> Outcome:
        self.calls.append({"method": "wait", "pgid": handle.pgid})
        return self._pending.pop(handle.pgid, self._default)

    def kill_group(self, pgid: int) -> None:
        self.calls.append({"method": "kill_group", "pgid": pgid})

    def called(self, method: str) -> list[dict[str, Any]]:
        """Every call to one method, in order — `FakeGit.called`'s own shape."""
        return [call for call in self.calls if call["method"] == method]
