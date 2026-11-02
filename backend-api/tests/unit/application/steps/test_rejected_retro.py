"""Story 2-2 (2026-11-02, CAP-9): a `rejected` retrospective parks the Run before it carries on.

A retro row routes through the row's own `expect` contract (AD-9, 2026-11-01 amendment) on a
marker that is not the retrospective document: `retro.md` under `stories/.auto/`, with
`rejected` under `expect.blocked`. Every behaviour below is asserted on a Template this module
owns, planned and executed through the shared fakes; no test reads a shipped Template (hard
rule 6), so the shipped rows are free to evolve.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.rules.signals import admitted_signals
from orchestrator.application.steps import agent_answer
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.context import StepContext
from orchestrator.application.templates.agent_row import EXPECT_KEY, RETRY_KEY
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    a_gate_record,
    an_attempt,
)
from tests.unit.application.steps.agent_tail_fixtures import a_tail_world
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.writer_fixtures import a_world as a_writer_world
from tests.unit.application.writer_fixtures import an_attempt as a_stored_attempt
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

SPEC_FOLDER = "docs/epic-1"
MARKER = f"{SPEC_FOLDER}/stories/.auto/retro.md"
DOCUMENT = f"{SPEC_FOLDER}/RETROSPECTIVE.md"
ARCHIVED = f"{SPEC_FOLDER}/stories/.auto/.answers/retro-attempt-1.md"

FINDINGS = "cross-association write is live (src/assoc.py:41); e2e assertion weakened (a1b2c3d)"

#: The epic tail this Template owns: a retro row on a marker of its own, then a row that
#: must not run while the retro stands rejected.
TEMPLATE = """name: retro-fixture
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  spec_folder: { type: path,       required: true }
  harness:     { type: enum, values: [claude, codex, local], default: claude }
steps:
  - id: retro
    uses: agent
    with:
      harness: "{{harness}}"
      skill: bmad-retrospective
      args: { folder: "{{spec_folder}}" }
      prompt_extra: >-
        Write the verdict to {{spec_folder}}/stories/.auto/retro.md, last.
    prompts:
      dispatch: "Run the skill {skill} in folder+id dispatch mode: spec folder {spec_folder}."
      rendered: "The workflow for skill {skill} is rendered at {path}."
      answer: 'Answer from the operator to the blocking condition "{condition}": {answer}'
    expect:
      files: ["{{spec_folder}}/stories/.auto/retro.md"]
      success: [accepted, accepted-with-open-items]
      blocked: [rejected]
    retry:
      max: 1
      prompt: "No readable retro marker; write it now."
      resume_session: true
    gate: liveness

  - id: commit-retro
    run: "true"
    gate: deterministic
