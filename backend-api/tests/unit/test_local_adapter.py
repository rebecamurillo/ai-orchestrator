"""`LocalHarness`: the OpenCode invocation, and what is read back out of it (AD-10, AD-14).

The third adapter behind the `Harness` port, and the sibling of `test_codex_adapter.py`: the
argv is asserted as a whole list rather than by substring, because the adapter is the only
place an OpenCode flag is written and a flag silently dropped changes what the agent may do
without changing any other gate.

**The whole invocation is provisional and is asserted as provisional.**
`briefs/7-3-opencode-adapter.md` marks the argv, the session capture, the store fallback and
the content switch `[verify]`, and story 7.4 settles each against the real CLI on the real
host. These tests pin the documented shape and the behaviour around it — the prompt is last,
an unbound model falls back to the first `LOCAL_MODELS` alias, a stream that named no session
falls through to the store, a store that cannot be read is not an exception — none of which
changes when a flag name turns out to differ.

Two capabilities are `False` and are pinned here because nothing else would catch them.
`preassign_session`: OpenCode names its own session, so the caller's pre-allocated id never
reaches the command line and only `wait` can report one. `resume`: there is no resume form at
all, so `resume_command` is `None` — `application/steps/agent.py` reads the capability and
retries with the prompt prepended to a fresh session (5.5), which is why nothing in this
system ever calls `resume` on this adapter.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.domain.ports.harness import Harness, HarnessResult
from orchestrator.domain.ports.process import Outcome
from orchestrator.infrastructure.harness.opencode.adapter import (
    LocalHarness,
    local_aliases,
)
from orchestrator.infrastructure.harness.opencode.sessions import (
    DIRECTORY_COLUMN,
    ID_COLUMN,
    ORDER_COLUMN,
    SESSION_TABLE,
    store_path,
)
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

FIXTURES = Path(__file__).parent / "infrastructure" / "harness" / "fixtures" / "opencode"
SESSION_ID = "ses_7f3c1a0b9d2e4f5a"
STORED_SESSION = "ses_from_the_store"
#: What the caller pre-assigned. OpenCode names its own session, so this is never in the argv.
PREASSIGNED = "0199a1f2-7c3d-7b2a-9f21-0d1e2f3a4b5c"
TIMEOUT_MIN = 45.0
TOKENS_IN = 880
TOKENS_OUT = 210
MODEL = "local-general"
#: `.env.example` ships `LOCAL_MODELS=local-coder,local-general`; the first alias is the default.
DEFAULT_MODEL = "local-coder"
PROMPT = "Run bmad-build-auto for story 7-3."
WORKTREE = Path("/work/acme/widgets/wt/feat-x")
ENV = {"ORCH_RUN_ID": "r-1", "ORCH_LOG_CONTENT": "0"}
LOGGING_ENV = {"ORCH_RUN_ID": "r-1", "ORCH_LOG_CONTENT": "1"}

#: A contract as `env.py::_contract` builds one — what an `AliasBuilder` is given (AD-5).
CONTRACT = {
    "ORCH_RUN_ID": "01998f0e-0000-7000-8000-000000000001",
    "ORCH_ATTEMPT_ID": "01998f0e-0000-7000-8000-000000000002",
    "LANGFUSE_BASE_URL": "http://langfuse:3000",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
    "LANGFUSE_SECRET_KEY": "sk-lf-test",
    "LITELLM_API_KEY": "sk-virtual-key-for-a-test",
    "ORCH_LANGFUSE_TAGS": '["run:r-1", "attempt:a-1", "story:7-3", "harness:local"]',
    "ORCH_LOG_CONTENT": "0",
}


@pytest.fixture
def settings(env: dict[str, str], tmp_path: Path) -> Settings:
    """`agent_home` is the tmp dir so the session store this adapter reads is writable."""
    return Settings(agent_home=tmp_path / "agent")


@pytest.fixture
def runner() -> FakeProcessRunner:
    return FakeProcessRunner()


@pytest.fixture
def harness(runner: FakeProcessRunner, settings: Settings) -> LocalHarness:
    return LocalHarness(runner, settings)


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "007-3.log"


def with_stream(log_path: Path, name: str) -> Path:
    """The log the fake runner's process would have written, written for it."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text((FIXTURES / f"{name}.jsonl").read_text())
    return log_path


