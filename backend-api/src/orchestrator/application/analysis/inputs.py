"""What one calculation reads of each repository of a Run (ARCHITECTURE §7.1, §7.4).

Pure over ports. Head is the commit the Run pushed (`head_pushed`) and never another one;
base is the merge base of head and the remote's base branch; the repository's declaration is
read at base. A failure of one repository is that repository's `failed` analysis and never
stops the next.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.declaration import (
    DECLARATION_FILE,
    DEFAULT_DECLARATION,
    Declaration,
    parse_declaration,
)
from orchestrator.application.metrics.scopes import repository_of
from orchestrator.domain.entities.analysis import Analysis, AnalysisStatus
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run_records import ROOT_PATH, RunCommit, RunRepositoryRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.ports.workspace import Workspace

ANALYSIS_DIRECTORY = "analysis"
ROOT_SLUG = "root"
NO_HEAD = "commit missing: no pushed head"
COMMIT_MISSING = "commit missing: {sha}\n{error}"
NO_MERGE_BASE = "no merge base: {head} and origin/{base}"
BASE_REFSPEC = "+refs/heads/{branch}:refs/remotes/origin/{branch}"


@dataclass(frozen=True)
class AttemptRange:
    path: str
    start: str
    end: str


@dataclass(frozen=True)
class RepositoryInputs:
    analysis: Analysis
    scratch: Path | None
    declaration: Declaration
    commits_not_made_by_run: tuple[str, ...]
    hub: bool


def slug(path: str) -> str:
    return ROOT_SLUG if path == ROOT_PATH else path.replace("/", "-")


def attempt_ranges(
    pairs: Iterable[tuple[Attempt, StepRun]], known_paths: Iterable[str]
) -> tuple[AttemptRange, ...]:
    """Each attempt's `start_sha..end_sha` per repository; an open range is skipped."""
    known = list(known_paths)
    found: list[AttemptRange | None] = []
    for attempt, row in pairs:
        path = repository_of(row, known)
        found.append(_range(path, attempt.start_sha, attempt.end_sha))
        if path != ROOT_PATH:
            found.append(_range(ROOT_PATH, attempt.root_start_sha, attempt.root_end_sha))
    return tuple(r for r in found if r is not None)


def _range(path: str, start: str | None, end: str | None) -> AttemptRange | None:
    return AttemptRange(path, start, end) if start is not None and end is not None else None


def _failed(analysis: Analysis, output: str, **over: str | None) -> Analysis:
    return analysis.model_copy(update={"status": "failed", "output": output, **over})


def _made_by_run(
    git: Git,
    scratch: Path,
    path: str,
    commits: Sequence[RunCommit],
    ranges: Sequence[AttemptRange],
) -> set[str]:
    made = {c.sha for c in commits if c.path == path}
    for attempt_range in ranges:
        if attempt_range.path == path:
            made.update(git.commits_between(scratch, attempt_range.start, attempt_range.end))
    return made


def _empty(analysis: Analysis, hub: bool) -> RepositoryInputs:
    return RepositoryInputs(analysis, None, DEFAULT_DECLARATION, (), hub)


def prepare_repository(  # noqa: PLR0913 — one record and the facts its analysis reads
    *,
    analysis_id: UUID,
    run_id: UUID,
    calculation_id: UUID,
    record: RunRepositoryRecord,
    hub: bool,
    commits: Sequence[RunCommit],
    ranges: Sequence[AttemptRange],
    git: Git,
    work_dir: Path,
    clock: Clock,
) -> RepositoryInputs:
    scratch = work_dir / ANALYSIS_DIRECTORY / str(analysis_id) / slug(record.path)
    head = record.head_pushed
    analysis = Analysis(
        id=analysis_id,
        run_id=run_id,
        calculation_id=calculation_id,
        repository_path=record.path,
        status="failed",
        created_at=clock.now(),
    )
    if head is None:
        return _empty(_failed(analysis, NO_HEAD), hub)
    try:
        git.fetch(record.remote_url, (BASE_REFSPEC.format(branch=record.base_branch),), scratch)
    except GitError as error:
        return _empty(_failed(analysis, error.output), hub)
    try:
        git.fetch(record.remote_url, (head,), scratch)
    except GitError as error:
        return _empty(_failed(analysis, COMMIT_MISSING.format(sha=head, error=error.output)), hub)
    try:
        return _read(
            git=git,
            scratch=scratch,
            record=record,
            head=head,
            analysis=analysis,
            hub=hub,
            commits=commits,
            ranges=ranges,
        )
    except GitError as error:  # a timeout: the adapter answers every other failure as absent
        return _empty(_failed(analysis, error.output), hub)


def _read(  # noqa: PLR0913 — the fetched clone and the facts its analysis reads
    *,
    git: Git,
    scratch: Path,
    record: RunRepositoryRecord,
    head: str,
    analysis: Analysis,
    hub: bool,
    commits: Sequence[RunCommit],
    ranges: Sequence[AttemptRange],
) -> RepositoryInputs:
    base = git.merge_base(scratch, head, f"origin/{record.base_branch}")
    if base is None:
        output = NO_MERGE_BASE.format(head=head, base=record.base_branch)
        return _empty(_failed(analysis, output), hub)
    parsed = parse_declaration(git.read_file(scratch, base, DECLARATION_FILE))
    status: AnalysisStatus = "partial" if parsed.problems else "ok"
    ready = analysis.model_copy(
        update={
            "base": base,
            "head": head,
            "status": status,
            "output": "\n".join(parsed.problems),
            "declaration_hash": parsed.hash,
        }
    )
    made = _made_by_run(git, scratch, record.path, commits, ranges)
    not_made = tuple(sha for sha in git.commits_between(scratch, base, head) if sha not in made)
    return RepositoryInputs(ready, scratch, parsed.declaration, not_made, hub)


@contextmanager
def prepare_analysis(  # noqa: PLR0913 — the Run's records and the ports the preparation needs
    *,
    run_id: UUID,
    calculation_id: UUID,
    records: Sequence[RunRepositoryRecord],
    commits: Sequence[RunCommit],
    ranges: Sequence[AttemptRange],
    git: Git,
    scratch_root: Workspace,
    work_dir: Path,
    new_id: Callable[[], UUID],
    clock: Clock,
) -> Iterator[list[RepositoryInputs]]:
    """Yield one `RepositoryInputs` per record; the scratch folders go whatever happens."""
    allocated: list[UUID] = []
    try:
        has_members = any(record.path != ROOT_PATH for record in records)
        prepared: list[RepositoryInputs] = []
        for record in records:
            analysis_id = new_id()
            allocated.append(analysis_id)
            prepared.append(
                prepare_repository(
                    analysis_id=analysis_id,
                    run_id=run_id,
                    calculation_id=calculation_id,
                    record=record,
                    hub=record.path == ROOT_PATH and has_members,
                    commits=commits,
                    ranges=ranges,
                    git=git,
                    work_dir=work_dir,
                    clock=clock,
                )
            )
        yield prepared
    finally:
        for analysis_id in allocated:
            scratch_root.remove(str(analysis_id))
