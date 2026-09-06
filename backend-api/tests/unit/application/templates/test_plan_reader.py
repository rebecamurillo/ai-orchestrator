"""`PlanReader`: the only thing in the planner that touches `Git`, and it asks once.

FR-10 says a list file is read once per Run. That is a property of this object rather than
of the walker: the walker asks for the same `(ref, path)` as often as the tree makes it
ask, and the memo below is what turns those into one `Git` call — which is exactly what
makes the rule checkable on `FakeGit.calls` instead of by reading the walker.

`record` is separate from `read` on purpose. `Run.plan_refs` is "the commit each list file
was read at, so a plan can be called stale", so it holds the list files and not every file
the plan happened to open; a story file is read at its frame's ref and records nothing.
"""

from __future__ import annotations

from orchestrator.application.templates.reader import PlanReader
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit

REF = fixtures.BASE_SHA
PATH = "docs/epic-1/stories.yaml"
PREFIX = "docs/epic-1/stories"

#: One read per ref: two refs, two reads.
READS_PER_REF = 2


def reader(git: FakeGit) -> PlanReader:
    return PlanReader(git, base=fixtures.BASE, url=fixtures.REPOSITORY.url)


def test_a_branch_the_remote_holds_answers_its_sha() -> None:
    git = FakeGit(refs={"main": REF})

    assert reader(git).sha("main") == REF


def test_a_branch_the_remote_does_not_hold_answers_nothing() -> None:
    git = FakeGit(refs={"main": REF})

    assert reader(git).sha("chore/bmad-init") is None


def test_the_same_branch_is_asked_of_the_remote_once() -> None:
    git = FakeGit(refs={"main": REF})
    memo = reader(git)

    memo.sha("main")
    memo.sha("main")

    assert len(git.called("ls_remote")) == 1


def test_a_branch_that_is_not_there_is_asked_once_too() -> None:
    """Memoising only the answers that exist would re-ask for every absent branch."""
    git = FakeGit(refs={"main": REF})
    memo = reader(git)

    memo.sha("nope")
    memo.sha("nope")

    assert len(git.called("ls_remote")) == 1


def test_a_file_is_read_out_of_the_base_clone_at_the_ref_it_was_asked_for() -> None:
    git = FakeGit(files={(REF, PATH): "- id: 1\n"})

    assert reader(git).read(REF, PATH) == "- id: 1\n"
    assert git.called("read_file") == [(fixtures.BASE, REF, PATH)]


def test_a_file_that_is_not_in_the_tree_answers_nothing() -> None:
    git = FakeGit(files={})

    assert reader(git).read(REF, PATH) is None


def test_the_same_file_at_the_same_ref_is_read_once() -> None:
    git = FakeGit(files={(REF, PATH): "- id: 1\n"})
    memo = reader(git)

    memo.read(REF, PATH)
    memo.read(REF, PATH)

    assert len(git.called("read_file")) == 1


def test_the_same_file_at_two_refs_is_two_reads() -> None:
    """A frame at another commit is another file; one memo entry would hide that."""
    git = FakeGit(files={(REF, PATH): "a"})
    memo = reader(git)

    memo.read(REF, PATH)
    memo.read(fixtures.WORK_SHA, PATH)

    assert len(git.called("read_file")) == READS_PER_REF


def test_a_listing_answers_every_path_under_the_prefix() -> None:
    git = FakeGit(listings={(REF, PREFIX): [f"{PREFIX}/1-a.md"]})

    assert reader(git).listing(REF, PREFIX) == (f"{PREFIX}/1-a.md",)


def test_a_prefix_with_nothing_under_it_answers_nothing() -> None:
    git = FakeGit(listings={})

    assert reader(git).listing(REF, PREFIX) == ()


def test_the_same_listing_is_asked_for_once() -> None:
    git = FakeGit(listings={(REF, PREFIX): [f"{PREFIX}/1-a.md"]})
    memo = reader(git)

    memo.listing(REF, PREFIX)
    memo.listing(REF, PREFIX)

    assert len(git.called("list_files")) == 1


def test_a_prefix_with_nothing_under_it_is_asked_for_once_too() -> None:
    """A Story folder nobody has written to yet is one `ls-tree` per Run, not per Story."""
    git = FakeGit(listings={})
    memo = reader(git)

    memo.listing(REF, PREFIX)
    memo.listing(REF, PREFIX)

    assert len(git.called("list_files")) == 1


def test_a_file_that_is_not_there_is_asked_for_once_too() -> None:
    git = FakeGit(files={})
    memo = reader(git)

    memo.read(REF, PATH)
    memo.read(REF, PATH)

    assert len(git.called("read_file")) == 1


def test_a_recorded_list_file_is_the_commit_it_was_read_at() -> None:
    memo = reader(FakeGit())

    memo.record(PATH, REF)

    assert memo.plan_refs == {PATH: REF}


def test_reading_a_file_records_nothing_by_itself() -> None:
    """A story file is not what makes a plan stale, so it is not in `plan_refs`."""
    git = FakeGit(files={(REF, PATH): "a"})
    memo = reader(git)

    memo.read(REF, PATH)

    assert memo.plan_refs == {}
