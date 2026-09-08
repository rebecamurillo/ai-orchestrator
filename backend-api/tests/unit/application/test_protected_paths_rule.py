"""`application/rules/protected_paths.py`: AD-17's frozen-anchor rule, as a pure function.

Four things are settled here and nowhere else, because they are the rule rather than either
of its call sites: which paths a Run's anchors are (`build`), what `git status --porcelain`
says changed (`uncommitted`), which of a range's changes are hits once the Operator's
accepted files come off (`check`), and how `FrameAnchors` — the `ProtectedPaths` the walker
binds for `git.commit` — unions the frame's own agent ranges with what that row staged.

The two call sites are asserted elsewhere: the agent tail's own range in
`tests/unit/application/steps/test_agent_protected_paths.py`, the walker's resolution in
`tests/unit/application/test_walk_frame_anchors.py`.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.rules import protected_paths
from orchestrator.application.rules.protected_paths import FrameAnchors
from orchestrator.domain.ports.git import Change
from orchestrator.domain.ports.protected_paths import ProtectedPaths
from tests.unit.fakes.git import FakeGit

SPEC_FOLDER = "specs/notifications"
OTHER_FOLDER = "specs/billing"
INITIATIVE = "_bmad-output/mvp"
WORKTREE = Path("/work/acme/widgets/wt/feat-x")
START, END = "a" * 40, "b" * 40
FROZEN = ("tests/unit/test_a.py", "tests/unit/test_b.py")
SPEC_MD = f"{SPEC_FOLDER}/SPEC.md"
STORIES_YAML = f"{SPEC_FOLDER}/stories.yaml"


def anchors(**over: object) -> frozenset[str]:
    fields: dict[str, object] = {
        "spec_folders": (SPEC_FOLDER,),
        "initiative_folder": "",
        "frozen_test_files": (),
    }
    fields.update(over)
    return protected_paths.build(**fields)  # type: ignore[arg-type]


# ── build ───────────────────────────────────────────────────────────────────


def test_a_spec_folder_contributes_its_spec_and_its_story_list() -> None:
    assert anchors() == {f"{SPEC_FOLDER}/SPEC.md", f"{SPEC_FOLDER}/stories.yaml"}


def test_every_spec_folder_of_an_initiative_contributes_its_own() -> None:
    """`initiative@1` binds one spec folder per epic, so the set is not a single Run input."""
    built = anchors(spec_folders=(SPEC_FOLDER, OTHER_FOLDER))

    assert f"{OTHER_FOLDER}/SPEC.md" in built
    assert f"{SPEC_FOLDER}/SPEC.md" in built


def test_a_run_with_no_spec_folder_at_all_contributes_none() -> None:
    """`repo-init@1` declares none, and an empty string is not a folder named `""`."""
    assert anchors(spec_folders=("",)) == frozenset()


def test_the_initiative_folder_contributes_the_epic_list() -> None:
    assert f"{INITIATIVE}/epics.yaml" in anchors(initiative_folder=INITIATIVE)


def test_a_run_that_names_no_initiative_folder_freezes_no_epic_list() -> None:
    assert not any(path.endswith("epics.yaml") for path in anchors())


def test_the_frozen_test_files_are_anchors_verbatim() -> None:
    """They are the tree's own paths as `Git.list_files` answered them (AD-17)."""
    assert set(FROZEN) <= anchors(frozen_test_files=FROZEN)


# ── uncommitted ─────────────────────────────────────────────────────────────


def test_a_clean_worktree_changed_nothing() -> None:
    assert protected_paths.uncommitted("") == ()


def test_blank_porcelain_lines_are_not_changes() -> None:
    assert protected_paths.uncommitted("   \n  \n") == ()


def test_an_untracked_file_is_an_addition() -> None:
    assert protected_paths.uncommitted("?? web-client/AGENTS.md\n") == (
        Change(path="web-client/AGENTS.md", kind="added"),
    )


def test_a_staged_new_file_is_an_addition() -> None:
    assert protected_paths.uncommitted("A  tests/new.py\n") == (
        Change(path="tests/new.py", kind="added"),
    )


def test_a_removed_file_is_a_deletion() -> None:
    assert protected_paths.uncommitted(" D tests/a.py\n") == (
        Change(path="tests/a.py", kind="deleted"),
    )


def test_anything_else_is_a_modification() -> None:
    assert protected_paths.uncommitted(" M SPEC.md\n") == (Change(path="SPEC.md", kind="modified"),)


def test_a_rename_is_split_into_the_two_ends_it_is() -> None:
    """Porcelain writes one line; AD-17 reads a lost anchor and a new file."""
    assert protected_paths.uncommitted("R  tests/a.py -> tests/b.py\n") == (
        Change(path="tests/a.py", kind="deleted"),
        Change(path="tests/b.py", kind="added"),
    )


# ── check ───────────────────────────────────────────────────────────────────


def test_a_change_to_an_anchor_is_a_hit() -> None:
    change = Change(path=f"{SPEC_FOLDER}/SPEC.md", kind="modified")

    assert protected_paths.check((change,), anchors(), ()) == (change,)


def test_a_change_to_anything_else_is_not() -> None:
    change = Change(path="src/thing.py", kind="modified")

    assert protected_paths.check((change,), anchors(), ()) == ()


def test_an_agents_file_anywhere_is_protected_without_being_enumerated() -> None:
    """AD-17: every `AGENTS.md`, and creating one is a hit — a set cannot list them."""
    created = Change(path="web-client/AGENTS.md", kind="added")

    assert protected_paths.check((created,), frozenset(), ()) == (created,)


