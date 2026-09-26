"""In-memory `Harness` — the one fake for that port (AD-18). Reuse it; do not write another.

Results are scripted as a *list consumed in order* rather than keyed by command, which is
where this differs from `fakes/process.py`: an agent row's second attempt is the same
dispatch as its first with a different answer, so "the first call blocks, the second one
finishes" is the shape 5.4 and 5.5 need, and a key built from the prompt would make every
test restate the prompt it does not care about.

Every call is recorded whole — `prompt`, `env`, `cwd`, `model`, `session_id` and
`budget_usd_remaining` — because AD-5 is a rule about what reached the harness, and only a
call log can settle "the executor passed the environment it built" in a unit test.

`start` and `wait` are the port's two halves (5.4), recorded under their own names. Two
call logs compared afterwards cannot tell "committed between them" from "committed after
both", so `on_wait` is the hook that can: it runs as the first statement of `wait`, while
the process is conceptually still running, and a test that snapshots
`FakeAttemptRepository.calls` from inside it is reading the world at exactly the instant
AD-14 legislates about. `run` records one `"run"` call and answers the next
scripted result directly rather than delegating to the pair: `tests/unit/test_harness_port.py`
is frozen and asserts that one dispatch leaves exactly one entry in `calls`. Both paths
consume the same script, so a test that scripts one result gets it whichever it calls.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.harness import (
    HarnessCapabilities,
    HarnessHandle,
    HarnessResult,
    ProbeResult,
)

#: The claude adapter's own capabilities: the default, so a test about an executor need not
#: restate them.
DEFAULT_CAPABILITIES = HarnessCapabilities(preassign_session=True, resume=True, native_tracing=True)

#: The process group `start` reports when a test names none. A number no real group would
#: have, so an assertion on it cannot pass by coincidence.
DEFAULT_PGID = 4242
#: The pid `start` reports; `ProcessRunner.Handle` carries both and nothing here forks.
DEFAULT_PID = 4241


class FakeHarness:
    """Scripted results in order, a call log, and no process at all."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        name: str = "claude",
        capabilities: HarnessCapabilities = DEFAULT_CAPABILITIES,
        results: list[HarnessResult] | None = None,
        pgid: int = DEFAULT_PGID,
        on_wait: Callable[[], None] | None = None,
        on_resume: Callable[[], None] | None = None,
        probe_results: list[ProbeResult] | None = None,
        skills_dir: Path | None = None,
    ) -> None:
        self.name = name
        self.capabilities = capabilities
        #: `None` by default: a test about dispatch renders no workflow snapshot, and one
        #: about `agent_render` names the directory it expects in the command.
        self.skills_dir = skills_dir
        self.results = list(results or [])
        self.pgid = pgid
        self.on_wait = on_wait
        #: `resume`'s own `on_wait`: a session-mode dispatch never calls `wait`, so a test
        #: that has to simulate what the resumed agent itself would have written back
        #: (`agent_tail.finish` routes on a Story file no fake process here can produce)
        #: needs a hook on `resume` directly, run before its own call is recorded.
        self.on_resume = on_resume
        self.calls: list[dict[str, Any]] = []
        self._probe_queue: list[ProbeResult] = list(probe_results or [])

    def run(  # noqa: PLR0913 — the port's own signature
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        model: str | None,
        session_id: str,
        budget_usd_remaining: Decimal,
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
    ) -> HarnessResult:
        self.calls.append(
            {
                "method": "run",
                "cwd": cwd,
                "prompt": prompt,
                "env": dict(env),
                "model": model,
                "session_id": session_id,
                "budget_usd_remaining": budget_usd_remaining,
                "timeout_min": timeout_min,
                "stall_min": stall_min,
                "log_path": log_path,
            }
        )
        return self._next(session_id, log_path)

    def start(  # noqa: PLR0913 — the port's own signature
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        model: str | None,
        session_id: str,
        budget_usd_remaining: Decimal,
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
    ) -> HarnessHandle:
        self.calls.append(
            {
                "method": "start",
                "cwd": cwd,
                "prompt": prompt,
                "env": dict(env),
                "model": model,
                "session_id": session_id,
                "budget_usd_remaining": budget_usd_remaining,
                "timeout_min": timeout_min,
                "stall_min": stall_min,
                "log_path": log_path,
            }
        )
        return HarnessHandle(
            session_id=session_id, log_path=log_path, pid=DEFAULT_PID, pgid=self.pgid
        )

    def wait(self, handle: HarnessHandle) -> HarnessResult:
        # first, before anything else this method does: the hook observes the world as it
        # stood when the caller began to block on the process
        if self.on_wait is not None:
            self.on_wait()
        self.calls.append({"method": "wait", "pgid": handle.pgid})
        return self._next(handle.session_id, handle.log_path)

    def resume(  # noqa: PLR0913 — the port's own signature
        self,
        *,
        cwd: Path,
        session_id: str,
        message: str,
        env: Mapping[str, str],
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
    ) -> HarnessResult:
        if self.on_resume is not None:
            self.on_resume()
        self.calls.append(
            {
                "method": "resume",
                "cwd": cwd,
                "session_id": session_id,
                "message": message,
                "env": dict(env),
                "timeout_min": timeout_min,
                "stall_min": stall_min,
                "log_path": log_path,
            }
        )
        return self._next(session_id, log_path)

    def resume_command(self, cwd: str, session_id: str) -> str:
        return f"cd {cwd} && {self.name} --resume {session_id}"

    def probe(self) -> ProbeResult:
        """Pop and return the next scripted ProbeResult; raise AssertionError on empty queue."""
        if not self._probe_queue:
            raise AssertionError("probe queue empty")
        return self._probe_queue.pop(0)

    def called(self, method: str) -> list[dict[str, Any]]:
        """Every call to one method, in order — `FakeProcessRunner.called`'s own shape."""
        return [call for call in self.calls if call["method"] == method]

    def _next(self, session_id: str, log_path: Path) -> HarnessResult:
        """The next scripted result, or a clean exit with nothing parsed from the log."""
        if self.results:
            return self.results.pop(0)
        return HarnessResult(session_id=session_id, exit_code=0, log_path=log_path)
