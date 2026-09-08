"""The `Harness` port's two halves, and that `run` is still exactly one of them after the
other (AD-14, 5.4).

5.1 implemented `run` as one call that started and waited, and recorded the gap in
`domain/ports/harness.py`'s own docstring: AD-14 wants `attempt.pgid` stored *before* the
process is awaited, which one call cannot give. `start` → `HarnessHandle` → `wait` is the
split, and the property that makes it safe is asserted here rather than assumed: a dispatch
made through `run` and one made through the pair reach the runner with the same argv and
come back with the same result, so every frozen assertion about `run` still describes what
the adapter does.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.domain.ports.harness import Harness, HarnessHandle, HarnessResult
from orchestrator.domain.ports.process import Outcome
from orchestrator.infrastructure.harness import ClaudeHarness
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.harness import DEFAULT_PGID, FakeHarness
from tests.unit.fakes.process import FakeProcessRunner

SESSION_ID = "0199a1f2-7c3d-7b2a-9f21-0d1e2f3a4b5c"
PROMPT = "Run bmad-build-auto for story 5-4."
WORKTREE = Path("/work/acme/widgets/wt/feat-x")
BUDGET = Decimal("12.5")
TIMEOUT_MIN = 45.0
#: A group a test names itself, to prove the fake reports the one it was given.
SCRIPTED_PGID = 77
#: The first group `FakeProcessRunner` allocates — both `pid` and `pgid`, since nothing forks.
FIRST_GROUP = 1


@pytest.fixture
def runner() -> FakeProcessRunner:
    return FakeProcessRunner()


@pytest.fixture
def harness(runner: FakeProcessRunner, env: dict[str, str]) -> ClaudeHarness:
    return ClaudeHarness(runner, Settings())


def kwargs(log_path: Path) -> dict[str, object]:
    return {
        "cwd": WORKTREE,
        "prompt": PROMPT,
        "env": {"ORCH_RUN_ID": "r-1"},
        "model": "claude-opus-5",
        "session_id": SESSION_ID,
        "budget_usd_remaining": BUDGET,
        "timeout_min": TIMEOUT_MIN,
        "log_path": log_path,
    }


# ── the port ─────────────────────────────────────────────────────────────────


def test_the_port_declares_both_halves_beside_run() -> None:
    for member in ("run", "start", "wait", "resume", "resume_command"):
        assert member in Harness.__protocol_attrs__, member


def test_the_handle_carries_what_a_later_wait_and_a_later_kill_both_need() -> None:
    """`pid` and `pgid` both: `ProcessRunner.wait` takes a `Handle(pid, pgid)` (AD-14)."""
    handle = HarnessHandle(session_id="s-1", log_path=Path("/work/a.log"), pid=11, pgid=12)

    assert (handle.session_id, handle.log_path, handle.pid, handle.pgid) == (
        "s-1",
        Path("/work/a.log"),
        11,
        12,
    )


def test_the_handle_is_frozen() -> None:
    handle = HarnessHandle(session_id="s-1", log_path=Path("/work/a.log"), pid=11, pgid=12)

    with pytest.raises(AttributeError):
        handle.pgid = 13  # type: ignore[misc]


def test_both_implementations_still_satisfy_the_port(harness: ClaudeHarness) -> None:
    assert isinstance(harness, Harness)
    assert isinstance(FakeHarness(), Harness)


# ── the adapter ──────────────────────────────────────────────────────────────


def test_start_starts_the_process_and_waits_for_nothing(
    harness: ClaudeHarness, runner: FakeProcessRunner, tmp_path: Path
) -> None:
    handle = harness.start(**kwargs(tmp_path / "a.log"))  # type: ignore[arg-type]

    assert [call["method"] for call in runner.calls] == ["start"]
    assert handle.session_id == SESSION_ID
    assert handle.log_path == tmp_path / "a.log"
    # the runner's own group, carried through unchanged so a later `kill_group` reaches it
    assert (handle.pid, handle.pgid) == (FIRST_GROUP, FIRST_GROUP)


def test_wait_reports_the_group_the_session_and_the_log_the_handle_named(
    harness: ClaudeHarness, runner: FakeProcessRunner, tmp_path: Path
) -> None:
    log_path = tmp_path / "a.log"
    handle = harness.start(**kwargs(log_path))  # type: ignore[arg-type]

    result = harness.wait(handle)

    assert result.session_id == SESSION_ID
    assert result.log_path == log_path
    assert result.pgid == handle.pgid
    assert result.exit_code == 0


def test_run_is_start_then_wait_and_nothing_else(
    harness: ClaudeHarness, runner: FakeProcessRunner, tmp_path: Path
) -> None:
    log_path = tmp_path / "a.log"

    through_run = harness.run(**kwargs(log_path))  # type: ignore[arg-type]
    argv_from_run = runner.calls[0]["cmd"]
    runner.calls.clear()
    through_pair = harness.wait(harness.start(**kwargs(log_path)))  # type: ignore[arg-type]

    assert runner.calls[0]["cmd"] == argv_from_run
    assert through_pair.session_id == through_run.session_id
    assert through_pair.exit_code == through_run.exit_code
    assert through_pair.log_path == through_run.log_path


def test_a_wait_that_raises_still_kills_the_group_it_was_handed(
    harness: ClaudeHarness, runner: FakeProcessRunner, tmp_path: Path
) -> None:
    """The handle is the only thing that knows the `pgid`; losing it is AD-14's orphan."""
    handle = harness.start(**kwargs(tmp_path / "a.log"))  # type: ignore[arg-type]

    def explode(_handle: object) -> Outcome:
        raise KeyboardInterrupt

    runner.wait = explode  # type: ignore[method-assign]

    with pytest.raises(KeyboardInterrupt):
        harness.wait(handle)

    assert runner.called("kill_group") == [{"method": "kill_group", "pgid": handle.pgid}]


