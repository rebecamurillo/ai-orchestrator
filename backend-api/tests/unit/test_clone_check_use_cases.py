"""The clone check as a rule: four lines, in order, stopping at the first one that failed.

Every row of the story's I/O matrix that is a use-case decision is asserted here, over the
fake `Git` and the fake stores (AD-18). Nothing reaches a network or a process: what a real
`git` does is `tests/unit/test_subprocess_git.py`'s subject, and what the *rules* do with
its answers is this module's.

The `FakeClock` only moves when something moves it, and `FakeGit` moves it once per command,
so a line's `seconds` is an assertion about the check's bookkeeping rather than about how
fast this machine happens to be.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.use_cases.clone_check import (
    MANIFEST_PATH,
    _reason,
    installed_version,
    run_clone_check,
    run_clone_checks_for_project,
)
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import (
    AUTH_HINT,
    DEFAULT_PACKAGE_MANAGER,
    DEFAULT_TEST_GLOBS,
    LINE_CLONE,
    LINE_DEFAULT_BRANCH,
    LINE_LS_REMOTE,
    LINE_METHOD_VERSION,
    MISSING_VERSION,
    NOT_FOUND_HINT,
    OUTDATED_VERSION,
    CloneCheck,
    Repository,
)
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import CloneResult, GitError, RemoteRef
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
WORK_DIR = Path("/work")
BMAD_VERSION = "6.11.0"
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
COMMAND_SECONDS = 0.5

FOUR_LINES = 4
THREE_LINES = 3
TWO_LINES = 2
ONE_LINE = 1

MANIFEST = "installation:\n  version: 6.11.0\n  installDate: 2026-08-24\nmodules: []\n"
OTHER_MANIFEST = "installation:\n  version: 6.12.0\n"

NOT_FOUND_OUTPUT = "remote: Repository not found.\nfatal: repository not found"
AUTH_OUTPUT = "fatal: Authentication failed for 'https://github.com/org/my-repo.git/'"
TIMEOUT_OUTPUT = "timeout after 120 s"


class Harness:
    """One Project, its Repositories, a scripted `Git`, and a clock that only it moves."""

    def __init__(self, git: FakeGit | None = None, *, attach_git: bool = True) -> None:
        self.clock = FakeClock(AT)
        self.git = git or FakeGit()
        self.git.clock = self.clock
        self.git.seconds = COMMAND_SECONDS
        self.uow = FakeUnitOfWork()
        self.uow.__enter__()
        self.projects = FakeProjectRepository()
        self.repositories = FakeRepositoryRepository()
        self.project = Project(
            id=new_id(),
            slug="my-project",
            name="My Project",
            context_text="",
            context_paths=(),
            env_vars_enc=(),
            log_prompt_content=False,
            created_at=AT,
            updated_at=AT,
        )
        self.projects.add(self.project)
        self.ports = ProjectPorts(
            uow=self.uow,
            projects=self.projects,
            repositories=self.repositories,
            crypto=None,  # type: ignore[arg-type] — no rule here encrypts anything
            clock=self.clock,
            git=self.git if attach_git else None,
        )

    def repository(self, slug: str = "my-repo", **overrides: object) -> Repository:
        fields: dict[str, object] = {
            "id": new_id(),
            "project_id": self.project.id,
            "slug": slug,
            "url": f"https://github.com/org/{slug}.git",
            "default_branch": "main",
            "install_command": "",
            "quality_gate_command": "",
            "unit_test_command": "",
            "test_globs": DEFAULT_TEST_GLOBS,
            "package_manager": DEFAULT_PACKAGE_MANAGER,
            "clone_check": CloneCheck.pending(),
            "created_at": AT,
            "updated_at": AT,
        }
        fields.update(overrides)
        repository = Repository(**fields)  # type: ignore[arg-type]
        self.repositories.add(repository)
        return repository

    def check(self, repository: Repository) -> Repository:
        return run_clone_check(
            self.ports, repository.id, work_dir=WORK_DIR, bmad_version=BMAD_VERSION
        )


def reachable(manifest: str | None = MANIFEST) -> FakeGit:
    """A remote that answers everything, with whatever manifest the row needs."""
    return FakeGit(
        ls_remote=[RemoteRef(ref="HEAD", sha=SHA), RemoteRef(ref="refs/heads/main", sha=SHA)],
        clone_base=[CloneResult(seconds=1.0, bytes=4096)],
        read_file=[manifest],
    )


def line(repository: Repository, name: str) -> object:
    return next(item for item in repository.clone_check.lines if item.name == name)


# ── the ok path ──────────────────────────────────────────────────────────────


def test_a_reachable_repository_reports_four_ok_lines_in_order() -> None:
    harness = Harness(reachable())

    checked = harness.check(harness.repository())

    assert [item.name for item in checked.clone_check.lines] == [
        LINE_LS_REMOTE,
        LINE_CLONE,
        LINE_DEFAULT_BRANCH,
        LINE_METHOD_VERSION,
    ]
    assert {item.status for item in checked.clone_check.lines} == {"ok"}


def test_the_ok_path_is_ok_with_no_summary_output_and_no_hint() -> None:
    harness = Harness(reachable())

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "ok"
    assert checked.clone_check.output == ""
    assert checked.clone_check.hint == ""


def test_each_line_carries_the_time_its_commands_took() -> None:
    """The duration comes from the `Clock`, which is why a fake can state it exactly.

    Line 2 is twice the others because it runs two commands: it asks whether a base clone
    is there before it makes or fetches one.
    """
    harness = Harness(reachable())

    checked = harness.check(harness.repository())

    assert [item.seconds for item in checked.clone_check.lines] == [
        COMMAND_SECONDS,
        COMMAND_SECONDS * 2,
        COMMAND_SECONDS,
        COMMAND_SECONDS,
    ]


def test_the_check_is_stamped_with_the_instant_it_finished() -> None:
    """Five commands at half a second each; `clone_check.at` is when the last one ended."""
    harness = Harness(reachable())

    checked = harness.check(harness.repository())

    assert (checked.clone_check.at - AT).total_seconds() == COMMAND_SECONDS * 5


def test_the_base_clone_goes_under_the_project_and_repository_slugs() -> None:
    """AD-14: `/work/{project.slug}/{repository.slug}/base`, and nowhere else."""
    harness = Harness(reachable())

    harness.check(harness.repository())

    assert harness.git.called("clone_base")[0][1] == WORK_DIR / "my-project" / "my-repo" / "base"


def test_the_clone_line_reports_what_the_clone_wrote() -> None:
    harness = Harness(reachable())

    checked = harness.check(harness.repository())

    assert "4096" in line(checked, LINE_CLONE).output  # type: ignore[attr-defined]


def test_the_result_is_stored_and_committed() -> None:
    harness = Harness(reachable())
    repository = harness.repository()

    harness.check(repository)

    assert harness.repositories.get(repository.id).clone_check.status == "ok"  # type: ignore[union-attr]
    assert harness.uow.committed is True


def test_the_check_never_bumps_updated_at() -> None:
    """`updated_at` is when the Operator last edited the Repository; `clone_check.at` is
    when the check ran. Bumping the first would make every check look like an edit."""
    harness = Harness(reachable())
    repository = harness.repository()

    checked = harness.check(repository)

    assert checked.updated_at == repository.updated_at


def test_the_check_changes_nothing_but_the_clone_check() -> None:
    harness = Harness(reachable())
    repository = harness.repository()

    checked = harness.check(repository)

    assert checked.model_dump(exclude={"clone_check"}) == repository.model_dump(
        exclude={"clone_check"}
    )


# ── the method version ───────────────────────────────────────────────────────


def test_a_manifest_stating_this_instances_version_reports_it() -> None:
    harness = Harness(reachable())

    checked = harness.check(harness.repository())

    assert checked.clone_check.bmad_version == BMAD_VERSION


def test_the_manifest_is_read_from_the_repositorys_default_branch() -> None:
    harness = Harness(reachable())

    harness.check(harness.repository())

    assert harness.git.called("read_file")[0][1:] == ("main", MANIFEST_PATH)


def test_a_manifest_stating_another_version_reads_outdated() -> None:
    harness = Harness(reachable(OTHER_MANIFEST))

    checked = harness.check(harness.repository())

    assert checked.clone_check.bmad_version == OUTDATED_VERSION
    assert checked.clone_check.status == "ok"


def test_a_repository_with_no_manifest_reads_missing_and_still_passes() -> None:
    harness = Harness(reachable(None))

    checked = harness.check(harness.repository())

    assert checked.clone_check.bmad_version == MISSING_VERSION
    assert checked.clone_check.status == "ok"
    assert line(checked, LINE_METHOD_VERSION).status == "ok"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "manifest",
    ["installation:\n  name: bmad\n", "not: a manifest\n", "]]] not yaml at all\n"],
    ids=["no-version", "no-installation", "unparseable"],
)
def test_a_manifest_that_states_no_version_reads_missing_with_the_reason(manifest: str) -> None:
    """A parse failure is a fact about the repository, not a failure of the check."""
    harness = Harness(reachable(manifest))

    checked = harness.check(harness.repository())

    assert checked.clone_check.bmad_version == MISSING_VERSION
    assert MANIFEST_PATH in line(checked, LINE_METHOD_VERSION).output  # type: ignore[attr-defined]


def test_a_manifest_that_could_not_be_read_reads_missing_and_never_fails_the_check() -> None:
    git = reachable()
    git._scripts["read_file"] = [GitError(command="git show", exit_code=128, output="fatal: bad")]
    harness = Harness(git)

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "ok"
    assert checked.clone_check.bmad_version == MISSING_VERSION
    assert line(checked, LINE_METHOD_VERSION).status == "ok"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        ("installation:\n  version: 6.11.0\n", "6.11.0"),
        ("installation:\n  version: '6.11.0'\n", "6.11.0"),
        ('installation:\n  version: "6.11.0"\n', "6.11.0"),
        ("# a comment\ninstallation:\n\n  version: 6.11.0\n", "6.11.0"),
        ("modules:\n  - version: 1.0\ninstallation:\n  version: 6.11.0\n", "6.11.0"),
        ("installation:\n  version: 6.11.0  # pinned by the image\n", "6.11.0"),
        ("installation:\n  version: '6.11.0 # not a comment'\n", "6.11.0 # not a comment"),
        ("installation:\n  version:\n", None),
        ("installation: {}\nmodules:\n  version: 9\n", None),
        ("", None),
        ("  version: 6.11.0\n", None),
    ],
    ids=[
        "plain",
        "single-quoted",
        "double-quoted",
        "comment-and-blank-line",
        "another-section-first",
        "inline-comment",
        "hash-inside-quotes",
        "empty-value",
        "version-under-another-key",
        "empty-file",
        "indented-with-no-section",
    ],
)
def test_the_manifest_reader_takes_installation_version_and_nothing_else(
    manifest: str, expected: str | None
) -> None:
    assert installed_version(manifest) == expected


# ── the failing lines ────────────────────────────────────────────────────────


def test_an_unreachable_url_fails_at_the_first_line_and_runs_nothing_after_it() -> None:
    error = GitError(command="git ls-remote", exit_code=128, output=NOT_FOUND_OUTPUT)
    harness = Harness(FakeGit(ls_remote=[error]))

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "failed"
    assert len(checked.clone_check.lines) == ONE_LINE
    assert checked.clone_check.output == NOT_FOUND_OUTPUT
    assert checked.clone_check.hint == NOT_FOUND_HINT
    assert harness.git.called("clone_base") == []


def test_a_remote_that_answers_no_ref_at_all_is_a_failed_first_line() -> None:
    harness = Harness(FakeGit(ls_remote=[None]))

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "failed"
    assert len(checked.clone_check.lines) == ONE_LINE


def test_a_refused_credential_is_reported_with_the_hint_that_names_the_token() -> None:
    error = GitError(command="git ls-remote", exit_code=128, output=AUTH_OUTPUT)
    harness = Harness(FakeGit(ls_remote=[error]))

    checked = harness.check(harness.repository())

    assert checked.clone_check.hint == AUTH_HINT


def test_a_failing_clone_stops_before_the_branch_check() -> None:
    error = GitError(command="git clone", exit_code=128, output="fatal: could not create work tree")
    harness = Harness(FakeGit(clone_base=[error]))

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "failed"
    assert len(checked.clone_check.lines) == TWO_LINES
    assert line(checked, LINE_CLONE).status == "failed"  # type: ignore[attr-defined]
    assert harness.git.called("read_file") == []


def test_a_default_branch_the_origin_does_not_have_fails_the_third_line() -> None:
    git = FakeGit(ls_remote=[RemoteRef(ref="HEAD", sha=SHA), None])
    harness = Harness(git)

    checked = harness.check(harness.repository(default_branch="develop"))

    assert checked.clone_check.status == "failed"
    assert len(checked.clone_check.lines) == THREE_LINES
    assert checked.clone_check.hint == "branch develop does not exist on origin"
    assert harness.git.called("read_file") == []


def test_a_branch_lookup_that_errors_is_a_failed_third_line() -> None:
    error = GitError(command="git ls-remote", exit_code=128, output="fatal: the end hung up")
    harness = Harness(FakeGit(ls_remote=[RemoteRef(ref="HEAD", sha=SHA), error]))

    checked = harness.check(harness.repository())

    assert len(checked.clone_check.lines) == THREE_LINES
    assert checked.clone_check.hint == ""


def test_a_command_that_ran_out_of_time_says_so_verbatim() -> None:
    error = GitError(command="git clone", exit_code=-1, output=TIMEOUT_OUTPUT)
    harness = Harness(FakeGit(clone_base=[error]))

    checked = harness.check(harness.repository())

    assert line(checked, LINE_CLONE).output == TIMEOUT_OUTPUT  # type: ignore[attr-defined]
    assert checked.clone_check.output == TIMEOUT_OUTPUT


# ── a failure that is not git's ──────────────────────────────────────────────
#
# The adapter raises `OSError`, not `GitError`, on the ordinary paths that have nothing to do
# with a remote: an unwritable `WORK_DIR`, a `git` that is not on `PATH`, a file that vanished
# while a clone was being measured. Each one is a fact about this instance, and each one has
# to arrive as a failed line — an exception escaping here would answer a 500 for a `PUT` that
# had already committed.


@pytest.mark.parametrize(
    ("method", "expected_lines"),
    [
        ("ls_remote", ONE_LINE),
        ("clone_base", TWO_LINES),
    ],
    ids=["reaching-the-remote", "making-the-clone"],
)
def test_an_environment_failure_is_a_failed_line_and_never_escapes(
    method: str, expected_lines: int
) -> None:
    git = reachable()
    git._scripts[method] = [PermissionError(13, "Permission denied", "/work")]
    harness = Harness(git)

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "failed"
    assert len(checked.clone_check.lines) == expected_lines
    assert "PermissionError" in checked.clone_check.output


def test_a_git_binary_that_is_not_installed_is_a_failed_line() -> None:
    """`subprocess.run(["git", ...])` raises `FileNotFoundError`, not a `GitError`."""
    harness = Harness(FakeGit(ls_remote=[FileNotFoundError(2, "No such file", "git")]))

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "failed"
    assert "FileNotFoundError" in checked.clone_check.output


def test_an_environment_failure_looking_up_the_branch_is_a_failed_third_line() -> None:
    git = reachable()
    git._scripts["ls_remote"] = [
        RemoteRef(ref="HEAD", sha=SHA),
        OSError("the work directory went away"),
    ]
    harness = Harness(git)

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "failed"
    assert len(checked.clone_check.lines) == THREE_LINES
    assert "OSError" in checked.clone_check.output


def test_an_environment_failure_reading_the_manifest_still_leaves_the_check_ok() -> None:
    """Line 4 is informational whatever failed, not only when git was the one refusing."""
    git = reachable()
    git._scripts["read_file"] = [OSError("cannot read the object store")]
    harness = Harness(git)

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "ok"
    assert checked.clone_check.bmad_version == MISSING_VERSION
    assert line(checked, LINE_METHOD_VERSION).status == "ok"  # type: ignore[attr-defined]
    assert "OSError" in line(checked, LINE_METHOD_VERSION).output  # type: ignore[attr-defined]


def test_a_failed_check_never_stops_the_save_from_checking_the_rest() -> None:
    """The invariant a `PUT` depends on, against the failure class that is not git's."""
    git = FakeGit(
        ls_remote=[
            PermissionError(13, "Permission denied", "/work"),
            RemoteRef(ref="HEAD", sha=SHA),
            RemoteRef(ref="refs/heads/main", sha=SHA),
        ],
        read_file=[MANIFEST],
    )
    harness = Harness(git)
    harness.repository("first")
    harness.repository("second")

    first, second = run_clone_checks_for_project(
        harness.ports, harness.project.id, work_dir=WORK_DIR, bmad_version=BMAD_VERSION
    )

    assert (first.clone_check.status, second.clone_check.status) == ("failed", "ok")


