"""`session_view`: what `GET /runs/{id}/session` reads (story 2-3, AD-23)."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.session_view import session_view
from orchestrator.application.use_cases.signals import session_ports
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from tests.unit.application.session_fixtures import (
    HEAD_SHA,
    MODEL,
    SPEC_FOLDER,
    WORKTREE,
    SessionWorld,
    a_session_world,
)
from tests.unit.fakes.git import FakeGit

STORIES = f"{SPEC_FOLDER}/stories.yaml"


def view(session: SessionWorld):  # type: ignore[no-untyped-def]
    return session_view(session_ports(session.ports), session.world.run.id)


def test_a_stop_with_no_session_offers_one() -> None:
    found = view(a_session_world())

    assert found.active is False
    assert found.available is True
    assert found.scopes == ("story", "epic", "run")
    assert (found.scope, found.harness, found.model) == (None, None, None)
    assert found.anchor_edits == ()


def test_an_open_session_reads_its_payload_and_its_edits() -> None:
    git = FakeGit(
        changes={WORKTREE: (Change(path=STORIES, kind="modified"),)},
        statuses={WORKTREE: ""},
        heads={WORKTREE: [HEAD_SHA]},
    )
    session = a_session_world(git=git)
    session.start(scope="epic")
    session.turn()

    found = view(session)

    assert found.active is True
    assert found.available is False
    assert (found.scope, found.harness, found.model) == ("epic", "claude", MODEL)
    assert found.anchor_edits == (Change(path=STORIES, kind="modified"),)


def test_a_terminal_run_has_no_active_session() -> None:
    session = a_session_world()
    session.start()
    session.world.ports.runs.update(
        session.world.stored_run().model_copy(update={"status": "failed"})
    )

    found = view(session)

    assert (found.active, found.available, found.anchor_edits) == (False, False, ())


def test_a_run_not_parked_offers_no_scope() -> None:
    session = a_session_world(park_kind=None, park_path=None)
    session.world.ports.runs.update(
        session.world.stored_run().model_copy(update={"status": "running"})
    )

    found = view(session)

    assert (found.available, found.scopes) == (False, ())


def test_an_unknown_run_is_not_found() -> None:
    session = a_session_world()

    with pytest.raises(NotFound):
        session_view(session_ports(session.ports), new_id())
