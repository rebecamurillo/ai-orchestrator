"""`CodexHarness`: the argv, the process, and what is read back out of the stream (AD-10, AD-14).

The adapter is the only place a Codex CLI flag is written, so the argv is asserted as a whole
list rather than by substring — the same rule `test_claude_adapter.py` holds the other adapter
to, and for the same reason: a flag silently dropped changes what the agent may do without
changing any other gate.

**The whole invocation is provisional and is asserted as provisional.** `briefs/7-1-codex-
adapter.md` marks the flags, the resume form, the session event and the content switch
`[verify]`, and story 7.2 is where they are settled against the real CLI on the real host. These
tests therefore pin the *documented shape* and the behaviour around it — the prompt is last, a
missing model drops its flag, an absent session event is `None` rather than an exception, a
timeout is reported with the group — none of which changes when a flag name turns out to differ.

`preassign_session` is `False`, and one consequence is pinned here because nothing else would
catch it: `start` cannot know the session, so its handle carries no id and only `wait` reports
one. A `resume` keeps the session it was handed when the stream names none.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.domain.ports.harness import Harness, HarnessResult
from orchestrator.domain.ports.process import Outcome
from orchestrator.infrastructure.harness.codex.adapter import CodexHarness, codex_aliases
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

FIXTURES = Path(__file__).parent / "infrastructure" / "harness" / "fixtures" / "codex"
SESSION_ID = "0199c4a1-6d2e-7f31-8a44-51b6c7d8e9f0"
#: What the caller pre-assigned. Codex names its own thread, so this is never in the argv.
PREASSIGNED = "0199a1f2-7c3d-7b2a-9f21-0d1e2f3a4b5c"
TIMEOUT_MIN = 45.0
TOKENS_IN = 1200
TOKENS_OUT = 340
MODEL = "gpt-5-codex"
PROMPT = "Run bmad-build-auto for story 7-1."
WORKTREE = Path("/work/acme/widgets/wt/feat-x")
ENV = {"ORCH_RUN_ID": "r-1", "ORCH_LOG_CONTENT": "0"}
LOGGING_ENV = {"ORCH_RUN_ID": "r-1", "ORCH_LOG_CONTENT": "1"}


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


@pytest.fixture
def runner() -> FakeProcessRunner:
    return FakeProcessRunner()


@pytest.fixture
def harness(runner: FakeProcessRunner, settings: Settings) -> CodexHarness:
    return CodexHarness(runner, settings)


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "007-1.log"


def dispatch(
    harness: CodexHarness,
    log_path: Path,
    *,
    model: str | None = MODEL,
    env: dict[str, str] | None = None,
) -> HarnessResult:
    return harness.run(
        cwd=WORKTREE,
        prompt=PROMPT,
        env=ENV if env is None else env,
        model=model,
        session_id=PREASSIGNED,
        budget_usd_remaining=Decimal("12.5"),
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )


def write_stream(log_path: Path, fixture: str) -> None:
    """The fake runner writes nothing, so a test that wants a stream writes it itself."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(FIXTURES.joinpath(fixture).read_text(encoding="utf-8"))


# ── identity ─────────────────────────────────────────────────────────────────


def test_the_adapter_names_itself_and_its_capabilities(harness: CodexHarness) -> None:
    """`preassign_session` is False: Codex names its own thread, which is why the session is
    read out of the stream instead of being handed to the process."""
    assert harness.name == "codex"
    assert harness.capabilities.preassign_session is False
    assert harness.capabilities.resume is True
    assert harness.capabilities.native_tracing is True


def test_the_adapter_satisfies_the_port(harness: CodexHarness) -> None:
    assert isinstance(harness, Harness)


# ── the invocation ───────────────────────────────────────────────────────────


