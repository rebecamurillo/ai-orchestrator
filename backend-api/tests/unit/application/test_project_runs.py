"""`embedded_runs` (SPEC CAP-10, UX-DR12): the **RUNS ON THIS PROJECT** list.

The I/O half (`embedded_runs`, over `RunRepository`/`StepRunRepository`) is proven with the
shared fakes; the pure half (`_current_step_label`, `_terminal_reason`, `_token`) is proven
directly, the way `domain/entities/repository.py::CloneCheck.hint` — another derived,
never-stored field — is proven in its own module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from orchestrator.application.use_cases.project_runs import (
    CANCELLED_REASON,
    EMBED_LIMIT,
    embedded_runs,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 9, 6, tzinfo=UTC)
PROJECT_ID = new_id()
REPOSITORY_ID = new_id()


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "repo-init",
        "template_version": 1,
        "status": "running",
        "budget_usd": 0,
        "inputs": {"base_branch": "main"},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(run_id: UUID, seq: int, path: str, label: str, status: str, **over: object) -> StepRun:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": run_id,
        "seq": seq,
        "path": path,
        "label": label,
        "kind": "shell",
        "gate": "deterministic",
        "status": status,
    }
    fields.update(over)
    return StepRun(**fields)  # type: ignore[arg-type]


def summary_for(run: Run, steps: list[StepRun]) -> object:
    runs = FakeRunRepository([run])
    steps_repo = FakeStepRunRepository(steps)
    (summary,) = embedded_runs(runs, steps_repo, PROJECT_ID)
    return summary


# ── wiring: unwired ports, the embed limit ───────────────────────────────────────────────


def test_unwired_ports_answer_no_runs() -> None:
    assert embedded_runs(None, FakeStepRunRepository(), PROJECT_ID) == []
    assert embedded_runs(FakeRunRepository(), None, PROJECT_ID) == []


def test_the_list_is_capped_at_the_embed_limit() -> None:
    runs = [a_run(created_at=NOW) for _ in range(EMBED_LIMIT + 5)]

    result = embedded_runs(FakeRunRepository(runs), FakeStepRunRepository(), PROJECT_ID)

    assert len(result) == EMBED_LIMIT


def test_a_run_of_another_project_is_not_embedded() -> None:
    other = a_run(project_id=new_id())

    result = embedded_runs(FakeRunRepository([other]), FakeStepRunRepository(), PROJECT_ID)

    assert result == []


# ── token ─────────────────────────────────────────────────────────────────────────────────


def test_token_reads_the_status_for_every_non_parked_status() -> None:
    for status, token in [
        ("queued", "QUE"),
        ("running", "RUN"),
        ("done", "DON"),
        ("failed", "ERR"),
        ("cancelled", "CAN"),
    ]:
        summary = summary_for(a_run(status=status), [])
        assert summary.token == token, status


def test_token_reads_blk_for_a_park_that_is_not_a_checkpoint() -> None:
    run = a_run(status="needs_you", park_kind="blocked", park_path="build")

    summary = summary_for(run, [])

    assert summary.token == "BLK"


def test_token_reads_chk_for_a_checkpoint_park() -> None:
    run = a_run(status="needs_you", park_kind="checkpoint", park_path="review")

    summary = summary_for(run, [])

    assert summary.token == "CHK"


# ── current_step_label ───────────────────────────────────────────────────────────────────


def test_label_with_no_rows_is_empty() -> None:
    summary = summary_for(a_run(), [])

    assert summary.current_step_label == ""


def test_label_prefers_the_parked_row() -> None:
    run = a_run(status="needs_you", park_kind="blocked", park_path="install")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "blocked"),
        a_row(run.id, 3, "commit", "commit", "planned"),
    ]

    summary = summary_for(run, rows)

    assert summary.current_step_label == "install"


def test_label_falls_back_to_the_running_row_when_the_parked_path_names_no_row() -> None:
    """Defensive: a stored `park_path` should always name a real row, but the lookup does
    not assume it — falling through to the next check is the honest answer either way."""
    run = a_run(status="needs_you", park_kind="blocked", park_path="gone")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "running"),
    ]

    summary = summary_for(run, rows)

    assert summary.current_step_label == "install"


def test_label_falls_back_to_the_running_row() -> None:
    run = a_run(status="running")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "running"),
        a_row(run.id, 3, "commit", "commit", "planned"),
    ]

    summary = summary_for(run, rows)

    assert summary.current_step_label == "install"


def test_label_falls_back_to_the_next_queued_row() -> None:
    run = a_run(status="running")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "queued"),
        a_row(run.id, 3, "commit", "commit", "planned"),
    ]

    summary = summary_for(run, rows)

    assert summary.current_step_label == "install"


def test_label_is_the_last_row_touched_once_the_run_is_terminal() -> None:
    run = a_run(status="done")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "done"),
        a_row(run.id, 3, "link", "link", "done"),
    ]

    summary = summary_for(run, rows)

    assert summary.current_step_label == "link"


def test_label_is_the_first_row_before_anything_has_started() -> None:
    run = a_run(status="queued")
    rows = [
        a_row(run.id, 1, "plan", "plan", "planned"),
        a_row(run.id, 2, "checkout", "checkout", "planned"),
    ]

    summary = summary_for(run, rows)

    assert summary.current_step_label == "plan"


# ── reason ────────────────────────────────────────────────────────────────────────────────


def test_reason_is_empty_for_a_run_still_in_flight() -> None:
    for status in ("queued", "running", "needs_you", "done"):
        summary = summary_for(a_run(status=status), [])
        assert summary.reason == "", status


def test_reason_is_the_errored_rows_own_reason_for_a_failed_run() -> None:
    run = a_run(status="failed")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "error", reason="install failed: exit 1"),
    ]

    summary = summary_for(run, rows)

    assert summary.reason == "install failed: exit 1"


def test_reason_is_empty_when_a_failed_run_has_no_errored_row_to_read() -> None:
    """Defensive: `_fail` never runs without one, but the field itself is optional."""
    summary = summary_for(a_run(status="failed"), [])

    assert summary.reason == ""


def test_reason_is_the_fixed_sentence_for_a_cancelled_run() -> None:
    summary = summary_for(a_run(status="cancelled"), [])

    assert summary.reason == CANCELLED_REASON


# ── `is_init`: the configured Template, never a name written down here ────────────────────
# Operator decision 2026-09-30: no template name hardcoded in product code. The Projects
# screen used to decide "this Run initialised the Repository" by testing the Template's
# name client-side; `embedded_runs` answers it now, against `INIT_TEMPLATE` (AD-20).


def test_a_run_of_the_configured_init_template_is_marked() -> None:
    runs = FakeRunRepository([a_run(template_name="house-init")])

    (summary,) = embedded_runs(runs, FakeStepRunRepository(), PROJECT_ID, "house-init")

    assert summary.is_init is True


def test_a_run_of_any_other_template_is_not_marked() -> None:
    runs = FakeRunRepository([a_run(template_name="house-epic")])

    (summary,) = embedded_runs(runs, FakeStepRunRepository(), PROJECT_ID, "house-init")

    assert summary.is_init is False


def test_no_run_is_marked_when_no_init_template_is_wired() -> None:
    """`""` is the "not wired" value, and a Run whose `template_name` is also `""` must not
    become the init Run by accident."""
    runs = FakeRunRepository([a_run(template_name=""), a_run(template_name="house-init")])

    summaries = embedded_runs(runs, FakeStepRunRepository(), PROJECT_ID)

    assert [summary.is_init for summary in summaries] == [False, False]
