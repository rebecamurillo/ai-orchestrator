"""`ClaudeHarness`: `claude -p` through the `ProcessRunner` port (AD-10, AD-14, FR-14).

The invocation is written once, here, and nowhere else:

    claude -p --session-id {uuid} [--add-dir {hub root}] --permission-mode dontAsk
           --allowedTools {CLAUDE_ALLOWED_TOOLS} --disallowedTools "mcp__*,Bash(git push*)"
           --output-format stream-json --verbose --max-budget-usd {remaining}
           [--model {model}] "{prompt}"

`--bare` is not used and cannot be: at 2.1.x it exposes exactly `Bash, Edit, Read` — no
`Task`, no `Write`, no `Skill` — and `bmad-build-auto` needs all three (addendum §B). The
container is the sandbox instead: `dontAsk` with an explicit allowlist, and `mcp__*` denied
because a container has no personal connectors and the exclusion should be stated rather
than assumed.

**Resume** (AD-10): `--resume {id}` replaces `--session-id`; every other flag is the
dispatch's, `--model` included — a resumed session not told its model runs on the default.

**Usage** is tolerant: the log is scanned for the last `"type": "result"` JSON object; fields
from `total_cost_usd`, `usage.input_tokens`, `usage.output_tokens`; missing → `None`. The
object travels as `raw_result` (AD-10 forbids deciding what other fields mean).

**Two halves** (AD-14): `start` → `HarnessHandle`; `wait` blocks and parses; `run` =
`wait(start(...))`. `resume` uses the same halves. Log parsing is in `result.py`.

**Static config** (AD-10): `ANTHROPIC_BASE_URL`, OTLP and `DISABLE_AUTOUPDATER` are set by
`scripts/harness/claude.sh configure`; adapter writes only the prompt file beside the log.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

from orchestrator.domain.ports.harness import HarnessCapabilities, HarnessHandle, HarnessResult
from orchestrator.domain.ports.process import Handle, ProcessRunner
from orchestrator.infrastructure.harness.claude.aliases import (
    SUBSCRIPTION_KEY_HEADER,
    claude_aliases,
    claude_native_aliases,
    claude_subscription_aliases,
)
from orchestrator.infrastructure.harness.claude.result import (
    ENCODING,
    RESULT_TYPE,
    RESULT_TYPE_FIELD,
    json_objects,
    read_text,
    result_object,
    usage_from,
)
from orchestrator.infrastructure.harness.probe import ProbeResult, run_probe_script
from orchestrator.infrastructure.settings import Settings

__all__ = [
    "ENCODING",
    "RESULT_TYPE",
    "RESULT_TYPE_FIELD",
    "SUBSCRIPTION_KEY_HEADER",
    "ClaudeHarness",
    "claude_aliases",
    "claude_native_aliases",
    "claude_subscription_aliases",
    "json_objects",
    "read_text",
    "render_budget",
    "result_object",
    "usage_from",
]

#: The executable the image installs at `CLAUDE_CODE_VERSION`.
EXECUTABLE = "claude"
#: The permission mode the container's own isolation makes safe (AD-10).
PERMISSION_MODE = "dontAsk"
#: A deny beats the allowlist's `Bash(git *)`: no personal MCP connectors in a container, and
#: an agent never pushes — `git.push` does, with a credential the harness is never handed.
DISALLOWED_TOOLS = "mcp__*,Bash(git push*)"
#: One JSON event per line, appended to the log as it happens: the runner's stall detector
#: reads log growth as liveness, and a killed attempt still leaves its transcript. Claude
#: Code refuses `stream-json` under `-p` without `--verbose`.
OUTPUT_FORMAT = "stream-json"
VERBOSE = "--verbose"
#: Variadic in Claude Code's own parser: `_argv` always follows its value with a flag.
ADD_DIR = "--add-dir"

#: The suffix the prompt is written under, beside the attempt's own log.
PROMPT_SUFFIX = ".prompt"

#: Cents. `--max-budget-usd` takes an amount, and the amount is rounded *down* to it.
BUDGET_PRECISION = Decimal("0.01")
#: What is passed when nothing remains: the CLI is never handed a negative amount.
NO_BUDGET = "0.00"


class ClaudeHarness:
    """Claude Code, headless, in the worktree, under the runner's own deadline."""

    name = "claude"
    capabilities = HarnessCapabilities(preassign_session=True, resume=True, native_tracing=True)

    def __init__(self, runner: ProcessRunner, settings: Settings) -> None:
        self.runner = runner
        self.settings = settings
        #: `scripts/harness/claude.sh` installs the stubs here — Claude Code reads
        #: `~/.claude/skills` and not `~/.agents/skills`.
        self.skills_dir = settings.agent_home / ".claude" / "skills"

    def run(  # noqa: PLR0913 — the port's own signature (AD-10)
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        model: str | None,
        session_id: str,
        budget_usd_remaining: Decimal | None,
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
        add_dirs: Sequence[Path] = (),
    ) -> HarnessResult:
        """First dispatch, start to finish: exactly `wait(start(...))` (AD-14)."""
        return self.wait(
            self.start(
                cwd=cwd,
                prompt=prompt,
                env=env,
                model=model,
                session_id=session_id,
                budget_usd_remaining=budget_usd_remaining,
                timeout_min=timeout_min,
                log_path=log_path,
                stall_min=stall_min,
                add_dirs=add_dirs,
            )
        )

    def start(  # noqa: PLR0913 — the port's own signature (AD-10)
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        model: str | None,
        session_id: str,
        budget_usd_remaining: Decimal | None,
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
        add_dirs: Sequence[Path] = (),
    ) -> HarnessHandle:
        """Start the dispatch and hand its group back before anything waits on it (AD-14)."""
        argv = self._argv(
            ["--session-id", session_id, *_add_dir_flags(add_dirs)],
            budget_usd_remaining=budget_usd_remaining,
            model=model,
            message=prompt,
        )
        self._record_prompt(log_path, prompt)
        return self._start(
            argv,
            cwd=cwd,
            env=env,
            timeout_min=timeout_min,
            log_path=log_path,
            session_id=session_id,
            stall_min=stall_min,
        )

    def resume(  # noqa: PLR0913 — the port's own signature (AD-10)
        self,
        *,
        cwd: Path,
        session_id: str,
        message: str,
        env: Mapping[str, str],
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
        model: str | None = None,
        budget_usd_remaining: Decimal | None = None,
        add_dirs: Sequence[Path] = (),
    ) -> HarnessResult:
        """Continue the session this row already opened — `retry`'s path only (AD-10)."""
        argv = self._argv(
            ["--resume", session_id, *_add_dir_flags(add_dirs)],
            budget_usd_remaining=budget_usd_remaining,
            model=model,
            message=message,
        )
        self._record_prompt(log_path, message)
        return self.wait(
            self._start(
                argv,
                cwd=cwd,
                env=env,
                timeout_min=timeout_min,
                log_path=log_path,
                session_id=session_id,
                stall_min=stall_min,
            )
        )

    def resume_command(self, cwd: str, session_id: str) -> str:
        """What the Operator pastes to take the session over by hand (FR-21)."""
        return f"cd {cwd} && {EXECUTABLE} --resume {session_id}"

    def _argv(
        self,
        session_flags: list[str],
        *,
        budget_usd_remaining: Decimal | None,
        model: str | None,
        message: str,
    ) -> list[str]:
        """The whole command line. Pure: everything it reads is an argument or a setting."""
        argv = [
            EXECUTABLE,
            "-p",
            *session_flags,
            "--permission-mode",
            PERMISSION_MODE,
            "--allowedTools",
            ",".join(self.settings.claude_allowed_tools),
            "--disallowedTools",
            DISALLOWED_TOOLS,
            "--output-format",
            OUTPUT_FORMAT,
            VERBOSE,
        ]
        if budget_usd_remaining is not None:
            argv += ["--max-budget-usd", render_budget(budget_usd_remaining)]
        if model is not None:
            argv += ["--model", model]
        argv.append(message)
        return argv

    def wait(self, handle: HarnessHandle) -> HarnessResult:
        """Wait for the process `start` returned, then read its log (AD-14).

        Guarded: a raise here would orphan the group — kill is idempotent on a finished
        process and the original exception still reaches the walker.
        """
        try:
            outcome = self.runner.wait(Handle(pid=handle.pid, pgid=handle.pgid))
        except BaseException:
            # BaseException, not Exception: a cancelled walker thread must not orphan a
            # harness either. The group is killed and the original exception re-raised.
            self.runner.kill_group(handle.pgid)
            raise
        raw_result = result_object(read_text(handle.log_path))
        return HarnessResult(
            session_id=handle.session_id,
            exit_code=outcome.exit_code,
            log_path=handle.log_path,
            usage=usage_from(raw_result),
            timed_out=outcome.timed_out,
            pgid=handle.pgid,
            raw_result=raw_result,
            stalled=outcome.stalled,
            stall_cwd=handle.cwd if outcome.stalled else None,
        )

    def _start(  # noqa: PLR0913 — the runner's own call, one argument per port parameter
        self,
        argv: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_min: float | None,
        log_path: Path,
        session_id: str,
        stall_min: float | None = None,
    ) -> HarnessHandle:
        """The runner's handle, as the port's own: what `wait` needs and nothing more."""
        handle = self.runner.start(
            argv,
            cwd=cwd,
            env=env,
            timeout_min=timeout_min,
            log_path=log_path,
            stall_min=stall_min,
        )
        return HarnessHandle(
            session_id=session_id,
            log_path=log_path,
            pid=handle.pid,
            pgid=handle.pgid,
            cwd=cwd,
        )

    def probe(self) -> ProbeResult:
        return run_probe_script(self.settings.harness_scripts_dir / "claude.sh")

    def _record_prompt(self, log_path: Path, message: str) -> None:
        """The prompt, beside the log, so an attempt's record holds what was asked."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        Path(f"{log_path}{PROMPT_SUFFIX}").write_text(message, encoding=ENCODING)


def _add_dir_flags(add_dirs: Sequence[Path]) -> list[str]:
    """`--add-dir` and its values, placed before `--permission-mode` by `_argv`'s callers."""
    return [ADD_DIR, *map(str, add_dirs)] if add_dirs else []


def render_budget(remaining: Decimal) -> str:
    """The remaining budget as `--max-budget-usd` takes it: two decimals, rounded *down*.

    Down, and not to nearest: `f"{Decimal('12.499'):.2f}"` is `12.50`, which would hand the
    CLI half a cent more than the Run actually has left, and FR-17 allows a Run to exceed
    its budget by at most one attempt — not by a rounding rule. A remainder that is zero or
    negative (the budget is already spent, and 5.7 has not parked the Run yet) is passed as
    `0.00` rather than as a negative amount the CLI has no meaning for.
    """
    if remaining <= 0:
        return NO_BUDGET
    return str(remaining.quantize(BUDGET_PRECISION, rounding=ROUND_DOWN))
