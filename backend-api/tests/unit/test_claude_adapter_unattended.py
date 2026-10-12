"""`ClaudeHarness` for an unattended hub Run: streamed output, a resume that keeps the model
and the budget, and `--add-dir` for a dispatch that stands in a submodule.

O-1, O-2 and O-4 of `_bmad-output/specs/unattended-hub-run/PLAN.md` (2026-10-12). The
whole-argv shapes stay pinned in `test_claude_adapter.py`; this module pins what changed.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.domain.ports.harness import HarnessUsage
from orchestrator.infrastructure.harness.claude.adapter import ClaudeHarness
from orchestrator.infrastructure.harness.claude.result import result_object, usage_from
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

SESSION_ID = "0199a1f2-7c3d-7b2a-9f21-0d1e2f3a4b5c"
MODEL = "claude-opus-5"
HUB = Path("/work/acme/hub/wt/feat-x")
MEMBER = HUB / "repos" / "member"

#: A `claude -p --output-format stream-json --verbose` log, as the runner appends it: one
#: event per line, a stderr warning between two of them, the result envelope last.
STREAM_LOG = "\n".join(
    [
        json.dumps(
            {
                "type": "system",
                "subtype": "init",
                "session_id": SESSION_ID,
                "model": MODEL,
                "tools": ["Bash", "Edit", "Read"],
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "session_id": SESSION_ID,
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Reading the story."}],
                    "usage": {"input_tokens": 10, "output_tokens": 3},
                },
            }
        ),
        "npm warn deprecated something@1.0.0",
        json.dumps(
            {
                "type": "user",
                "session_id": SESSION_ID,
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "content": '{"a": 1}'}],
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "session_id": SESSION_ID,
                "total_cost_usd": 0.0342,
                "usage": {"input_tokens": 1200, "output_tokens": 340},
                "result": "done",
            }
        ),
        "",
    ]
)


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


def a_dispatch(harness: ClaudeHarness, log_path: Path, **over: object) -> None:
    fields: dict[str, object] = {
        "cwd": HUB,
        "prompt": "p",
        "env": {},
        "model": MODEL,
        "session_id": SESSION_ID,
        "budget_usd_remaining": Decimal("5"),
        "timeout_min": None,
        "log_path": log_path,
    }
    fields.update(over)
    harness.start(**fields)  # type: ignore[arg-type]


def a_resume(harness: ClaudeHarness, log_path: Path, **over: object) -> None:
    fields: dict[str, object] = {
        "cwd": HUB,
        "session_id": SESSION_ID,
        "message": "go on",
        "env": {},
        "timeout_min": None,
        "log_path": log_path,
    }
    fields.update(over)
    harness.resume(**fields)  # type: ignore[arg-type]


def after(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


# ── O-1: streamed output ────────────────────────────────────────────────────


def test_a_dispatch_streams_one_event_per_line(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    a_dispatch(harness, log_path)

    cmd = runner.called("start")[0]["cmd"]
    assert after(cmd, "--output-format") == "stream-json"
    assert "--verbose" in cmd


def test_a_resume_streams_too(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    a_resume(harness, log_path)

    cmd = runner.called("start")[0]["cmd"]
    assert after(cmd, "--output-format") == "stream-json"
    assert "--verbose" in cmd


def test_the_result_envelope_is_found_in_a_stream_log() -> None:
    found = result_object(STREAM_LOG)

    assert found is not None
    assert found["type"] == "result"
    assert found["session_id"] == SESSION_ID
    assert usage_from(found) == HarnessUsage(
        tokens_in=1200, tokens_out=340, cost_usd=Decimal("0.0342")
    )


def test_a_dispatch_reads_usage_and_the_envelope_out_of_a_stream_log(
    harness: ClaudeHarness, log_path: Path
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(STREAM_LOG)

    result = harness.run(
        cwd=HUB,
        prompt="p",
        env={},
        model=MODEL,
        session_id=SESSION_ID,
        budget_usd_remaining=Decimal("5"),
        timeout_min=None,
        log_path=log_path,
    )

    assert result.session_id == SESSION_ID
    assert result.usage == HarnessUsage(tokens_in=1200, tokens_out=340, cost_usd=Decimal("0.0342"))
    assert result.raw_result is not None
    assert result.raw_result["subtype"] == "success"


# ── O-2: resume keeps the model and the budget ──────────────────────────────


def test_a_resume_names_the_declared_model(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    a_resume(harness, log_path, model=MODEL)

    assert after(runner.called("start")[0]["cmd"], "--model") == MODEL


def test_a_resume_carries_the_remaining_budget(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    a_resume(harness, log_path, budget_usd_remaining=Decimal("3.499"))

    assert after(runner.called("start")[0]["cmd"], "--max-budget-usd") == "3.49"


def test_a_resume_told_no_model_and_no_budget_passes_neither(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    a_resume(harness, log_path)

    cmd = runner.called("start")[0]["cmd"]
    assert "--model" not in cmd
    assert "--max-budget-usd" not in cmd


def test_the_message_stays_last_on_a_resume_with_a_model(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    a_resume(harness, log_path, model=MODEL, budget_usd_remaining=Decimal("1"))

    assert runner.called("start")[0]["cmd"][-1] == "go on"


# ── O-4: --add-dir for a dispatch standing in a submodule ────────────────────


def test_a_dispatch_with_an_extra_directory_passes_add_dir(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    a_dispatch(harness, log_path, cwd=MEMBER, add_dirs=(HUB,))

    cmd = runner.called("start")[0]["cmd"]
    assert after(cmd, "--add-dir") == str(HUB)
    assert runner.called("start")[0]["cwd"] == MEMBER


def test_add_dir_is_followed_by_a_flag_so_its_variadic_list_never_swallows_the_prompt(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    """`--add-dir <directories...>` is variadic: the token after its value must be a flag."""
    a_dispatch(harness, log_path, cwd=MEMBER, add_dirs=(HUB,))

    cmd = runner.called("start")[0]["cmd"]
    assert cmd[cmd.index("--add-dir") + 2].startswith("--")
    assert cmd[-1] == "p"


def test_a_dispatch_with_no_extra_directory_passes_no_add_dir(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    a_dispatch(harness, log_path)

    assert "--add-dir" not in runner.called("start")[0]["cmd"]


def test_a_resume_with_an_extra_directory_passes_add_dir(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    a_resume(harness, log_path, cwd=MEMBER, add_dirs=(HUB,))

    assert after(runner.called("start")[0]["cmd"], "--add-dir") == str(HUB)


def test_run_forwards_the_extra_directory_to_start(
    harness: ClaudeHarness, runner: FakeProcessRunner, log_path: Path
) -> None:
    harness.run(
        cwd=MEMBER,
        prompt="p",
        env={},
        model=None,
        session_id=SESSION_ID,
        budget_usd_remaining=None,
        timeout_min=None,
        log_path=log_path,
        add_dirs=(HUB,),
    )

    assert after(runner.called("start")[0]["cmd"], "--add-dir") == str(HUB)