def test_git_says_it_in_its_own_words_and_anything_else_names_its_class() -> None:
    """A `GitError` already carries git's redacted output; the rest report themselves."""
    assert _reason(GitError(command="git clone", exit_code=1, output="fatal: nope")) == (
        "fatal: nope"
    )
    assert _reason(PermissionError(13, "Permission denied")) == (
        "PermissionError: [Errno 13] Permission denied"
    )


# ── the second check ─────────────────────────────────────────────────────────


def test_an_existing_base_is_fetched_rather_than_cloned_again() -> None:
    git = reachable()
    git._scripts["base_exists"] = [True]
    harness = Harness(git)

    checked = harness.check(harness.repository())

    assert harness.git.called("clone_base") == []
    assert harness.git.called("fetch_base") == [
        (WORK_DIR / "my-project" / "my-repo" / "base", "main")
    ]
    assert "fetched" in line(checked, LINE_CLONE).output  # type: ignore[attr-defined]
    assert checked.clone_check.status == "ok"


def test_a_fetch_that_fails_is_a_failed_second_line() -> None:
    git = reachable()
    git._scripts["base_exists"] = [True]
    git._scripts["fetch_base"] = [
        GitError(command="git fetch", exit_code=128, output="fatal: refusing")
    ]
    harness = Harness(git)

    checked = harness.check(harness.repository())

    assert checked.clone_check.status == "failed"
    assert len(checked.clone_check.lines) == TWO_LINES


