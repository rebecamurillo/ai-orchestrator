"""`next_run` through `advance_initiative` (epic 8 story 3, AC1, AC3-AC7, AC9-AC11).

Every template and sequence is `initiative_transition_world`'s own fixture (hard rule 6)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.use_cases import initiative_next
from orchestrator.application.use_cases.initiative_advance import advance_initiative
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.git import CloneResult, GitError
from tests.unit.application.initiative_transition_world import (
    BUILD,
    FEAT_SHA,
    MAIN_SHA,
    MERGE,
    PLAIN_BUILD,
    PROJECT_BUDGET,
    SLUG,
    SPEC,
    SPEC_BUDGET,
    TransitionWorld,
)

FEAT = f"feat/{SLUG}"


def run_advance(world: TransitionWorld, advance: InitiativeAdvance) -> InitiativeAdvance:
    advance_initiative(world.advance_ports(), advance.id)
    return next(a for a in world.advances.advances if a.id == advance.id)


def created(world: TransitionWorld, position: int, round_: int = 1) -> list[Run]:
    return [
        r
        for r in world.runs.runs.values()
        if r.initiative_id == world.initiative_row.id
        and (r.initiative_position, r.initiative_round) == (position, round_)
        and r.status != "done"
    ]


def branch_calls(world: TransitionWorld) -> list[str]:
    names = {"create_remote_branch", "fast_forward_remote_branch"}
    return [name for name, _ in world.remote.calls if name in names]


# --- AC1 -----------------------------------------------------------------------------------


def test_ac1_a_pass_with_a_clean_preflight_creates_the_merge_run() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=True)
    spec, advance = world.spec_run("pass")

    stored = run_advance(world, advance)

    [merge] = created(world, 1)
    assert stored.consumed_at is not None and stored.blocked_reason is None
    assert (merge.template_name, merge.template_version) == MERGE
    assert merge.lane == "walk"
    assert merge.budget_usd == SPEC_BUDGET
    assert merge.inputs["harness"] == spec.inputs["harness"]
    assert merge.inputs["model"] == spec.inputs["model"]
    assert merge.inputs["initiative_folder"] == "initiatives"
    assert merge.inputs["branch"] == "main"
    assert ("enqueue", (merge.id, f"{world.hub.id}:main", "walk")) in world.harness.engine.calls


def test_ac1_the_build_preflight_reads_the_spec_branch() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=True)
    _, advance = world.spec_run("pass")

    run_advance(world, advance)

    reads = [args for name, args in world.remote.calls if name == "read_file"]
    assert {ref for _, ref, path in reads if path.endswith("epics.yaml")} == {"d" * 40}


# --- AC3, AC4 ------------------------------------------------------------------------------


def test_ac3_a_missing_epics_file_reopens_the_tech_step() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    _, advance = world.spec_run("pass")

    stored = run_advance(world, advance)

    assert stored.consumed_at is not None
    assert world.initiatives.initiatives[world.initiative_row.id].round == 2  # noqa: PLR2004
    [reopened] = created(world, 0, 2)
    assert reopened.inputs["round_steps"] == "tech"
    first_turn = reopened.inputs["first_turn"]
    assert first_turn.startswith("epics.yaml: ") and "list file not found" in first_turn
    assert first_turn.count("list file not found") == 1
    assert created(world, 1) == []


def test_ac3_a_spec_run_without_a_conversation_row_has_no_owner_for_the_defect() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=False)
    _, advance = world.spec_run("pass", talks=False)

    stored = run_advance(world, advance)

    assert (stored.consumed_at, stored.blocked_reason) == (None, "gate failed with no owner")


def test_ac4_a_failure_that_is_not_a_spec_file_blocks_without_a_run() -> None:
    world = TransitionWorld(probes=False)
    world.spec_branch(epics=True)
    _, advance = world.spec_run("pass")

    stored = run_advance(world, advance)

    assert stored.consumed_at is None
    assert (stored.blocked_reason or "").startswith("preflight: harness: ")
    assert created(world, 1) == [] and created(world, 0, 2) == []


# --- AC5, AC6 ------------------------------------------------------------------------------


def test_ac5_a_fail_reopens_the_owners_in_step_order() -> None:
    world = TransitionWorld()
    _, advance = world.spec_run("fail", owners=["tech", "ux"], text="- one\n- two")

    stored = run_advance(world, advance)

    assert stored.consumed_at is not None
    [reopened] = created(world, 0, 2)
    assert reopened.inputs["round_steps"] == "ux,tech"
    assert reopened.inputs["first_turn"] == "- one\n- two"
    assert world.initiatives.initiatives[world.initiative_row.id].round == 2  # noqa: PLR2004


@pytest.mark.parametrize(
    ("owners", "reason"),
    [
        (["deploy"], "gate owner deploy is not a step of fx.spec"),
        ([], "gate failed with no owner"),
        (None, "gate failed with no owner"),
        ("tech", "gate failed with no owner"),
    ],
)
def test_ac5_a_fail_that_names_no_usable_owner_blocks(owners: Any, reason: str) -> None:
    world = TransitionWorld()
    _, advance = world.spec_run("fail", owners=owners)

    stored = run_advance(world, advance)

    assert (stored.consumed_at, stored.blocked_reason) == (None, reason)
    assert created(world, 0, 2) == []


@pytest.mark.parametrize(
    ("word", "reason"),
    [("maybe", "gate word maybe is not declared"), (None, "no gate verdict")],
)
def test_ac6_an_undeclared_word_or_no_verdict_blocks(word: str | None, reason: str) -> None:
    world = TransitionWorld()
    _, advance = world.spec_run(word)

    stored = run_advance(world, advance)

    assert (stored.consumed_at, stored.blocked_reason) == (None, reason)
    assert created(world, 1) == []


# --- AC7, AC9 ------------------------------------------------------------------------------


def a_merge_done(world: TransitionWorld) -> InitiativeAdvance:
    return world.advance_of(world.ended_run(1))


def test_ac7_a_merge_done_creates_feat_then_the_build_with_the_project_defaults() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=True)
    world.defaults(
        default_budget_usd=PROJECT_BUDGET,
        default_harness="claude",
        default_model="sonnet",
        default_senior_model="opus",
    )
    advance = a_merge_done(world)

    stored = run_advance(world, advance)

    assert stored.consumed_at is not None
    [(_, (base_dir, branch, sha))] = [
        c for c in world.remote.calls if c[0] == "create_remote_branch"
    ]
    assert (base_dir, branch, sha) == (world.base_dir, FEAT, MAIN_SHA)
    [build] = created(world, 2)
    assert (build.template_name, build.template_version) == BUILD
    assert build.budget_usd == PROJECT_BUDGET
    assert build.inputs["harness"] == "claude"
    assert (build.inputs["model"], build.inputs["plan_model"], build.inputs["review_model"]) == (
        "sonnet",
        "sonnet",
        "sonnet",
    )
    assert build.inputs["senior_model"] == "opus"
    assert build.inputs["initiative_folder"] == f"initiatives/{SLUG}"
    assert build.inputs["branch"] == FEAT


def test_ac7_a_main_missing_from_the_remote_blocks() -> None:
    world = TransitionWorld()
    world.defaults(default_budget_usd=PROJECT_BUDGET)
    assert world.remote.refs is not None
    del world.remote.refs["main"]

    stored = run_advance(world, a_merge_done(world))

    assert stored.blocked_reason == "branch main is not on the hub's remote"
    assert branch_calls(world) == []


def test_ac8_without_a_project_budget_nothing_is_touched() -> None:
    world = TransitionWorld()
    world.defaults(default_budget_usd=None)

    stored = run_advance(world, a_merge_done(world))

    assert (stored.consumed_at, stored.blocked_reason) == (None, "no project budget")
    assert branch_calls(world) == [] and created(world, 2) == []
    assert [name for name, _ in world.remote.calls if name == "ls_remote"] == []


def test_ac9_a_feat_branch_at_main_is_attached_as_it_is() -> None:
    world = TransitionWorld()
    world.defaults(default_budget_usd=PROJECT_BUDGET, default_harness="claude")
    assert world.remote.refs is not None
    world.remote.refs[FEAT] = MAIN_SHA

    stored = run_advance(world, a_merge_done(world))

    assert stored.consumed_at is not None
    assert branch_calls(world) == []
    assert len(created(world, 2)) == 1


def test_ac9_a_feat_branch_behind_main_is_fast_forwarded() -> None:
    world = TransitionWorld()
    world.defaults(default_budget_usd=PROJECT_BUDGET, default_harness="claude")
    assert world.remote.refs is not None
    world.remote.refs[FEAT] = FEAT_SHA
    world.remote.analysis.merge_bases[(FEAT_SHA, MAIN_SHA)] = FEAT_SHA

    stored = run_advance(world, a_merge_done(world))

    assert stored.consumed_at is not None
    [(_, arguments)] = [c for c in world.remote.calls if c[0] == "fast_forward_remote_branch"]
    assert arguments == (world.base_dir, FEAT, MAIN_SHA)
    assert len(created(world, 2)) == 1


def test_ac9_a_feat_branch_not_from_main_blocks() -> None:
    world = TransitionWorld()
    world.defaults(default_budget_usd=PROJECT_BUDGET, default_harness="claude")
    assert world.remote.refs is not None
    world.remote.refs[FEAT] = FEAT_SHA
    world.remote.analysis.merge_bases[(FEAT_SHA, MAIN_SHA)] = "e" * 40

    stored = run_advance(world, a_merge_done(world))

    assert stored.consumed_at is None
    assert stored.blocked_reason == f"feat/{SLUG} exists and is not from main; delete it or reopen"
    assert branch_calls(world) == [] and created(world, 2) == []


def test_a_refused_branch_write_is_a_failure_that_blocks() -> None:
    world = TransitionWorld()
    world.defaults(default_budget_usd=PROJECT_BUDGET, default_harness="claude")
    world.remote._create_script = [GitError(command="push", exit_code=1, output="denied")]

    stored = run_advance(world, a_merge_done(world))

    assert (stored.blocked_reason or "").startswith("advance failed:")


def test_no_remote_branch_port_is_a_failure_that_blocks() -> None:
    world = TransitionWorld()
    world.defaults(default_budget_usd=PROJECT_BUDGET)
    ports = replace(world.advance_ports(), branches=None)
    advance = a_merge_done(world)

    advance_initiative(ports, advance.id)

    stored = next(a for a in world.advances.advances if a.id == advance.id)
    assert (stored.blocked_reason or "").startswith("advance failed:")


def test_a_missing_base_clone_is_cloned_first() -> None:
    world = TransitionWorld(scripts={"base_exists": [False], "clone_base": [CloneResult(0.0, 0)]})
    world.defaults(default_budget_usd=PROJECT_BUDGET, default_harness="claude")

    run_advance(world, a_merge_done(world))

    names = [name for name, _ in world.remote.calls]
    assert (
        names.index("clone_base") < names.index("fetch_base") < names.index("create_remote_branch")
    )


# --- AC10 ----------------------------------------------------------------------------------


def test_ac10_a_done_build_creates_nothing_and_is_consumed() -> None:
    world = TransitionWorld()
    advance = world.advance_of(world.ended_run(2))

    stored = run_advance(world, advance)

    assert stored.consumed_at is not None
    assert world.harness.engine.calls == []


def test_ac10_a_done_run_of_another_entry_blocks() -> None:
    world = TransitionWorld()
    sequence = world.initiative_row.sequence
    other = sequence.workflows[1].model_copy(update={"type": "auto", "shown_as": "workflow"})
    odd = sequence.model_copy(
        update={"workflows": (sequence.workflows[0], sequence.workflows[2], other)}
    )
    world.initiatives.update(world.initiative_row.model_copy(update={"sequence": odd}))
    advance = world.advance_of(world.ended_run(2))

    stored = run_advance(world, advance)

    assert stored.blocked_reason == "no transition for merge"


# --- AC11 ----------------------------------------------------------------------------------


def test_ac11_the_default_autonomy_reaches_a_build_that_declares_it() -> None:
    world = TransitionWorld()
    world.defaults(
        default_budget_usd=PROJECT_BUDGET, default_harness="claude", default_autonomy="checkpoints"
    )

    run_advance(world, a_merge_done(world))

    [build] = created(world, 2)
    assert build.inputs["autonomy"] == "checkpoints"


def test_ac11_a_build_that_does_not_declare_it_is_offered_nothing() -> None:
    world = TransitionWorld(build=PLAIN_BUILD)
    world.defaults(
        default_budget_usd=PROJECT_BUDGET, default_harness="claude", default_autonomy="checkpoints"
    )

    run_advance(world, a_merge_done(world))

    [build] = created(world, 2)
    assert "autonomy" not in build.inputs and "senior_model" not in build.inputs


def test_ac11_a_null_default_is_never_passed() -> None:
    world = TransitionWorld()
    world.defaults(default_budget_usd=PROJECT_BUDGET, default_harness="claude")

    run_advance(world, a_merge_done(world))

    [build] = created(world, 2)
    assert "autonomy" not in build.inputs and "senior_model" not in build.inputs


def test_the_fixture_names_are_the_ones_the_sequence_freezes() -> None:
    world = TransitionWorld()
    names = [w.template for w in world.initiative_row.sequence.workflows]
    assert names == [SPEC[0], MERGE[0], BUILD[0]]


def test_decide_is_what_next_run_answers() -> None:
    world = TransitionWorld()
    run = world.ended_run(2)
    advance = world.advance_of(run)

    decision = initiative_next.decide(world.advance_ports(), world.initiative_row, advance, run)

    assert decision is None


def without_a_build(world: TransitionWorld) -> None:
    """The fixture sequence cut to its spec and its merge: nothing auto follows."""
    sequence = world.initiative_row.sequence
    cut = sequence.model_copy(update={"workflows": sequence.workflows[:2]})
    world.initiative_row = world.initiative_row.model_copy(update={"sequence": cut})
    world.initiatives.update(world.initiative_row)


def test_a_pass_with_no_auto_entry_after_the_spec_goes_straight_to_the_merge() -> None:
    world = TransitionWorld()
    without_a_build(world)
    _, advance = world.spec_run("pass")

    stored = run_advance(world, advance)

    assert stored.consumed_at is not None
    assert len(created(world, 1)) == 1
    reads = [args for name, args in world.remote.calls if name == "read_file"]
    assert not [path for _, _, path in reads if path.endswith("epics.yaml")]


def test_a_merge_done_with_no_build_after_it_has_no_transition() -> None:
    world = TransitionWorld()
    without_a_build(world)
    world.defaults(default_budget_usd=PROJECT_BUDGET)

    stored = run_advance(world, a_merge_done(world))

    assert stored.blocked_reason == "no transition for merge"


def test_a_base_clone_that_exists_is_not_cloned_again() -> None:
    world = TransitionWorld(scripts={"base_exists": [True]})
    world.defaults(default_budget_usd=PROJECT_BUDGET, default_harness="claude")

    run_advance(world, a_merge_done(world))

    assert world.remote.called("clone_base") == []
    assert world.remote.called("fetch_base") != []


def test_a_vanished_project_is_a_failure_that_blocks() -> None:
    world = TransitionWorld()
    advance = a_merge_done(world)
    world.projects.projects.clear()

    stored = run_advance(world, advance)

    assert (stored.blocked_reason or "").startswith("advance failed:")


def test_a_template_that_is_not_stored_is_a_failure_that_blocks() -> None:
    world = TransitionWorld()
    world.defaults(default_budget_usd=PROJECT_BUDGET, default_harness="claude")
    advance = a_merge_done(world)
    world.templates.versions.pop(BUILD)

    stored = run_advance(world, advance)

    assert (stored.blocked_reason or "").startswith("advance failed:")
