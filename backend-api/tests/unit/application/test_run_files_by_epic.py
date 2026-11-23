"""`files_by_epic` and `story_diff` over the shared fakes (story 7, AC1-AC6)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from orchestrator.application.use_cases.run_files_by_epic import (
    FilesByEpicPorts,
    StoryDiff,
    files_by_epic,
    story_diff,
)
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change, GitError
from tests.unit.application.test_run_step_drawer import (
    NOW,
    WORKTREE,
    A,
    B,
    a_row,
    a_run,
    an_attempt,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_history import FakeGitHistory
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.workspace import FakeWorkspace

EPICS = "- {id: e1, spec_folder: e1, title: One}\n- {id: e2, spec_folder: e2, title: Two}\n"
STORIES = "- {id: '1', title: First}\n- {id: '2', title: Second}\n"
HUB = {"initiative_folder": "initiatives/i"}
E1 = "initiatives/i/e1"
FILES = {
    "initiatives/i/epics.yaml": EPICS,
    f"{E1}/SPEC.md": "s",
    f"{E1}/stories.yaml": STORIES,
    f"{E1}/spec-gate-result.md": "g",
    f"{E1}/stories/1-x.md": "x",
}
HOUR = timedelta(hours=1)
GIT_ERROR = GitError(command="git diff", exit_code=1, output="boom")


class Rig:
    def __init__(  # noqa: PLR0913 — one keyword per fixture knob
        self,
        inputs: dict[str, object] | None = None,
        files: dict[str, str] | None = None,
        *,
        prefix: str = "epics[0].stories[0]",
        workdir: str = "",
        attempts: list[dict[str, object]] | None = None,
        git: FakeGit | None = None,
        **run_overrides: object,
    ) -> None:
        self.run = a_run(inputs=HUB if inputs is None else inputs, **run_overrides)
        resolved = {"workdir": workdir} if workdir else {}
        self.row = a_row(self.run, kind="agent", path=f"{prefix}.build", with_resolved=resolved)
        self.other = a_row(self.run, seq=2, path=f"{prefix[:-1]}0].build", kind="agent")
        made = [an_attempt(self.row, n=i + 1, **kw) for i, kw in enumerate(attempts or [])]
        made.append(an_attempt(self.other, start_sha="c" * 40, end_sha="d" * 40))
        self.repo = f"{WORKTREE}/{workdir}" if workdir else WORKTREE
        change = Change(path="src/a.py", kind="modified")
        self.git = git or FakeGit(changes={self.repo: (change,)})
        self.history = FakeGitHistory(diffs={(self.repo, A, B, "src/a.py"): "THE DIFF"})
        self.workspace = FakeWorkspace(files=FILES if files is None else files)
        self.ports = FilesByEpicPorts(
            runs=FakeRunRepository([self.run]),
            steps=FakeStepRunRepository([self.row, self.other]),
            attempts=FakeAttemptRepository(made),
            git=self.git,
            history=self.history,
            workspace=lambda _root: self.workspace,
        )

    def epics(self):  # type: ignore[no-untyped-def]
        return files_by_epic(self.ports, self.run.id)

    def diff(self, epic: int = 0, story: str = "1", path: str = "src/a.py") -> StoryDiff:
        return story_diff(self.ports, self.run.id, epic, story, path)


RANGE = [{"start_sha": A, "end_sha": B, "started_at": NOW, "ended_at": NOW}]


def test_ac1_epics_list_their_files_in_order_and_the_story_file() -> None:
    epics = Rig().epics()

    assert [(e.index, e.title, e.folder) for e in epics] == [
        (0, "One", E1),
        (1, "Two", "initiatives/i/e2"),
    ]
    assert epics[0].files == (f"{E1}/SPEC.md", f"{E1}/stories.yaml", f"{E1}/spec-gate-result.md")
    assert epics[1].files == ()
    assert [s.story_file for s in epics[0].stories] == [f"{E1}/stories/1-x.md", None]
    assert [s.title for s in epics[0].stories] == ["First", "Second"]


def test_a_retrospective_comes_last() -> None:
    files = {**FILES, f"{E1}/RETROSPECTIVE.md": "r"}

    assert Rig(files=files).epics()[0].files[-1] == f"{E1}/RETROSPECTIVE.md"


def test_ac2_a_started_story_reads_the_paths_between_first_start_and_last_end() -> None:
    story = Rig(attempts=RANGE).epics()[0].stories[0]

    assert story.started is True
    assert story.changed == ("src/a.py",)


def test_the_range_runs_from_the_earliest_start_to_the_latest_end() -> None:
    attempts = [
        {
            "start_sha": "9" * 40,
            "end_sha": "8" * 40,
            "started_at": NOW + HOUR,
            "ended_at": NOW + HOUR,
        },
        {"start_sha": A, "end_sha": "7" * 40, "started_at": NOW, "ended_at": NOW},
        {"start_sha": None, "end_sha": B, "started_at": NOW + HOUR * 2, "ended_at": NOW + HOUR * 2},
        {"start_sha": "6" * 40, "end_sha": None, "started_at": None, "ended_at": None},
    ]
    r = Rig(attempts=attempts)

    r.epics()

    assert r.git.called("diff_changes") == [(Path(WORKTREE), A, B)]


def test_ac2_a_workdir_roots_the_repo_and_prefixes_the_paths() -> None:
    r = Rig(workdir="repos/a", attempts=RANGE)

    story = r.epics()[0].stories[0]

    assert story.changed == ("repos/a/src/a.py",)
    assert r.git.called("diff_changes") == [(Path(WORKTREE) / "repos/a", A, B)]


def test_ac2_a_git_error_gives_no_paths_but_the_story_stays_started() -> None:
    story = Rig(attempts=RANGE, git=FakeGit(diff_changes=[GIT_ERROR])).epics()[0].stories[0]

    assert story.started is True
    assert story.changed == ()


def test_ac3_an_unstarted_story_has_no_file_no_paths_and_no_git_call() -> None:
    r = Rig(attempts=RANGE)

    story = r.epics()[0].stories[1]

    assert (story.story_file, story.started, story.changed) == (None, False, ())
    assert len(r.git.called("diff_changes")) == 1


def test_ac3_a_start_without_an_end_is_started_with_no_paths() -> None:
    story = Rig(attempts=[{"start_sha": A, "started_at": NOW}]).epics()[0].stories[0]

    assert (story.started, story.changed) == (True, ())


def test_story_ten_does_not_lend_its_attempts_to_story_one() -> None:
    r = Rig(prefix="epics[0].stories[1]")

    assert [s.started for s in r.epics()[0].stories] == [False, False]


def test_ac4_a_single_spec_folder_is_one_epic_over_stories_frames() -> None:
    files = {"specs/s/stories.yaml": STORIES, "specs/s/SPEC.md": "s"}
    r = Rig(inputs={"spec_folder": "specs/s"}, files=files, prefix="stories[0]", attempts=RANGE)

    epics = r.epics()

    assert [(e.index, e.title, e.folder) for e in epics] == [(0, "specs/s", "specs/s")]
    assert [s.started for s in epics[0].stories] == [True, False]


@pytest.mark.parametrize(
    "overrides",
    [
        {"worktree_path": None},
        {"worktrees_removed": True},
        {"inputs": {}},
        {"files": {}},
        {"files": {"initiatives/i/epics.yaml": "just text"}},
        {"files": {"initiatives/i/epics.yaml": "- a\n- b\n"}},
    ],
)
def test_ac5_nothing_to_read_answers_empty(overrides: dict[str, object]) -> None:
    assert Rig(**overrides).epics() == ()


def test_ac5_an_entry_without_a_folder_is_skipped_and_later_ones_keep_their_index() -> None:
    files = {**FILES, "initiatives/i/epics.yaml": "- {id: x}\n- {spec_folder: e1}\n"}

    epics = Rig(files=files).epics()

    assert [(e.index, e.title) for e in epics] == [(1, E1)]


def test_ac5_a_parent_segment_skips_that_epic_only() -> None:
    files = {**FILES, "initiatives/i/epics.yaml": "- {spec_folder: ../out}\n- {spec_folder: e1}\n"}

    assert [e.index for e in Rig(files=files).epics()] == [1]


def test_a_spec_folder_with_a_parent_segment_answers_empty() -> None:
    assert Rig(inputs={"spec_folder": "../x"}).epics() == ()


def test_a_missing_stories_list_means_no_stories() -> None:
    files = {"initiatives/i/epics.yaml": EPICS}

    assert Rig(files=files).epics()[0].stories == ()


def test_story_entries_without_an_id_are_skipped_and_without_a_title_take_the_id() -> None:
    files = {**FILES, f"{E1}/stories.yaml": "- {title: no id}\n- {id: '2'}\n"}

    stories = Rig(files=files).epics()[0].stories

    assert [(s.id, s.title) for s in stories] == [("2", "2")]


def test_the_first_sorted_story_file_wins() -> None:
    files = {**FILES, f"{E1}/stories/1-a.md": "a"}

    assert Rig(files=files).epics()[0].stories[0].story_file == f"{E1}/stories/1-a.md"


def test_ac5_an_unknown_run_is_not_found() -> None:
    r = Rig()

    with pytest.raises(NotFound):
        files_by_epic(r.ports, new_id())


def test_ac6_the_diff_of_a_changed_path() -> None:
    assert Rig(attempts=RANGE).diff() == StoryDiff("src/a.py", A, B, "THE DIFF")


def test_ac6_a_workdir_prefix_is_stripped_before_asking_git() -> None:
    r = Rig(workdir="repos/a", attempts=RANGE)

    result = r.diff(path="repos/a/src/a.py")

    assert result.path == "repos/a/src/a.py"
    assert r.history.calls == [("diff_path", f"{WORKTREE}/repos/a", A, B, "src/a.py")]


@pytest.mark.parametrize(
    ("epic", "story", "path"),
    [(5, "1", "src/a.py"), (0, "9", "src/a.py"), (0, "1", "src/other.py"), (0, "2", "src/a.py")],
)
def test_ac6_anything_else_is_not_found(epic: int, story: str, path: str) -> None:
    with pytest.raises(NotFound):
        Rig(attempts=RANGE).diff(epic, story, path)


def test_ac6_an_unknown_run_is_not_found() -> None:
    r = Rig(attempts=RANGE)

    with pytest.raises(NotFound):
        story_diff(r.ports, new_id(), 0, "1", "src/a.py")


def test_ac6_the_epic_is_matched_on_its_index_not_its_position() -> None:
    files = {**FILES, "initiatives/i/epics.yaml": "- {id: x}\n- {spec_folder: e1}\n"}
    r = Rig(files=files, prefix="epics[1].stories[0]", attempts=RANGE)

    assert r.diff(epic=1).diff == "THE DIFF"
    with pytest.raises(NotFound):
        r.diff(epic=0)


def test_ac6_a_failing_diff_is_not_found() -> None:
    r = Rig(attempts=RANGE)
    r.ports.history.error = GIT_ERROR  # type: ignore[attr-defined]

    with pytest.raises(NotFound):
        r.diff()


def test_an_unreadable_list_file_answers_empty() -> None:
    assert Rig(inputs={"initiative_folder": "../x"}).epics() == ()


def test_a_repeated_story_id_diffs_over_the_first_entrys_range() -> None:
    files = {**FILES, f"{E1}/stories.yaml": "- {id: '1'}\n- {id: '1'}\n"}
    r = Rig(files=files, attempts=RANGE)

    assert r.epics()[0].stories[0].changed == ("src/a.py",)
    assert r.diff().diff == "THE DIFF"
