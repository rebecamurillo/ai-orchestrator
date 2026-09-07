"""`ClaudeHarness`: the argv, the process, and what is read back out of the log (AD-10, AD-14).

The adapter is the only place a Claude Code flag is written, so the argv is asserted as a
whole list rather than by substring: PRD FR-14 pins the invocation, `--bare` is unusable
(addendum §B), and a flag silently dropped would change what the agent may do without
changing any other gate. Two shapes are pinned — a first dispatch and a `--resume` — and
their difference is itself a rule: a resumed attempt runs in the same container with the
same tools, so it keeps `--disallowedTools` and drops only the session and budget flags.

Everything else here is about what the adapter is *not* allowed to interpret. It reads the
log for the last JSON object, fills `usage` from three fields when they are all there, and
otherwise reports `usage = None` and hands the parsed object on as `raw_result` — 5.7 is
what decides whether an exit was the budget cap, from a field this story does not name.

The process itself goes through the `ProcessRunner` port (AD-14): the fake records `cwd`,
`env`, `timeout_min` and `log_path`, and the pgid the adapter reports is the handle's own.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.ports.process import Handle, Outcome
from orchestrator.infrastructure.harness.claude.adapter import ClaudeHarness
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

SESSION_ID = "0199a1f2-7c3d-7b2a-9f21-0d1e2f3a4b5c"
#: The row's own deadline, which the runner and not the adapter enforces (AD-14).
TIMEOUT_MIN = 45.0
TOKENS_IN = 1200
TOKENS_OUT = 340
MODEL = "claude-opus-5"
PROMPT = "Run bmad-build-auto for story 5-1."
WORKTREE = Path("/work/acme/widgets/wt/feat-x")

#: A `claude -p --output-format json` result, cut to the fields the adapter reads.
SAMPLE_RESULT = {
    "type": "result",
    "subtype": "success",
    "session_id": SESSION_ID,
    "total_cost_usd": 0.0342,
    "usage": {"input_tokens": TOKENS_IN, "output_tokens": TOKENS_OUT},
    "result": "done",
}


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


@pytest.fixture
def runner() -> FakeProcessRunner:
    return FakeProcessRunner()


@pytest.fixture
def harness(runner: FakeProcessRunner, settings: Settings) -> ClaudeHarness:
    return ClaudeHarness(runner, settings)


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "007-1.log"


def dispatch(
    harness: ClaudeHarness,
    log_path: Path,
    *,
    model: str | None = MODEL,
    budget: Decimal = Decimal("12.5"),
    timeout_min: float = TIMEOUT_MIN,
) -> HarnessResult:
    return harness.run(
        cwd=WORKTREE,
        prompt=PROMPT,
        env={"ORCH_RUN_ID": "r-1"},
        model=model,
        session_id=SESSION_ID,
        budget_usd_remaining=budget,
        timeout_min=timeout_min,
        log_path=log_path,
    )


def write_log(log_path: Path, text: str) -> None:
    """The fake runner writes nothing, so a test that wants output writes it itself."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(text)


# ── identity ─────────────────────────────────────────────────────────────────


def test_the_adapter_names_itself_and_its_capabilities(harness: ClaudeHarness) -> None:
    assert harness.name == "claude"
    assert harness.capabilities.preassign_session is True
    assert harness.capabilities.resume is True
    assert harness.capabilities.native_tracing is True


# ── the invocation ───────────────────────────────────────────────────────────


def test_the_dispatch_argv_is_the_documented_invocation(
    harness: ClaudeHarness, runner: FakeProcessRunner, settings: Settings, log_path: Path
) -> None:
    dispatch(harness, log_path)

    assert runner.called("start")[0]["cmd"] == [
        "claude",
        "-p",
        "--session-id",
        SESSION_ID,
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        ",".join(settings.claude_allowed_tools),
        "--disallowedTools",
        "mcp__*",
        "--output-format",
        "json",
        "--max-budget-usd",
        "12.50",
        "--model",
        MODEL,
        PROMPT,
    ]


