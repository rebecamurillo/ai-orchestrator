"""`with {workdir}` on an `agent` row: one attempt, two trees, both checked (AD-9, AD-17).

Story H4 of the hub-Run initiative workflow, 2026-09-23. What is settled here is everything
that depends on *which tree* a question is asked of, because nothing else can settle it:

- the workdir is resolved through the port before anything is written, and a path that is no
  initialized submodule parks AD-9's own sentence with no commit and no attempt column behind
  it;
- the harness is dispatched **in the member checkout** — its `cwd`, and so the stall
  detector's folder — while the orchestrator's own writes stay at the hub;
- the prompt carries the spec folder **absolute**, because the agent stands somewhere else
  and the Story file has to land in the hub (the contract H3's templates encode);
- the attempt records the submodule's `start_sha`/`end_sha` and the hub's
  `root_start_sha`/`root_end_sha` at the same two moments;
- `repository.test_globs` are matched against workdir-relative paths, and the frame freezes
  both trees' matches in the one spelling every hit is reported in;
- the protected-path check covers both trees, prefixes a workdir hit `{workdir}/`, and never
  reports the gitlink pointer.

A row that declares no `workdir` is covered by the modules that always covered it; the two
tests at the end are the ones that pin "unchanged" as a fact rather than as a hope.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.application.steps import agent_workdir
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.agent_tail import PROTECTED
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ports.git import Change
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    ROW_PATH,
    SPEC_FOLDER,
    WORKTREE,
    World,
    a_gate_record,
    an_agent_row,
    an_attempt,
)
from tests.unit.application.steps.agent_tail_fixtures import (
    END_SHA,
    LOG_PATH,
    a_tail_world,
    contracted,
)
from tests.unit.fakes.git import FakeGit

#: The member repository this Run's rows work in, and where it sits inside the hub worktree.
WORKDIR = "repos/member"
MEMBER = f"{WORKTREE}/{WORKDIR}"

#: Four distinct SHAs, so "which tree answered" is never a coincidence.
MEMBER_START = "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111"
MEMBER_END = "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"
ROOT_START = "cccc3333cccc3333cccc3333cccc3333cccc3333"
ROOT_END = "dddd4444dddd4444dddd4444dddd4444dddd4444"

#: The anchors a hub Run freezes, and the two test files the two trees hold.
SPEC_MD = f"{SPEC_FOLDER}/SPEC.md"
MEMBER_TEST = "tests/test_member.py"
HUB_TEST = "tests/test_hub.py"
ANCHORS = frozenset({SPEC_MD, f"{WORKDIR}/{MEMBER_TEST}", HUB_TEST})

TEST_GLOBS = ("tests/**",)


def a_workdir_git(**over: Any) -> FakeGit:
    """A hub worktree holding one initialized submodule, with both trees answerable apart.

    The submodule resolves because `FakeGit.submodule_path` answers the workdir it was asked
    about unless a test scripts otherwise — the probe H6 replaced `submodule_update` with
    (2026-09-23), so nothing here scripts a listing any more.
    """
    fields: dict[str, Any] = {
        "heads": {MEMBER: [MEMBER_START, MEMBER_END], WORKTREE: [ROOT_START, ROOT_END]},
        "statuses": {MEMBER: "", WORKTREE: ""},
        "changes": {MEMBER: (), WORKTREE: ()},
    }
    fields.update(over)
    return FakeGit(**fields)


def a_workdir_world(*, anchors: frozenset[str] = frozenset(), **over: Any) -> World:
    """A dispatch world whose row declares `workdir`, wired the way the walker leaves one."""
    over.setdefault("with_resolved", contracted(workdir=WORKDIR))
    over.setdefault("git", a_workdir_git())
    world = a_tail_world(**over)
    environment = world.ctx.ports.run_env
    assert environment is not None
    world.ctx = replace(
        world.ctx,
        ports=replace(world.ctx.ports, run_env=replace(environment, anchors=anchors)),
    )
    return world


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def a_workdir_attempt(**over: Any) -> Attempt:
    """A finished `workdir` attempt: both trees' ranges, as `mark_finished` left them."""
    fields: dict[str, Any] = {
        "status": "error",
        "start_sha": MEMBER_START,
        "end_sha": MEMBER_END,
        "root_start_sha": ROOT_START,
        "root_end_sha": ROOT_END,
    }
    fields.update(over)
    return an_attempt(an_agent_row(), 1, **fields)


# ── resolving the workdir, before anything is written ───────────────────────


