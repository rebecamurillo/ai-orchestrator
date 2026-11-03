"""`session_end {confirmed_paths?}` (story 2-3, AD-23, AD-17, hard rule 1).

The close refuses while a turn runs and while an anchor edit made by the session's own
attempts is neither confirmed nor reverted. A clean close releases the lock and leaves the
Run parked on the same stop; confirmed files never join `run.accepted_paths`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.rules.session import TURNS_KEY
from orchestrator.application.use_cases import session_checks
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.signals import session_ports
from orchestrator.domain.errors import Conflict, Invalid
from orchestrator.domain.ports.git import Change
from orchestrator.domain.values import Signal
from tests.unit.application.session_fixtures import (
    BUILD,
    HEAD_SHA,
    SPEC_FOLDER,
    START_SHA,
    WORKTREE,
    SessionWorld,
    a_session_world,
)
from tests.unit.fakes.git import FakeGit

STORIES = f"{SPEC_FOLDER}/stories.yaml"
SPEC = f"{SPEC_FOLDER}/SPEC.md"
MEMBER = "repos/m"
ROOT_SHA = "c" * 40


def edited(*changes: Change, status: str = "", **trees: tuple[Change, ...]) -> FakeGit:
    return FakeGit(
        changes={WORKTREE: changes, **trees},
        statuses={WORKTREE: status},
        heads={WORKTREE: [HEAD_SHA]},
    )


def opened(git: FakeGit | None = None, **over: object) -> SessionWorld:
    session = a_session_world(git=git, **over)  # type: ignore[arg-type]
    session.start()
    return session


def refused(session: SessionWorld, error: type[Exception], **payload: object) -> str:
    before = (session.world.stored_run(), len(session.world.records()))

    with pytest.raises(error) as raised:
        session.send("session_end", **payload)

    assert (session.world.stored_run(), len(session.world.records())) == before
    return str(raised.value)


# ── clean ────────────────────────────────────────────────────────────────────


def test_a_session_with_no_turn_ends_and_the_run_stays_on_its_stop() -> None:
    session = opened()

    outcome = session.send("session_end")

    stored = session.world.stored_run()
    assert stored.senior_session is False
    assert (stored.status, stored.park_kind, stored.park_path) == ("needs_you", "blocked", BUILD)
    assert session.world.status_of(BUILD) == "blocked"
    assert outcome.resumed is False
    assert session.world.engine.calls == []
    record = session.world.records()[-1]
    assert (record.event, record.actor, record.path) == ("session_end", "operator", BUILD)
    assert record.payload == {TURNS_KEY: 0}
    assert record.text == "senior session ended"


def test_a_turn_that_touched_no_anchor_ends_cleanly() -> None:
    session = opened(edited(Change(path="src/app.py", kind="modified")))
    session.turn()

    session.send("session_end")

    assert session.world.stored_run().senior_session is False
    assert session.world.records()[-1].payload == {TURNS_KEY: 1}


def test_a_test_file_edit_is_not_an_anchor_edit() -> None:
    """AD-23: an Operator's test edit in conversation is declared under hard rule 1."""
    session = opened(edited(Change(path="tests/test_app.py", kind="modified")))
    session.turn(frozen_test_files=("tests/test_app.py",))

    session.send("session_end")

    assert session.world.stored_run().senior_session is False


def test_a_reverted_anchor_no_longer_differs_and_is_not_listed() -> None:
    """Turn 1 edits `stories.yaml` and turn 2 reverts it. The net diff from the session's
    first start SHA to HEAD holds nothing; turn 1's own range, read alone, would hold it."""
    git = FakeGit(
        diff_changes=[(), (Change(path=STORIES, kind="modified"),)],
        statuses={WORKTREE: ""},
        heads={WORKTREE: [HEAD_SHA]},
    )
    session = opened(git)
    session.turn(n=1, start_sha=START_SHA, end_sha=ROOT_SHA)
    session.turn(n=2, start_sha=ROOT_SHA, end_sha=HEAD_SHA)

    session.send("session_end")

    assert session.world.stored_run().senior_session is False
    assert git.called("diff_changes") == [(Path(WORKTREE), START_SHA, HEAD_SHA)]
    assert session.world.records()[-1].payload == {TURNS_KEY: 2}


