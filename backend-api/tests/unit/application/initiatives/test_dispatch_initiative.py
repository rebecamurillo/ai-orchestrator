"""`dispatch_initiative`: the writes AD-12 describes, in the order it describes (S6).

"One use case creates every member Run of an initiative **saved**, in topological order of
`epics.yaml`'s `depends_on` (AD-7) — one Run per epic on the epic's `repo`, one merge Run
per epic on that repository's integration branch, and at most one go-live checkpoint Run —
wiring `after_run_ids` as it goes … Only the Runs with no dependencies are enqueued, and
only once every row exists."

The fixture initiative is two repositories, one dependency, one `go_live` epic and one
`block_merge` epic, so every wiring rule above has a case in it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.initiatives.model import (
    DEFAULT_EPIC_TEMPLATE,
    DEFAULT_GOLIVE_TEMPLATE,
    DEFAULT_MERGE_TEMPLATE,
    ROLE_EPIC,
    ROLE_GOLIVE,
    ROLE_MERGE,
    InitiativeRequest,
)
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.initiatives import fixtures as fx


def roles(result: object) -> list[tuple[str, str | None]]:
    return [(member.role, member.epic_id) for member in result.members]  # type: ignore[attr-defined]


# ── what gets created ─────────────────────────────────────────────────────────


def test_every_epic_gets_an_epic_run_and_a_merge_run_in_topological_order() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request())

    assert roles(result) == [
        (ROLE_EPIC, "web-1"),
        (ROLE_MERGE, "web-1"),
        (ROLE_EPIC, "api-1"),
        (ROLE_MERGE, "api-1"),
        (ROLE_GOLIVE, None),
    ]


def test_every_member_run_is_saved_and_tagged_with_the_initiative() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request())

    for member in result.members:
        run = harness.run_of(member)
        assert run.status == "queued"
        assert run.initiative == fx.SLUG
        assert run.initiative_role == member.role
        assert run.initiative_epic_id == member.epic_id


def test_the_slug_is_the_basename_of_the_initiative_folder() -> None:
    harness = fx.Harness()

    assert harness.dispatch(fx.request()).slug == "q4"


def test_a_trailing_separator_on_the_folder_does_not_change_the_slug() -> None:
    request = fx.request(initiative_folder=f"{fx.INITIATIVE_FOLDER}/")

    assert request.slug == "q4"
    assert request.epics_path == fx.EPICS_PATH


def test_the_default_template_names_are_the_shipped_ones() -> None:
    """Names, never versions: the version is resolved to the latest at dispatch time."""
    bare = InitiativeRequest(
        project_id=fx.PROJECT_ID,
        repository_id=fx.HUB_ID,
        base_branch=fx.MAIN,
        initiative_folder=fx.INITIATIVE_FOLDER,
    )

    assert bare.templates == (
        DEFAULT_EPIC_TEMPLATE,
        DEFAULT_MERGE_TEMPLATE,
        DEFAULT_GOLIVE_TEMPLATE,
    )


def test_the_latest_stored_version_of_each_template_is_the_one_instantiated() -> None:
    harness = fx.Harness(epic_versions=(1, 2))

    result = harness.dispatch(fx.request())

    epics = [harness.run_of(m) for m in result.members if m.role == ROLE_EPIC]
    assert {(run.template_name, run.template_version) for run in epics} == {(fx.EPIC_TEMPLATE, 2)}


# ── the inputs each role binds ────────────────────────────────────────────────


def test_an_epic_run_works_off_the_integration_branch_on_its_own_branch() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request())
    web = harness.run_of(next(m for m in result.members if m.role == ROLE_EPIC))

    assert web.inputs["base_branch"] == fx.WEB_BRANCH
    assert web.inputs["branch"] == f"{fx.WEB_BRANCH}-web-1"
    assert web.inputs["spec_folder"] == fx.WEB_SPEC


def test_a_block_merge_epic_binds_done_checkpoint_true_and_the_others_blank() -> None:
    """The DSL has no bool input (S5): `"true"` stops, `""` does not."""
    harness = fx.Harness()

    result = harness.dispatch(fx.request())
    bound = {
        member.epic_id: harness.run_of(member).inputs["done_checkpoint"]
        for member in result.members
        if member.role == ROLE_EPIC
    }

    assert bound == {"web-1": "", "api-1": "true"}


def test_an_epic_run_leaves_the_optional_item_input_unbound() -> None:
    """An `item` is what a `for_each` frame hands a callee; a root Run has no frame."""
    harness = fx.Harness()

    web = harness.run_of(next(m for m in harness.dispatch(fx.request()).members))

    assert "epic" not in web.inputs


def test_a_merge_run_merges_the_epics_allocated_branch_into_the_integration_one() -> None:
    """`from_branch` is the branch AD-7 allocated, not the one the Template declared."""
    harness = fx.Harness()

    result = harness.dispatch(fx.request())
    epic = next(m for m in result.members if m.role == ROLE_EPIC)
    merge = harness.run_of(next(m for m in result.members if m.role == ROLE_MERGE))

    assert merge.inputs["develop_branch"] == fx.WEB_BRANCH
    assert merge.inputs["from_branch"] == epic.working_branch
    assert merge.inputs["from_branch"] != epic.run_id  # not the declared name either
    assert merge.inputs["from_branch"].startswith(f"{fx.WEB_BRANCH}-web-1-")


def test_the_go_live_run_is_on_the_hub_and_names_the_epics_it_holds_for() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request())
    golive = next(m for m in result.members if m.role == ROLE_GOLIVE)
    run = harness.run_of(golive)

    assert golive.repository_id == fx.HUB_ID
    assert run.inputs["base_branch"] == fx.MAIN
    assert run.inputs["holds"] == "web-1"


def test_no_go_live_run_exists_when_no_epic_declares_one() -> None:
    none_live = (
        f"- id: a\n  title: A\n  repo: web\n  branch: {fx.WEB_BRANCH}\n"
        f"  spec_folder: {fx.WEB_SPEC}\n"
    )
    harness = fx.Harness(epics=none_live, specs=(fx.WEB_SPEC,))

    result = harness.dispatch(fx.request())

    assert roles(result) == [(ROLE_EPIC, "a"), (ROLE_MERGE, "a")]


# ── the after_run_ids wiring ──────────────────────────────────────────────────


def test_a_merge_run_waits_for_its_own_epic_run() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request())
    epic = next(m for m in result.members if m.role == ROLE_EPIC)
    merge = next(m for m in result.members if m.role == ROLE_MERGE)

    assert merge.after_run_ids == (epic.run_id,)


def test_an_epic_run_waits_for_the_merge_runs_of_what_it_depends_on() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request())
    web_merge = next(m for m in result.members if m.role == ROLE_MERGE and m.epic_id == "web-1")
    api_epic = next(m for m in result.members if m.role == ROLE_EPIC and m.epic_id == "api-1")

    assert api_epic.after_run_ids == (web_merge.run_id,)


def test_the_go_live_run_waits_for_the_merge_runs_of_every_go_live_epic() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request())
    web_merge = next(m for m in result.members if m.role == ROLE_MERGE and m.epic_id == "web-1")
    golive = next(m for m in result.members if m.role == ROLE_GOLIVE)

    assert golive.after_run_ids == (web_merge.run_id,)


def test_the_stored_runs_carry_the_same_edges_the_result_reports() -> None:
    """The edges are the durable record the DAG is rendered from (AD-12)."""
    harness = fx.Harness()

    for member in harness.dispatch(fx.request()).members:
        assert harness.run_of(member).after_run_ids == member.after_run_ids


# ── the integration branches ──────────────────────────────────────────────────


def test_each_repositorys_integration_branch_is_pushed_once_before_any_run_exists() -> None:
    harness = fx.Harness()

    harness.dispatch(fx.request())

    assert [(str(base), branch) for base, branch, _at in harness.git.called("push_branch")] == [
        ("/work/my-project/web/base", fx.WEB_BRANCH),
        ("/work/my-project/api/base", fx.API_BRANCH),
    ]


def test_the_branch_is_created_at_the_default_branch_head_by_default() -> None:
    harness = fx.Harness()

    harness.dispatch(fx.request())

    assert {at for _base, _branch, at in harness.git.called("push_branch")} == {fx.MAIN_SHA}


def test_an_entrys_baseline_sha_is_where_its_branch_is_created() -> None:
    pinned = (
        f"- id: a\n  title: A\n  repo: web\n  branch: {fx.WEB_BRANCH}\n"
        f"  spec_folder: {fx.WEB_SPEC}\n  baseline_sha: {fx.MAIN_SHA}\n"
    )
    harness = fx.Harness(epics=pinned, specs=(fx.WEB_SPEC,))

    harness.dispatch(fx.request())

    assert harness.git.called("push_branch") == [
        (harness.preflight.work_dir / "my-project" / "web" / "base", fx.WEB_BRANCH, fx.MAIN_SHA)
    ]


def test_two_epics_on_one_repository_push_its_branch_only_once() -> None:
    shared = (
        f"- id: a\n  title: A\n  repo: web\n  branch: {fx.WEB_BRANCH}\n"
        f"  spec_folder: {fx.WEB_SPEC}\n"
        f"- id: b\n  title: B\n  repo: web\n  branch: {fx.WEB_BRANCH}\n"
        f"  spec_folder: {fx.WEB_SPEC}\n"
    )
    harness = fx.Harness(epics=shared, specs=(fx.WEB_SPEC,))

    harness.dispatch(fx.request())

    assert len(harness.git.called("push_branch")) == 1


# ── the wave-0 enqueue ────────────────────────────────────────────────────────


def test_only_the_epics_with_no_dependency_are_enqueued() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request())

    assert result.started == ("web-1",)
    enqueued = {run_id for _name, (run_id, _key) in harness.engine.calls}
    assert enqueued == {next(m.run_id for m in result.members if m.epic_id == "web-1")}


def test_an_enqueued_run_is_partitioned_by_its_own_declared_branch() -> None:
    harness = fx.Harness()

    harness.dispatch(fx.request())

    assert [key for _name, (_run_id, key) in harness.engine.calls] == [
        f"{fx.WEB_ID}:{fx.WEB_BRANCH}-web-1"
    ]


def test_nothing_is_enqueued_until_every_row_of_the_initiative_exists() -> None:
    """AD-12: "Only the Runs with no dependencies are enqueued, and only once every row
    exists" — the crash posture the docstring states rests on this ordering."""
    harness = fx.Harness()

    created_before_enqueue: list[int] = []
    original = harness.engine.enqueue

    def record(run_id, partition_key):  # type: ignore[no-untyped-def]
        created_before_enqueue.append(len(harness.runs.runs))
        return original(run_id, partition_key)

    harness.engine.enqueue = record  # type: ignore[method-assign]
    result = harness.dispatch(fx.request())

    assert created_before_enqueue == [len(result.members)]


