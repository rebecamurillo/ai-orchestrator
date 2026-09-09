"""`Alert.payload`: the parking record's own details, on the read model (story 6-6, AD-17).

`StepResult.payload` has carried AD-17's hit list to the gate record since 5.6, and nothing
read it back — `GateRecordOut` publishes no payload, so the protected-path body had no way
to render a file's added/deleted/modified mark or to link its diff. `build_alert` now
answers it off the same record list `run_detail` already reads for `gate_record`.

Read off the *record* rather than off `run.park_reason` for the reason `_needs_you_since`
already reads the records: the three park fields are overwritten by the next park, while the
records are append-only, so the record is where a stop's own details survive.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.rules.protected_paths import HITS_KEY, hits_payload
from orchestrator.application.use_cases.run_views_alert import build_alert
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change

NOW = datetime(2026, 9, 9, tzinfo=UTC)
BUILD = "stories[0].build"
HITS = (Change(path="tests/a.py", kind="modified"), Change(path="AGENTS.md", kind="added"))


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
        "park_kind": "protected_path",
        "park_path": BUILD,
        "park_reason": "protected path modified: tests/a.py, AGENTS.md",
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


def a_record(run: Run, event: str, payload: dict[str, object] | None = None) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=run.id,
        at=NOW,
        path=run.park_path,
        event=event,  # type: ignore[arg-type]
        actor="machine",
        text=run.park_reason or "",
        payload=payload or {},
    )


def alert_for(run: Run, records: tuple[GateRecord, ...]):  # type: ignore[no-untyped-def]
    return build_alert(
        run,
        None,
        row_kind="agent",
        rows=(),
        park_row=None,
        attempts_by_row={},
        records=records,
    )


def test_the_parking_records_payload_reaches_the_alert() -> None:
    run = a_run()
    alert = alert_for(run, (a_record(run, "protected_path", hits_payload(HITS)),))

    assert alert is not None
    assert alert.payload[HITS_KEY] == [
        {"path": "tests/a.py", "kind": "modified"},
        {"path": "AGENTS.md", "kind": "added"},
    ]


def test_the_latest_record_of_that_kind_wins() -> None:
    """A row retried and re-flagged parks twice; the Operator is answering the last one."""
    run = a_run()
    first = a_record(run, "protected_path", hits_payload((Change(path="old.py", kind="added"),)))
    second = a_record(run, "protected_path", hits_payload(HITS))

    alert = alert_for(run, (first, second))

    assert alert is not None
    assert [entry["path"] for entry in alert.payload[HITS_KEY]] == ["tests/a.py", "AGENTS.md"]


def test_a_record_of_another_kind_is_not_read() -> None:
    """`park_kind` is what picks the record, so a later `continue` does not become the stop."""
    run = a_run()
    records = (a_record(run, "protected_path", hits_payload(HITS)), a_record(run, "continue"))

    alert = alert_for(run, records)

    assert alert is not None
    assert HITS_KEY in alert.payload


def test_a_stop_that_kept_no_payload_answers_an_empty_one() -> None:
    run = a_run(park_kind="blocked", park_reason="intent gap")

    alert = alert_for(run, (a_record(run, "blocked"),))

    assert alert is not None
    assert alert.payload == {}


def test_a_park_whose_record_is_not_there_answers_an_empty_payload() -> None:
    """The read model never invents a stop's details; an unrecorded park has none."""
    run = a_run()

    alert = alert_for(run, ())

    assert alert is not None
    assert alert.payload == {}


def test_a_caller_that_passes_no_records_still_gets_an_alert() -> None:
    """`records` is defaulted, so every `build_alert(...)` construction predating this story
    keeps working — the same backward compatibility `row_kind` was added with (6.2)."""
    run = a_run()

    alert = build_alert(run, None, row_kind="agent", rows=(), park_row=None, attempts_by_row={})

    assert alert is not None
    assert alert.payload == {}
