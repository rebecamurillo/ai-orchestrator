"""What a stop outside every loop offers the Operator: no skip with nothing to skip (FR-20).

AD-13's table is keyed on the park *kind*, so a `checkpoint` admits `skip_story` and
`skip_epic` wherever it happens — and `validate` still does, deliberately: a skip posted at a
stop that cannot use it is admissible and harmless, exactly as it is for the re-baseline case
`run_admitted_signals` already narrows.

What the Operator is *offered* is a different question, and `repo-init@1` is the first
Template to ask it. Its `context-review` row is a `checkpoint` a Template declared at the top
of its own file: no `stories[n]` and no `epics[n]` under `park_path`, so
`signals_table.py::_has_story_frame` and `_has_epic_frame` would both refuse a button this
set had already put on the screen — two dead controls on the one stop a repository's
onboarding has.

The frame reading here is the same one those two predicates make, so the offer and the
refusal cannot disagree.
"""

from __future__ import annotations

from orchestrator.application.rules.signals import run_admitted_signals
from tests.unit.application.writer_fixtures import build_run

#: `repo-init@1`'s own stop: the row's path is its step id, with no frame around it.
CONTEXT_REVIEW = "context-review"
#: A Story frame's own done checkpoint, for the contrast.
STORY_STOP = "stories[1].after"


def a_stop(path: str, template: str = "repo-init") -> tuple[str, ...]:
    run = build_run(
        status="needs_you",
        park_kind="checkpoint",
        park_path=path,
        template_name=template,
    )
    return run_admitted_signals(run, "checkpoint")


# ── the stop with no frame around it ────────────────────────────────────────


def test_a_checkpoint_outside_every_loop_offers_continue_and_cancel_only() -> None:
    assert a_stop(CONTEXT_REVIEW) == ("continue", "cancel")


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
    admitted = a_stop(STORY_STOP, template="epic")

    assert "skip_story" in admitted
    assert "skip_epic" in admitted


def test_a_run_that_is_itself_one_epic_still_offers_skip_epic_anywhere_in_it() -> None:
    """`_has_epic_frame`'s own second clause: `epic@1` is an epic whatever the path says."""
    assert "skip_epic" in a_stop("stories[0].build", template="epic")


def test_an_initiatives_epic_frame_still_offers_skip_epic() -> None:
    assert "skip_epic" in a_stop("epics[1].stories[0].build", template="initiative")
