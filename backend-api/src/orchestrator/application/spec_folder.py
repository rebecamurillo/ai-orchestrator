"""The spec-folder rules: the one place a list file or a `SPEC.md` is judged (AD-35).

The launch plan reads a list file through the `Git` port and hands what it read here; the
check route hands the files an agent sent. Both get the same findings because there is one
function that makes them. Pure: no I/O, only text in, `PlanError`s out. Story-file texts are
never read; only their paths count.

The prefix-free rule is the one that looks arbitrary and is not: a Story's file is found by
`{id}-*.md`, so ids `4-1` and `4-1-a` would make `4-1`'s glob match `4-1-a`'s file and
"is this Story done" would have two answers. `4-1` and `4-10` are fine, because the rule
compares on the separator rather than on the text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from orchestrator.application.templates.lines import line_of, load_sequence
from orchestrator.application.templates.plan_model import (
    AMBIGUOUS_STORY_FILE,
    DUPLICATE_ENTRY_ID,
    ENTRY_MISSING_FIELDS,
    ID_NOT_PREFIX_FREE,
    LIST_FILE_NOT_A_LIST,
    LIST_FILE_NOT_FOUND,
    PlanError,
)

#: What separates the segments of a repository-relative path. Not the row path's separator.
PATH_SEPARATOR = "/"

#: The two lists the method knows, by the basename that identifies each.
STORIES_KIND = "stories"
EPICS_KIND = "epics"
LIST_BASENAMES: dict[str, str] = {
    "stories.yaml": STORIES_KIND,
    "epics.yaml": EPICS_KIND,
}

#: What an entry of each list has to state. A loop over any other file requires nothing —
#: the method has no opinion about a file it did not define.
REQUIRED_FIELDS: dict[str | None, tuple[str, ...]] = {
    STORIES_KIND: ("id", "title", "description"),
    EPICS_KIND: ("id", "title", "branch", "spec_folder"),
}

#: The key every entry is identified by, in both lists.
ID_KEY = "id"
SPEC_FOLDER_KEY = "spec_folder"

#: The folder a Story's file is written to, beside the list file that named the Story.
STORIES_DIRECTORY = "stories"
#: What a Story's file is called, and what makes two of them ambiguous.
STORY_SUFFIX = ".md"
STORY_ID_SEPARATOR = "-"

SPEC_FILENAME = "SPEC.md"
SPEC_MD_MISSING = "SPEC.md missing"

#: The reasons this module raises for a list file; pre-flight routes on them.
RULE_REASONS: frozenset[str] = frozenset(
    {
        LIST_FILE_NOT_FOUND,
        LIST_FILE_NOT_A_LIST,
        ENTRY_MISSING_FIELDS,
        DUPLICATE_ENTRY_ID,
        ID_NOT_PREFIX_FREE,
        AMBIGUOUS_STORY_FILE,
    }
)

#: One entry of a list file: whatever mapping the Operator wrote.
Entry = Mapping[str, Any]


def list_kind(path: str) -> str | None:
    """Which list this is, by basename; `None` for a loop over anything else."""
    return LIST_BASENAMES.get(path.rpartition(PATH_SEPARATOR)[2])


def stories_directory(path: str) -> str:
    """`{spec_folder}/stories` — the folder beside the list file that named the Stories."""
    parent = parent_of(path)
    return f"{parent}{PATH_SEPARATOR}{STORIES_DIRECTORY}" if parent else STORIES_DIRECTORY


def parent_of(path: str) -> str:
    """The folder a path sits in; `""` for a path at the root."""
    return path.rpartition(PATH_SEPARATOR)[0]


def join(folder: str, name: str) -> str:
    """`folder/name`, or just `name` for the root folder."""
    return f"{folder}{PATH_SEPARATOR}{name}" if folder else name


def read_entries(text: str) -> tuple[Entry, ...] | None:
    """The file's entries, or `None` when it is not a sequence of mappings."""
    document = load_sequence(text)
    if document is None:
        return None
    entries: list[Entry] = []
    for entry in document:
        if not isinstance(entry, Mapping):
            return None
        entries.append(entry)
    return tuple(entries)


def story_files(paths: Sequence[str], directory: str, story_id: str) -> list[str]:
    """The files of `paths` that are this Story's: `{directory}/{id}-*.md`, directly in it."""
    opening = f"{directory}{PATH_SEPARATOR}{story_id}{STORY_ID_SEPARATOR}"
    return [
        path
        for path in paths
        if path.startswith(opening)
        and path.endswith(STORY_SUFFIX)
        # a listing is recursive, so `stories/4-1-notes/scratch.md` starts the same way
        # and is not this Story's file
        and PATH_SEPARATOR not in path[len(opening) :]
    ]


def story_file_findings(paths: Sequence[str], directory: str, story_id: str) -> list[PlanError]:
    """One finding when two files match one Story, else none: "is it done" has one answer."""
    matches = story_files(paths, directory, story_id)
    if len(matches) > 1:
        return [PlanError(reason=AMBIGUOUS_STORY_FILE, item=story_id, file=matches[0])]
    return []