def test_a_file_merely_ending_in_the_anchors_name_is_not_one() -> None:
    """`MY-AGENTS.md` is a file; the rule is about the document, not about a suffix."""
    change = Change(path="MY-AGENTS.md", kind="added")

    assert protected_paths.check((change,), frozenset(), ()) == ()


def test_an_accepted_path_is_excluded_from_the_check() -> None:
    """`run.accepted_paths`: what a `continue` on an earlier park let through (AD-9)."""
    change = Change(path="tests/unit/test_a.py", kind="modified")
    frozen = anchors(frozen_test_files=FROZEN)

    assert protected_paths.check((change,), frozen, ("tests/unit/test_a.py",)) == ()


def test_a_file_the_agent_created_inside_the_frame_stays_editable() -> None:
    """The frozen set is the tree at the frame's first attempt; `tests/new.py` was not in it."""
    change = Change(path="tests/new.py", kind="modified")

    assert protected_paths.check((change,), anchors(frozen_test_files=FROZEN), ()) == ()


def test_a_deleted_anchor_is_a_hit_and_says_so() -> None:
    change = Change(path="tests/unit/test_a.py", kind="deleted")

    assert protected_paths.check((change,), anchors(frozen_test_files=FROZEN), ()) == (change,)


def test_one_path_touched_twice_is_reported_once() -> None:
    """The tail unions a commit range with the uncommitted tree; the Operator reads a list
    of files, not a list of observations."""
    anchor = f"{SPEC_FOLDER}/SPEC.md"

    hits = protected_paths.check(
        (Change(path=anchor, kind="modified"), Change(path=anchor, kind="deleted")), anchors(), ()
    )

    assert hits == (Change(path=anchor, kind="modified"),)


# ── FrameAnchors ────────────────────────────────────────────────────────────


def test_the_frame_anchors_object_is_the_port_the_commit_guard_already_calls() -> None:
    assert isinstance(FrameAnchors(git=FakeGit(), worktree=WORKTREE), ProtectedPaths)


def test_what_the_commit_guard_staged_is_checked() -> None:
    rule = FrameAnchors(git=FakeGit(), worktree=WORKTREE, anchors=anchors())

    assert rule.check(changed=("src/a.py", f"{SPEC_FOLDER}/stories.yaml"), accepted=()) == (
        f"{SPEC_FOLDER}/stories.yaml",
    )


def test_the_frames_own_agent_ranges_are_checked_with_it() -> None:
    """AD-17's second call site is the union: an anchor an earlier attempt committed is a
    hit at the commit-guard even though the tree is clean of it now."""
    git = FakeGit(diff_changes=[(Change(path=f"{SPEC_FOLDER}/SPEC.md", kind="modified"),)])
    rule = FrameAnchors(git=git, worktree=WORKTREE, anchors=anchors(), ranges=((START, END),))

    assert rule.check(changed=("src/a.py",), accepted=()) == (f"{SPEC_FOLDER}/SPEC.md",)
    assert git.called("diff_changes") == [(WORKTREE, START, END)]


def test_a_frame_with_no_recorded_range_asks_git_nothing() -> None:
    git = FakeGit()
    rule = FrameAnchors(git=git, worktree=WORKTREE, anchors=anchors())

    rule.check(changed=("src/a.py",), accepted=())

    assert git.called("diff_changes") == []


def test_an_accepted_path_is_excluded_at_the_commit_guard_too() -> None:
    rule = FrameAnchors(git=FakeGit(), worktree=WORKTREE, anchors=anchors())

    hits = rule.check(changed=(f"{SPEC_FOLDER}/SPEC.md",), accepted=(f"{SPEC_FOLDER}/SPEC.md",))

    assert hits == ()


# ── the two readings of a rename ────────────────────────────────────────────


def test_an_ordinary_path_holding_the_arrow_is_one_path_and_not_two() -> None:
    """A tracked file may be named `a -> b`; the status code is what says it is a rename."""
    assert protected_paths.uncommitted(" M src/a -> b.py\n") == (
        Change(path="src/a -> b.py", kind="modified"),
    )


def test_a_copy_is_split_the_way_a_rename_is() -> None:
    assert protected_paths.uncommitted("C  tests/a.py -> tests/b.py\n") == (
        Change(path="tests/a.py", kind="deleted"),
        Change(path="tests/b.py", kind="added"),
    )


def test_a_staged_rename_of_an_anchor_is_read_as_losing_it() -> None:
    """`git_commit.py` strips the status letters, so a rename reaches the rule as one string
    holding both ends and the letter that would identify it is already gone."""
    rule = FrameAnchors(git=FakeGit(), worktree=WORKTREE, anchors=anchors())

    hits = rule.check(changed=(f"{SPEC_FOLDER}/SPEC.md -> {SPEC_FOLDER}/OLD.md",), accepted=())

    assert hits == (f"{SPEC_FOLDER}/SPEC.md",)


def test_a_staged_path_that_merely_holds_the_arrow_is_still_checked_whole() -> None:
    """Both readings are offered, so the one that was wrong costs nothing."""
    rule = FrameAnchors(git=FakeGit(), worktree=WORKTREE, anchors=frozenset({"src/a -> b.py"}))

    assert rule.check(changed=("src/a -> b.py",), accepted=()) == ("src/a -> b.py",)


# ── how several hits are reported ───────────────────────────────────────────


def test_several_hits_keep_the_order_they_were_first_seen_in() -> None:
    """The reason and the payload are one list, in the range's own order (first mention wins)."""
    changed = (
        Change(path=STORIES_YAML, kind="modified"),
        Change(path=SPEC_MD, kind="deleted"),
        Change(path=STORIES_YAML, kind="deleted"),
    )

    assert protected_paths.check(changed, anchors(), ()) == (
        Change(path=STORIES_YAML, kind="modified"),
        Change(path=SPEC_MD, kind="deleted"),
    )
