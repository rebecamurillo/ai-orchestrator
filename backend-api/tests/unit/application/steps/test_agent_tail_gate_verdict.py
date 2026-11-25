"""The `agent` tail records a `spec-gate` row's verdict on its result (epic 8 story 2, AC1-AC5)."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.steps import agent_tail, gate_verdict
from orchestrator.application.steps.context import StepContext
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_tail_fixtures import (
    LOG_PATH,
    SESSION_ID,
    SPEC_FOLDER,
    a_tail_world,
    contracted,
)
from tests.unit.fakes.harness import FakeHarness  # noqa: F401

GATE = f"{SPEC_FOLDER}/gate.md"


def gate_text(word: str, body: str = "- one\n- two\n") -> str:
    return f"---\nstatus: {word}\nowners: [ux, tech]\n---\n\n{body}"


def run_tail(role: str, files: dict[str, str], story: str | None = None) -> StepResult:
    expect = {
        "files": [GATE],
        "status_in": [],
        "success": ["pass", "fail"],
        "blocked": ["blocked"],
        "checkpoint": [],
        "misconfigured_when": [],
    }
    world = a_tail_world(story=story, files=files, with_resolved=contracted(expect=expect))
    ctx: StepContext = replace(world.ctx, row=world.row.model_copy(update={"role": role}))
    harness_result = HarnessResult(session_id=SESSION_ID, exit_code=0, log_path=LOG_PATH)
    return agent_tail.tail(ctx, world.attempt, harness_result)


def test_a_failing_gate_routes_done_with_its_verdict() -> None:
    result = run_tail("spec-gate", {GATE: gate_text("fail")})

    assert result.status == "done"
    assert result.verdict is not None
    assert result.verdict.word == "fail"
    assert result.verdict.fields["owners"] == ["ux", "tech"]
    assert (
        result.verdict.text == "\n- one\n- two\n".rstrip("\n")
        or result.verdict.text.strip() == "- one\n- two"
    )


def test_a_passing_gate_routes_done_with_its_word() -> None:
    result = run_tail("spec-gate", {GATE: gate_text("pass")})

    assert result.status == "done"
    assert result.verdict is not None and result.verdict.word == "pass"


def test_a_long_body_is_cut() -> None:
    result = run_tail("spec-gate", {GATE: gate_text("pass", "y" * 70_000)})

    assert result.verdict is not None
    assert result.verdict.text == ("\n" + "y" * 70_000)[: gate_verdict.VERDICT_TEXT_MAX]


def test_a_missing_gate_file_parks_without_a_verdict() -> None:
    result = run_tail("spec-gate", {})

    assert result.status != "done"
    assert result.verdict is None


def test_another_role_has_no_verdict() -> None:
    result = run_tail("implement", {GATE: gate_text("pass")})

    assert result.verdict is None
