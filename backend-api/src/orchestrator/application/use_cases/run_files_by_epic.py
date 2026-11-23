"""A Run's spec files and changed paths, grouped by epic and Story (SPEC CAP-7, AD-40).

Read-only and pure: the list files come through the Run's `Workspace`, the changed paths
through `Git`, the one path's diff through `GitHistory`. Which attempts belong to a Story is
the frame's rows (`rows_in_frame`), not a name match.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from orchestrator.application.rules.frames import rows_in_frame
from orchestrator.application.spec_folder import (
    ID_KEY,
    SPEC_FOLDER_KEY,
    Entry,
    join,
    read_entries,
    stories_directory,
    story_files,
)
from orchestrator.application.steps import AGENT_KIND
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.ports.git_history import GitHistory
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.workspace import Workspace, WorkspaceError

EPIC_FILES = ("SPEC.md", "stories.yaml", "spec-gate-result.md", "RETROSPECTIVE.md")
NOT_FOUND = "No such Run, epic, story or changed path."
_EARLY = datetime.min.replace(tzinfo=UTC)
_LATE = datetime.max.replace(tzinfo=UTC)


@dataclass(frozen=True)
class FilesByEpicPorts:
    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    git: Git
    history: GitHistory
    workspace: Callable[[str | None], Workspace]


@dataclass(frozen=True)
class StoryFiles:
    id: str
    title: str
    story_file: str | None
    started: bool
    changed: tuple[str, ...]


@dataclass(frozen=True)
class EpicFiles:
    index: int
    title: str
    folder: str
    files: tuple[str, ...]
    stories: tuple[StoryFiles, ...]


@dataclass(frozen=True)
class StoryDiff:
    path: str
    from_sha: str
    to_sha: str
    diff: str


@dataclass(frozen=True)
class _Read:
    ports: FilesByEpicPorts
    run: Run
    rows: list[StepRun]
    workspace: Workspace


@dataclass(frozen=True)
class _Span:
    from_sha: str
    to_sha: str
    repo: Path
    workdir: str


@dataclass(frozen=True)
class _Story:
    files: StoryFiles
    span: _Span | None


def _epic_sources(run: Run, workspace: Workspace) -> list[tuple[int, str, str, str]]:
    """`(index, folder, title, frame prefix base)` per epic the Run names."""
    initiative = run.inputs.get("initiative_folder")
    if isinstance(initiative, str) and initiative:
        entries = read_entries(workspace.read(join(initiative, "epics.yaml")) or "")
        sources: list[tuple[int, str, str, str]] = []
        for index, entry in enumerate(entries or ()):
            folder = entry.get(SPEC_FOLDER_KEY)
            if not isinstance(folder, str) or not folder:
                continue
            title = entry.get("title")
            shown = title if isinstance(title, str) and title else join(initiative, folder)
            sources.append((index, join(initiative, folder), shown, f"epics[{index}]."))
        return sources
    spec = run.inputs.get("spec_folder")
    if isinstance(spec, str) and spec:
        return [(0, spec, spec, "")]
    return []


def _story_range(attempts: list[Attempt]) -> tuple[str | None, str | None]:
    started = [a for a in attempts if a.start_sha]
    ended = [a for a in attempts if a.end_sha]
    first = min(started, key=lambda a: (a.started_at or _LATE, a.n), default=None)
    last = max(ended, key=lambda a: (a.ended_at or _EARLY, a.n), default=None)
    return (first.start_sha if first else None, last.end_sha if last else None)


def _repo(run: Run, frame_rows: list[StepRun]) -> tuple[Path, str]:
    agent = next((r for r in frame_rows if r.kind == AGENT_KIND), None)
    workdir = str(agent.with_resolved.get("workdir") or "") if agent else ""
    base = Path(str(run.worktree_path))
    return (base / workdir if workdir else base), workdir


def _changed(git: Git, span: _Span) -> tuple[str, ...]:
    try:
        changes = git.diff_changes(span.repo, span.from_sha, span.to_sha)
    except GitError:
        return ()
    prefix = f"{span.workdir}/" if span.workdir else ""
    return tuple(f"{prefix}{change.path}" for change in changes)


def _story(read: _Read, prefix: str, entry: Entry, stories_dir: str) -> _Story | None:
    ports, workspace = read.ports, read.workspace
    if not entry.get(ID_KEY):
        return None
    story_id = str(entry[ID_KEY])
    found = story_files(workspace.glob(f"{stories_dir}/{story_id}-*.md"), stories_dir, story_id)
    frame_rows = rows_in_frame(read.rows, prefix)
    attempts = [a for row in frame_rows for a in ports.attempts.list_for_row(row.id)]
    from_sha, to_sha = _story_range(attempts)
    span = None
    if from_sha and to_sha:
        repo, workdir = _repo(read.run, frame_rows)
        span = _Span(from_sha, to_sha, repo, workdir)
    files = StoryFiles(
        id=story_id,
        title=str(entry.get("title") or story_id),
        story_file=min(found, default=None),
        started=bool(attempts),
        changed=_changed(ports.git, span) if span else (),
    )
    return _Story(files, span)


def _epic(
    read: _Read, source: tuple[int, str, str, str]
) -> tuple[EpicFiles, dict[str, _Span | None]]:
    workspace = read.workspace
    index, folder, title, base = source
    files = tuple(join(folder, n) for n in EPIC_FILES if workspace.exists(join(folder, n)))
    entries = read_entries(workspace.read(join(folder, "stories.yaml")) or "") or ()
    stories_dir = stories_directory(join(folder, "stories.yaml"))
    built = [
        _story(read, f"{base}stories[{j}]", entry, stories_dir) for j, entry in enumerate(entries)
    ]
    kept = [story for story in built if story is not None]
    epic = EpicFiles(index, title, folder, files, tuple(s.files for s in kept))
    # first entry wins on a repeated id, as `story_diff` finds the Story by `next(...)`
    return epic, {s.files.id: s.span for s in reversed(kept)}


def _all(ports: FilesByEpicPorts, run_id: UUID) -> list[tuple[EpicFiles, dict[str, _Span | None]]]:
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(NOT_FOUND)
    if run.worktree_path is None or run.worktrees_removed:
        return []
    workspace = ports.workspace(run.worktree_path)
    try:
        sources = _epic_sources(run, workspace)
    except WorkspaceError:
        return []
    read = _Read(ports, run, ports.steps.list_for_run(run_id), workspace)
    epics: list[tuple[EpicFiles, dict[str, _Span | None]]] = []
    for source in sources:
        try:
            epics.append(_epic(read, source))
        except WorkspaceError:
            continue
    return epics


def files_by_epic(ports: FilesByEpicPorts, run_id: UUID) -> tuple[EpicFiles, ...]:
    """The Run's epics in list order; `()` when it has no worktree or names no epic."""
    return tuple(epic for epic, _ in _all(ports, run_id))


def story_diff(
    ports: FilesByEpicPorts, run_id: UUID, epic: int, story_id: str, path: str
) -> StoryDiff:
    """One changed path's unified diff over the Story's range; `NotFound` for anything else."""
    for found, spans in _all(ports, run_id):
        story = next((s for s in found.stories if s.id == story_id), None)
        span = spans.get(story_id)
        if found.index != epic or story is None or span is None or path not in story.changed:
            continue
        prefix = f"{span.workdir}/" if span.workdir else ""
        try:
            text = ports.history.diff_path(
                span.repo, span.from_sha, span.to_sha, path.removeprefix(prefix)
            )
        except GitError as error:
            raise NotFound(NOT_FOUND) from error
        return StoryDiff(path, span.from_sha, span.to_sha, text)
    raise NotFound(NOT_FOUND)
