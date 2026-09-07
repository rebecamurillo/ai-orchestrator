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

**Static configuration is not this module's** (AD-10). `ANTHROPIC_BASE_URL`, the OTLP
exporter and `DISABLE_AUTOUPDATER` are written to `~/.claude/settings.json` by
`scripts/harness/claude.sh configure` at container start; the adapter writes nothing under
`AGENT_HOME`. The one file it does write is the prompt, beside the log, so an attempt's
record holds what was asked as well as what came back.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.harness import HarnessCapabilities, HarnessResult, HarnessUsage
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.infrastructure.settings import Settings

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

#: The envelope field `claude -p --output-format json` puts on its own final object, and the
#: value that marks it. Reading it is the same class of read as `session_id` — the harness's
#: own framing, not anything the model produced (AD-10).
RESULT_TYPE_FIELD = "type"
RESULT_TYPE = "result"

#: Cents. `--max-budget-usd` takes an amount, and the amount is rounded *down* to it.
BUDGET_PRECISION = Decimal("0.01")
#: What is passed when nothing remains: the CLI is never handed a negative amount.
NO_BUDGET = "0.00"

#: The one encoding every log and prompt file is written and read in, so the container's
#: locale never decides what is parsed out of an attempt's own record.
ENCODING = "utf-8"


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
        """First dispatch: a pre-assigned session, the remaining budget as the harness cap."""
        argv = self._argv(
            ["--session-id", session_id],
            budget_usd_remaining=budget_usd_remaining,
            model=model,
            message=prompt,
        )
        self._record_prompt(log_path, prompt)
        return self._execute(
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
        return self._execute(
            argv,
            cwd=cwd,
            env=env,
            timeout_min=timeout_min,
            log_path=log_path,
            session_id=session_id,
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

    def _execute(  # noqa: PLR0913 — the runner's own call, one argument per port parameter
        self,
        argv: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_min: float,
        log_path: Path,
        session_id: str,
    ) -> HarnessResult:
        """Start, wait, and read the log — the whole of AD-14's contract for this adapter.

        The wait is guarded because the group is the only handle on the process and this
        frame is the only place that holds it: a `wait` that raises would leave a coding
        agent running in a worktree with nothing left that knows its `pgid`, which is the
        orphan AD-14 exists to prevent. The kill is the runner's own idempotent one, so it
        is safe on a process that already ended, and the exception still reaches the walker.
        """
        handle = self.runner.start(
            argv, cwd=cwd, env=env, timeout_min=timeout_min, log_path=log_path
        )
        try:
            outcome = self.runner.wait(handle)
        except BaseException:
            # BaseException, not Exception: a cancelled walker thread must not orphan a
            # harness either. The group is killed and the original exception re-raised.
            self.runner.kill_group(handle.pgid)
            raise
        raw_result = result_object(read_text(log_path))
        return HarnessResult(
            session_id=session_id,
            exit_code=outcome.exit_code,
            log_path=log_path,
            usage=usage_from(raw_result),
            timed_out=outcome.timed_out,
            pgid=handle.pgid,
            raw_result=raw_result,
        )

    def _record_prompt(self, log_path: Path, message: str) -> None:
        """The prompt, beside the log, so an attempt's record holds what was asked."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        Path(f"{log_path}{PROMPT_SUFFIX}").write_text(message, encoding=ENCODING)


def read_text(log_path: Path) -> str:
    """The log's text, or nothing at all — a process killed before it wrote has no log."""
    if not log_path.is_file():
        return ""
    return log_path.read_text(encoding=ENCODING, errors="replace")


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


def json_objects(text: str) -> list[dict[str, Any]]:
    """Every top-level JSON object in `text`, in the order they appear.

    Scanning rather than `json.loads`: the log holds stdout and stderr interleaved, so the
    result object is normally surrounded by whatever the tooling printed. Each `{` is
    offered to `raw_decode`, and a successful decode advances past the whole object, so a
    nested one is never mistaken for a top-level one.
    """
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    index = text.find("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            index = text.find("{", index + 1)
            continue
        found.append(value)
        index = text.find("{", end)
    return found


def result_object(text: str) -> dict[str, Any] | None:
    """The harness's own result object, or `None` when the log holds no JSON at all.

    The brief's rule is "the last JSON object", and that is the fallback here rather than
    the rule, because stdout and stderr share one file: an OTLP exporter error or an npm
    error payload printed *after* the result would take its place, and `usage` would go
    `None` on a run that reported it. So the last object carrying `"type": "result"` wins.

    That is not an interpretation of model output (AD-10). `type` is the envelope field
    `--output-format json` puts on the object it prints — the same class of read as
    `session_id`, which this adapter already takes from the harness's own framing. Nothing
    inside the envelope is read here; `raw_result` carries it on whole.
    """
    objects = json_objects(text)
    envelopes = [item for item in objects if item.get(RESULT_TYPE_FIELD) == RESULT_TYPE]
    if envelopes:
        return envelopes[-1]
    return objects[-1] if objects else None


def _as_int(value: Any) -> int | None:
    """A token count, or `None` when the field is there but is not one.

    `bool` is rejected explicitly because it is an `int` in Python, and `True` tokens is a
    reading error rather than one token.
    """
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _as_decimal(value: Any) -> Decimal | None:
    """A USD amount, or `None` when the field is there but is not one."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def usage_from(result: dict[str, Any] | None) -> HarnessUsage | None:
    """The three numbers AD-11 records, or `None` when the result does not carry all three.

    Nothing is inferred and nothing raises. A result with a cost and no token counts is as
    unusable as no result at all, because `attempt.tokens_in`/`tokens_out` would then be
    written as zero and read as measured; a field that is present but not a number
    (`"total_cost_usd": "n/a"`) is the same fact, and is reported the same way rather than
    as an exception a walker would have to catch. `raw_result` still carries the object, so
    nothing observed is lost.
    """
    if result is None:
        return None
    usage = result.get("usage")
    if not isinstance(usage, dict):
        return None
    cost = _as_decimal(result.get("total_cost_usd"))
    tokens_in = _as_int(usage.get("input_tokens"))
    tokens_out = _as_int(usage.get("output_tokens"))
    if cost is None or tokens_in is None or tokens_out is None:
        return None
    return HarnessUsage(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)