"""


def planned_retro() -> dict[str, Any]:
    result = validate(TEMPLATE, templates=FakeTemplateVersionRepository([]))
    assert result.template is not None, result.errors
    plan = plan_run(
        ResolvedTree(root=result.template),
        fixtures.inputs(values={"spec_folder": SPEC_FOLDER}),
        git=FakeGit(refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA}, files={}, listings={}),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    return next(row for row in plan.rows if row.path == "retro").with_resolved


def marker(status: str, findings: str | None = None) -> str:
    lines = ["---", f"status: {status}", "---", "", "## Auto Run Result", "", f"Status: {status}"]
    if findings is not None:
        bullet = "- cross-association write: src/assoc.py:41"
        lines.extend([f"Blocking condition: {findings}", "", bullet])
    return "\n".join([*lines, ""])


def the_retro_row(**files: str) -> Any:
    """The planned retro row, dispatched as the row `retro`, with no Story behind it."""
    world = a_tail_world(story=None, files=dict(files), with_resolved=planned_retro())
    row = world.row.model_copy(update={"path": "retro", "story_id": None})
    return replace(world, ctx=replace(world.ctx, row=row), row=row)


def run(world: Any) -> StepResult:
    return AgentExecutor().execute(world.ctx)


# ── what the plan writes ─────────────────────────────────────────────────────


def test_the_plan_routes_the_retro_on_a_marker_that_is_not_the_document() -> None:
    expect = planned_retro()[EXPECT_KEY]

    assert expect["files"] == [MARKER]
    assert DOCUMENT not in expect["files"]
    assert expect["blocked"] == ["rejected"]
    assert expect["success"] == ["accepted", "accepted-with-open-items"]
    assert planned_retro()[RETRY_KEY]["max"] == 1


# ── the verdicts ─────────────────────────────────────────────────────────────


def test_a_rejected_verdict_parks_blocked_on_the_retro_row_with_its_findings() -> None:
    world = the_retro_row(**{MARKER: marker("rejected", FINDINGS), DOCUMENT: "# Retro"})

    result = run(world)

    assert result.status == "blocked"
    assert result.park is not None
    assert (result.park.kind, result.park.path) == ("blocked", "retro")
    assert f"Blocking condition: {FINDINGS}" in result.park.reason
    assert "src/assoc.py:41" in result.park.reason


@pytest.mark.parametrize("verdict", ["accepted", "accepted-with-open-items"])
def test_the_other_verdicts_do_not_park(verdict: str) -> None:
    world = the_retro_row(**{MARKER: marker(verdict), DOCUMENT: "# Retro"})

    result = run(world)

    assert result.status == "done"
    assert result.park is None


def test_a_retrospective_with_no_marker_is_not_taken_for_a_verdict() -> None:
    result = run(the_retro_row(**{DOCUMENT: "# Retro\n\nVerdict: rejected\n"}))

    assert result.park is not None
    assert (result.park.kind, result.park.reason) == ("misconfigured", "no story file")


def test_a_verdict_outside_the_three_spellings_takes_the_same_retry() -> None:
    result = run(the_retro_row(**{MARKER: marker("done")}))

    assert result.retry is not None
    assert result.reason == "unexpected status: done"


def test_the_document_alone_is_never_the_file_the_row_matches() -> None:
    world = the_retro_row(**{DOCUMENT: marker("rejected", FINDINGS)})

    run(world)

    assert DOCUMENT not in world.workspace.globbed
    assert MARKER in world.workspace.globbed


# ── the Run ──────────────────────────────────────────────────────────────────


def test_the_rejected_park_stops_the_run_before_the_next_row() -> None:
    result = run(the_retro_row(**{MARKER: marker("rejected", FINDINGS)}))
    world = a_writer_world(
        "running",
        (("retro", "agent"), ("commit-retro", "shell")),
        {"retro": "running"},
    )
    a_stored_attempt(world, "retro")

    apply_step_result(world.ports, world.run.id, 1, result)

    stored = world.stored_run()
    assert (stored.status, stored.park_kind, stored.park_path) == ("needs_you", "blocked", "retro")
    assert FINDINGS in (stored.park_reason or "")
    assert world.status_of("retro") == "blocked"
    assert world.status_of("commit-retro") == "planned"


# ── the human's way out (AD-13) ──────────────────────────────────────────────


def test_the_stop_admits_answer_and_skip_step_and_not_continue() -> None:
    admitted = admitted_signals("blocked", "agent")

    assert {"answer", "skip_step", "cancel"} <= set(admitted)
    assert "continue" not in admitted


def answered(world: Any) -> StepContext:
    previous = an_attempt(world.row, 1)
    record = a_gate_record(world.row, "answer", {"text": "the write is behind a flag"})
    return replace(world.ctx, previous_attempt=previous, resume_signal=record)


def test_an_answer_archives_the_marker_and_never_the_retrospective() -> None:
    world = the_retro_row(**{MARKER: marker("rejected", FINDINGS), DOCUMENT: "# Retro"})

    moved = agent_answer.archive_with_answer(answered(world))

    assert moved == (MARKER, ARCHIVED)
    assert world.workspace.read(MARKER) is None
    assert world.workspace.read(DOCUMENT) == "# Retro"
    archived = world.workspace.read(ARCHIVED) or ""
    assert FINDINGS in archived
    assert "the write is behind a flag" in archived
