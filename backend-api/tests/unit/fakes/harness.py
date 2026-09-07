"""In-memory `Harness` — the one fake for that port (AD-18). Reuse it; do not write another.

Results are scripted as a *list consumed in order* rather than keyed by command, which is
where this differs from `fakes/process.py`: an agent row's second attempt is the same
dispatch as its first with a different answer, so "the first call blocks, the second one
finishes" is the shape 5.4 and 5.5 need, and a key built from the prompt would make every
test restate the prompt it does not care about.

Every call is recorded whole — `prompt`, `env`, `cwd`, `model`, `session_id` and
`budget_usd_remaining` — because AD-5 is a rule about what reached the harness, and only a
call log can settle "the executor passed the environment it built" in a unit test.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.harness import HarnessCapabilities, HarnessResult

#: The claude adapter's own capabilities: the default, so a test about an executor need not
#: restate them.
DEFAULT_CAPABILITIES = HarnessCapabilities(preassign_session=True, resume=True, native_tracing=True)


class FakeHarness:
    """Scripted results in order, a call log, and no process at all."""

    def __init__(
        self,
        *,
        name: str = "claude",
        capabilities: HarnessCapabilities = DEFAULT_CAPABILITIES,
        results: list[HarnessResult] | None = None,
    ) -> None:
        self.name = name
        self.capabilities = capabilities
        self.results = list(results or [])
        self.calls: list[dict[str, Any]] = []

    def run(  # noqa: PLR0913 — the port's own signature
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
                "log_path": log_path,
            }
        )
        return self._next(session_id, log_path)

    def resume(  # noqa: PLR0913 — the port's own signature
        self,
        *,
        cwd: Path,
        session_id: str,
        message: str,
        env: Mapping[str, str],
        timeout_min: float,
        log_path: Path,
    ) -> HarnessResult:
        self.calls.append(
            {
                "method": "resume",
                "cwd": cwd,
                "session_id": session_id,
                "message": message,
                "env": dict(env),
                "timeout_min": timeout_min,
                "log_path": log_path,
            }
        )
        return self._next(session_id, log_path)

    def resume_command(self, cwd: str, session_id: str) -> str:
        return f"cd {cwd} && {self.name} --resume {session_id}"

    def called(self, method: str) -> list[dict[str, Any]]:
        """Every call to one method, in order — `FakeProcessRunner.called`'s own shape."""
        return [call for call in self.calls if call["method"] == method]

    def _next(self, session_id: str, log_path: Path) -> HarnessResult:
        """The next scripted result, or a clean exit with nothing parsed from the log."""
        if self.results:
            return self.results.pop(0)
        return HarnessResult(session_id=session_id, exit_code=0, log_path=log_path)
