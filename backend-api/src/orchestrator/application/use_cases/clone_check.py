"""Running a Repository's clone check, and deciding what its four lines mean.

The check answers one question — *can this instance actually work in this repository?* — by
running the four cheapest commands that can answer it, in the order that makes each one
worth running:

1. **`ls-remote`** — the URL resolves and the credential is accepted.
2. **`clone`** — the base clone at `{work_dir}/{project.slug}/{repository.slug}/base`
   (AD-14) exists; it is made blobless the first time and fetched every time after.
3. **`default branch`** — the branch a Run would work from is on the origin.
4. **`method version`** — which BMAD version the repository carries (FR-30).

Two rules decide the outcome. **The first three stop the check**: a clone is pointless if the
URL is wrong, and a branch lookup is pointless if there is nothing cloned, so a failed line
is the last line and `status` is `failed`. **The fourth never does**: a repository with no
`_bmad/` is a repository this orchestrator can still install into, so a missing or
unreadable manifest is reported as `bmad_version` and leaves the check `ok`.

Nothing here performs I/O. The `Git` port runs the commands, the `Clock` port times them,
and `work_dir` and `bmad_version` arrive as arguments, because `application/` may not import
`subprocess`, `os` or `shutil` (AD-2) and may not read the environment (AD-20). A failure
arrives as a `GitError` whose `output` the adapter has already redacted (AD-5), so storing
it verbatim — which is what an Operator needs to see — cannot leak the token.

**Every failure a step can have is a failed line**, not only the ones git reports. An
unwritable `WORK_DIR`, a `git` that is not on `PATH`, a file that vanishes while the adapter
measures a clone: each of those is an `OSError` from the adapter rather than a `GitError`,
and each of them describes this instance's environment — exactly what the Operator opened
the check to find out. Letting one escape would also break the rule the save depends on: the
Project and its Repositories are already committed when the checks run, so an exception
leaving here would answer a 500 for a `PUT` that had in fact succeeded.

`repository.clone_check` is written here and by nothing else (AD-14).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.use_cases.projects import (
    ProjectPorts,
    _repos,
    _require,
    _require_repository,
)
from orchestrator.domain.entities.repository import (
    LINE_CLONE,
    LINE_DEFAULT_BRANCH,
    LINE_LS_REMOTE,
    LINE_METHOD_VERSION,
    MISSING_VERSION,
    OUTDATED_VERSION,
    CloneCheck,
    CloneCheckLine,
    CloneCheckLineStatus,
    Repository,
)
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git, GitError

#: The directory a Repository's base clone lives in, under its Project's (AD-14).
BASE_DIRECTORY = "base"

#: Where a repository states which BMAD version was installed into it (AD-16, FR-30).
MANIFEST_PATH = "_bmad/_config/manifest.yaml"
MANIFEST_SECTION = "installation"
MANIFEST_KEY = "version"

OK: CloneCheckLineStatus = "ok"
FAILED: CloneCheckLineStatus = "failed"

#: What a step can fail with. `GitError` is git refusing; `OSError` is this instance's
#: environment refusing — an unwritable work directory, or no `git` on `PATH`.
STEP_FAILURES = (GitError, OSError)

#: Marks the start of an inline comment in a manifest's scalar.
COMMENT_MARKER = " #"


def _reason(error: Exception) -> str:
    """The sentence a failed line carries.

    A `GitError` already holds the adapter's redacted output, and it is git's own words,
    which is what an Operator needs. Anything else is an environment failure that never saw
    the token, and reports itself by class and message so the line names what went wrong
    rather than saying only that something did.
    """
    if isinstance(error, GitError):
        return error.output
    return f"{type(error).__name__}: {error}"


@dataclass(frozen=True)
class _Outcome:
    """What one checked command decided: its line's status, its output, and any version."""

    status: CloneCheckLineStatus
    output: str
    bmad_version: str | None = None


