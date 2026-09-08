"""`ClaudeHarness`: `claude -p` through the `ProcessRunner` port (AD-10, AD-14, FR-14).

The invocation is written once, here, and nowhere else:

    claude -p --session-id {uuid} --permission-mode dontAsk
           --allowedTools {CLAUDE_ALLOWED_TOOLS} --disallowedTools "mcp__*"
           --output-format json --max-budget-usd {remaining} [--model {model}] "{prompt}"

`--bare` is not used and cannot be: at 2.1.x it exposes exactly `Bash, Edit, Read` — no
`Task`, no `Write`, no `Skill` — and `bmad-build-auto` needs all three (addendum §B). The
container is the sandbox instead: `dontAsk` with an explicit allowlist, and `mcp__*` denied
because a container has no personal connectors and the exclusion should be stated rather
than assumed.

**Resume keeps the tool flags.** `--resume` drops `--session-id` (the session is named by
`--resume`) and `--max-budget-usd` (the cap belongs to a dispatch, and the retry rule is
5.7's), and keeps `--permission-mode`, `--allowedTools` and `--disallowedTools`: a resumed
attempt runs in the same container as the one that started it, and letting the sandbox
depend on which call opened the turn would be a difference nothing could justify.

**Usage parsing is tolerant and terminal.** After the process ends, the log is scanned for
the harness's own result envelope — the last top-level JSON object carrying
`"type": "result"`, falling back to the last top-level object when none does — and `usage`
is filled from `total_cost_usd`, `usage.input_tokens` and `usage.output_tokens`. Anything
else — no JSON, a JSON array, missing fields, a field that is present but not a number — is
`usage = None`, never an exception: the log holds two interleaved streams, and npm's
warnings and an exporter's errors share it with the result. The object itself is handed on
whole as `raw_result`, because AD-10 forbids this adapter from deciding what any other
field means; 5.7 reads the budget-cap field out of it.

**A dispatch is two halves** (AD-14, 5.4). `start` hands back a `HarnessHandle` carrying
the process group, `wait` blocks on it and parses the log, and `run` is `wait(start(...))`
— so `application/steps/agent.py` can commit `attempt.pgid` between the two. `resume` goes
through the same private start and the same public `wait`, because a resumed attempt is the
same process under a different argv. What the log is read *for* moved to `result.py`, whose
public names this module re-exports.

**Static configuration is not this module's** (AD-10). `ANTHROPIC_BASE_URL`, the OTLP
exporter and `DISABLE_AUTOUPDATER` are written to `~/.claude/settings.json` by
`scripts/harness/claude.sh configure` at container start; the adapter writes nothing under
`AGENT_HOME`. The one file it does write is the prompt, beside the log, so an attempt's
record holds what was asked as well as what came back.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

from orchestrator.domain.ports.harness import (
    HarnessCapabilities,
    HarnessHandle,
    HarnessResult,
)
from orchestrator.domain.ports.process import Handle, ProcessRunner
from orchestrator.infrastructure.harness.claude.result import (
    ENCODING,
    RESULT_TYPE,
    RESULT_TYPE_FIELD,
    json_objects,
    read_text,
    result_object,
    usage_from,
)
from orchestrator.infrastructure.settings import Settings

#: What this module still owns, plus what it re-exports from `result.py`: the parsing moved
#: out when `start`/`wait` moved in (5.4), and every name it was reachable under here stays
#: reachable here, because a reader who knows the adapter should not have to learn a second
#: module path to find what it reads back.
__all__ = [
    "ENCODING",
    "RESULT_TYPE",
    "RESULT_TYPE_FIELD",
    "ClaudeHarness",
    "claude_aliases",
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
#: Denied explicitly: a container holds no personal MCP connectors.
DISALLOWED_TOOLS = "mcp__*"
#: One JSON result object per run, on stdout, which is what `usage` is read from.
OUTPUT_FORMAT = "json"

#: The five headers every gateway request of an attempt carries (AD-11), in the order
#: `scripts/harness/claude.sh` documents them. `ANTHROPIC_CUSTOM_HEADERS` is one string of
#: `Name: value` lines, so the order is the order a reader of that file sees.
HEADER_SOURCES: tuple[tuple[str, str], ...] = (
    ("langfuse_session_id", "ORCH_RUN_ID"),
    ("langfuse_tags", "ORCH_LANGFUSE_TAGS"),
    ("x-litellm-end-user-id", "ORCH_RUN_ID"),
    ("x-litellm-session-id", "ORCH_ATTEMPT_ID"),
    ("x-litellm-tags", "ORCH_TAGS"),
)

#: The two names Claude Code reads to put prompt and tool content into its OTLP spans. Added
#: only when the Project asked for content logging (`ORCH_LOG_CONTENT == "1"`).
CONTENT_LOGGING_NAMES = ("OTEL_LOG_USER_PROMPTS", "OTEL_LOG_TOOL_CONTENT")

#: The suffix the prompt is written under, beside the attempt's own log.
PROMPT_SUFFIX = ".prompt"

#: Cents. `--max-budget-usd` takes an amount, and the amount is rounded *down* to it.
BUDGET_PRECISION = Decimal("0.01")
#: What is passed when nothing remains: the CLI is never handed a negative amount.
NO_BUDGET = "0.00"


def claude_aliases(contract: Mapping[str, str]) -> dict[str, str]:
    """The harness-native names `scripts/harness/claude.sh` declares, derived from contract.

    `HARNESS_ENV_ALIASES=(ANTHROPIC_AUTH_TOKEN=LITELLM_API_KEY ANTHROPIC_CUSTOM_HEADERS=derived)`
    — the token is the Gateway's virtual key and never an Anthropic one (AD-5), and the
    headers are the five lines AD-11 pins, built from contract values so nothing here reads
    a setting of its own.

    The content-logging pair is not an alias and is not in either script list: it is a
    switch, present only when `ORCH_LOG_CONTENT` says the Project asked for it.
    """
    headers = "\n".join(f"{header}: {contract[name]}" for header, name in HEADER_SOURCES)
    aliases = {
        "ANTHROPIC_AUTH_TOKEN": contract["LITELLM_API_KEY"],
        "ANTHROPIC_CUSTOM_HEADERS": headers,
    }
    if contract.get("ORCH_LOG_CONTENT") == "1":
        aliases.update(dict.fromkeys(CONTENT_LOGGING_NAMES, "1"))
    return aliases


class ClaudeHarness:
    """Claude Code, headless, in the worktree, under the runner's own deadline."""

    name = "claude"
    capabilities = HarnessCapabilities(preassign_session=True, resume=True, native_tracing=True)

    def __init__(self, runner: ProcessRunner, settings: Settings) -> None:
        self.runner = runner
        self.settings = settings

    def run(  # noqa: PLR0913 — the port's own signature (AD-10)
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
        budget_usd_remaining: Decimal,
        timeout_min: float,
        log_path: Path,
    ) -> HarnessHandle:
        """Start the dispatch and hand its group back before anything waits on it (AD-14)."""
        argv = self._argv(
            ["--session-id", session_id],
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
        )

    def resume(  # noqa: PLR0913 — the port's own signature (AD-10)
        self,
        *,
        cwd: Path,
        session_id: str,
        message: str,
        env: Mapping[str, str],
        timeout_min: float,
        log_path: Path,
    ) -> HarnessResult:
        """Continue the session this row already opened — `retry`'s path only (AD-10)."""
        argv = self._argv(
            ["--resume", session_id],
            budget_usd_remaining=None,
            model=None,
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
        ]
        if budget_usd_remaining is not None:
            argv += ["--max-budget-usd", render_budget(budget_usd_remaining)]
        if model is not None:
            argv += ["--model", model]
        argv.append(message)
        return argv

    def wait(self, handle: HarnessHandle) -> HarnessResult:
        """Wait for the process `start` returned, then read its log (AD-14).

        The wait is guarded because the group is the only handle on the process and this
        frame is the only place that holds it: a `wait` that raises would leave a coding
        agent running in a worktree with nothing left that knows its `pgid`, which is the
        orphan AD-14 exists to prevent. The kill is the runner's own idempotent one, so it
        is safe on a process that already ended, and the exception still reaches the walker.
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
        )

    def _start(  # noqa: PLR0913 — the runner's own call, one argument per port parameter
        self,
        argv: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_min: float,
        log_path: Path,
        session_id: str,
    ) -> HarnessHandle:
        """The runner's handle, as the port's own: what `wait` needs and nothing more."""
        handle = self.runner.start(
            argv, cwd=cwd, env=env, timeout_min=timeout_min, log_path=log_path
        )
        return HarnessHandle(
            session_id=session_id, log_path=log_path, pid=handle.pid, pgid=handle.pgid
        )

    def _record_prompt(self, log_path: Path, message: str) -> None:
        """The prompt, beside the log, so an attempt's record holds what was asked."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        Path(f"{log_path}{PROMPT_SUFFIX}").write_text(message, encoding=ENCODING)


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
