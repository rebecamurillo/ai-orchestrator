"""The list files a `for_each` expands over, and everything that can be wrong with one.

A loop's source is a path in the Operator's own repository, so what it names is **data, not
a Template**: it is loaded by `lines.load_sequence` — the one YAML import site there is
(AD-2, AD-15) — and never by `validate()`. What the file has to contain depends on which
list it is, and that is decided by the resolved source's **basename**, not by the loop's
id: `stories.yaml` is what makes a frame a Story frame, which is also what selects the
required fields, the `story {id}` label form and the already-done rule. A loop over any
other file is still a loop; it simply has none of those rules.

**Where a list file is read.** At the frame's own ref, and — when it is not there and the
frame works on a branch the remote holds — at that branch's head, which then becomes the
ref the frame's story files are read at too, so one frame never mixes two commits. That is
the Initiative case: `epics.yaml` sits on the base branch while an epic's `stories.yaml`
may only exist on the epic's own branch.

**Every refusal names the entry.** An Operator whose `stories.yaml` is wrong needs to know
which line and which id, so each `PlanError` carries the Template, the line of the loop that
read the file, and the entry at fault — the fields `api/errors.py::ProblemError` renders.

The prefix-free rule is the one that looks arbitrary and is not: a Story's file is found by
`{id}-*.md`, so ids `4-1` and `4-1-a` would make `4-1`'s glob match `4-1-a`'s file and
"is this Story done" would have two answers. `4-1` and `4-10` are fine, because the rule
compares on the separator rather than on the text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from orchestrator.application.templates.lines import load_sequence, load_with_lines
from orchestrator.application.templates.plan_model import (
    AMBIGUOUS_STORY_FILE,
    DUPLICATE_ENTRY_ID,
    ENTRY_MISSING_FIELDS,
    ID_NOT_PREFIX_FREE,
    LIST_FILE_NOT_A_LIST,
    LIST_FILE_NOT_FOUND,
    ONLY_NOT_IN_LIST,
    PlanError,
)
from orchestrator.application.templates.reader import PlanReader

if TYPE_CHECKING:  # a frame is the walker's; naming it here would be a second one
    from orchestrator.application.templates.rows import Frame

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

#: The folder a Story's file is written to, beside the list file that named the Story.
STORIES_DIRECTORY = "stories"
#: What a Story's file is called, and what makes two of them ambiguous.
STORY_SUFFIX = ".md"
STORY_ID_SEPARATOR = "-"

#: The fence a story file's YAML frontmatter opens and closes with.
FRONTMATTER_FENCE = "---"
#: The frontmatter key FR-10 reads, and the one value that means the Story is finished.
STATUS_KEY = "status"
DONE_STATUS = "done"

#: One entry of a list file: whatever mapping the Operator wrote.
Entry = Mapping[str, Any]


def list_kind(path: str) -> str | None:
    """Which list this is, by basename; `None` for a loop over anything else."""
    return LIST_BASENAMES.get(path.rpartition(PATH_SEPARATOR)[2])


def stories_directory(path: str) -> str:
    """`{spec_folder}/stories` — the folder beside the list file that named the Stories."""
    parent = path.rpartition(PATH_SEPARATOR)[0]
    return f"{parent}{PATH_SEPARATOR}{STORIES_DIRECTORY}" if parent else STORIES_DIRECTORY


def read_list(
    reader: PlanReader, frame: Frame, path: str, *, line: int
) -> tuple[tuple[Entry, ...], str]:
    """One list file's entries, and the commit they were read at.

    `line` is the loop's own line, so a refusal points at the `for_each` that named the
    file rather than at the file the Operator would then have to go and count lines in.
    """
    text = reader.read(frame.ref, path)
    ref_used = frame.ref
    if text is None and frame.branch is not None:
        head = reader.sha(frame.branch)
        if head is not None:
            text, ref_used = reader.read(head, path), head
    if text is None:
        raise _refuse(frame, LIST_FILE_NOT_FOUND, path, line)
    entries = _entries(text)
    if entries is None:
        raise _refuse(frame, LIST_FILE_NOT_A_LIST, path, line)
    reader.record(path, ref_used, branch=_recorded_branch(reader, frame))
    return entries, ref_used


def _recorded_branch(reader: PlanReader, frame: Frame) -> str | None:
    """The branch a fresh copy of this frame's list file would come from, or `None`.

    `PlanReader.record`'s own contract: `None` means the base branch, "which is exactly what
    a Template naming no branch, or naming one the remote does not hold yet, resolves to".
    The frame carries the branch the Template *declared*, which `plan_ref` resolves the same
    way — so a branch the remote does not hold is one this Run is about to create, and the
    commit its list file was actually read at came off the base branch.

    Recording the declared name regardless is what parked `plan.check` on `plan_stale` at
    row 1 of the first Run of every new branch: `ls_remote(url, branch)` answers `None` for
    a branch that is not there, so the "current" content is nothing and never matches.

    `reader.sha` is memoised, and `plan_ref` has already asked this exact question, so the
    answer costs no second `Git` call however many list files the walk reads (FR-10).
    """
    if frame.branch is None:
        return None
    return frame.branch if reader.sha(frame.branch) is not None else None


def check_entries(items: Sequence[Entry], kind: str | None, frame: Frame, *, line: int) -> None:
    """Refuse a list whose entries a plan could not be built from. Silent when they are fine."""
    required = REQUIRED_FIELDS.get(kind)
    if required is None:
        return
    ids: list[str] = []
    for index, entry in enumerate(items):
        _require(entry, required, index, frame, line)
        ids.append(str(entry[ID_KEY]))
    _check_ids(ids, frame, line)


def filter_only(
    items: Sequence[Entry], only: str | None, frame: Frame, *, line: int
) -> Sequence[Entry]:
    """The entries a loop's `only:` keeps — all of them when it declares none (story 4-8).

    A resolved `only` id that matches no entry is a refusal rather than an empty loop: the
    Operator named a Story the list does not hold, and zero rows would read as "already
    done". Lives here beside `read_list`/`check_entries` rather than in `rows.py` on line
    count alone (the 400-line module limit).
    """
    if only is None:
        return items
    filtered = [entry for entry in items if entry.get(ID_KEY) == only]
    if not filtered:
        raise _refuse(frame, ONLY_NOT_IN_LIST, only, line)
    return filtered


def story_done(reader: PlanReader, frame: Frame, directory: str, story_id: str, line: int) -> bool:
    """Whether this Story's file already states `status: done` at the frame's ref (FR-10).

    Read at `frame.ref` — the commit the frame's own list file was read at — so a Story's
    state and the list that named it always come from the same tree. Two files matching
    `{id}-*.md` is a refusal rather than a guess: the plan would otherwise call a Story
    finished on the strength of whichever file happened to sort first.
    """
    opening = f"{directory}{PATH_SEPARATOR}{story_id}{STORY_ID_SEPARATOR}"
    matches = [
        path
        for path in reader.listing(frame.ref, directory)
        if path.startswith(opening)
        and path.endswith(STORY_SUFFIX)
        # the listing is recursive, so `stories/4-1-notes/scratch.md` starts the same way
        # and is not this Story's file
        and PATH_SEPARATOR not in path[len(opening) :]
    ]
    if len(matches) > 1:
        raise _refuse(frame, AMBIGUOUS_STORY_FILE, story_id, line)
    if not matches:
        return False
    text = reader.read(frame.ref, matches[0])
    return text is not None and _states_done(text)


# --- reading one file -------------------------------------------------------------------------


def _entries(text: str) -> tuple[Entry, ...] | None:
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


def _states_done(text: str) -> bool:
    """`status: done` in the file's YAML frontmatter, and nothing else."""
    body = _frontmatter(text)
    if body is None:
        return False
    loaded = load_with_lines(body)
    if loaded.root is None:
        return False
    return loaded.root.get(STATUS_KEY) == DONE_STATUS


