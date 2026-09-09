"""`skip_epic` through `handle_signal` (6.5, SPEC CAP-5, FR-20; binds AD-13).

Until this story the kind was refused `skip_epic not available yet` after `validate`
passed — 4.5's writer (`signal_effects.py::_skip_epic`) and AD-13's own table
(`rules/signals.py::VALID["skip_epic"]`) were both already correct and are proved whole by
`test_signal_run.py`/`test_signal_rules.py`. `tests/unit/application/test_handle_signal.py`'s
and `test_answer_signal_scope.py`'s pending-gate registries carried the refusal and this
story removed both rows; the tests below are the coverage that replaces them, run through
`handle_signal` rather than `signal_run` on purpose — the scope gate is the one thing this
story changed about the path.

The three scenarios are the brief's own three acceptance criteria, one test each, plus the
fourth (`budget` park refuses with AD-13's own 409, never reaching the scope gate at all).
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.signal_run import SignalOutcome
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.domain.errors import Conflict
from orchestrator.domain.statuses import StepStatus
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, INITIATIVE_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

WORK_DIR = "/work"


def parked(
    park_kind: str,
    park_path: str,
    row_status: StepStatus,
    plan: tuple[tuple[str, str], ...] = EPIC_PLAN,
    template_name: str = "epic",
    **rows: StepStatus,
) -> World:
    statuses: dict[str, StepStatus] = {park_path: row_status}
    statuses.update(rows)
    return a_world(
        "needs_you",
        plan,
        statuses,
        park_kind=park_kind,
        park_path=park_path,
        park_reason="why it stopped",
        template_name=template_name,
    )


def ports_for(world: World) -> SignalEffectPorts:
    return SignalEffectPorts(
        signal=world.signal_ports,
        git=FakeGit(),
        process=FakeProcessRunner(),
        work_dir=WORK_DIR,
        read_environment=lambda _run_id: None,
    )


def skip_epic(world: World) -> SignalOutcome:
    return handle_signal(ports_for(world), world.run.id, Signal(kind="skip_epic", payload={}))


def test_a_blocked_story_mid_epic_skips_the_remaining_story_frames_and_leaves_push_planned() -> (
    None
):
    """AC1: `epics[0].stories[1].build` blocked, `epics[1]` untouched, `epics[0].push`/
    `link` stay `planned` so the done work still reaches the remote."""
    world = parked(
        "blocked",
        "epics[0].stories[0].build",
        "blocked",
        plan=INITIATIVE_PLAN,
        template_name="initiative",
    )

    outcome = skip_epic(world)

    assert world.status_of("epics[0].stories[1].build") == "skipped"
    assert (world.status_of("epics[0].push"), world.status_of("epics[0].link")) == (
        "planned",
        "planned",
    )
    assert world.status_of("epics[0].stories[0].verify") == "queued"
    assert outcome.run.status == "running"
    assert "skip_epic" in world.events()


def test_a_rejected_push_skips_push_and_link_and_queues_the_next_epics_checkout() -> None:
    """AC2: `push_rejected` on `epics[0].push` — the variant the brief adds its own confirm
    sentence for."""
    world = parked(
        "push_rejected",
        "epics[0].push",
        "error",
        plan=INITIATIVE_PLAN,
        template_name="initiative",
    )

    outcome = skip_epic(world)

    assert world.status_of("epics[0].push") == "skipped"
    assert world.status_of("epics[0].link") == "skipped"
    assert world.status_of("epics[1].checkout") == "queued"
    assert outcome.run.status == "running"


def test_a_rejected_push_of_the_last_epic_ends_the_run_done() -> None:
    """The `epic`-template special case AD-13 admits without an `epics[i]` frame: this Run
    *is* the one epic, so `_has_epic_frame`'s `template_name == "epic"` branch is what admits
    the signal (`epic_frame("push")` is `None` — there is no bracket to read)."""
    world = parked("push_rejected", "push", "error")

    outcome = skip_epic(world)

    assert (world.status_of("push"), world.status_of("link")) == ("skipped", "skipped")
    assert outcome.run.status == "done"


def test_a_re_baseline_failed_after_skip_park_takes_the_error_verify_row_and_proceeds() -> None:
    """AC3: the `error` verify row a `re-baseline failed after skip` park left behind is
    itself skipped, and the frame's `git.commit` row is queued to run in its place."""
    world = parked("verify_failed", "stories[0].verify", "error")

    outcome = skip_epic(world)

    assert world.status_of("stories[0].verify") == "skipped"
    assert world.status_of("stories[0].commit-guard") == "queued"
    assert outcome.run.status == "running"


def test_a_budget_park_is_refused_by_ad13s_own_table_not_by_this_storys_scope_gate() -> None:
    """AC4: `skip_epic` is excluded from `VALID["skip_epic"].park_kinds` on a `budget` park,
    so `validate` refuses it before the scope gate this story widened is ever reached."""
    world = parked("budget", "stories[0].build", "blocked")

    with pytest.raises(Conflict, match="signal skip_epic invalid for status needs_you"):
        skip_epic(world)

    assert world.status_of("stories[0].build") == "blocked"
    assert world.engine.calls == []
