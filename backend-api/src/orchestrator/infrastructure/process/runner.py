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
#: How long each iteration of the stall-detection loop waits on the process (FR-10).
_POLL_SECONDS = 10.0
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
    """One process this process forked, the deadline `wait` holds it to, and stall config."""

    popen: subprocess.Popen[bytes]
    timeout_seconds: float | None
    #: The working directory monitored for filesystem activity; `None` disables stall checks.
    cwd: Path | None
    #: The log file whose size is checked as an additional activity signal.
    log_path: Path
    #: Seconds of inactivity before the stall detector fires; `None` disables stall checks.
    stall_min_s: float | None


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
        _remember(
            pgid,
            _Child(
                popen=popen,
                timeout_seconds=timeout_min * 60 if timeout_min is not None else None,
                cwd=cwd,
                log_path=log_path,
                stall_min_s=stall_min * 60 if stall_min is not None else None,
            ),
        )
        return Handle(pid=popen.pid, pgid=pgid)

    def wait(self, handle: Handle) -> Outcome:  # noqa: PLR0911 — stall path adds returns
        child = _child_of(handle.pgid)
        if child is None:
            return Outcome(exit_code=None, timed_out=False, stalled=False)
        popen = child.popen
        try:
            if child.stall_min_s is None:
                # No stall detection — simple wait with optional wall-clock deadline.
                if child.timeout_seconds is None:
                    popen.wait()
                    return Outcome(exit_code=popen.returncode, timed_out=False, stalled=False)
                try:
                    popen.wait(timeout=child.timeout_seconds)
                    return Outcome(exit_code=popen.returncode, timed_out=False, stalled=False)
                except subprocess.TimeoutExpired:
                    self.kill_group(handle.pgid)
                    popen.wait()
                    return Outcome(exit_code=popen.returncode, timed_out=True, stalled=False)
            # Stall detection: poll every ~10 s, watching mtime and log growth.
            deadline = (
                time.monotonic() + child.timeout_seconds
                if child.timeout_seconds is not None
                else None
            )
            last_activity = time.monotonic()
            last_mtime = _max_mtime(child.cwd)
            last_log_size = _log_size(child.log_path)
            while True:
                try:
                    popen.wait(timeout=_POLL_SECONDS)
                    # Natural exit.
                    return Outcome(exit_code=popen.returncode, timed_out=False, stalled=False)
                except subprocess.TimeoutExpired:
                    pass
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    self.kill_group(handle.pgid)
                    popen.wait()
                    return Outcome(exit_code=popen.returncode, timed_out=True, stalled=False)
                current_mtime = _max_mtime(child.cwd)
                current_log_size = _log_size(child.log_path)
                if current_mtime != last_mtime or current_log_size != last_log_size:
                    last_activity = now
                    last_mtime = current_mtime
                    last_log_size = current_log_size
                elif now - last_activity >= child.stall_min_s:
                    self.kill_group(handle.pgid)
                    popen.wait()
                    return Outcome(exit_code=None, timed_out=False, stalled=True)
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


def _max_mtime(cwd: Path | None) -> float:
    """The highest mtime of any file under `cwd` (including `.git`), or `0.0` if empty/None.

    Used by the stall-detection loop to detect that something in the worktree has changed.
    A git commit updates `.git/index` and `.git/COMMIT_EDITMSG`, so any commit counts as
    activity.  Symlinks are not followed to avoid loops; `OSError` on any entry is skipped.
    """
    if cwd is None:
        return 0.0
    best = 0.0
    for dirpath, _dirs, filenames in os.walk(str(cwd)):
        for fname in filenames:
            try:
                t = os.path.getmtime(os.path.join(dirpath, fname))
                best = max(best, t)
            except OSError:
                pass
    return best


def _log_size(log_path: Path) -> int:
    """The current byte size of `log_path`, or `0` when the file does not exist yet."""
    try:
        return log_path.stat().st_size
    except OSError:
        return 0
