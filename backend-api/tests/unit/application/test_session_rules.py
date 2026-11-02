"""`rules/session.py`: the senior session's pure half (story 2-3, AD-21, AD-23)."""

from __future__ import annotations

from datetime import timedelta

from orchestrator.application.rules import session
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from tests.unit.application.writer_fixtures import EPIC_PLAN, INITIATIVE_PLAN, build_rows
from tests.unit.fakes.clock import EPOCH

RUN_ID = new_id()
ROW_ID = new_id()


def a_record(event: str, seconds: int = 0, **payload: object) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=RUN_ID,
        at=EPOCH + timedelta(seconds=seconds),
        event=event,  # type: ignore[arg-type]
        actor="operator",
        payload=dict(payload),
    )


def an_attempt(n: int, seconds: int | None = 0, **over: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": RUN_ID,
        "step_run_id": ROW_ID,
        "n": n,
        "status": "done",
        "role": "session",
        "started_at": None if seconds is None else EPOCH + timedelta(seconds=seconds),
    }
    fields.update(over)
    return Attempt(**fields)  # type: ignore[arg-type]


def test_the_session_attempts_are_the_session_role_since_the_last_start() -> None:
    records = [a_record("session_start"), a_record("session_end", 5), a_record("session_start", 10)]
    before = an_attempt(1, 3)
    agent = an_attempt(2, 12, role="agent")
    unstarted = an_attempt(3, None)
    at_start = an_attempt(4, 10)
    after = an_attempt(5, 20)

    found = session.session_attempts([before, agent, unstarted, at_start, after], records)

    assert found == (at_start, after)


def test_no_start_record_means_no_session_attempts() -> None:
    assert session.session_attempts([an_attempt(1)], [a_record("blocked")]) == ()


def test_the_last_start_payload_is_read() -> None:
    records = [a_record("session_start", scope="story"), a_record("session_start", 1, scope="run")]

    assert session.last_start_payload(records) == {"scope": "run"}
    assert session.last_start_payload([]) == {}


def test_the_first_shas_are_the_first_recorded_per_tree() -> None:
    attempts = (
        an_attempt(1),
        an_attempt(2, start_sha="a", root_start_sha=None),
        an_attempt(3, start_sha="b", root_start_sha="r"),
    )

    assert session.first_shas(attempts) == ("a", "r")
    assert session.first_shas(()) == (None, None)


def test_an_open_turn_is_one_with_no_ended_at() -> None:
    assert session.turn_open((an_attempt(1, ended_at=EPOCH), an_attempt(2))) is True
    assert session.turn_open((an_attempt(1, ended_at=EPOCH),)) is False


def test_anchor_edits_exclude_tests_and_keep_agents_md_anywhere() -> None:
    changes = (
        Change(path="tests/test_a.py", kind="modified"),
        Change(path="pkg/AGENTS.md", kind="added"),
        Change(path="specs/x/SPEC.md", kind="modified"),
        Change(path="specs/x/SPEC.md", kind="modified"),
    )

    edits = session.anchor_edits(changes, frozenset({"specs/x/SPEC.md"}))

    assert [edit.path for edit in edits] == ["pkg/AGENTS.md", "specs/x/SPEC.md"]


def test_the_scopes_a_stop_admits() -> None:
    epic_rows = build_rows(RUN_ID, EPIC_PLAN)
    hub_rows = build_rows(RUN_ID, INITIATIVE_PLAN)

    assert session.scopes_at("stories[0].build", epic_rows) == ("story", "epic", "run")
    assert session.scopes_at("plan", hub_rows) == ("run",)
    assert session.scopes_at("epics[0].push", hub_rows) == ("epic", "run")
    assert session.scopes_at(None, hub_rows) == ()


def test_confirmed_paths_read_a_list_only() -> None:
    assert session.confirmed_paths({"confirmed_paths": ["a", 1]}) == ("a", "1")
    assert session.confirmed_paths({"confirmed_paths": "a"}) == ()
    assert session.confirmed_paths({}) == ()


def test_the_end_record_names_the_confirmed_files() -> None:
    assert session.ended_text({"confirmed_paths": ["a", "b"]}) == (
        "senior session ended; confirmed: a, b"
    )
    assert session.ended_text({}) is None
