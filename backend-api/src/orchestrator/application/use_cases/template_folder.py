"""`seed_folder` — the folder pass (SPEC CAP-4, AD-26).

Each `*.yaml` of the operator's folder, from one snapshot, is stored as the next version of its
name when it validates, its stem is its `name:`, it strands no unpinned caller and its text
differs from the name's **latest** version. A file that cannot be read, validate, match its
stem or keep its callers is refused and reported, never raised; refused files are retried
while a round stores something, so a caller may sit before its callee; nothing is deleted.
The repository's own errors, and the `Conflict` of a concurrent save, propagate: only text
is judged leniently (`judge_text`).
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.application.templates.calls import check_callers
from orchestrator.application.templates.lines import key_line, load_with_lines
from orchestrator.application.templates.model import ValidationError
from orchestrator.application.templates.table import problem
from orchestrator.application.use_cases.template_judge import judge_text
from orchestrator.application.use_cases.templates import (
    FIRST_VERSION,
    TemplatePorts,
    calls_of,
    following_callers,
    text_hash,
)
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.template_folders import FolderFile, OperatorFolder

#: `template_version.source` of a version the folder pass stored.
SOURCE_FOLDER = "folder"

#: Reasons a folder file is refused that the validator does not give.
FILE_UNREADABLE = "file unreadable"
NAME_DIFFERS = "file name differs from template name"


@dataclass(frozen=True)
class FolderEntry:
    """A folder file that stored a version (`stored`) or equals its name's latest one."""

    name: str
    version: int
    file: str
    overrides_shipped: bool


@dataclass(frozen=True)
class FolderRefusal:
    """A folder file the pass could not store, and why, in the last round's errors."""

    file: str
    errors: tuple[ValidationError, ...]


@dataclass(frozen=True)
class NotInFolder:
    """A name the folder once stored a version of and no longer has a file for."""

    name: str
    overrides_shipped: bool


@dataclass(frozen=True)
class FolderOutcome:
    """What one folder pass did. Empty when the folder is off or missing."""

    stored: tuple[FolderEntry, ...] = ()
    unchanged: tuple[FolderEntry, ...] = ()
    refused: tuple[FolderRefusal, ...] = ()
    not_in_folder: tuple[NotInFolder, ...] = ()


@dataclass
class _FolderPass:
    """What one `seed_folder` call has settled so far."""

    shipped: frozenset[str]
    stored: list[FolderEntry]
    unchanged: list[FolderEntry]
    refusals: dict[str, tuple[ValidationError, ...]]


def seed_folder(ports: TemplatePorts, folder: OperatorFolder) -> FolderOutcome:
    """Store every changed, valid file of `folder` as the next version of its name.

    Does not commit: the caller owns the unit of work. Refused files never raise; a port
    error, and the `Conflict` of a concurrent save, propagate.
    """
    if ports.folders is None or folder.state != "ready":
        return FolderOutcome()
    state = _FolderPass(ports.folders.shipped_names(), [], [], {})
    pending = sorted(folder.files, key=lambda item: item.file)
    while pending:
        state.refusals = {}
        before = len(state.stored)
        pending = _folder_round(ports, pending, state)
        if len(state.stored) == before:
            break
    refused = tuple(FolderRefusal(f.file, state.refusals[f.file]) for f in pending)
    gone = ports.templates.names_with_source(SOURCE_FOLDER) - {f.stem for f in folder.files}
    return FolderOutcome(
        stored=tuple(state.stored),
        unchanged=tuple(state.unchanged),
        refused=refused,
        not_in_folder=tuple(NotInFolder(n, n in state.shipped) for n in sorted(gone)),
    )


def _folder_round(
    ports: TemplatePorts, pending: list[FolderFile], state: _FolderPass
) -> list[FolderFile]:
    """One pass over the files not yet settled; returns the ones still refused."""
    still: list[FolderFile] = []
    for item in pending:
        errors = _folder_file(ports, item, state)
        if errors:
            state.refusals[item.file] = errors
            still.append(item)
    return still


def _folder_file(
    ports: TemplatePorts, item: FolderFile, state: _FolderPass
) -> tuple[ValidationError, ...]:
    """Settle one file: store it, find it unchanged, or return why it is refused."""
    stem = item.stem
    if item.read_error is not None:
        return (_about(problem(1, FILE_UNREADABLE), stem),)
    result = judge_text(item.text, ports.templates)
    if result.errors:
        return result.errors
    parsed = result.template
    assert parsed is not None  # judge_text never leaves both empty
    if parsed.name != stem:
        return (_about(problem(_name_line(item.text), NAME_DIFFERS), stem),)
    digest = text_hash(item.text)
    existing = ports.templates.list_versions(stem)
    latest = ports.templates.get(stem, max(existing)) if existing else None
    if latest is not None and latest.hash == digest:
        state.unchanged.append(FolderEntry(stem, latest.version, item.file, stem in state.shipped))
        return ()
    stranded = check_callers(stem, item.text, following_callers(ports.templates, stem))
    if stranded:
        return tuple(stranded)
    next_version = max(existing) + 1 if existing else FIRST_VERSION
    ports.templates.add_version(
        TemplateVersion(
            id=new_id(),
            name=stem,
            version=next_version,
            yaml=item.text,
            hash=digest,
            calls=calls_of(parsed),
            created_at=ports.clock.now(),
            source=SOURCE_FOLDER,
        ),
        description=parsed.description,
    )
    state.stored.append(FolderEntry(stem, next_version, item.file, stem in state.shipped))
    return ()


def _about(record: ValidationError, stem: str) -> ValidationError:
    return record.model_copy(update={"template": stem})


def _name_line(text: str) -> int:
    root = load_with_lines(text).root
    assert root is not None  # the text validated, so it loaded
    return key_line(root, "name", root.line)