def test_resume_still_answers_the_session_it_was_given(
    harness: ClaudeHarness, runner: FakeProcessRunner, tmp_path: Path
) -> None:
    """`resume` goes through the same private start and the same public `wait`."""
    result = harness.resume(
        cwd=WORKTREE,
        session_id=SESSION_ID,
        message="the answer",
        env={},
        timeout_min=TIMEOUT_MIN,
        log_path=tmp_path / "b.log",
    )

    assert result.session_id == SESSION_ID
    assert [call["method"] for call in runner.calls] == ["start", "wait"]


# ── the fake ─────────────────────────────────────────────────────────────────


def test_the_fake_records_the_two_halves_under_their_own_names(tmp_path: Path) -> None:
    fake = FakeHarness()

    handle = fake.start(**kwargs(tmp_path / "a.log"))  # type: ignore[arg-type]
    fake.wait(handle)

    assert [call["method"] for call in fake.calls] == ["start", "wait"]
    assert fake.called("start")[0]["prompt"] == PROMPT
    assert handle.pgid == DEFAULT_PGID


def test_the_fakes_group_is_the_one_a_test_scripted(tmp_path: Path) -> None:
    fake = FakeHarness(pgid=SCRIPTED_PGID)

    assert fake.start(**kwargs(tmp_path / "a.log")).pgid == SCRIPTED_PGID  # type: ignore[arg-type]


def test_the_fakes_wait_consumes_the_same_script_run_does(tmp_path: Path) -> None:
    scripted = HarnessResult(session_id="s-9", exit_code=3, log_path=tmp_path / "a.log")
    fake = FakeHarness(results=[scripted])

    answered = fake.wait(fake.start(**kwargs(tmp_path / "a.log")))  # type: ignore[arg-type]

    assert answered is scripted


def test_the_fakes_hook_runs_before_wait_records_anything(tmp_path: Path) -> None:
    """`on_wait` is how a test reads the world at the instant the caller begins to block —
    which is the only vantage point AD-14's "pgid before the await" can be seen from."""
    seen: list[list[str]] = []
    fake = FakeHarness()
    fake.on_wait = lambda: seen.append([call["method"] for call in fake.calls])

    fake.wait(fake.start(**kwargs(tmp_path / "a.log")))  # type: ignore[arg-type]

    assert seen == [["start"]]


def test_a_fake_with_no_hook_simply_waits(tmp_path: Path) -> None:
    fake = FakeHarness()

    fake.wait(fake.start(**kwargs(tmp_path / "a.log")))  # type: ignore[arg-type]

    assert fake.on_wait is None
    assert [call["method"] for call in fake.calls] == ["start", "wait"]


def test_the_fake_still_leaves_exactly_one_entry_for_a_whole_run(tmp_path: Path) -> None:
    """`tests/unit/test_harness_port.py` is frozen and asserts that `run` logs one call."""
    fake = FakeHarness()

    fake.run(**kwargs(tmp_path / "a.log"))  # type: ignore[arg-type]

    assert [call["method"] for call in fake.calls] == ["run"]