def test_a_declared_workdir_is_normalised_to_one_spelling() -> None:
    world = a_workdir_world(with_resolved=contracted(workdir=f"./{WORKDIR}/"))

    assert agent_workdir.declared(world.ctx) == WORKDIR
    assert agent_workdir.tree(world.ctx) == Path(MEMBER)


def test_a_row_declaring_no_workdir_works_in_the_worktree_root() -> None:
    world = a_tail_world()

    assert agent_workdir.declared(world.ctx) == ""
    assert agent_workdir.tree(world.ctx) == Path(WORKTREE)
    assert agent_workdir.verify(world.ctx) is None


def test_a_workdir_that_is_not_an_initialized_submodule_parks_the_spines_sentence() -> None:
    """`submodule_path` answering `None` is the port's "not an initialized submodule" — the
    probe replaced the `submodule_update` listing this scripted, H6 (2026-09-23)."""
    world = a_workdir_world(git=a_workdir_git(submodule_path=[None]))

    result = run(world)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.path == ROW_PATH
    assert result.reason == f"workdir {WORKDIR} is not an initialized submodule"


def test_an_unresolvable_workdir_leaves_no_commit_and_no_dispatch_behind() -> None:
    """AD-9's order: the stop is a decision about a tree nothing has touched — which is now
    true of the question itself as well, the probe being read-only (H6, 2026-09-23)."""
    world = a_workdir_world(git=a_workdir_git(submodule_path=[None]))

    run(world)

    assert world.git.called("commit") == []
    assert world.harness.calls == []
    assert world.attempts.calls == [("add", world.attempt.id)]


def test_the_park_names_the_workdir_the_template_wrote_not_the_normalised_one() -> None:
    """The Operator has to find the value in the Template, so it is echoed verbatim.

    The probe answers `None` for it (H6, 2026-09-23): the row names a folder this worktree
    does not hold as a submodule, which is what the park is about."""
    world = a_workdir_world(
        with_resolved=contracted(workdir="./repos/other/"),
        git=a_workdir_git(submodule_path=[None]),
    )

    assert run(world).reason == "workdir ./repos/other/ is not an initialized submodule"


# ── the verification is a read, never an update (H6, 2026-09-23) ────────────


def test_a_workdir_dispatch_verifies_through_the_probe_and_never_updates_the_submodule() -> None:
    """The H6 defect, as a call-log fact. `verify` asked `Git.submodule_update` — a **write**:
    default checkout mode resets the submodule to the commit the hub's index records, and the
    hub Run never advances that gitlink (AD-14), so the second `workdir` dispatch into one
    submodule detached the member checkout at the stale pointer and orphaned everything an
    earlier row had committed there. The probe answers the same question and mutates nothing,
    so "no update ran" is what has to be asserted, not merely "the probe was asked"."""
    world = a_workdir_world()

    run(world)

    assert world.git.called("submodule_path") == [(Path(WORKTREE), WORKDIR)]
    assert world.git.called("submodule_update") == []


def test_the_probe_is_asked_of_the_hub_worktree_with_the_normalised_workdir() -> None:
    """Whatever spelling the Template wrote, one question is asked — and it is asked of the
    run worktree root, the only tree that can say what its submodules are."""
    world = a_workdir_world(with_resolved=contracted(workdir=f"./{WORKDIR}/"))

    run(world)

    assert world.git.called("submodule_path") == [(Path(WORKTREE), WORKDIR)]


# ── where the harness runs, and what it is told ─────────────────────────────


def test_the_harness_is_dispatched_inside_the_member_checkout() -> None:
    world = a_workdir_world()

    run(world)

    assert [call["cwd"] for call in world.harness.calls if call["method"] == "start"] == [
        Path(MEMBER)
    ]


def test_the_prompt_carries_the_spec_folder_as_an_absolute_hub_path() -> None:
    """The agent stands in the member checkout; a relative `specs/…` would make it write the
    Story file into the member repository instead of the hub (the contract H3 encodes)."""
    world = a_workdir_world()

    run(world)

    [start] = [call for call in world.harness.calls if call["method"] == "start"]
    assert f"spec folder {WORKTREE}/{SPEC_FOLDER}," in start["prompt"]
    assert f"spec folder {SPEC_FOLDER}," not in start["prompt"]


def test_a_row_with_no_spec_folder_has_nothing_to_absolutise() -> None:
    world = a_workdir_world(with_resolved=contracted(workdir=WORKDIR, spec_folder=""))

    assert agent_workdir.prompt_scope(world.ctx) is world.ctx.with_resolved