# ── the refusals ─────────────────────────────────────────────────────────────


def test_an_unknown_repository_id_is_a_not_found() -> None:
    harness = Harness(reachable())

    with pytest.raises(NotFound, match="repository"):
        run_clone_check(harness.ports, UUID(int=1), work_dir=WORK_DIR, bmad_version=BMAD_VERSION)


def test_a_ports_object_with_no_git_refuses_loudly_rather_than_writing_pending() -> None:
    """Only a route wires this use case, and every route wires a git adapter."""
    harness = Harness(attach_git=False)
    repository = harness.repository()

    with pytest.raises(RuntimeError, match="git"):
        run_clone_check(harness.ports, repository.id, work_dir=WORK_DIR, bmad_version=BMAD_VERSION)


def test_a_ports_object_with_no_repository_store_refuses_loudly() -> None:
    harness = Harness(reachable())
    ports = ProjectPorts(
        uow=harness.uow,
        projects=harness.projects,
        crypto=None,  # type: ignore[arg-type]
        clock=harness.clock,
        git=harness.git,
    )

    with pytest.raises(RuntimeError, match="repositories"):
        run_clone_check(ports, UUID(int=1), work_dir=WORK_DIR, bmad_version=BMAD_VERSION)


# ── a Project's Repositories ─────────────────────────────────────────────────


