"""What a stop outside every loop offers the Operator: no skip with nothing to skip (FR-20).

AD-13's table is keyed on the park *kind*, so a `checkpoint` admits `skip_story` and
`skip_epic` wherever it happens — and `validate` still does, deliberately: a skip posted at a
stop that cannot use it is admissible and harmless, exactly as it is for the re-baseline case
`run_admitted_signals` already narrows.

What the Operator is *offered* is a different question, and an initialisation Template is the
first shape to ask it. A `context-review` row is a `checkpoint` declared at the top of a
Template's own file: no `stories[n]` and no `epics[n]` under `park_path`, so
`signals_table.py::_has_story_frame` and `_has_epic_frame` would both refuse a button this
set had already put on the screen — two dead controls on the one stop a repository's
onboarding has.

The frame reading here is the same one those two predicates make, so the offer and the
refusal cannot disagree. Since the Operator decision of 2026-09-30 (no template name
hardcoded in product code) the *shape of the plan* is what says whether a Run is one epic,
so each stop below is built with the rows a Run of that shape really has — the fixture plans
this suite owns, not a shipped Template's.
"""

from __future__ import annotations

from orchestrator.application.rules.signals import run_admitted_signals
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import (
    EPIC_PLAN,
    INITIATIVE_PLAN,
    build_rows,
    build_run,
)

#: An initialisation Run's own stop: the row's path is its step id, with no frame around it.
CONTEXT_REVIEW = "context-review"
#: A Story frame's own done checkpoint, for the contrast.
STORY_STOP = "stories[1].after"

#: The plan an initialisation Run has: no loop at all, so no frame anywhere.
INIT_PLAN: tuple[tuple[str, str], ...] = (
    ("checkout", "git.worktree"),
    (CONTEXT_REVIEW, "checkpoint"),
    ("install", "bmad.install"),
)


def a_stop(path: str, plan: tuple[tuple[str, str], ...] = INIT_PLAN) -> tuple[str, ...]:
    run = build_run(status="needs_you", park_kind="checkpoint", park_path=path)
    rows: list[StepRun] = build_rows(new_id(), plan)
    return run_admitted_signals(run, "checkpoint", rows=rows)


# ── the stop with no frame around it ────────────────────────────────────────


def test_a_checkpoint_outside_every_loop_offers_continue_skip_step_and_cancel() -> None:
    # story 1 (2026-09-25): skip_step is admitted on every park kind including checkpoint —
    # no frame predicate narrows it, so it appears even when there is no story or epic to skip.
    assert a_stop(CONTEXT_REVIEW) == ("continue", "skip_step", "cancel")


def test_it_offers_no_skip_story_because_there_is_no_story_to_skip() -> None:
    assert "skip_story" not in a_stop(CONTEXT_REVIEW)


def test_it_offers_no_skip_epic_because_there_is_no_epic_to_skip() -> None:
    assert "skip_epic" not in a_stop(CONTEXT_REVIEW)


def test_a_run_parked_on_no_path_at_all_offers_neither_skip() -> None:
    """Defensive: AD-8 writes `park_path` with the kind, but a missing one names no frame."""
    admitted = a_stop(None)  # type: ignore[arg-type]

    assert "skip_story" not in admitted
    assert "skip_epic" not in admitted


# ── what is unchanged ───────────────────────────────────────────────────────


def test_a_story_frames_own_checkpoint_still_offers_both_skips() -> None:
    """The case every Story Run has had since 5.10 — narrowing must not reach it."""
    admitted = a_stop(STORY_STOP, plan=EPIC_PLAN)

    assert "skip_story" in admitted
    assert "skip_epic" in admitted


def test_a_run_that_is_itself_one_epic_still_offers_skip_epic_anywhere_in_it() -> None:
    """`_has_epic_frame`'s own second clause, now read off the plan: a Run that loops over
    Stories and over nothing above them is one epic whatever the path — and whatever the
    Template is called."""
    assert "skip_epic" in a_stop("stories[0].build", plan=EPIC_PLAN)


def test_an_epic_frame_in_the_plan_still_offers_skip_epic() -> None:
    assert "skip_epic" in a_stop("epics[1].stories[0].build", plan=INITIATIVE_PLAN)


def test_a_caller_that_hands_over_no_rows_offers_skip_epic_only_on_an_epic_frame() -> None:
    """The list view's own conservative answer (`RunSummaryOut`): with no rows to read, only
    the parked path can say there is an epic to skip."""
    run = build_run(status="needs_you", park_kind="checkpoint", park_path="stories[0].build")

    assert "skip_epic" not in run_admitted_signals(run, "checkpoint")

    in_epic = build_run(
        status="needs_you", park_kind="checkpoint", park_path="epics[0].stories[0].build"
    )

    assert "skip_epic" in run_admitted_signals(in_epic, "checkpoint")