def run_clone_check(
    ports: ProjectPorts, repository_id: UUID, *, work_dir: Path, bmad_version: str
) -> Repository:
    """Check one Repository and store the result. Only this function writes `clone_check`."""
    repositories = _repos(ports)
    repository = _require_repository(repositories, repository_id)
    project = _require(ports.projects, repository.project_id)
    base = _base(work_dir, project.slug, repository.slug)
    checked = _checked(_git(ports), ports.clock, repository, base, bmad_version)
    repositories.update(checked)
    ports.uow.commit()
    return checked


def run_clone_checks_for_project(
    ports: ProjectPorts, project_id: UUID, *, work_dir: Path, bmad_version: str
) -> list[Repository]:
    """Check every Repository a Project holds, after the save that stored them committed.

    A `ProjectPorts` with no `git` — or no repository store — is the Project-only harness
    that predates both ports, not a wiring bug, so it checks nothing rather than raising;
    `run_clone_check`, which only a route reaches, refuses loudly instead. A Repository whose
    check failed is still stored with its result: a failing check never fails the save.
    """
    if ports.git is None or ports.repositories is None:
        return []
    repositories = ports.repositories
    project = _require(ports.projects, project_id)
    checked = [
        _checked(
            ports.git,
            ports.clock,
            repository,
            _base(work_dir, project.slug, repository.slug),
            bmad_version,
        )
        for repository in repositories.list_by_project(project_id)
    ]
    for repository in checked:
        repositories.update(repository)
    ports.uow.commit()
    return checked


def installed_version(manifest: str) -> str | None:
    """`installation.version` out of a BMAD manifest, or `None` when it does not state one.

    Deliberately not a YAML parse. The one value this reads is a scalar under a top-level
    key, the file is written by a tool rather than by hand, and a malformed manifest is a
    fact to report — `bmad_version: "missing"` — rather than an exception to handle. Adding a
    YAML runtime dependency to read two lines would be the larger cost.
    """
    inside = False
    for raw in manifest.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            inside = line.split(":", 1)[0].strip() == MANIFEST_SECTION
            continue
        key, _, value = line.strip().partition(":")
        if inside and key == MANIFEST_KEY and _scalar(value):
            return _scalar(value)
    return None


def _scalar(value: str) -> str:
    """A manifest scalar as this reader takes it: quotes stripped, inline comment dropped.

    A quoted value keeps everything between its quotes — a `#` in there is content. An
    unquoted one ends at ` #`, so `version: 6.11.0  # pinned` is the version and not the
    version plus a sentence, which would otherwise read as `outdated` against a matching
    instance.
    """
    text = value.strip()
    if text[:1] in ("'", '"'):
        return text[1:].partition(text[0])[0]
    return text.partition(COMMENT_MARKER)[0].strip()


# ── the four lines ───────────────────────────────────────────────────────────


def _git(ports: ProjectPorts) -> Git:
    """Type-narrow `ports.git`, refusing a `ProjectPorts` no route built."""
    if ports.git is None:
        raise RuntimeError("ProjectPorts.git is not set: the clone check needs a git port")
    return ports.git


def _base(work_dir: Path, project_slug: str, repository_slug: str) -> Path:
    """`{work_dir}/{project.slug}/{repository.slug}/base` — the one layout (AD-14)."""
    return work_dir / project_slug / repository_slug / BASE_DIRECTORY


def _checked(
    git: Git, clock: Clock, repository: Repository, base: Path, bmad_version: str
) -> Repository:
    """The Repository with its new `clone_check`. Nothing else about it changes."""
    return repository.model_copy(
        update={"clone_check": _check(git, clock, repository, base, bmad_version)}
    )


def _check(
    git: Git, clock: Clock, repository: Repository, base: Path, bmad_version: str
) -> CloneCheck:
    """Run the lines in order, stopping at the first of the three that can fail."""
    lines: list[CloneCheckLine] = []
    version: str | None = None
    for name, action in _steps(git, repository, base, bmad_version):
        line, outcome = _timed(clock, name, action)
        lines.append(line)
        version = outcome.bmad_version or version
        if line.status == FAILED:
            return _result(clock, FAILED, line.output, version, lines)
    return _result(clock, OK, "", version, lines)


