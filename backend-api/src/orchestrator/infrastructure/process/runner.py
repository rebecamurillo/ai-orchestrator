"""`RealProcessRunner`: `subprocess.Popen` in its own session, timed and signalled (AD-14).

**Why the process group rather than the pid.** `start_new_session=True` makes the child a
new session leader, which on POSIX makes it a new process-group leader too — `pgid ==
pid`. A shell command that forks a compiler and a linker leaves both inside that group, so
`os.killpg` reaches all of them with the one signal a pid alone could not guarantee to.

**Why `wait` and `kill_group` share one sequence.** `wait`'s own expiry — `SIGTERM`, ten
seconds, `SIGKILL` — is exactly `kill_group`'s body, called on the same `pgid` and then
reaped so the exit code the process actually left is the one the `Outcome` reports. Writing
the escalation twice would be the two places this system already knows not to trust: one
that changed and one that was forgotten.

**Why the runner never inherits its own environment.** `_child_env` starts from the
caller's mapping and adds exactly five names read from *this* process's own environment —
`PATH`, `HOME`, `LANG`, plus the fixed `TERM=dumb` and `GIT_TERMINAL_PROMPT=0` — and nothing
else the orchestrator holds (a database URL, a gateway key, `GITHUB_TOKEN`) ever reaches a
child this way.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from orchestrator.domain.ports.process import Handle, Outcome

#: Seconds a group is given to leave on its own after `SIGTERM`, before `SIGKILL` (AD-14).
GRACE_SECONDS = 10.0
#: How often `kill_group` checks whether the group has gone, while it waits out the grace.
POLL_SECONDS = 0.1
#: The two names the runner sets itself rather than reading from its own environment.
_TERM = "dumb"
_GIT_TERMINAL_PROMPT = "0"
#: What this process falls back to when its own environment carries none of the three
#: names a child needs to do anything at all.
_DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_DEFAULT_HOME = "/root"
_DEFAULT_LANG = "C.UTF-8"


class RealProcessRunner:
    """One process group per `start`, tracked until `wait` reaps it."""

    def __init__(self) -> None:
        self._running: dict[int, tuple[subprocess.Popen[bytes], float]] = {}

    def start(
        self,
        cmd: Sequence[str] | str,
        *,
        cwd: Path | None,
        env: Mapping[str, str],
        timeout_min: float,
        log_path: Path,
    ) -> Handle:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log_file:
            popen = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd is not None else None,
                env=_child_env(env),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                shell=isinstance(cmd, str),
            )
        pgid = os.getpgid(popen.pid)
        self._running[pgid] = (popen, timeout_min * 60)
        return Handle(pid=popen.pid, pgid=pgid)

    def wait(self, handle: Handle) -> Outcome:
        entry = self._running.pop(handle.pgid, None)
        if entry is None:
            return Outcome(exit_code=None, timed_out=False)
        popen, timeout_seconds = entry
        try:
            popen.wait(timeout=timeout_seconds)
            return Outcome(exit_code=popen.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            self.kill_group(handle.pgid)
            popen.wait()
            return Outcome(exit_code=popen.returncode, timed_out=True)

    def kill_group(self, pgid: int) -> None:
        if not _signal_group(pgid, signal.SIGTERM):
            return
        deadline = time.monotonic() + GRACE_SECONDS
        while time.monotonic() < deadline:
            if not _group_alive(pgid):
                return
            time.sleep(POLL_SECONDS)
        _signal_group(pgid, signal.SIGKILL)


def _child_env(caller_env: Mapping[str, str]) -> dict[str, str]:
    """The caller's own variables, plus the five names never read from `os.environ` beyond."""
    return {
        **caller_env,
        "PATH": os.environ.get("PATH") or _DEFAULT_PATH,
        "HOME": os.environ.get("HOME") or _DEFAULT_HOME,
        "LANG": os.environ.get("LANG") or _DEFAULT_LANG,
        "TERM": _TERM,
        "GIT_TERMINAL_PROMPT": _GIT_TERMINAL_PROMPT,
    }


def _signal_group(pgid: int, sig: int) -> bool:
    """Send `sig` to the group, or say it was already gone rather than raise (AD-13).

    Any `OSError` here means there is nothing left to signal: `ProcessLookupError` is a
    group fully reaped, and `PermissionError` is the same fact seen through a BSD `kill()`'s
    own quirk — a group that is a zombie, signalled but not yet reaped by `Popen.wait()`,
    answers signal `0` with `EPERM` rather than `ESRCH` on Darwin.
    """
    try:
        os.killpg(pgid, sig)
    except OSError:
        return False
    return True


def _group_alive(pgid: int) -> bool:
    """Whether any process of the group still answers — signal `0` probes without killing."""
    return _signal_group(pgid, 0)