def test_a_session_with_no_start_sha_has_no_edits() -> None:
    session = opened(edited(Change(path=STORIES, kind="modified")))
    session.turn(start_sha=None)

    session.send("session_end")

    assert session.world.stored_run().senior_session is False


def test_an_agent_attempt_on_the_row_is_not_a_turn() -> None:
    session = opened(edited(Change(path=STORIES, kind="modified")))
    session.turn(role="agent", ended_at=None)

    session.send("session_end")

    assert session.world.records()[-1].payload == {TURNS_KEY: 0}


def test_a_turn_of_an_earlier_session_is_not_this_sessions() -> None:
    session = opened(edited(Change(path=STORIES, kind="modified")))
    session.turn(ended_at=None)
    session.world.ports.runs.update(
        session.world.stored_run().model_copy(update={"senior_session": False})
    )
    session.world.clock.advance(60)
    session.start()

    session.send("session_end")

    assert session.world.stored_run().senior_session is False


# ── anchors ──────────────────────────────────────────────────────────────────


def test_an_unconfirmed_anchor_edit_is_refused_naming_it() -> None:
    session = opened(edited(Change(path=STORIES, kind="modified")))
    session.turn()

    message = refused(session, Conflict)

    assert message == f"anchor edits neither confirmed nor reverted: {STORIES}"


def test_the_diff_runs_from_the_first_start_sha_to_head() -> None:
    git = edited(Change(path=STORIES, kind="modified"))
    session = opened(git)
    session.turn(start_sha=START_SHA)
    session.turn(n=2, start_sha="d" * 40)

    refused(session, Conflict)

    assert git.called("diff_changes")[-1] == (Path(WORKTREE), START_SHA, HEAD_SHA)


def test_an_uncommitted_anchor_edit_counts_too() -> None:
    session = opened(edited(status=f" M {SPEC}\n?? {SPEC_FOLDER}/notes.md\n"))
    session.turn()

    assert refused(session, Conflict).endswith(SPEC)


def test_every_agents_md_and_the_initiative_epic_list_are_anchors() -> None:
    session = opened(
        edited(
            Change(path="docs/AGENTS.md", kind="added"),
            Change(path="initiatives/one/epics.yaml", kind="modified"),
        ),
        inputs={"spec_folder": SPEC_FOLDER, "initiative_folder": "initiatives/one"},
    )
    session.turn()

    message = refused(session, Conflict)

    assert message.endswith("docs/AGENTS.md, initiatives/one/epics.yaml")


def test_a_rows_own_spec_folder_is_an_anchor_folder() -> None:
    session = opened(
        edited(Change(path="specs/other/SPEC.md", kind="modified")),
        with_resolved={"stories[1].build": {"spec_folder": "specs/other"}},
    )
    session.turn()

    assert refused(session, Conflict).endswith("specs/other/SPEC.md")


def test_confirming_every_edit_releases_and_records_them() -> None:
    session = opened(edited(Change(path=STORIES, kind="modified")))
    session.turn()

    session.send("session_end", confirmed_paths=[STORIES])

    stored = session.world.stored_run()
    assert stored.senior_session is False
    assert stored.accepted_paths == ()
    record = session.world.records()[-1]
    assert record.payload == {"confirmed_paths": [STORIES], TURNS_KEY: 1}
    assert record.text == f"senior session ended; confirmed: {STORIES}"


def test_confirming_a_file_that_is_not_an_edit_is_invalid() -> None:
    session = opened(edited(Change(path=STORIES, kind="modified")))
    session.turn()

    message = refused(session, Invalid, confirmed_paths=[STORIES, "README.md"])

    assert message == "not an anchor edit of this session: README.md"


def test_a_confirmed_list_that_is_not_a_list_confirms_nothing() -> None:
    session = opened(edited(Change(path=STORIES, kind="modified")))
    session.turn()

    assert refused(session, Conflict, confirmed_paths=STORIES).endswith(STORIES)