def test_a_root_row_hands_the_prompt_builder_its_row_unchanged() -> None:
    world = a_tail_world()

    assert agent_workdir.prompt_scope(world.ctx) is world.ctx.with_resolved


def test_the_orchestrators_own_writes_stay_at_the_hub() -> None:
    """The specs live there, so `project-context.md` and the prepare commit do too."""
    world = a_workdir_world(
        git=a_workdir_git(statuses={MEMBER: "", WORKTREE: f" M {SPEC_FOLDER}/project-context.md\n"})
    )

    run(world)

    assert world.workspace.read(f"{SPEC_FOLDER}/project-context.md") is not None
    assert [str(path) for path, _ in world.git.called("commit")] == [WORKTREE]


# ── the two trees' SHAs ─────────────────────────────────────────────────────


def test_the_attempt_records_both_trees_at_both_moments() -> None:
    world = a_workdir_world()

    run(world)

    stored = world.attempts.attempts[world.attempt.id]
    assert (stored.start_sha, stored.end_sha) == (MEMBER_START, MEMBER_END)
    assert (stored.root_start_sha, stored.root_end_sha) == (ROOT_START, ROOT_END)


def test_a_root_row_records_no_root_range_at_all() -> None:
    """The spine's "written only when the row declares `workdir`", as a fact about a row."""
    world = a_tail_world()

    run(world)

    stored = world.attempts.attempts[world.attempt.id]
    assert (stored.start_sha, stored.end_sha) == (HEAD_SHA, END_SHA)
    assert (stored.root_start_sha, stored.root_end_sha) == (None, None)


# ── the WIP commit, in the tree the row works in ────────────────────────────


def test_a_dirty_member_checkout_is_committed_in_the_submodule() -> None:
    world = a_workdir_world(
        previous=a_workdir_attempt(end_sha=None),
        git=a_workdir_git(statuses={MEMBER: " M src/thing.py\n", WORKTREE: ""}),
    )

    run(world)

    assert world.git.called("commit")[0] == (
        Path(WORKTREE),
        "wip: story 4-1 attempt 2 (interrupted)",
        WORKDIR,
    )
    # the submodule is staged and committed in one call; the only `stage` left is the hub's
    # own prepare write, which never moves
    assert world.git.called("stage") == [(Path(WORKTREE), f"{SPEC_FOLDER}/project-context.md")]


def test_a_clean_member_checkout_makes_no_wip_commit() -> None:
    world = a_workdir_world(previous=a_workdir_attempt(end_sha=None))

    run(world)

    assert [call for call in world.git.called("commit") if call[1].startswith("wip:")] == []


def test_the_hub_being_dirty_is_not_the_member_checkout_being_dirty() -> None:
    """The WIP commit asks the tree the harness will run in, and only that one."""
    world = a_workdir_world(
        previous=a_workdir_attempt(end_sha=None),
        git=a_workdir_git(statuses={MEMBER: "", WORKTREE: " M src/hub.py\n"}),
    )

    run(world)

    assert [call for call in world.git.called("commit") if call[1].startswith("wip:")] == []


# ── the frozen test set: globs on workdir-relative paths ────────────────────


def a_frozen_world(**over: Any) -> World:
    return a_workdir_world(
        test_globs=TEST_GLOBS,
        git=a_workdir_git(
            listings={
                (MEMBER_START, "."): [MEMBER_TEST, "src/member.py"],
                (ROOT_START, "."): [HUB_TEST, f"{SPEC_FOLDER}/SPEC.md"],
            },
            **over,
        ),
    )


def test_the_frame_freezes_both_trees_in_the_one_spelling() -> None:
    world = a_frozen_world()

    run(world)

    assert world.attempts.attempts[world.attempt.id].frozen_test_files == (
        f"{WORKDIR}/{MEMBER_TEST}",
        HUB_TEST,
    )


def test_the_globs_are_matched_against_workdir_relative_paths() -> None:
    """`tests/**` is what a member repository writes; it would match nothing at all if it
    were asked about `repos/member/tests/…` (AD-17's amendment, in one assertion)."""
    world = a_frozen_world()

    run(world)

    assert world.git.called("list_files") == [
        (Path(MEMBER), MEMBER_START, "."),
        (Path(WORKTREE), ROOT_START, "."),
    ]


