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

**Why the escalation reaps before it looks.** A dead child is not gone: until its parent
collects its exit status it is a zombie, and a zombie is still a member of its process
group, so `os.killpg(pgid, 0)` answers for it. On Linux it answers *successfully* — a
group that left the instant it was asked to still reads as alive, and the grace would be
waited out in full before `SIGKILL` reached a corpse. Only this process can collect that
status, because only this process forked it. So the probe reaps first, through `_CHILDREN`,
and the group's answer means what it says on both platforms.

**Why the runner never inherits its own environment.** `_child_env` starts from the
caller's mapping and adds exactly five names read from *this* process's own environment —
`PATH`, `HOME`, `LANG`, plus the fixed `TERM=dumb` and `GIT_TERMINAL_PROMPT=0` — and nothing
else the orchestrator holds (a database URL, a gateway key, `GITHUB_TOKEN`) ever reaches a
child this way.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from orchestrator.domain.ports.process import Handle, Outcome

#: Seconds a group is given to leave on its own after `SIGTERM`, before `SIGKILL` (AD-14).
GRACE_SECONDS = 10.0
#: How often `kill_group` checks whether the group has gone, while it waits out the grace.
POLL_SECONDS = 0.1
#: How long a `SIGKILL`ed child is given to become reapable, so a `kill_group` that no
#: `wait` ever follows — `cancel`'s, AD-13 — leaves no zombie holding the group open.
#: Short on purpose: `SIGKILL` cannot be caught, so this is the kernel's own latency, and
#: `wait`'s deadline is already `timeout_min` plus the whole grace.
REAP_SECONDS = 0.5
#: The two names the runner sets itself rather than reading from its own environment.
_TERM = "dumb"
_GIT_TERMINAL_PROMPT = "0"
#: What this process falls back to when its own environment carries none of the three
#: names a child needs to do anything at all.
_DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_DEFAULT_HOME = "/root"
_DEFAULT_LANG = "C.UTF-8"


@dataclass(frozen=True)
class _Child:
    """One process this process forked, and the deadline `wait` holds it to."""

    popen: subprocess.Popen[bytes]
    timeout_seconds: float


#: Every child *this operating-system process* forked, by the process group it leads.
#:
#: Module-level rather than per-`RealProcessRunner`, because reaping is a property of the
#: process, not of an object: only the parent may `waitpid` a child, and the composition
#: root builds two runners — one for the walker, at start-up
#: (`infrastructure/dbos/startup.py`), and one per request for `cancel`
#: (`api/providers.py`, `signal_effect_ports`). They are the same process, so the one that
#: cancels can and must reap what the one that started is holding; a per-instance registry
#: would leave `cancel` blind and waiting out the grace on every kill.
_CHILDREN: dict[int, _Child] = {}
#: The walker's threads and the API's threadpool both reach `_CHILDREN`.
_CHILDREN_LOCK = threading.Lock()


class RealProcessRunner:
    """One process group per `start`, reaped by whichever call ends it."""

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
        _remember(pgid, _Child(popen=popen, timeout_seconds=timeout_min * 60))
        return Handle(pid=popen.pid, pgid=pgid)

    def wait(self, handle: Handle) -> Outcome:
        child = _child_of(handle.pgid)
        if child is None:
            return Outcome(exit_code=None, timed_out=False)
        popen = child.popen
        try:
            popen.wait(timeout=child.timeout_seconds)
            return Outcome(exit_code=popen.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            # the registry is still holding this child, so the escalation below can reap it
            self.kill_group(handle.pgid)
            popen.wait()
            return Outcome(exit_code=popen.returncode, timed_out=True)
        finally:
            _forget(handle.pgid)

    def kill_group(self, pgid: int) -> None:
        if not _signal_group(pgid, signal.SIGTERM):
            return
        if not _left_within_the_grace(pgid):
            _signal_group(pgid, signal.SIGKILL)
        # every path ends here, so no `kill_group` leaves a zombie of its own behind —
        # not the `SIGKILL` one, and not the Darwin one, where `EPERM` says "gone" of a
        # child this process has not collected yet
        _reap(pgid, timeout=REAP_SECONDS)


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


def _left_within_the_grace(pgid: int) -> bool:
    """Whether the group went on its own inside `GRACE_SECONDS`, polled while it had time."""
    deadline = time.monotonic() + GRACE_SECONDS
    while True:
        if not _group_alive(pgid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)


def _remember(pgid: int, child: _Child) -> None:
    with _CHILDREN_LOCK:
        _CHILDREN[pgid] = child


def _child_of(pgid: int) -> _Child | None:
    """The child this process forked into `pgid`, or `None` — a group started before a
    restart, or one nothing here ever started, is exactly the same fact to every caller."""
    with _CHILDREN_LOCK:
        return _CHILDREN.get(pgid)


def _forget(pgid: int) -> None:
    """Drop the registration. Only `wait` does: a `kill_group` that races a `wait` must
    leave the exit code there for it to report."""
    with _CHILDREN_LOCK:
        _CHILDREN.pop(pgid, None)


def _reap(pgid: int, *, timeout: float = 0.0) -> None:
    """Collect the exit status of the child this process forked into `pgid`, if it has one.

    `timeout=0` polls and returns either way; a positive one waits that long for a child
    that has just been `SIGKILL`ed to become reapable. A group this process did not start
    has nothing here to collect, and says so by doing nothing.
    """
    child = _child_of(pgid)
    if child is None:
        return
    if timeout <= 0:
        child.popen.poll()
        return
    with contextlib.suppress(subprocess.TimeoutExpired):
        child.popen.wait(timeout=timeout)


def _signal_group(pgid: int, sig: int) -> bool:
    """Send `sig` to the group, or say it was already gone rather than raise (AD-13).

    Any `OSError` here means there is nothing left for this process to signal:
    `ProcessLookupError` is a group with no members at all, and `PermissionError` is the
    same fact seen through a BSD `kill()`'s own quirk — on Darwin a zombie answers signal
    `0` with `EPERM` rather than `ESRCH`. Linux has no such quirk: there a zombie answers
    normally, and it is `_group_alive`'s reap, not this branch, that makes the answer true.
    """
    try:
        os.killpg(pgid, sig)
    except OSError:
        return False
    return True


def _group_alive(pgid: int) -> bool:
    """Whether any process of the group still answers — signal `0` probes without killing.

    Reaps first: a zombie is still a group member, so on Linux a group that has been killed
    but not collected answers this probe successfully. The reap is what makes "alive" mean
    alive on both platforms, and it is why a group that exits at once costs one poll rather
    than the whole of `GRACE_SECONDS`.
    """
    _reap(pgid)
    return _signal_group(pgid, 0)