def _frontmatter(text: str) -> str | None:
    """The text between the opening `---` and the next one, or `None` when there is none."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_FENCE:
            return "\n".join(lines[1:index])
    return None


# --- checking the entries ---------------------------------------------------------------------


def _require(entry: Entry, required: tuple[str, ...], index: int, frame: Frame, line: int) -> None:
    """Every field the list needs, present and saying something."""
    if all(entry.get(name) for name in required):
        return
    raise _refuse(frame, ENTRY_MISSING_FIELDS, _named(entry, index), line)


def _named(entry: Entry, index: int) -> str:
    """The entry as the Operator would find it: by its id, or by where it sits."""
    return str(entry[ID_KEY]) if entry.get(ID_KEY) else f"entry {index}"


def _check_ids(ids: list[str], frame: Frame, line: int) -> None:
    """Ids that identify one entry each, and that no `{id}-*` glob can confuse."""
    seen: set[str] = set()
    for entry_id in ids:
        if entry_id in seen:
            raise _refuse(frame, DUPLICATE_ENTRY_ID, entry_id, line)
        seen.add(entry_id)
    for shorter in ids:
        for longer in ids:
            if longer.startswith(f"{shorter}{STORY_ID_SEPARATOR}"):
                raise _refuse(frame, ID_NOT_PREFIX_FREE, longer, line)


def _refuse(frame: Frame, reason: str, item: str | None, line: int) -> PlanError:
    """A refusal that names the Template, the line and the entry (`ProblemError`)."""
    return PlanError(
        reason=reason,
        template=frame.template.name,
        version=frame.template.version,
        line=line,
        item=item,
    )