def test_the_remaining_budget_is_rendered_with_two_decimals(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    dispatch(harness, log_path, budget=Decimal("7"))

    cmd = runner.called("start")[0]["cmd"]
    assert cmd[cmd.index("--max-budget-usd") + 1] == "7.00"


def test_no_model_means_no_model_flag(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """The Template may leave `model` unbound; the gateway's own default then decides."""
    dispatch(harness, log_path, model=None)

    cmd = runner.called("start")[0]["cmd"]
    assert "--model" not in cmd
    assert cmd[-1] == PROMPT


def test_the_process_runs_in_the_worktree_under_the_rows_deadline(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    dispatch(harness, log_path)

    call = runner.called("start")[0]
    assert call["cwd"] == WORKTREE
    assert call["timeout_min"] == TIMEOUT_MIN
    assert call["log_path"] == log_path
    assert call["env"] == {"ORCH_RUN_ID": "r-1"}


def test_the_prompt_is_written_beside_the_log_for_the_record(
    harness: ClaudeHarness, log_path: Path
) -> None:
    dispatch(harness, log_path)

    assert Path(f"{log_path}.prompt").read_text() == PROMPT


# ── what comes back ──────────────────────────────────────────────────────────


def test_the_result_carries_the_preassigned_session_the_exit_code_and_the_usage(
    harness: ClaudeHarness, log_path: Path
) -> None:
    write_log(log_path, json.dumps(SAMPLE_RESULT))

    result = dispatch(harness, log_path)

    assert result.session_id == SESSION_ID
    assert result.exit_code == 0
    assert result.log_path == log_path
    assert result.timed_out is False
    assert result.pgid == 1
    assert result.usage is not None
    assert result.usage.tokens_in == TOKENS_IN
    assert result.usage.tokens_out == TOKENS_OUT
    assert result.usage.cost_usd == Decimal("0.0342")
    assert result.raw_result == SAMPLE_RESULT


def test_a_json_result_after_other_output_is_the_one_that_is_read(
    harness: ClaudeHarness, log_path: Path
) -> None:
    """Claude Code prints warnings on stderr, and both streams land in this one file."""
    write_log(
        log_path,
        "npm warn deprecated something\n{ not json at all }\n" + json.dumps(SAMPLE_RESULT) + "\n",
    )

    result = dispatch(harness, log_path)

    assert result.raw_result == SAMPLE_RESULT
    assert result.usage is not None
    assert result.usage.cost_usd == Decimal("0.0342")


def test_plain_text_output_yields_no_usage_and_no_raw_result(
    harness: ClaudeHarness, log_path: Path
) -> None:
    write_log(log_path, "Error: could not reach the gateway\n")

    result = dispatch(harness, log_path)

    assert result.usage is None
    assert result.raw_result is None
    assert result.exit_code == 0


def test_a_log_that_was_never_written_is_not_an_exception(
    harness: ClaudeHarness, log_path: Path
) -> None:
    result = dispatch(harness, log_path)

    assert result.usage is None
    assert result.raw_result is None


def test_a_json_array_is_not_a_result_object(harness: ClaudeHarness, log_path: Path) -> None:
    write_log(log_path, "[1, 2, 3]\n")

    result = dispatch(harness, log_path)

    assert result.raw_result is None
    assert result.usage is None


@pytest.mark.parametrize(
    "result_object",
    [
        {"usage": {"input_tokens": 1, "output_tokens": 2}},
        {"total_cost_usd": 0.1},
        {"total_cost_usd": 0.1, "usage": {"input_tokens": 1}},
        {"total_cost_usd": 0.1, "usage": "not an object"},
        {"total_cost_usd": "n/a", "usage": {"input_tokens": 1, "output_tokens": 2}},
        {"total_cost_usd": 0.1, "usage": {"input_tokens": "many", "output_tokens": 2}},
        {"total_cost_usd": 0.1, "usage": {"input_tokens": 1, "output_tokens": True}},
        {"total_cost_usd": True, "usage": {"input_tokens": 1, "output_tokens": 2}},
    ],
    ids=[
        "no cost",
        "no usage",
        "no output tokens",
        "usage is not an object",
        "cost is not a number",
        "tokens are not a number",
        "tokens are a bool",
        "cost is a bool",
    ],
)
def test_a_result_missing_a_usage_field_yields_no_usage_but_keeps_the_object(
    harness: ClaudeHarness, log_path: Path, result_object: dict[str, object]
) -> None:
    """AD-10: the adapter interprets nothing. An incomplete result is handed on whole."""
    write_log(log_path, json.dumps(result_object))

    result = dispatch(harness, log_path)

    assert result.usage is None
    assert result.raw_result == result_object


def test_a_timeout_is_reported_with_the_group_the_runner_killed(
    settings: Settings, log_path: Path
) -> None:
    runner = FakeProcessRunner(default=Outcome(exit_code=None, timed_out=True))
    harness = ClaudeHarness(runner, settings)

    result = dispatch(harness, log_path)

    # The kill itself is not asserted here and cannot be: AD-14 puts the escalation inside
    # `ProcessRunner.wait`, so the adapter never calls `kill_group` on a timeout and the
    # fake records only the wait. That the runner does kill the group — SIGTERM, ten
    # seconds, SIGKILL — is proved in `tests/unit/test_process_runner.py` against the real
    # one. What this test owns is the half the adapter is responsible for: the outcome is
    # reported as a timeout rather than as an exit code, and the group is on the record.
    assert result.timed_out is True
    assert result.exit_code is None
    assert result.pgid == runner.called("wait")[0]["pgid"]


def test_a_nonzero_exit_is_reported_as_it_stands(settings: Settings, log_path: Path) -> None:
    runner = FakeProcessRunner(default=Outcome(exit_code=1, timed_out=False))

    result = dispatch(ClaudeHarness(runner, settings), log_path)

    assert result.exit_code == 1
    assert result.timed_out is False


# ── resume ───────────────────────────────────────────────────────────────────


def test_the_resume_argv_uses_the_session_and_carries_the_message_last(
    harness: ClaudeHarness, runner: FakeProcessRunner, settings: Settings, log_path: Path
) -> None:
    harness.resume(
        cwd=WORKTREE,
        session_id=SESSION_ID,
        message="Answer from the operator: use pnpm.",
        env={"ORCH_RUN_ID": "r-1"},
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )

    assert runner.called("start")[0]["cmd"] == [
        "claude",
        "-p",
        "--resume",
        SESSION_ID,
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        ",".join(settings.claude_allowed_tools),
        "--disallowedTools",
        "mcp__*",
        "--output-format",
        "json",
        "Answer from the operator: use pnpm.",
    ]


def test_resume_carries_no_budget_flag_and_no_second_session_id(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    harness.resume(
        cwd=WORKTREE,
        session_id=SESSION_ID,
        message="go on",
        env={},
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )

    cmd = runner.called("start")[0]["cmd"]
    assert "--max-budget-usd" not in cmd
    assert "--session-id" not in cmd


def test_resume_reports_the_session_it_was_given(harness: ClaudeHarness, log_path: Path) -> None:
    write_log(log_path, json.dumps(SAMPLE_RESULT))

    result = harness.resume(
        cwd=WORKTREE,
        session_id=SESSION_ID,
        message="go on",
        env={},
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )

    assert result.session_id == SESSION_ID
    assert result.usage is not None


def test_the_resume_command_is_what_the_operator_types(harness: ClaudeHarness) -> None:
    assert harness.resume_command("/work/p/r/wt/feat-x", "abc") == (
        "cd /work/p/r/wt/feat-x && claude --resume abc"
    )


# ── the result envelope is preferred over whatever printed last ──────────────


def test_a_json_line_printed_after_the_result_does_not_displace_it(
    harness: ClaudeHarness, log_path: Path
) -> None:
    """stdout and stderr share this file, so the result is not always what printed last.

    An OTLP exporter that fails on shutdown prints its own JSON after `claude` has already
    printed the result. Taking the last object would report `usage = None` on a run that
    reported usage, and hand 5.7 an error payload as `raw_result`.
    """
    write_log(
        log_path,
        json.dumps(SAMPLE_RESULT)
        + "\n"
        + json.dumps({"severity": "error", "message": "otlp exporter shutdown failed"})
        + "\n",
    )

    result = dispatch(harness, log_path)

    assert result.raw_result == SAMPLE_RESULT
    assert result.usage is not None
    assert result.usage.cost_usd == Decimal("0.0342")


def test_the_last_result_envelope_wins_when_the_log_holds_more_than_one(
    harness: ClaudeHarness, log_path: Path
) -> None:
    """A re-attempt appends to the same log; the newest envelope is this attempt's."""
    earlier = {**SAMPLE_RESULT, "total_cost_usd": 0.9, "result": "an earlier attempt"}
    write_log(log_path, json.dumps(earlier) + "\n" + json.dumps(SAMPLE_RESULT) + "\n")

    result = dispatch(harness, log_path)

    assert result.raw_result == SAMPLE_RESULT


def test_without_an_envelope_the_last_object_is_still_read(
    harness: ClaudeHarness, log_path: Path
) -> None:
    """The brief's own rule, kept as the fallback: a harness that stops printing `type`
    still has its result read rather than dropped."""
    unlabelled = {"total_cost_usd": 0.5, "usage": {"input_tokens": 3, "output_tokens": 4}}
    write_log(log_path, "warning: something\n" + json.dumps(unlabelled) + "\n")

    result = dispatch(harness, log_path)

    assert result.raw_result == unlabelled
    assert result.usage is not None
    assert result.usage.cost_usd == Decimal("0.5")


# ── the budget is rounded down, never up, and never below zero ───────────────


def test_the_remaining_budget_is_rounded_down_and_not_to_nearest(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """FR-17 lets a Run exceed its budget by at most one attempt — not by a rounding rule.

    Two decimals to nearest would hand the CLI `12.50` for a remainder of `12.499`, which
    is half a cent the Run does not have.
    """
    dispatch(harness, log_path, budget=Decimal("12.499"))

    cmd = runner.called("start")[0]["cmd"]
    assert cmd[cmd.index("--max-budget-usd") + 1] == "12.49"


@pytest.mark.parametrize("remaining", [Decimal("0"), Decimal("-3.20")])
def test_a_spent_budget_is_passed_as_zero_and_never_as_a_negative_amount(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path, remaining: Decimal
) -> None:
    """5.7 owns the park; until it lands, the CLI is still never handed a negative amount."""
    dispatch(harness, log_path, budget=remaining)

    cmd = runner.called("start")[0]["cmd"]
    assert cmd[cmd.index("--max-budget-usd") + 1] == "0.00"


# ── a wait that raises must not leave the harness running ────────────────────


class RaisingRunner(FakeProcessRunner):
    """A `FakeProcessRunner` whose `wait` fails, which the shared fake cannot script.

    Subclassed rather than changed: `tests/unit/fakes/process.py` is the one fake for the
    port (AD-18) and nothing about a `wait` that raises belongs to every test that uses it.
    """

    def wait(self, handle: Handle) -> Outcome:
        self.calls.append({"method": "wait", "pgid": handle.pgid})
        raise RuntimeError("the engine went away mid-attempt")


def test_a_wait_that_raises_kills_the_group_before_the_exception_escapes(
    settings: Settings, log_path: Path
) -> None:
    """AD-14: the group is the only handle on the process, and this frame is the only place
    that holds it. An exception on the way out would otherwise leave a coding agent running
    in a worktree with nothing left that knows its `pgid`."""
    runner = RaisingRunner()
    harness = ClaudeHarness(runner, settings)

    with pytest.raises(RuntimeError, match="went away"):
        dispatch(harness, log_path)

    started = runner.called("wait")[0]["pgid"]
    assert [call["pgid"] for call in runner.called("kill_group")] == [started]


def test_a_wait_that_raises_on_resume_kills_the_group_too(
    settings: Settings, log_path: Path
) -> None:
    """`resume` runs the same process through the same port, so it holds the same rule."""
    runner = RaisingRunner()
    harness = ClaudeHarness(runner, settings)

    with pytest.raises(RuntimeError):
        harness.resume(
            cwd=WORKTREE,
            session_id=SESSION_ID,
            message="go on",
            env={},
            timeout_min=TIMEOUT_MIN,
            log_path=log_path,
        )

    assert runner.called("kill_group")
