"""Story 2-1, AD-13's `pause` row read as rules: when it is admitted, what a paused stop offers,
and the token it renders."""

from __future__ import annotations

import pytest

from orchestrator.application.graph import _run_token as graph_token
from orchestrator.application.rules.signals import (
    VALID,
    admitted_signals,
    run_admitted_signals,
    validate,
)
from orchestrator.application.use_cases.project_runs import _token as board_token
from orchestrator.application.use_cases.run_views_alert import run_token
from orchestrator.domain.errors import Conflict
from orchestrator.domain.statuses import CHK_PARK_KINDS, PARK_KINDS, SIGNAL_KINDS
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, build_rows, build_run

BUILD = "stories[0].build"


def paused(**over: object):
    return build_run("needs_you", park_kind="paused", park_path=BUILD, park_reason="r", **over)


def queued_row():
    rows = build_rows(build_run().id, EPIC_PLAN, {BUILD: "queued"})
    return rows, next(row for row in rows if row.path == BUILD)


def test_the_new_kinds_are_named_by_the_alphabets() -> None:
    assert "paused" in PARK_KINDS
    assert "pause" in SIGNAL_KINDS
    assert CHK_PARK_KINDS == frozenset({"checkpoint", "paused"})


# ── pause: when it is admitted ───────────────────────────────────────────────


def test_a_pause_is_admitted_on_a_running_run_with_no_request() -> None:
    assert validate(build_run("running"), None, Signal(kind="pause")) is VALID["pause"]


def test_a_pause_is_refused_while_one_is_requested() -> None:
    with pytest.raises(Conflict, match="signal pause invalid for status running"):
        validate(build_run("running", pause_requested=True), None, Signal(kind="pause"))


@pytest.mark.parametrize("status", ["queued", "done", "failed", "cancelled"])
def test_a_pause_is_refused_outside_running(status: str) -> None:
    with pytest.raises(Conflict):
        validate(build_run(status), None, Signal(kind="pause"))  # type: ignore[arg-type]


def test_a_pause_is_refused_at_a_stop() -> None:
    rows, row = queued_row()
    with pytest.raises(Conflict):
        validate(paused(), row, Signal(kind="pause"), rows)


def test_a_pause_is_an_operator_action_with_its_own_sentence() -> None:
    rule = VALID["pause"]

    assert rule.operator_action
    assert rule.run_event is None
    assert rule.actor == "operator"
    assert "pause" in rule.text


# ── what a paused stop offers ────────────────────────────────────────────────


@pytest.mark.parametrize("row_kind", ["agent", "shell", "git.commit", "checkpoint"])
def test_a_paused_stop_offers_continue_and_cancel_whatever_the_row(row_kind: str) -> None:
    assert admitted_signals("paused", row_kind) == ("continue", "cancel")


def test_a_paused_run_offers_continue_and_cancel() -> None:
    rows, row = queued_row()

    offered = run_admitted_signals(paused(), row.kind, park_row_status=row.status, rows=rows)

    assert offered == ("continue", "cancel")


@pytest.mark.parametrize(
    "kind", ["answer", "retry", "skip_step", "skip_story", "skip_epic", "terminal_start"]
)
def test_a_paused_stop_refuses_everything_else_even_on_a_story_row(kind: str) -> None:
    rows, row = queued_row()

    with pytest.raises(Conflict, match="park paused"):
        validate(paused(), row, Signal(kind=kind), rows)  # type: ignore[arg-type]


def test_a_paused_stop_accepts_continue_and_cancel() -> None:
    rows, row = queued_row()

    assert validate(paused(), row, Signal(kind="continue"), rows) is VALID["continue"]
    assert validate(paused(), row, Signal(kind="cancel"), rows) is VALID["cancel"]


def test_a_running_run_offers_pause_beside_cancel() -> None:
    assert run_admitted_signals(build_run("running"), None) == ("pause", "cancel")


def test_a_running_run_with_a_request_offers_cancel_only() -> None:
    assert run_admitted_signals(build_run("running", pause_requested=True), None) == ("cancel",)


def test_a_queued_run_never_offers_pause() -> None:
    assert run_admitted_signals(build_run("queued", engine_ref={"ref": 1}), None) == ("cancel",)


# ── the token ────────────────────────────────────────────────────────────────


def test_a_paused_run_renders_chk_on_every_reader() -> None:
    run = paused()

    assert (run_token(run), board_token(run), graph_token(run)) == ("CHK", "CHK", "CHK")


def test_other_stops_still_render_blk() -> None:
    run = build_run("needs_you", park_kind="blocked", park_path=BUILD, park_reason="r")

    assert (run_token(run), board_token(run), graph_token(run)) == ("BLK", "BLK", "BLK")