def test_a_save_checks_every_repository_the_project_holds() -> None:
    harness = Harness(reachable())
    first = harness.repository("first")
    second = harness.repository("second")

    checked = run_clone_checks_for_project(
        harness.ports, harness.project.id, work_dir=WORK_DIR, bmad_version=BMAD_VERSION
    )

    assert [item.id for item in checked] == [first.id, second.id]
    assert harness.repositories.get(first.id).clone_check.status == "ok"  # type: ignore[union-attr]
    assert harness.repositories.get(second.id).clone_check.status == "ok"  # type: ignore[union-attr]


def test_one_repository_failing_never_stops_the_others_from_being_checked() -> None:
    error = GitError(command="git ls-remote", exit_code=128, output=NOT_FOUND_OUTPUT)
    git = FakeGit(
        ls_remote=[
            error,
            RemoteRef(ref="HEAD", sha=SHA),
            RemoteRef(ref="refs/heads/main", sha=SHA),
        ],
        read_file=[MANIFEST],
    )
    harness = Harness(git)
    harness.repository("first")
    harness.repository("second")

    first, second = run_clone_checks_for_project(
        harness.ports, harness.project.id, work_dir=WORK_DIR, bmad_version=BMAD_VERSION
    )

    assert (first.clone_check.status, second.clone_check.status) == ("failed", "ok")
    assert first.clone_check.hint == NOT_FOUND_HINT