def test_every_run_but_the_enqueued_ones_keeps_an_empty_engine_ref() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request())

    saved = {m.epic_id for m in result.members if not harness.run_of(m).engine_ref}
    assert saved == {"web-1", "api-1", None}


# ── the budget, the harness and the model ─────────────────────────────────────


def test_the_budget_applies_to_the_epic_runs_and_to_nothing_else() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request(budget_usd_per_epic=Decimal("7")))
    budgets = {member.role: harness.run_of(member).budget_usd for member in result.members}

    assert budgets == {ROLE_EPIC: Decimal("7"), ROLE_MERGE: None, ROLE_GOLIVE: None}


def test_the_requested_model_reaches_the_epic_runs_and_not_the_others() -> None:
    harness = fx.Harness()

    result = harness.dispatch(fx.request(model="a-model"))
    models = {member.role: harness.run_of(member).inputs["model"] for member in result.members}

    assert models == {ROLE_EPIC: "a-model", ROLE_MERGE: None, ROLE_GOLIVE: None}


# ── the refusals ──────────────────────────────────────────────────────────────


def test_a_failing_line_refuses_the_whole_dispatch_and_writes_nothing() -> None:
    """Every refusal is computed before the first write — the crash posture's first half."""
    harness = fx.Harness(specs=(fx.WEB_SPEC,))

    with pytest.raises(Conflict, match="spec folder"):
        harness.dispatch(fx.request())

    assert harness.runs.runs == {}
    assert harness.git.called("push_branch") == []
    assert harness.engine.calls == []


def test_a_project_that_is_not_stored_is_a_not_found() -> None:
    harness = fx.Harness()

    with pytest.raises(NotFound, match="no project"):
        harness.dispatch(fx.request(project_id=new_id()))


def test_a_hub_repository_that_is_not_stored_is_a_not_found() -> None:
    harness = fx.Harness()

    with pytest.raises(NotFound, match="no repository"):
        harness.dispatch(fx.request(repository_id=new_id()))
