"""Interactive anchors: the initiative folder is a conversation's product (epic 5 story 2,
2026-11-23; AD-17 amended, owner ruling R1).

`folder_patterns`, `matches`, `check_interactive`, `FrameAnchors(interactive=…)`, the
`frame_anchors` wiring and the commit-guard over it, on fixture rows this module owns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from orchestrator.application.rules import protected_paths
from orchestrator.application.rules.protected_paths import (
    FrameAnchors,
    check,
    check_interactive,
    folder_patterns,
    matches,
)
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.steps.git_commit import GitCommitExecutor
from orchestrator.application.use_cases.walk_frame import WalkFrame, frame_anchors
from orchestrator.domain.ports.git import Change
from tests.unit.application.writer_fixtures import build_rows, build_run
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import a_context

REPO_ROOT = Path(__file__).resolve().parents[4]
WRITES = ["epics.yaml", "*/SPEC.md", "*/stories.yaml"]
FOLDER, SLUG = "initiatives", "demo"
ALLOWED = (
    "initiatives/demo/epics.yaml",
    "initiatives/demo/*/SPEC.md",
    "initiatives/demo/*/stories.yaml",
)
LETTING = [
    "initiatives/demo/epics.yaml",
    "initiatives/demo/epic-1/SPEC.md",
    "initiatives/demo/epic-1/stories.yaml",
    "initiatives/demo/notes.md",
]
STOPPING = [
    "initiatives/other/epics.yaml",
    "initiatives/demo/a/b/SPEC.md",
    "initiatives/demo/../x/SPEC.md",
    "AGENTS.md",
    "initiatives/demo/AGENTS.md",
    "templates/SPEC.md",
]
R1_LINE = (
    "   - A `conversation` step of an `interactive` Run may write the anchors its row declares in "
    "`writes` (`epics.yaml`, `SPEC.md`, `stories.yaml`) inside its own initiative folder, "
    "`{initiative_folder}/{slug}/`, without a `protected_path` stop: it writes them in the "
    "Operator's conversation and closes only on her word. Every other anchor, every `AGENTS.md`, "
    "every test file and every path outside that folder still stops for the Operator. "
    "(Operator ruling R1, 2026-11-22, initiative orchestrator-initiative-steps; AD-17.)"
)


def changes(*paths: str) -> list[Change]:
    return [Change(path=path, kind="modified") for path in paths]


def hit_paths(paths: list[str], **over: Any) -> list[str]:
    args: dict[str, Any] = {"protected": frozenset(), "accepted": (), "allowed": ALLOWED}
    args.update(over)
    return [hit.path for hit in check_interactive(changes(*paths), **args)]


def test_folder_patterns_join_under_the_folder_and_slug() -> None:
    assert folder_patterns(WRITES, FOLDER, SLUG) == ALLOWED


@pytest.mark.parametrize(
    ("folder", "slug"), [("", SLUG), (FOLDER, ""), ("  ", SLUG), (FOLDER, " ")]
)
def test_a_blank_folder_or_slug_builds_no_pattern(folder: str, slug: str) -> None:
    assert folder_patterns(WRITES, folder, slug) == ()


def test_ac1_the_declared_paths_pass_and_every_other_anchor_is_reported() -> None:
    assert hit_paths(LETTING) == []
    assert hit_paths(STOPPING) == STOPPING


def test_ac2_a_blank_slug_or_folder_exempts_nothing() -> None:
    documents = [path for path in [*LETTING, *STOPPING] if protected_paths.is_document(path)]
    for folder, slug in ((FOLDER, ""), ("", SLUG)):
        allowed = folder_patterns(WRITES, folder, slug)
        assert hit_paths(documents, allowed=allowed) == documents


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("a/b", "a/b", True),
        ("a/b/c", "a/*", False),
        ("a", "a/*", False),
        ("a/x.md", "a/*.md", True),
        ("a/../b", "a/../b", False),
        ("a/./b", "a/./b", False),
        ("/a/b", "/a/b", False),
        ("A/b", "a/b", False),
    ],
)
def test_matches_is_segment_wise_and_refuses_dot_segments(
    path: str, pattern: str, expected: bool
) -> None:
    assert matches(path, pattern) is expected


def test_check_interactive_keeps_protected_literals_accepted_and_dedupe() -> None:
    protected = frozenset({"src/frozen_test.py", "initiatives/other/epics.yaml"})
    seen = hit_paths(
        [
            "src/frozen_test.py",
            "src/frozen_test.py",
            "initiatives/other/epics.yaml",
            "initiatives/demo/epics.yaml",
            "x/SPEC.md",
        ],
        protected=protected,
        accepted=("x/SPEC.md",),
    )
    assert seen == ["src/frozen_test.py", "initiatives/other/epics.yaml"]


def test_an_agents_md_is_never_exempted_even_by_a_matching_pattern() -> None:
    allowed = folder_patterns(["*.md"], FOLDER, SLUG)
    assert hit_paths(
        ["initiatives/demo/AGENTS.md", "initiatives/demo/SPEC.md"], allowed=allowed
    ) == ["initiatives/demo/AGENTS.md"]


def test_frame_anchors_check_picks_the_rule_by_its_flag() -> None:
    git = FakeGit()
    interactive = FrameAnchors(git=git, worktree=Path("/w"), interactive=True, allowed=ALLOWED)
    plain = FrameAnchors(git=git, worktree=Path("/w"))
    assert interactive.check(changed=[*LETTING, *STOPPING], accepted=()) == tuple(STOPPING)
    assert plain.check(changed=["a/AGENTS.md", "x/SPEC.md"], accepted=()) == ("a/AGENTS.md",)
    assert not plain.interactive
    assert plain.allowed == ()


def frame_rows(*kinds: str, writes: list[str] = WRITES) -> tuple[Any, ...]:
    plan = tuple((f"stories[0].r{index}", kind) for index, kind in enumerate(kinds))
    resolved = {path: {"writes": writes} for path, kind in plan if kind == "conversation"}
    return tuple(build_rows(build_run().id, plan, None, resolved))


def environment() -> RunEnvironment:
    return RunEnvironment(
        run_id=build_run().id,
        project_slug="acme",
        repository_slug="widgets",
        repository_url="u",
        default_branch="main",
        bmad_version="6.11.0",
        spec_folder=None,
    )


def anchors_for(rows: tuple[Any, ...], lane: str, index: int | None, **inputs: Any) -> FrameAnchors:
    run = build_run("running", lane=lane, inputs=inputs, worktree_path="/w")
    row = rows[index] if index is not None else None
    return frame_anchors(FakeGit(), run, environment(), WalkFrame(rows=rows), row)


INPUTS = {"initiative_folder": FOLDER, "slug": SLUG}


def test_ac3_a_walk_lane_run_builds_todays_anchors() -> None:
    for rows in (frame_rows("conversation", "git.commit"), frame_rows("agent", "git.commit")):
        rule = anchors_for(rows, "walk", 1, **INPUTS)
        assert rule.interactive is False
        assert rule.allowed == ()
        assert rule.anchors == protected_paths.build(
            spec_folders=(), initiative_folder=FOLDER, frozen_test_files=()
        )
        paths = [*LETTING, *STOPPING]
        assert rule.check(changed=paths, accepted=()) == tuple(
            hit.path for hit in check(changes(*paths), rule.anchors, ())
        )
        assert rule.check(changed=paths, accepted=()) == ("AGENTS.md", "initiatives/demo/AGENTS.md")


def test_an_interactive_frame_allows_the_nearest_conversation_rows_writes() -> None:
    rows = frame_rows("conversation", "git.commit")
    rule = anchors_for(rows, "interactive", 1, **INPUTS)
    assert rule.interactive is True
    assert rule.allowed == ALLOWED


def test_the_nearest_earlier_conversation_row_decides() -> None:
    rows = list(frame_rows("conversation", "git.commit", "conversation"))
    rows[2] = rows[2].model_copy(update={"with_resolved": {"writes": ["z.md"]}})
    rule = anchors_for(tuple(rows), "interactive", 1, **INPUTS)
    assert rule.allowed == ALLOWED
    later = anchors_for(tuple(rows), "interactive", 2, **INPUTS)
    assert later.allowed == ("initiatives/demo/z.md",)


@pytest.mark.parametrize(
    "inputs",
    [{}, {"initiative_folder": FOLDER}, {"slug": SLUG}],
    ids=["none", "no slug", "no folder"],
)
def test_a_missing_input_exempts_nothing(inputs: dict[str, str]) -> None:
    assert (
        anchors_for(frame_rows("conversation", "git.commit"), "interactive", 1, **inputs).allowed
        == ()
    )


def test_no_conversation_row_or_no_row_allows_nothing() -> None:
    assert anchors_for(frame_rows("agent", "git.commit"), "interactive", 1, **INPUTS).allowed == ()
    assert (
        anchors_for(frame_rows("conversation", "git.commit"), "interactive", None, **INPUTS).allowed
        == ()
    )
    first = anchors_for(frame_rows("git.commit", "conversation"), "interactive", 0, **INPUTS)
    assert first.allowed == ()


def commit_with(status: str) -> Any:
    rows = frame_rows("conversation", "git.commit")
    rule = anchors_for(rows, "interactive", 1, **INPUTS)
    row = rows[1].model_copy(update={"with_resolved": {"message": "m"}})
    git = FakeGit(status=[status])
    return GitCommitExecutor().execute(a_context(row, git=git, protected_paths=rule))


def test_ac4_the_commit_guard_commits_the_declared_files() -> None:
    result = commit_with("?? initiatives/demo/epics.yaml\n")
    assert result.status == "done"


def test_ac4_the_commit_guard_parks_on_any_other_anchor() -> None:
    result = commit_with("?? initiatives/demo/AGENTS.md\n")
    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.park.reason == "protected paths: initiatives/demo/AGENTS.md"
    assert result.payload["hits"] == [{"path": "initiatives/demo/AGENTS.md"}]


def test_ac8_the_member_agents_md_holds_the_r1_line_after_the_consult_senior_bullet() -> None:
    lines = (REPO_ROOT / "AGENTS.md").read_text().splitlines()
    senior = next(
        i
        for i, line in enumerate(lines)
        if "A consult senior may approve named existing test files" in line
    )
    assert lines[senior + 1] == R1_LINE
