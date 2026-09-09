"""`FakeHarness`: the scripted harness, against the port's own contract (AR-14, AD-10, AD-14).

Two things are worth proving about a test double that ships in `src/`. The first is that it
is a real `Harness` — the same three-way `start`/`wait`/`run` split, the same guarded wait,
the same "nothing interpreted" result — because a fake that took a shortcut through the port
would make every e2e scenario that runs on it prove a path production never takes. The
second is that it does exactly what the scenario says and nothing else: the writes land
where the liveness glob looks, and the process it starts carries the sleep, the commit and
the exit code the scenario declared.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.steps.agent import DISPATCH
from orchestrator.domain.ports.harness import Harness as HarnessPort
from orchestrator.domain.ports.process import Outcome
from orchestrator.infrastructure.harness.fake import FakeHarness
from orchestrator.infrastructure.harness.fake.adapter import (
    COMMIT_EMAIL,
    COMMIT_NAME,
    PROMPT_SUFFIX,
    SCRIPT_SUFFIX,
)
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

SPEC_FOLDER = "specs/gates"
STORY_ID = "1"
SESSION = "01a06887-79ab-759b-97a0-71c32ad939c2"

DONE = """
story_file:
  slug: notify
  content: |
    ---
    status: done
    ---
files:
  - path: NOTIFY.md
    content: |
      hello
commit: true
exit_code: 0
usage: { tokens_in: 12, tokens_out: 34, cost_usd: "0.05" }
"""


def a_prompt() -> str:
    return DISPATCH.format(skill="bmad-build-auto", spec_folder=SPEC_FOLDER, story_id=STORY_ID)


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    directory = tmp_path / "wt"
    (directory / ".fake-harness" / STORY_ID).mkdir(parents=True)
    return directory


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "run" / "001-1.log"


@pytest.fixture
def harness(env: dict[str, str], tmp_path: Path) -> FakeHarness:
    return FakeHarness(FakeProcessRunner(), Settings(work_dir=tmp_path / "work"))


def scripted(worktree: Path, text: str, name: str = "default.yaml") -> None:
    (worktree / ".fake-harness" / STORY_ID / name).write_text(text)


def dispatch(harness: FakeHarness, worktree: Path, log_path: Path, prompt: str | None = None):
    return harness.run(
        cwd=worktree,
        prompt=prompt if prompt is not None else a_prompt(),
        env={"ORCH_RUN_ID": "r"},
        model="claude-opus-5",
        session_id=SESSION,
        budget_usd_remaining=Decimal("5"),
        timeout_min=1.0,
        log_path=log_path,
    )


# ── the port ────────────────────────────────────────────────────────────────────────────


def test_it_is_the_harness_port_and_claims_only_what_it_does(harness: FakeHarness) -> None:
    assert isinstance(harness, HarnessPort)
    assert harness.name == "fake"
    assert harness.capabilities.preassign_session is True
    assert harness.capabilities.resume is True
    assert harness.capabilities.native_tracing is False


def test_run_is_exactly_wait_of_start(harness: FakeHarness, worktree: Path, log_path: Path) -> None:
    """AD-14's split, so the executor can commit `pgid` between the halves."""
    scripted(worktree, DONE)

    result = dispatch(harness, worktree, log_path)

    runner = harness.runner
    assert [call["method"] for call in runner.calls] == ["start", "wait"]  # type: ignore[attr-defined]
    assert result.session_id == SESSION
    assert result.pgid is not None
    assert result.exit_code == 0