def test_a_later_attempt_of_the_frame_freezes_nothing_again() -> None:
    world = a_workdir_world(test_globs=TEST_GLOBS, previous=a_workdir_attempt())

    run(world)

    assert world.attempts.attempts[world.attempt.id].frozen_test_files is None
    assert world.git.called("list_files") == []


def test_two_trees_with_no_commit_in_either_freeze_nothing() -> None:
    world = a_workdir_world(
        test_globs=TEST_GLOBS,
        git=a_workdir_git(heads={MEMBER: [None], WORKTREE: [None]}),
    )

    run(world)

    assert world.attempts.attempts[world.attempt.id].frozen_test_files is None


def test_a_member_checkout_with_no_commit_still_freezes_the_hubs_own_tests() -> None:
    world = a_workdir_world(
        test_globs=TEST_GLOBS,
        git=a_workdir_git(
            heads={MEMBER: [None], WORKTREE: [ROOT_START, ROOT_END]},
            listings={(ROOT_START, "."): [HUB_TEST]},
        ),
    )

    run(world)

    assert world.attempts.attempts[world.attempt.id].frozen_test_files == (HUB_TEST,)


def test_a_hub_with_no_commit_still_freezes_the_members_own_tests() -> None:
    world = a_workdir_world(
        test_globs=TEST_GLOBS,
        git=a_workdir_git(
            heads={MEMBER: [MEMBER_START, MEMBER_END], WORKTREE: [None]},
            listings={(MEMBER_START, "."): [MEMBER_TEST]},
        ),
    )

    run(world)

    assert world.attempts.attempts[world.attempt.id].frozen_test_files == (
        f"{WORKDIR}/{MEMBER_TEST}",
    )


# ── the protected-path check, over both trees ───────────────────────────────


def test_a_member_test_file_the_dispatch_edited_parks_the_run() -> None:
    """The safety property of the whole hub-Run workflow: without it a member repository's
    own tests are unprotected."""
    world = a_workdir_world(
        anchors=ANCHORS,
        git=a_workdir_git(changes={MEMBER: (Change(path=MEMBER_TEST, kind="modified"),)}),
    )

    result = run(world)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.reason == PROTECTED.format(paths=f"{WORKDIR}/{MEMBER_TEST}")
    assert result.payload == {"hits": [{"path": f"{WORKDIR}/{MEMBER_TEST}", "kind": "modified"}]}


def test_a_member_file_left_uncommitted_is_a_hit_like_a_committed_one() -> None:
    world = a_workdir_world(
        anchors=ANCHORS,
        git=a_workdir_git(statuses={MEMBER: f" M {MEMBER_TEST}\n", WORKTREE: ""}),
    )

    assert run(world).reason == PROTECTED.format(paths=f"{WORKDIR}/{MEMBER_TEST}")


def test_a_hub_anchor_the_same_dispatch_edited_is_a_hit_too() -> None:
    world = a_workdir_world(
        anchors=ANCHORS,
        git=a_workdir_git(changes={MEMBER: (), WORKTREE: (Change(path=SPEC_MD, kind="modified"),)}),
    )

    assert run(world).reason == PROTECTED.format(paths=SPEC_MD)


def test_an_agents_file_inside_the_member_checkout_is_a_hit() -> None:
    """AD-17 protects every `AGENTS.md`, and a submodule's own is one of them."""
    world = a_workdir_world(
        anchors=frozenset(), git=a_workdir_git(statuses={MEMBER: "?? AGENTS.md\n", WORKTREE: ""})
    )

    assert run(world).reason == PROTECTED.format(paths=f"{WORKDIR}/AGENTS.md")


def test_the_hub_range_is_read_between_the_root_shas_and_the_member_range_between_its_own() -> None:
    world = a_workdir_world(anchors=ANCHORS)

    run(world)

    assert world.git.called("diff_changes") == [
        (Path(MEMBER), MEMBER_START, MEMBER_END),
        (Path(WORKTREE), ROOT_START, ROOT_END),
    ]


def test_the_gitlink_pointer_the_member_commit_moved_is_never_a_hit() -> None:
    """A commit inside the submodule moves `repos/member` in the hub, and a dirty one shows
    as ` M repos/member`: neither is a file the agent edited."""
    world = a_workdir_world(
        anchors=frozenset({WORKDIR, f"{WORKDIR}/AGENTS.md"}),
        git=a_workdir_git(
            changes={MEMBER: (), WORKTREE: (Change(path=WORKDIR, kind="modified"),)},
            statuses={MEMBER: "", WORKTREE: f" M {WORKDIR}\n"},
        ),
    )

    result = run(world)

    assert result.park is None
    assert result.status == "done"