def a_store(settings: Settings, directory: Path, session_id: str) -> None:
    """One row in the documented store shape, under the agent's own home."""
    path = store_path(settings.agent_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            f"CREATE TABLE {SESSION_TABLE} "
            f"({ID_COLUMN} TEXT, {DIRECTORY_COLUMN} TEXT, {ORDER_COLUMN} INTEGER)"
        )
        connection.execute(
            f"INSERT INTO {SESSION_TABLE} VALUES (?, ?, ?)", (session_id, str(directory), 1)
        )
    connection.close()


def dispatch(
    harness: LocalHarness,
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


# ── the port ─────────────────────────────────────────────────────────────────


def test_the_adapter_satisfies_the_port(harness: LocalHarness) -> None:
    assert isinstance(harness, Harness)


def test_it_answers_to_the_name_the_harness_table_holds(harness: LocalHarness) -> None:
    """The table row and the Template's `harness:` value are both `local`; `opencode` is the
    CLI it drives and is never a key anywhere in this system."""
    assert harness.name == "local"


def test_it_claims_none_of_the_three_capabilities(harness: LocalHarness) -> None:
    assert harness.capabilities.preassign_session is False
    assert harness.capabilities.resume is False
    assert harness.capabilities.native_tracing is False


# ── the argv ─────────────────────────────────────────────────────────────────


def test_the_argv_is_the_documented_invocation_with_the_prompt_last(
    harness: LocalHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    with_stream(log_path, "turn")

    dispatch(harness, log_path)

    assert runner.called("start")[0]["cmd"] == [
        "opencode",
        "run",
        "--format",
        "json",
        "--dir",
        str(WORKTREE),
        "-m",
        f"litellm/{MODEL}",
        PROMPT,
    ]


def test_an_unbound_model_falls_back_to_the_first_local_models_alias(
    harness: LocalHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """Unlike `codex`, the flag is never dropped: OpenCode's own default is whatever the
    config file lists first, and the Gateway serves a route only for the aliases
    `LOCAL_MODELS` names."""
    with_stream(log_path, "turn")

    dispatch(harness, log_path, model=None)

    assert runner.called("start")[0]["cmd"][-2] == f"litellm/{DEFAULT_MODEL}"


def test_the_provider_prefix_is_the_one_the_script_configures(
    harness: LocalHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """`scripts/harness/opencode.sh configure` writes `provider.litellm`; a model named
    without that prefix would resolve against whichever provider OpenCode defaults to."""
    with_stream(log_path, "turn")

    dispatch(harness, log_path)

    assert runner.called("start")[0]["cmd"][-2].startswith("litellm/")


def test_the_content_switch_adds_no_flag_and_no_name(
    harness: LocalHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """`[verify; else record "no content switch"]` — the plugin documents none, so nothing is
    passed, and `ORCH_LOG_CONTENT` reaches the process as the contract name it already is."""
    with_stream(log_path, "turn")

    dispatch(harness, log_path, env=LOGGING_ENV)
    with_stream(log_path, "turn")
    dispatch(harness, log_path, env=ENV)

    calls = runner.called("start")
    assert calls[0]["cmd"] == calls[1]["cmd"]


def test_the_process_runs_in_the_worktree_and_with_exactly_the_environment_it_was_given(
    harness: LocalHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    with_stream(log_path, "turn")

    dispatch(harness, log_path)

    call = runner.called("start")[0]
    assert call["cwd"] == WORKTREE
    assert call["env"] == ENV
    assert call["timeout_min"] == TIMEOUT_MIN


def test_the_prompt_is_recorded_beside_the_log(harness: LocalHarness, log_path: Path) -> None:
    with_stream(log_path, "turn")

    dispatch(harness, log_path)

    assert Path(f"{log_path}.prompt").read_text() == PROMPT


# ── what comes back ──────────────────────────────────────────────────────────


def test_the_session_and_the_usage_come_from_the_stream(
    harness: LocalHarness, log_path: Path
) -> None:
    with_stream(log_path, "turn")

    result = dispatch(harness, log_path)

    assert result.session_id == SESSION_ID
    assert result.usage is not None
    assert (result.usage.tokens_in, result.usage.tokens_out) == (TOKENS_IN, TOKENS_OUT)
    assert result.usage.cost_usd == Decimal("0")
    assert result.exit_code == 0
    assert result.log_path == log_path


def test_a_stream_with_no_session_falls_back_to_the_store(
    harness: LocalHarness, settings: Settings, log_path: Path
) -> None:
    a_store(settings, WORKTREE, STORED_SESSION)
    with_stream(log_path, "no-session")

    assert dispatch(harness, log_path).session_id == STORED_SESSION


def test_the_stream_wins_over_the_store(
    harness: LocalHarness, settings: Settings, log_path: Path
) -> None:
    """The store is a fallback, not a second opinion: the id the attempt is recorded under
    must be the one the run itself printed."""
    a_store(settings, WORKTREE, STORED_SESSION)
    with_stream(log_path, "turn")

    assert dispatch(harness, log_path).session_id == SESSION_ID


def test_no_session_anywhere_is_recorded_as_no_session(
    harness: LocalHarness, log_path: Path
) -> None:
    """No store file at all — the ordinary state of a fresh container. 7.4's `session id
    recorded` readiness line is what reports it, and it is never an exception here."""
    with_stream(log_path, "no-session")

    assert dispatch(harness, log_path).session_id is None


def test_the_store_is_only_consulted_for_the_worktree_this_attempt_ran_in(
    harness: LocalHarness, settings: Settings, log_path: Path
) -> None:
    a_store(settings, Path("/work/somebody/else"), STORED_SESSION)
    with_stream(log_path, "no-session")

    assert dispatch(harness, log_path).session_id is None


def test_a_process_killed_before_it_wrote_a_log_reports_what_it_can(
    harness: LocalHarness, log_path: Path
) -> None:
    result = dispatch(harness, log_path)

    assert result.session_id is None
    assert result.usage is None
    assert result.raw_result is None


def test_a_timeout_is_reported_with_the_group_rather_than_raised(
    settings: Settings, log_path: Path
) -> None:
    runner = FakeProcessRunner(default=Outcome(exit_code=None, timed_out=True))
    harness = LocalHarness(runner, settings)
    with_stream(log_path, "turn")

    result = dispatch(harness, log_path)

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.pgid is not None


def test_the_raw_result_is_handed_on_whole(harness: LocalHarness, log_path: Path) -> None:
    """AD-10: the adapter interprets nothing inside it."""
    with_stream(log_path, "turn")

    result = dispatch(harness, log_path)

    assert result.raw_result is not None
    assert result.raw_result["tokens"]["input"] == TOKENS_IN
    # the fields this system does not record survive verbatim, which is the whole rule
    assert result.raw_result["tokens"]["cache"] == {"read": 0, "write": 0}
    assert result.raw_result["role"] == "assistant"


# ── the two halves, and the group AD-14 wants killed ─────────────────────────


def test_start_hands_back_the_group_and_the_directory_before_anything_waits(
    harness: LocalHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """`preassign_session` is `False`, so the handle carries no session — and it carries the
    worktree, because only `wait` consults the store and only `start` was told the path."""
    handle = harness.start(
        cwd=WORKTREE,
        prompt=PROMPT,
        env=ENV,
        model=MODEL,
        session_id=PREASSIGNED,
        budget_usd_remaining=Decimal("12.5"),
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )

    assert handle.session_id == ""
    assert handle.cwd == WORKTREE
    assert handle.pgid is not None
    assert runner.called("wait") == []


def test_a_wait_that_raises_kills_the_group_it_was_handed(
    settings: Settings, log_path: Path
) -> None:
    """AD-14: the handle is the only thing that knows the `pgid`."""

    class Exploding(FakeProcessRunner):
        def wait(self, handle: object) -> Outcome:  # type: ignore[override]
            raise RuntimeError("boom")

    runner = Exploding()
    harness = LocalHarness(runner, settings)
    handle = harness.start(
        cwd=WORKTREE,
        prompt=PROMPT,
        env=ENV,
        model=MODEL,
        session_id=PREASSIGNED,
        budget_usd_remaining=Decimal("12.5"),
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )

    with pytest.raises(RuntimeError):
        harness.wait(handle)

    assert [call["pgid"] for call in runner.called("kill_group")] == [handle.pgid]


# ── resume: there is none, and that is stated rather than faked ──────────────


def test_there_is_no_paste_able_resume_line(harness: LocalHarness) -> None:
    """FR-21, 6.7: the read model hides the block for a harness with no resume form, and a
    line that looked resumable would be worse than none."""
    assert harness.resume_command(str(WORKTREE), SESSION_ID) is None


def test_resume_refuses_rather_than_quietly_starting_a_new_session(
    harness: LocalHarness, log_path: Path
) -> None:
    """`application/steps/agent.py` gates on `capabilities.resume`, so this is unreachable;
    a fresh dispatch here would silently discard the session the caller asked to continue."""
    with pytest.raises(NotImplementedError):
        harness.resume(
            cwd=WORKTREE,
            session_id=SESSION_ID,
            message="continue",
            env=ENV,
            timeout_min=TIMEOUT_MIN,
            log_path=log_path,
        )


# ── the aliases the script declares ──────────────────────────────────────────


def test_the_aliases_are_the_three_names_the_script_declares() -> None:
    """Third name added by the fix of 2026-09-20: OpenCode substitutes `{env:...}` into
    `opencode.json` before parsing it, so the tag list needs a rendering of its own."""
    assert set(local_aliases(CONTRACT)) == {
        "LANGFUSE_BASEURL",
        "LANGFUSE_USER_ID",
        "OPENCODE_LANGFUSE_TAGS",
    }


def test_the_plugin_is_keyed_by_the_run_the_attempt_belongs_to() -> None:
    """AD-11: `local` is found by user and session, and `LANGFUSE_USER_ID` is the whole of
    how the Run gets onto the generations the plugin sends."""
    assert local_aliases(CONTRACT)["LANGFUSE_USER_ID"] == CONTRACT["ORCH_RUN_ID"]


def test_the_plugin_spells_the_base_url_without_the_underscore() -> None:
    assert local_aliases(CONTRACT)["LANGFUSE_BASEURL"] == CONTRACT["LANGFUSE_BASE_URL"]


def test_the_builder_carries_no_credential_out_of_the_contract() -> None:
    """AD-5 by construction: the three aliases are a URL, an id and a tag list, so there is no
    value here a secret could travel in — asserted rather than assumed, because the contract
    has three."""
    values = set(local_aliases(CONTRACT).values())

    assert CONTRACT["LANGFUSE_SECRET_KEY"] not in values
    assert CONTRACT["LITELLM_API_KEY"] not in values


def test_the_tag_list_is_escaped_for_the_json_string_it_is_substituted_into() -> None:
    """The defect of 2026-09-20. `ORCH_LANGFUSE_TAGS` is a JSON array, and OpenCode expands
    `{env:NAME}` textually *before* it parses `opencode.json`, so the raw value's quotes
    terminated the string it was substituted into and the CLI exited 1 on every dispatch."""
    escaped = local_aliases(CONTRACT)["OPENCODE_LANGFUSE_TAGS"]

    assert '"' not in escaped.replace('\\"', "")
    assert escaped == CONTRACT["ORCH_LANGFUSE_TAGS"].replace('"', '\\"')
    assert json.loads(f'"{escaped}"') == CONTRACT["ORCH_LANGFUSE_TAGS"]


def test_the_plugins_two_names_are_still_copied_verbatim() -> None:
    """Only the tag list is rendered; an alias that escaped a value the plugin reads as an
    ordinary environment variable would hand it a literal backslash."""
    built = local_aliases(CONTRACT)

    assert built["LANGFUSE_BASEURL"] == CONTRACT["LANGFUSE_BASE_URL"]
    assert built["LANGFUSE_USER_ID"] == CONTRACT["ORCH_RUN_ID"]