def test_a_hub_session_names_both_trees_edits_as_ad_17_spells_hits() -> None:
    """The parked row declares `workdir`: the member's own `AGENTS.md` comes back prefixed,
    the hub's `SPEC.md` as it stands, and the gitlink pointer is never an edit."""
    member = f"{WORKTREE}/{MEMBER}"
    git = FakeGit(
        changes={
            member: (Change(path="AGENTS.md", kind="modified"),),
            WORKTREE: (
                Change(path=SPEC, kind="modified"),
                Change(path=MEMBER, kind="modified"),
            ),
        },
        statuses={member: "", WORKTREE: f" M {MEMBER}\n"},
        heads={member: [HEAD_SHA], WORKTREE: [ROOT_SHA]},
    )
    session = opened(git, with_resolved={BUILD: {"workdir": MEMBER}})
    session.turn(start_sha=START_SHA, root_start_sha="e" * 40)

    message = refused(session, Conflict)

    assert message == f"anchor edits neither confirmed nor reverted: {MEMBER}/AGENTS.md, {SPEC}"
    assert (Path(member), START_SHA, HEAD_SHA) in git.called("diff_changes")
    assert (Path(WORKTREE), "e" * 40, ROOT_SHA) in git.called("diff_changes")


def test_a_hub_session_without_a_root_start_sha_checks_the_member_only() -> None:
    member = f"{WORKTREE}/{MEMBER}"
    git = FakeGit(
        changes={member: (), WORKTREE: (Change(path=SPEC, kind="modified"),)},
        statuses={member: "", WORKTREE: ""},
        heads={member: [HEAD_SHA], WORKTREE: [ROOT_SHA]},
    )
    session = opened(git, with_resolved={BUILD: {"workdir": f"./{MEMBER}/"}})
    session.turn()

    session.send("session_end")

    assert session.world.stored_run().senior_session is False


def test_a_tree_whose_head_cannot_be_read_contributes_only_its_uncommitted_files() -> None:
    git = FakeGit(
        changes={WORKTREE: (Change(path=STORIES, kind="modified"),)},
        statuses={WORKTREE: f" M {SPEC}\n"},
        heads={WORKTREE: [None]},
    )
    session = opened(git)
    session.turn()

    assert refused(session, Conflict).endswith(f": {SPEC}")


# ── busy ─────────────────────────────────────────────────────────────────────


def test_an_open_turn_refuses_the_close() -> None:
    session = opened(edited())
    session.turn(ended_at=None)

    assert refused(session, Conflict) == "turn running"


def test_a_turn_that_started_after_the_check_is_caught_under_the_lock() -> None:
    """The anchor check counted no turn; one started before `signal_run` took the lock."""
    session = opened(edited())
    session.turn()
    signal = Signal(kind="session_end", payload={TURNS_KEY: 0})
    calls = session.world.ports.uow.calls
    before = len(calls)

    with pytest.raises(Conflict, match="turn running"):
        signal_run(session.ports.signal, session.world.run.id, signal)

    assert session.world.stored_run().senior_session is True
    assert "commit" not in calls[before:]


def test_a_turn_still_running_under_the_lock_is_caught_too() -> None:
    session = opened(edited())
    session.turn(ended_at=None)
    signal = Signal(kind="session_end", payload={TURNS_KEY: 1})

    with pytest.raises(Conflict, match="turn running"):
        signal_run(session.ports.signal, session.world.run.id, signal)


def test_a_close_that_skipped_the_anchor_check_is_refused() -> None:
    session = opened()

    with pytest.raises(Conflict, match="turn running"):
        signal_run(session.ports.signal, session.world.run.id, Signal(kind="session_end"))


def test_no_session_refuses_a_close() -> None:
    session = a_session_world()

    assert "signal session_end invalid for status needs_you" in refused(session, Conflict)


# ── the reads, at their edges ────────────────────────────────────────────────


def test_a_run_parked_on_no_row_has_no_turns() -> None:
    session = opened()
    session.turn()

    assert session_checks.turns(session_ports(session.ports), session.world.run, None) == ()


def test_a_run_with_no_worktree_has_no_anchor_edits() -> None:
    session = opened(edited(Change(path=STORIES, kind="modified")))
    session.turn()
    run = session.world.stored_run().model_copy(update={"worktree_path": None})
    rows = session.world.ports.steps.list_for_run(run.id)

    edits = session_checks.anchor_edits(
        session_ports(session.ports), run, rows, session.world.row(BUILD)
    )

    assert edits == ()