def _steps(
    git: Git, repository: Repository, base: Path, bmad_version: str
) -> list[tuple[str, Callable[[], _Outcome]]]:
    """The four commands, paired with the line each one writes."""
    branch = repository.default_branch
    return [
        (LINE_LS_REMOTE, lambda: _reachable(git, repository.url)),
        (LINE_CLONE, lambda: _cloned(git, repository.url, base, branch)),
        (LINE_DEFAULT_BRANCH, lambda: _branch(git, repository.url, branch)),
        (LINE_METHOD_VERSION, lambda: _version(git, base, branch, bmad_version)),
    ]


def _timed(
    clock: Clock, name: str, action: Callable[[], _Outcome]
) -> tuple[CloneCheckLine, _Outcome]:
    """One line, with the duration read from the `Clock` rather than measured in here."""
    started = clock.now()
    outcome = action()
    seconds = (clock.now() - started).total_seconds()
    line = CloneCheckLine(name=name, status=outcome.status, seconds=seconds, output=outcome.output)
    return line, outcome


def _result(
    clock: Clock,
    status: str,
    output: str,
    version: str | None,
    lines: list[CloneCheckLine],
) -> CloneCheck:
    """`at` is the instant the check finished; `hint` is derived, never stored."""
    return CloneCheck(
        status="failed" if status == FAILED else "ok",
        at=clock.now(),
        output=output,
        bmad_version=version,
        lines=tuple(lines),
    )


def _reachable(git: Git, url: str) -> _Outcome:
    try:
        ref = git.ls_remote(url)
    except STEP_FAILURES as error:
        return _Outcome(FAILED, _reason(error))
    if ref is None:
        return _Outcome(FAILED, f"{url}: the remote answered no refs")
    return _Outcome(OK, f"reachable, HEAD at {ref.sha}")


def _cloned(git: Git, url: str, base: Path, branch: str) -> _Outcome:
    """The base clone: made once, fetched every time after (AD-14)."""
    try:
        if git.base_exists(base):
            git.fetch_base(base, branch)
            return _Outcome(OK, "fetched")
        result = git.clone_base(url, base)
        return _Outcome(OK, f"cloned {result.bytes} bytes")
    except STEP_FAILURES as error:
        return _Outcome(FAILED, _reason(error))


def _branch(git: Git, url: str, branch: str) -> _Outcome:
    """Asked of the origin rather than of the clone: the origin is what a Run pushes to."""
    try:
        ref = git.ls_remote(url, branch)
    except STEP_FAILURES as error:
        return _Outcome(FAILED, _reason(error))
    if ref is None:
        return _Outcome(FAILED, f"branch {branch} does not exist on origin")
    return _Outcome(OK, f"{branch} at {ref.sha}")


def _version(git: Git, base: Path, branch: str, expected: str) -> _Outcome:
    """Informational, always. Every path here is `ok`; only `bmad_version` differs."""
    try:
        manifest = git.read_file(base, branch, MANIFEST_PATH)
    except STEP_FAILURES as error:
        return _Outcome(OK, _reason(error), MISSING_VERSION)
    if manifest is None:
        return _Outcome(OK, f"no {MANIFEST_PATH} in the repository", MISSING_VERSION)
    stated = installed_version(manifest)
    if stated is None:
        return _Outcome(
            OK, f"{MANIFEST_PATH} states no {MANIFEST_SECTION}.{MANIFEST_KEY}", MISSING_VERSION
        )
    if stated != expected:
        return _Outcome(
            OK, f"{MANIFEST_PATH} states {stated}, this instance runs {expected}", OUTDATED_VERSION
        )
    return _Outcome(OK, f"{MANIFEST_PATH} states {stated}", stated)
