"""The hit list as stored state: writing it, finding it again, reading it back (story 6-6).

AD-17's rule reports which anchors an attempt touched; `hits_payload` is how that answer
travels — onto `StepResult.payload`, and from there onto the park's own gate record
(`use_cases/writers.py::park_run`). Two readers take it back off: the Accept, which refuses
a file list that is not exactly this one (FR-31), and the Run detail's `Alert.payload`,
which renders each file's added/deleted/modified mark and its diff link.

Both readers are deliberately defensive. This is JSONB read back out of a column, written by
whichever version of this system parked the Run — so a shape that is not the one written
today is *no paths*, never a crash on a read, the same rule `rules/signals.py::
accepted_files` applies to a payload the Operator sent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.rules.protected_paths import (
    HITS_KEY,
    hit_paths,
    hits_payload,
    park_record_payload,
)
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change

NOW = datetime(2026, 9, 9, tzinfo=UTC)


def a_run(**over: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "needs_you",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


def a_record(run: Run, event: str, payload: dict[str, object]) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=run.id,
        at=NOW,
        event=event,  # type: ignore[arg-type]
        actor="machine",
        payload=payload,
    )


# ── writing it ───────────────────────────────────────────────────────────────


def test_a_change_keeps_its_kind_which_is_what_the_screen_marks() -> None:
    payload = hits_payload((Change(path="AGENTS.md", kind="added"),))

    assert payload == {HITS_KEY: [{"path": "AGENTS.md", "kind": "added"}]}


def test_a_plain_path_carries_no_kind_rather_than_an_invented_one() -> None:
    """The commit-guard's rule answers paths only (`ProtectedPaths.check`, frozen)."""
    assert hits_payload(("AGENTS.md",)) == {HITS_KEY: [{"path": "AGENTS.md"}]}


def test_an_empty_hit_list_is_still_a_recorded_shape() -> None:
    assert hits_payload(()) == {HITS_KEY: []}


# ── finding the record again ─────────────────────────────────────────────────


def test_the_record_matching_the_runs_own_park_kind_is_the_one_read() -> None:
    run = a_run(park_kind="protected_path", park_reason="x")
    records = (
        a_record(run, "blocked", {"other": 1}),
        a_record(run, "protected_path", hits_payload(("AGENTS.md",))),
    )

    assert hit_paths(park_record_payload(records, run)) == ("AGENTS.md",)


def test_a_run_that_is_not_parked_at_all_has_no_park_record() -> None:
    run = a_run(status="running")

    assert park_record_payload((a_record(run, "continue", {"x": 1}),), run) == {}


def test_a_park_whose_record_is_absent_answers_an_empty_payload() -> None:
    run = a_run(park_kind="protected_path", park_reason="x")

    assert park_record_payload((), run) == {}


# ── reading it back ──────────────────────────────────────────────────────────


def test_the_paths_come_back_in_the_order_the_rule_reported_them() -> None:
    payload = hits_payload((Change(path="b.py", kind="added"), Change(path="a.py", kind="deleted")))

    assert hit_paths(payload) == ("b.py", "a.py")


@pytest.mark.parametrize(
    "payload",
    [{}, {HITS_KEY: None}, {HITS_KEY: "AGENTS.md"}, {HITS_KEY: 3}],
    ids=["absent", "null", "bare string", "number"],
)
def test_a_payload_whose_hits_are_not_a_list_name_no_paths(payload: dict[str, object]) -> None:
    assert hit_paths(payload) == ()


@pytest.mark.parametrize(
    "entry",
    ["AGENTS.md", None, 7, {"kind": "added"}, {"path": 3}],
    ids=["string", "null", "number", "no path", "path is not a string"],
)
def test_an_entry_that_is_not_a_mapping_with_a_string_path_is_skipped(entry: object) -> None:
    """Skipped rather than raised: a stored shape this version does not recognise must not
    turn a Run detail into a 500."""
    payload = {HITS_KEY: [entry, {"path": "AGENTS.md", "kind": "added"}]}

    assert hit_paths(payload) == ("AGENTS.md",)