def test_a_project_with_no_repositories_checks_nothing_and_still_commits() -> None:
    harness = Harness(reachable())

    assert (
        run_clone_checks_for_project(
            harness.ports, harness.project.id, work_dir=WORK_DIR, bmad_version=BMAD_VERSION
        )
        == []
    )
    assert harness.git.calls == []


def test_a_ports_object_without_a_git_port_checks_nothing_rather_than_raising() -> None:
    """The Project-only harnesses that predate this port are not a wiring bug."""
    harness = Harness(attach_git=False)
    harness.repository()

    assert (
        run_clone_checks_for_project(
            harness.ports, harness.project.id, work_dir=WORK_DIR, bmad_version=BMAD_VERSION
        )
        == []
    )


def test_a_ports_object_without_a_repository_store_checks_nothing() -> None:
    harness = Harness(reachable())
    ports = ProjectPorts(
        uow=harness.uow,
        projects=harness.projects,
        crypto=None,  # type: ignore[arg-type]
        clock=harness.clock,
        git=harness.git,
    )

    assert (
        run_clone_checks_for_project(
            ports, harness.project.id, work_dir=WORK_DIR, bmad_version=BMAD_VERSION
        )
        == []
    )


def test_an_unknown_project_id_is_a_not_found() -> None:
    harness = Harness(reachable())

    with pytest.raises(NotFound, match="project"):
        run_clone_checks_for_project(
            harness.ports, UUID(int=1), work_dir=WORK_DIR, bmad_version=BMAD_VERSION
        )
