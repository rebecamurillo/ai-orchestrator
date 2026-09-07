"""The `Harness` port's shape, and the one fake that satisfies it (AD-10, AD-18).

The port is what every adapter of Epic 5 and Epic 7 is measured against, so its own
construction is asserted here rather than only through `ClaudeHarness`: the defaults of
`HarnessResult` are what a 5.4 executor reads when a harness produced no usage at all, and
`HarnessCapabilities` is what tells that executor whether a session id may be pre-assigned
before the process starts.

`isinstance` against the protocol is the whole point of `runtime_checkable` here: it is the
only mechanical statement that `FakeHarness` and `ClaudeHarness` are the same thing to a
caller, which is what lets 5.4 and 5.5 test an executor against the fake.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from orchestrator.domain.ports.harness import (
    Harness,
    HarnessCapabilities,
    HarnessResult,
    HarnessUsage,
)
from orchestrator.infrastructure.harness import ClaudeHarness
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.process import FakeProcessRunner


def test_usage_carries_the_three_numbers_an_attempt_records() -> None:
    usage = HarnessUsage(tokens_in=120, tokens_out=45, cost_usd=Decimal("0.0342"))

    assert (usage.tokens_in, usage.tokens_out) == (120, 45)
    assert usage.cost_usd == Decimal("0.0342")


def test_capabilities_default_to_none_of_them() -> None:
    """A harness claims a capability; it never gets one by forgetting to say otherwise."""
    capabilities = HarnessCapabilities()

    assert capabilities.preassign_session is False
    assert capabilities.resume is False
    assert capabilities.native_tracing is False


def test_a_result_needs_only_what_every_harness_produces() -> None:
    result = HarnessResult(session_id="s-1", exit_code=0, log_path=Path("/work/logs/a.log"))

    assert result.usage is None
    assert result.raw_result is None
    assert result.timed_out is False
    assert result.pgid is None


def test_a_result_is_frozen() -> None:
    """AD-8: an executor reads a result; nothing edits one after the harness exited."""
    result = HarnessResult(session_id="s-1", exit_code=0, log_path=Path("/work/logs/a.log"))

    try:
        result.exit_code = 1  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("HarnessResult must be frozen")


def test_the_fake_satisfies_the_port() -> None:
    assert isinstance(FakeHarness(), Harness)


def test_the_claude_adapter_satisfies_the_port(env: dict[str, str]) -> None:
    """The adapter and the fake answer `isinstance` alike, or 5.4 cannot use the fake."""
    assert isinstance(ClaudeHarness(FakeProcessRunner(), Settings()), Harness)


def test_the_fake_records_every_dispatch_and_answers_the_scripted_result(tmp_path: Path) -> None:
    scripted = HarnessResult(session_id="s-9", exit_code=0, log_path=tmp_path / "a.log")
    fake = FakeHarness(results=[scripted])

    answered = fake.run(
        cwd=tmp_path,
        prompt="build story 5-1",
        env={"ORCH_RUN_ID": "r-1"},
        model="claude-opus-5",
        session_id="s-9",
        budget_usd_remaining=Decimal("12.5"),
        timeout_min=30.0,
        log_path=tmp_path / "a.log",
    )

    assert answered is scripted
    call = fake.calls[0]
    assert call["method"] == "run"
    assert call["prompt"] == "build story 5-1"
    assert call["env"] == {"ORCH_RUN_ID": "r-1"}
    assert call["cwd"] == tmp_path
    assert call["model"] == "claude-opus-5"
    assert call["session_id"] == "s-9"
    assert call["budget_usd_remaining"] == Decimal("12.5")


def test_the_fake_falls_back_to_a_default_result_when_the_script_runs_out(
    tmp_path: Path,
) -> None:
    fake = FakeHarness()

    first = fake.run(
        cwd=tmp_path,
        prompt="p",
        env={},
        model=None,
        session_id="s-1",
        budget_usd_remaining=Decimal("1"),
        timeout_min=1.0,
        log_path=tmp_path / "a.log",
    )
    second = fake.resume(
        cwd=tmp_path,
        session_id="s-1",
        message="the answer",
        env={},
        timeout_min=1.0,
        log_path=tmp_path / "b.log",
    )

    assert first.session_id == "s-1"
    assert second.session_id == "s-1"
    assert [call["method"] for call in fake.calls] == ["run", "resume"]
    assert fake.called("resume")[0]["message"] == "the answer"


def test_the_fake_reports_a_resume_command() -> None:
    assert FakeHarness().resume_command("/work/p/r/wt/feat-x", "abc") == (
        "cd /work/p/r/wt/feat-x && claude --resume abc"
    )