def test_the_process_is_started_in_the_worktree_with_exactly_the_environment_given(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    """AD-5: the adapter adds no name of its own to what `env_for` built."""
    scripted(worktree, DONE)

    dispatch(harness, worktree, log_path)

    started = harness.runner.calls[0]  # type: ignore[attr-defined]
    assert started["cwd"] == worktree
    assert started["env"] == {"ORCH_RUN_ID": "r"}
    assert started["timeout_min"] == 1.0
    assert started["cmd"][0] == "sh"


def test_a_wait_that_raises_kills_the_group_before_the_exception_escapes(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    """AD-14: this frame holds the only reference to the group."""
    scripted(worktree, DONE)
    runner = harness.runner

    def exploding_wait(handle: object) -> Outcome:
        raise RuntimeError("the runner went away")

    handle = harness.start(
        cwd=worktree,
        prompt=a_prompt(),
        env={},
        model=None,
        session_id=SESSION,
        budget_usd_remaining=Decimal("0"),
        timeout_min=1.0,
        log_path=log_path,
    )
    runner.wait = exploding_wait  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        harness.wait(handle)

    assert [call["pgid"] for call in runner.calls if call["method"] == "kill_group"] == [
        handle.pgid
    ]


# ── what the scenario writes ────────────────────────────────────────────────────────────


def test_the_story_file_lands_where_the_liveness_glob_looks(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    scripted(worktree, DONE)

    dispatch(harness, worktree, log_path)

    story = worktree / SPEC_FOLDER / "stories" / f"{STORY_ID}-notify.md"
    assert story.read_text().startswith("---\nstatus: done\n---")
    assert (worktree / "NOTIFY.md").read_text() == "hello\n"


def test_echo_prompt_appends_what_the_agent_was_asked(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    """How an e2e reads back the Answer clause `agent.py::ANSWER` put on the prompt."""
    scripted(worktree, "story_file: { slug: notify, content: 'body' }\necho_prompt: true\n")

    dispatch(harness, worktree, log_path, prompt=f"{a_prompt()} Answer: post it")

    story = (worktree / SPEC_FOLDER / "stories" / f"{STORY_ID}-notify.md").read_text()
    assert story.endswith(f"## Prompt\n\n{a_prompt()} Answer: post it\n")


def test_a_scenario_with_no_story_file_writes_only_its_files(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    scripted(worktree, "files:\n  - { path: a/b.md, content: x }\n")

    dispatch(harness, worktree, log_path)

    assert (worktree / "a" / "b.md").read_text() == "x"
    assert not (worktree / SPEC_FOLDER).exists()


def test_the_prompt_is_recorded_beside_the_log(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    scripted(worktree, DONE)

    dispatch(harness, worktree, log_path)

    assert Path(f"{log_path}{PROMPT_SUFFIX}").read_text() == a_prompt()


# ── the script it runs ──────────────────────────────────────────────────────────────────


def script_of(log_path: Path) -> str:
    return Path(f"{log_path}{SCRIPT_SUFFIX}").read_text()


def test_the_script_sleeps_commits_and_exits_with_what_the_scenario_declared(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    scripted(worktree, "sleep_seconds: 0.5\ncommit: true\nexit_code: 7\n")

    dispatch(harness, worktree, log_path)

    script = script_of(log_path)
    assert "sleep 0.5" in script
    assert f"user.name={COMMIT_NAME}" in script
    assert f"user.email={COMMIT_EMAIL}" in script
    assert "'story 1: fake'" in script
    assert script.rstrip().endswith("exit 7")


def test_a_scenario_that_commits_nothing_runs_no_git_at_all(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    scripted(worktree, "exit_code: 0\n")

    dispatch(harness, worktree, log_path)

    assert "git" not in script_of(log_path)


def test_the_result_envelope_is_printed_only_when_the_scenario_reports_usage(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    """AD-11: no figures printed means unmeasured, not zero."""
    scripted(worktree, DONE)
    dispatch(harness, worktree, log_path)
    with_usage = script_of(log_path)

    scripted(worktree, "exit_code: 0\n", name="attempt-2.yaml")
    dispatch(harness, worktree, log_path)

    assert '"type": "result"' in with_usage
    assert '"total_cost_usd": "0.05"' in with_usage
    assert "printf" not in script_of(log_path)


def test_usage_is_read_back_out_of_the_log_the_way_a_real_harness_is_read(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    """The parser is `claude/result.py`'s, so the path under test is the production one."""
    scripted(worktree, DONE)
    handle = harness.start(
        cwd=worktree,
        prompt=a_prompt(),
        env={},
        model=None,
        session_id=SESSION,
        budget_usd_remaining=Decimal("0"),
        timeout_min=1.0,
        log_path=log_path,
    )
    log_path.write_text(
        json.dumps(
            {
                "type": "result",
                "total_cost_usd": "0.05",
                "usage": {"input_tokens": 12, "output_tokens": 34},
            }
        )
    )

    result = harness.wait(handle)

    assert result.usage is not None
    assert result.usage.cost_usd == Decimal("0.05")
    assert (result.usage.tokens_in, result.usage.tokens_out) == (12, 34)


def test_a_log_with_no_envelope_reports_no_usage(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    scripted(worktree, "exit_code: 0\n")

    result = dispatch(harness, worktree, log_path)

    assert result.usage is None
    assert result.raw_result is None


# ── the second dispatch ─────────────────────────────────────────────────────────────────


def test_each_dispatch_of_a_story_reads_the_next_scenario(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    scripted(worktree, "story_file: { slug: notify, content: first }", name="attempt-1.yaml")
    scripted(worktree, "story_file: { slug: notify, content: second }", name="attempt-2.yaml")
    story = worktree / SPEC_FOLDER / "stories" / f"{STORY_ID}-notify.md"

    dispatch(harness, worktree, log_path)
    first = story.read_text()
    dispatch(harness, worktree, log_path)

    assert first == "first"
    assert story.read_text() == "second"


def test_resume_takes_the_next_scenario_under_the_session_already_opened(
    harness: FakeHarness, worktree: Path, log_path: Path
) -> None:
    scripted(worktree, "story_file: { slug: notify, content: first }", name="attempt-1.yaml")
    scripted(worktree, "story_file: { slug: notify, content: second }", name="attempt-2.yaml")
    dispatch(harness, worktree, log_path)

    result = harness.resume(
        cwd=worktree,
        session_id=SESSION,
        message=a_prompt(),
        env={},
        timeout_min=1.0,
        log_path=log_path,
    )

    assert result.session_id == SESSION
    story = worktree / SPEC_FOLDER / "stories" / f"{STORY_ID}-notify.md"
    assert story.read_text() == "second"


def test_the_resume_command_names_the_scenarios_rather_than_a_session_that_does_not_exist(
    harness: FakeHarness,
) -> None:
    line = harness.resume_command("/work/wt/x", SESSION)

    assert line.startswith("cd /work/wt/x && ")
    assert SESSION in line
