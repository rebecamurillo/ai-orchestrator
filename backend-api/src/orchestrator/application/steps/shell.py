"""The `shell` kind: one command, in the worktree, under its own timeout (AD-9, AD-14, FR-10).

**What a non-zero exit means is the row's own `on_fail`, read verbatim.** The planner
already resolved it (`application/templates/rows.py::_routing`) into exactly the four forms
`domain.values.Redispatch` and this module both speak: the plain words `fail` / `continue`,
absent (the DSL default, `escalate`), or `{target_seq, max}` — which is `Redispatch`'s own
field names, so `Redispatch(**action)` builds it directly, with nothing to translate.

**A timeout and a non-zero exit are different failures.** `ProcessRunner.wait` already
decided the process ran past `with_resolved["timeout_min"]`; that is always `error` with
park `timeout`, whatever `on_fail` says — `on_fail` is what a *command* decided, and a
command that never got to decide anything is not the case it describes.

**The command's own output is never read here.** `output_ref` is the log path
`ProcessRunner` was told to write to, not its contents; a shell command that failed is
reported by its exit code and that path, the same way a real Operator would open the log.

**Project environment variables are not wired in yet.** AD-5's `HARNESS_ENV_CONTRACT` names
them for the `agent` kind (Epic 5); nothing in this epic decrypts a Project's own vars for a
`shell` row, and `StepContext` carries no field that could without storing the plaintext in
`step_run.with_resolved` — a stored, API-read column (AD-5 forbids that). `env={}` is the
honest value until that plumbing exists; `ProcessRunner` still adds `PATH`/`HOME`/`LANG`/
`TERM`/`GIT_TERMINAL_PROMPT` underneath it.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.registry import register
from orchestrator.application.templates.plan_model import (
    ON_FAIL_KEY,
    REDISPATCH_MAX,
    REDISPATCH_TARGET_SEQ,
)
from orchestrator.application.templates.rows import COMMAND_KEY, TIMEOUT_KEY
from orchestrator.domain.values import Park, Redispatch, StepResult

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "shell"

#: `KIND_META["shell"].timeout_default_min` — the row always carries its own, but a default
#: costs nothing and needs no import back into the package that is still being built.
DEFAULT_TIMEOUT_MIN = 30

#: The `on_fail` words the planner leaves as plain strings (AD-9).
FAIL = "fail"
CONTINUE = "continue"

#: The reasons a non-zero exit or a timeout leaves, each read by the AC that names it.
EXIT_WITH_PATH = "{path} exit {code}"
EXIT_ONLY = "exit {code}"
EXIT_CONTINUED = "exit {code} (continued)"
TIMED_OUT = "timeout {path} after {n} min"

#: What `StepPorts.process` being unset means: a composition-root wiring bug, not a row's.
NO_RUNNER = "StepPorts.process is not set: shell needs a ProcessRunner"


class ShellExecutor:
    """Run the row's command; route a non-zero exit by the row's own `on_fail`."""

    def execute(self, ctx: StepContext) -> StepResult:
        resolved = ctx.with_resolved
        command = str(resolved.get(COMMAND_KEY, ""))
        timeout_min = resolved.get(TIMEOUT_KEY, DEFAULT_TIMEOUT_MIN)
        log = log_path(ctx)
        process = ctx.ports.process
        if process is None:
            raise RuntimeError(NO_RUNNER)
        cwd = Path(ctx.cwd) if ctx.cwd is not None else None
        handle = process.start(command, cwd=cwd, env={}, timeout_min=timeout_min, log_path=log)
        outcome = process.wait(handle)
        if outcome.timed_out:
            reason = TIMED_OUT.format(path=ctx.row.path, n=timeout_min)
            return StepResult(
                status="error",
                gate=ctx.row.gate,
                output_ref=str(log),
                log_path=str(log),
                reason=reason,
                park=Park(kind="timeout", reason=reason, path=ctx.row.path),
            )
        if outcome.exit_code == 0:
            return StepResult(
                status="done", gate=ctx.row.gate, output_ref=str(log), log_path=str(log)
            )
        return _on_fail(ctx, resolved.get(ON_FAIL_KEY), outcome.exit_code, log)


def _on_fail(ctx: StepContext, action: object, exit_code: int | None, log: Path) -> StepResult:
    """The row's own routing for a non-zero exit — `fail | continue | escalate | redispatch`."""
    if action == FAIL:
        return StepResult(
            status="error",
            gate=ctx.row.gate,
            output_ref=str(log),
            log_path=str(log),
            reason=EXIT_WITH_PATH.format(path=ctx.row.path, code=exit_code),
        )
    if action == CONTINUE:
        return StepResult(
            status="done",
            gate=ctx.row.gate,
            output_ref=str(log),
            log_path=str(log),
            reason=EXIT_CONTINUED.format(code=exit_code),
        )
    if isinstance(action, dict):
        return StepResult(
            status="error",
            gate=ctx.row.gate,
            output_ref=str(log),
            log_path=str(log),
            reason=EXIT_ONLY.format(code=exit_code),
            redispatch=Redispatch(
                target_seq=action[REDISPATCH_TARGET_SEQ], max=action[REDISPATCH_MAX]
            ),
        )
    # `escalate`, the DSL default an absent `on_fail` key means (AD-9).
    reason = EXIT_WITH_PATH.format(path=ctx.row.path, code=exit_code)
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=str(log),
        log_path=str(log),
        reason=reason,
        park=Park(kind="verify_failed", reason=reason, path=ctx.row.path),
    )


register(KIND, ShellExecutor())