def test_the_dispatch_argv_is_the_documented_invocation(
    harness: CodexHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    dispatch(harness, log_path)

    assert runner.called("start")[0]["cmd"] == [
        "codex",
        "exec",
        "--json",
        "-C",
        str(WORKTREE),
        "-m",
        MODEL,
        "-o",
        f"{log_path}.last.md",
        PROMPT,
    ]


def test_the_preassigned_session_never_reaches_the_command_line(
    harness: CodexHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """`preassign_session = False` is a claim about the argv, so the argv is what states it."""
    dispatch(harness, log_path)

    assert PREASSIGNED not in runner.called("start")[0]["cmd"]


def test_no_model_means_no_model_flag(
    harness: CodexHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """The Template may leave `model` unbound; the harness's configured default then decides."""
    dispatch(harness, log_path, model=None)

    cmd = runner.called("start")[0]["cmd"]
    assert "-m" not in cmd
    assert cmd[-1] == PROMPT


def test_the_content_switch_is_present_only_when_the_project_asked_for_it(
    harness: CodexHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """The config file is static, so the switch travels on the command line (AD-10)."""
    dispatch(harness, log_path, env=LOGGING_ENV)

    cmd = runner.called("start")[0]["cmd"]
    assert cmd[cmd.index("-c") + 1] == "otel.log_user_prompt=true"
    assert cmd[-1] == PROMPT


def test_the_content_switch_is_absent_when_it_was_not(
    harness: CodexHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    dispatch(harness, log_path)

    assert "-c" not in runner.called("start")[0]["cmd"]


def test_an_environment_that_names_no_content_switch_at_all_leaves_it_off(
    harness: CodexHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    dispatch(harness, log_path, env={"ORCH_RUN_ID": "r-1"})

    assert "-c" not in runner.called("start")[0]["cmd"]


def test_the_process_runs_in_the_worktree_under_the_rows_deadline(
    harness: CodexHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    dispatch(harness, log_path)

    call = runner.called("start")[0]
    assert call["cwd"] == WORKTREE
    assert call["timeout_min"] == TIMEOUT_MIN
    assert call["log_path"] == log_path
    assert call["env"] == ENV


def test_the_prompt_is_written_beside_the_log_for_the_record(
    harness: CodexHarness, log_path: Path
) -> None:
    dispatch(harness, log_path)

    assert Path(f"{log_path}.prompt").read_text() == PROMPT


# ── what comes back ──────────────────────────────────────────────────────────


def test_the_result_carries_the_captured_session_the_exit_code_and_the_usage(
    harness: CodexHarness, log_path: Path
) -> None:
    write_stream(log_path, "turn.jsonl")

    result = dispatch(harness, log_path)

    assert result.session_id == SESSION_ID
    assert result.exit_code == 0
    assert result.log_path == log_path
    assert result.timed_out is False
    assert result.pgid == 1
    assert result.usage is not None
    assert result.usage.tokens_in == TOKENS_IN
    assert result.usage.tokens_out == TOKENS_OUT
    assert result.usage.cost_usd == Decimal("0")
    assert result.raw_result is not None
    assert result.raw_result["type"] == "turn.completed"


def test_a_stream_without_the_thread_event_records_no_session(
    harness: CodexHarness, log_path: Path
) -> None:
    """7.2's readiness line `session id recorded` is what this fails; the dispatch does not."""
    write_stream(log_path, "no-thread.jsonl")

    result = dispatch(harness, log_path)

    assert result.session_id is None
    assert result.exit_code == 0
    assert result.usage is not None


def test_the_stream_is_read_out_of_a_log_two_streams_share(
    harness: CodexHarness, log_path: Path
) -> None:
    write_stream(log_path, "interleaved.jsonl")

    result = dispatch(harness, log_path)

    assert result.session_id == SESSION_ID
    assert result.usage is not None
    assert result.usage.tokens_in == TOKENS_IN


def test_a_log_that_was_never_written_is_not_an_exception(
    harness: CodexHarness, log_path: Path
) -> None:
    result = dispatch(harness, log_path)

    assert result.session_id is None
    assert result.usage is None
    assert result.raw_result is None


def test_a_timeout_is_reported_with_the_group_the_runner_killed(
    settings: Settings, log_path: Path
) -> None:
    runner = FakeProcessRunner(default=Outcome(exit_code=None, timed_out=True))

    result = dispatch(CodexHarness(runner, settings), log_path)

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.pgid == runner.called("wait")[0]["pgid"]


def test_a_nonzero_exit_is_reported_as_it_stands(settings: Settings, log_path: Path) -> None:
    runner = FakeProcessRunner(default=Outcome(exit_code=1, timed_out=False))

    result = dispatch(CodexHarness(runner, settings), log_path)

    assert result.exit_code == 1
    assert result.timed_out is False


def test_a_wait_that_raises_kills_the_group_rather_than_orphaning_it(
    settings: Settings, log_path: Path
) -> None:
    """AD-14: this frame holds the only reference to the group."""

    class Exploding(FakeProcessRunner):
        def wait(self, handle: object) -> Outcome:  # type: ignore[override]
            raise KeyboardInterrupt

    runner = Exploding()
    harness = CodexHarness(runner, settings)

    with pytest.raises(KeyboardInterrupt):
        dispatch(harness, log_path)

    assert [call["pgid"] for call in runner.called("kill_group")] == [1]


# ── resume ───────────────────────────────────────────────────────────────────


def test_the_resume_argv_uses_the_session_and_carries_the_message_last(
    harness: CodexHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    harness.resume(
        cwd=WORKTREE,
        session_id=SESSION_ID,
        message="Answer from the operator: use pnpm.",
        env=ENV,
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )

    assert runner.called("start")[0]["cmd"] == [
        "codex",
        "exec",
        "resume",
        SESSION_ID,
        "--json",
        "Answer from the operator: use pnpm.",
    ]


def test_resume_records_the_message_beside_the_log_like_a_dispatch(
    harness: CodexHarness, log_path: Path
) -> None:
    harness.resume(
        cwd=WORKTREE,
        session_id=SESSION_ID,
        message="go on",
        env=ENV,
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )

    assert Path(f"{log_path}.prompt").read_text() == "go on"


def test_resume_keeps_the_session_it_was_given_when_the_stream_names_none(
    harness: CodexHarness, log_path: Path
) -> None:
    """Unlike a first dispatch, a resume already knows the thread it continued."""
    write_stream(log_path, "no-thread.jsonl")

    result = harness.resume(
        cwd=WORKTREE,
        session_id=SESSION_ID,
        message="go on",
        env=ENV,
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )

    assert result.session_id == SESSION_ID
    assert result.usage is not None


def test_the_resume_command_is_what_the_operator_types(harness: CodexHarness) -> None:
    assert harness.resume_command("/work/p/r/wt/feat-x", "abc") == (
        "cd /work/p/r/wt/feat-x && codex resume abc"
    )


def test_the_resume_command_states_no_secret(harness: CodexHarness, settings: Settings) -> None:
    """AD-5, FR-21: the line goes on a screen, so it may carry identifiers and nothing else."""
    line = harness.resume_command("/work/p/r/wt/feat-x", SESSION_ID)

    for secret in (
        settings.litellm_api_key,
        settings.litellm_spend_key,
        settings.langfuse_secret_key,
        settings.github_token,
    ):
        assert secret.get_secret_value() not in line


# ── the environment names this harness adds ──────────────────────────────────


def test_the_alias_builder_adds_the_one_name_the_script_exports(settings: Settings) -> None:
    """`scripts/harness/codex.sh` declares `HARNESS_ENV_ALIASES=()` and exports `CODEX_HOME`
    itself; the process the adapter starts inherits nothing, so the builder supplies it."""
    built = codex_aliases(settings.agent_home)({"LITELLM_API_KEY": "sk-x"})

    assert built == {"CODEX_HOME": f"{settings.agent_home}/.codex"}


def test_the_alias_builder_reads_no_credential_out_of_the_contract(settings: Settings) -> None:
    """AD-5: Codex reads the contract names directly, so no alias carries a value."""
    built = codex_aliases(settings.agent_home)(
        {"LITELLM_API_KEY": "sk-secret", "LANGFUSE_SECRET_KEY": "lf-secret"}
    )

    assert "sk-secret" not in str(built)
    assert "lf-secret" not in str(built)
