"""The Accept: `continue` on a `protected_path` park (story 6-6, SPEC CAP-6, FR-31, AD-17).

This is the coverage that replaces `test_handle_signal.py::
test_continue_on_protected_path_is_refused_not_available_yet`, the pending-gate assertion
story 4-9 left for whichever story landed this gate. It asserts strictly more than that test
did: not only that the signal is no longer refused `not available yet`, but what it now does
— on an `agent` park and on a `git.commit` park, with the four ways a file list can be wrong.

**The hit list is the contract.** AD-17 stopped the Run naming exact files; an Accept says
"yes, those". A list that is not them is refused before anything is written, because a short
list would leave a hit unaccepted and park the resumed tail on the same file again, and a
long one would put a path into `run.accepted_paths` — which AD-17 subtracts on *every* later
check of the frame — that the Run never flagged.

No harness is called on any path here: AD-9 says an Accept re-applies the tail over the
previous attempt's own SHAs and dispatches nothing (`steps/agent_tail.py::re_check`, built
by 5.6 and given its first caller by this story).
"""

from __future__ import annotations

import pytest

from orchestrator.application.rules.protected_paths import hits_payload
from orchestrator.application.rules.signals import FILES_KEY, accepted_files
from orchestrator.application.steps.agent_tail import CONTINUE_EVENT
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

BUILD = "stories[0].build"
COMMIT_GUARD = "stories[0].commit-guard"
TEST_FILE = "tests/api/test_runs.py"
AGENTS = "AGENTS.md"
HITS = (Change(path=TEST_FILE, kind="modified"), Change(path=AGENTS, kind="added"))


def parked(path: str = BUILD, hits: tuple[Change, ...] = HITS, **over: object) -> World:
    """A Run stopped `protected_path` on one row, with the park's own record beside it."""
    fields: dict[str, object] = {
        "park_kind": "protected_path",
        "park_path": path,
        "park_reason": f"protected path modified: {TEST_FILE}, {AGENTS}",
    }
    fields.update(over)
    world = a_world("needs_you", EPIC_PLAN, {path: "error"}, **fields)
    world.ports.records.add(
        GateRecord(
            id=new_id(),
            run_id=world.run.id,
            at=world.clock.now(),
            path=path,
            event="protected_path",
            actor="machine",
            text=str(fields["park_reason"]),
            payload=hits_payload(hits),
        )
    )
    return world


def ports_for(world: World) -> SignalEffectPorts:
    return SignalEffectPorts(
        signal=world.signal_ports,
        git=FakeGit(),
        process=FakeProcessRunner(),
        work_dir="/work",
        read_environment=lambda _run_id: None,
    )


def accept(world: World, files: list[str]) -> object:
    signal = Signal(kind="continue", payload={FILES_KEY: files})
    return handle_signal(ports_for(world), world.run.id, signal)


def engine_calls(world: World) -> list[str]:
    return [name for name, _ in world.engine.calls]


def test_accepting_the_hits_records_them_and_resumes_the_row() -> None:
    """AC4: `accepted_paths` holds both, the row goes `error → running`, the Run resumes."""
    world = parked()

    accept(world, [TEST_FILE, AGENTS])

    stored = world.stored_run()
    assert stored.accepted_paths == (TEST_FILE, AGENTS)
    assert stored.status == "running"
    assert world.status_of(BUILD) == "running"
    assert engine_calls(world) == ["signal"]


def test_the_record_carries_the_files_and_names_them_in_its_text() -> None:
    """The brief's own voice: `accepted: tests/api/test_runs.py` is in the gate record."""
    world = parked()

    accept(world, [TEST_FILE, AGENTS])

    record = world.records()[-1]
    assert record.event == "continue"
    assert record.payload[FILES_KEY] == [TEST_FILE, AGENTS]
    assert record.text == f"accepted: {TEST_FILE}, {AGENTS}"


def test_an_accept_on_a_commit_guard_park_works_the_same_way() -> None:
    """AD-13 admits the Accept on either executor's park. The commit-guard's own rule
    answers paths without kinds (`ProtectedPaths.check`), so its hits carry none."""
    world = parked(COMMIT_GUARD, hits=(TEST_FILE, AGENTS))  # type: ignore[arg-type]

    accept(world, [TEST_FILE, AGENTS])

    assert world.stored_run().accepted_paths == (TEST_FILE, AGENTS)
    assert world.status_of(COMMIT_GUARD) == "running"


def test_the_order_the_operator_sent_the_files_in_does_not_matter() -> None:
    """The Operator is answering "yes to these files"; which order the list arrived in says
    nothing about that, so the two are compared as sets."""
    world = parked()

    accept(world, [AGENTS, TEST_FILE])

    assert world.stored_run().accepted_paths == (AGENTS, TEST_FILE)


@pytest.mark.parametrize(
    "files",
    [[], [TEST_FILE], [TEST_FILE, AGENTS, "src/other.py"], ["src/other.py"]],
    ids=["none", "short", "long", "wrong"],
)
def test_a_list_that_is_not_the_hits_is_a_409_naming_them(files: list[str]) -> None:
    """AC4's second half. Nothing is written on any of the four."""
    world = parked()

    with pytest.raises(Conflict, match="accepted files must be exactly the protected paths"):
        accept(world, files)

    stored = world.stored_run()
    assert stored.accepted_paths == ()
    assert (stored.status, stored.park_kind) == ("needs_you", "protected_path")
    assert world.status_of(BUILD) == "error"
    assert engine_calls(world) == []


def test_a_park_that_recorded_no_hit_list_at_all_is_refused() -> None:
    """Unreachable from a park this system writes today — both call sites of AD-17's rule
    record their hits — but a Run parked by an older backend carries no payload, and
    accepting nothing there would resume the tail onto the very files it stopped for."""
    world = parked(hits=())

    with pytest.raises(Conflict, match="no protected paths were recorded on this park"):
        accept(world, [])

    assert world.status_of(BUILD) == "error"


def test_a_continue_at_a_checkpoint_still_carries_no_files_and_its_own_sentence() -> None:
    """One kind, two park kinds, two sentences: the hit-list check is `protected_path`'s
    alone, and a checkpoint Continue keeps `continued by the operator`."""
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {"stories[1].after": "checkpoint"},
        park_kind="checkpoint",
        park_path="stories[1].after",
        park_reason="story checkpoint",
    )

    handle_signal(ports_for(world), world.run.id, Signal(kind="continue"))

    assert world.stored_run().accepted_paths == ()
    assert world.records()[-1].text == "continued by the operator"


def test_the_record_it_writes_is_what_the_executors_accept_branch_discriminates_on() -> None:
    """The seam between the two halves AD-9 splits this action across.

    `signal_run` writes the record; the walker hands it back to the row it resumed
    (`walk.py::_resume_signal`, keyed on the signal's kind), and `agent_tail.re_check` reads
    exactly two things off it to decide that this resume re-applies the tail instead of
    dispatching: the event, and whether the payload carries files. Neither half can drift
    without this failing.
    """
    world = parked()

    accept(world, [TEST_FILE, AGENTS])

    record = world.records()[-1]
    assert record.event == CONTINUE_EVENT
    assert accepted_files(record.payload) == (TEST_FILE, AGENTS)