def test_a_hub_path_merely_starting_with_the_workdirs_name_is_still_checked() -> None:
    """`repos/member-docs` is not inside `repos/member`, and the exclusion is by path
    segment rather than by string prefix."""
    world = a_workdir_world(
        anchors=frozenset({"repos/member-docs/AGENTS.md"}),
        git=a_workdir_git(
            changes={
                MEMBER: (),
                WORKTREE: (Change(path="repos/member-docs/AGENTS.md", kind="modified"),),
            }
        ),
    )

    assert run(world).reason == PROTECTED.format(paths="repos/member-docs/AGENTS.md")


def test_an_accepted_member_path_is_excluded_by_the_same_spelling() -> None:
    """`run.accepted_paths` stays one flat list: a workdir hit is accepted under the name the
    Run reported it under."""
    world = a_workdir_world(
        anchors=ANCHORS,
        git=a_workdir_git(changes={MEMBER: (Change(path=MEMBER_TEST, kind="modified"),)}),
    )
    environment = world.ctx.ports.run_env
    assert environment is not None
    world.ctx = replace(
        world.ctx,
        ports=replace(
            world.ctx.ports,
            run_env=replace(environment, accepted_paths=(f"{WORKDIR}/{MEMBER_TEST}",)),
        ),
    )

    result = run(world)

    assert result.park is None
    assert result.status == "done"


def test_an_accepted_continue_re_checks_both_of_the_previous_attempts_trees() -> None:
    """The Operator's *Accept* dispatches nothing and re-reads the ranges the parked attempt
    recorded — both of them, from `root_start_sha`/`root_end_sha` and the member's own pair."""
    row = an_agent_row()
    world = a_workdir_world(
        anchors=ANCHORS,
        previous=a_workdir_attempt(),
        resume=a_gate_record(row, "continue", {"files": [f"{WORKDIR}/{MEMBER_TEST}"]}),
        git=a_workdir_git(changes={MEMBER: (Change(path=MEMBER_TEST, kind="modified"),)}),
    )

    result = run(world)

    assert world.harness.calls == []
    assert world.git.called("diff_changes") == [
        (Path(MEMBER), MEMBER_START, MEMBER_END),
        (Path(WORKTREE), ROOT_START, ROOT_END),
    ]
    assert result.reason == PROTECTED.format(paths=f"{WORKDIR}/{MEMBER_TEST}")


def test_an_attempt_that_bounded_no_range_in_either_tree_asks_for_no_diff() -> None:
    world = a_workdir_world(
        anchors=ANCHORS, git=a_workdir_git(heads={MEMBER: [None], WORKTREE: [None]})
    )

    result = run(world)

    assert world.git.called("diff_changes") == []
    assert result.status == "done"


# ── a row that declares no workdir is unchanged ─────────────────────────────


def test_a_root_row_asks_the_submodule_listing_nothing_at_all() -> None:
    """The cost of this story is paid by the rows that use it and by no other. H6
    (2026-09-23) moved the question from `submodule_update` to `submodule_path`; a root row
    asks neither, which is strictly more than this pinned before."""
    world = a_tail_world()

    run(world)

    assert world.git.called("submodule_update") == []
    assert world.git.called("submodule_path") == []


def test_a_root_rows_check_reads_one_tree_and_reports_its_paths_unqualified() -> None:
    world = a_tail_world(
        git=FakeGit(
            status=[f" M {SPEC_MD}\n"],
            head_sha=[HEAD_SHA, END_SHA],
            diff_changes=[()],
        )
    )
    environment = world.ctx.ports.run_env
    assert environment is not None
    world.ctx = replace(
        world.ctx,
        ports=replace(world.ctx.ports, run_env=replace(environment, anchors=frozenset({SPEC_MD}))),
    )

    result = run(world)

    assert result.reason == PROTECTED.format(paths=SPEC_MD)
    assert world.git.called("status") == [(Path(WORKTREE),), (Path(WORKTREE),)]


def test_the_row_still_routes_on_the_story_file_the_hub_holds() -> None:
    """The Story file is written at the hub — `expect.files` stays run-root relative — so a
    `workdir` dispatch that finished reaches `done` through the ordinary tail."""
    world = a_workdir_world(anchors=ANCHORS)

    assert run(world) == StepResult(status="done", gate="liveness", output_ref=str(LOG_PATH))