def check_spec_folder(
    files: Mapping[str, str], *, expected: Sequence[str] | None = None
) -> list[PlanError]:
    """Every list-file finding of a spec folder, in the order the plan reads the files.

    `files` maps paths relative to the initiative folder to their text. The list files are
    every key whose basename is a list's, plus every path in `expected`. With `expected=None`
    each valid `epics.yaml` entry's `stories.yaml` is expected as well; with `expected` given
    nothing is inferred. Story-file texts are never read; only their paths count.
    """
    found: list[PlanError] = []
    for path in _list_paths(files, expected):
        found += _check_list(files, path)
    return found


def check_spec_md(
    files: Mapping[str, str], folders: Sequence[str] | None = None
) -> list[PlanError]:
    """One finding per spec folder without a `SPEC.md`. `folders` defaults to the derived ones."""
    found: list[PlanError] = []
    for folder in _spec_folders(files) if folders is None else folders:
        path = join(folder, SPEC_FILENAME)
        if path not in files:
            found.append(PlanError(reason=SPEC_MD_MISSING, item=folder, file=path))
    return found


def _epic_folders(files: Mapping[str, str]) -> list[str]:
    """Each valid `epics.yaml` entry's spec folder, as a path from the initiative folder."""
    folders: list[str] = []
    for path in sorted(key for key in files if list_kind(key) == EPICS_KIND):
        for entry in read_entries(files[path]) or ():
            folder = entry.get(SPEC_FOLDER_KEY)
            if isinstance(folder, str) and folder:
                folders.append(join(parent_of(path), folder))
    return folders


def _list_paths(files: Mapping[str, str], expected: Sequence[str] | None) -> list[str]:
    if expected is not None:
        return list(dict.fromkeys(expected))
    epics = sorted(key for key in files if list_kind(key) == EPICS_KIND)
    inferred = [join(folder, "stories.yaml") for folder in _epic_folders(files)]
    others = sorted(key for key in files if list_kind(key) is not None)
    return list(dict.fromkeys(epics + inferred + others))


def _spec_folders(files: Mapping[str, str]) -> list[str]:
    folders = _epic_folders(files)
    others = sorted(
        {parent_of(key) for key in files if list_kind(key) == STORIES_KIND} - set(folders)
    )
    return folders + others


def _check_list(files: Mapping[str, str], path: str) -> list[PlanError]:
    text = files.get(path)
    if text is None:
        return [PlanError(reason=LIST_FILE_NOT_FOUND, item=path, file=path)]
    entries = read_entries(text)
    if entries is None:
        return [PlanError(reason=LIST_FILE_NOT_A_LIST, item=path, file=path)]
    kind = list_kind(path)
    required = REQUIRED_FIELDS.get(kind)
    if required is None:
        return []
    found = _missing_fields(entries, required, path)
    ids = [str(entry[ID_KEY]) for entry in entries if entry.get(ID_KEY)]
    found += _id_findings(ids, path)
    if kind == STORIES_KIND:
        directory = stories_directory(path)
        under = [key for key in files if key.startswith(f"{directory}{PATH_SEPARATOR}")]
        for story_id in ids:
            found += story_file_findings(under, directory, story_id)
    return found


def _missing_fields(
    entries: Sequence[Entry], required: tuple[str, ...], path: str
) -> list[PlanError]:
    return [
        PlanError(
            reason=ENTRY_MISSING_FIELDS,
            item=str(entry[ID_KEY]) if entry.get(ID_KEY) else f"entry {index}",
            line=line_of(entry, 0) or None,
            file=path,
        )
        for index, entry in enumerate(entries)
        if not all(entry.get(name) for name in required)
    ]


def _id_findings(ids: Sequence[str], path: str) -> list[PlanError]:
    """Ids that identify one entry each, and that no `{id}-*` glob can confuse."""
    found: list[PlanError] = []
    seen: set[str] = set()
    for entry_id in ids:
        if entry_id in seen:
            found.append(PlanError(reason=DUPLICATE_ENTRY_ID, item=entry_id, file=path))
        seen.add(entry_id)
    # Linear in the ids' length, not quadratic in their count: the route takes 1 MiB lists. One
    # finding per `longer`, in the order a nested shorter-then-longer scan would meet them.
    longers: dict[str, list[str]] = {}
    for longer in dict.fromkeys(ids):
        for index, char in enumerate(longer):
            if char == STORY_ID_SEPARATOR and longer[:index] in seen:
                longers.setdefault(longer[:index], []).append(longer)
    named: set[str] = set()
    for shorter in dict.fromkeys(ids):
        for longer in longers.get(shorter, ()):
            if longer not in named:
                named.add(longer)
                found.append(PlanError(reason=ID_NOT_PREFIX_FREE, item=longer, file=path))
    return found
