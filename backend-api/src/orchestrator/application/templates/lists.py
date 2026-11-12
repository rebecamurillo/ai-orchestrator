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

The rules themselves — required fields, ids, ambiguous story files — live in
`application/spec_folder.py` (AD-35); this module reads the file through the plan's port and
hands the text there, so the plan and the check route cannot disagree.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from orchestrator.application.spec_folder import (
    EPICS_KIND,
    ID_KEY,
    REQUIRED_FIELDS,
    STORIES_KIND,
    Entry,
    check_spec_folder,
    list_kind,
    read_entries,
    stories_directory,
    story_file_findings,
    story_files,
)
from orchestrator.application.templates.lines import load_with_lines
from orchestrator.application.templates.plan_model import ONLY_NOT_IN_LIST, PlanError
from orchestrator.application.templates.reader import PlanReader

if TYPE_CHECKING:  # a frame is the walker's; naming it here would be a second one
    from orchestrator.application.templates.rows import Frame

#: The fields a Template may be written against beyond the required ones. The entry is handed
#: whole to the Template and read there (`{{story.invoke_dev_with}}`, `{{epic.workdir}}`), so no
#: Python reads these by name; this is where the vocabulary is held.
DONE_CHECKPOINT_FIELD = "done_checkpoint"
SPEC_CHECKPOINT_FIELD = "spec_checkpoint"
INVOKE_DEV_WITH_FIELD = "invoke_dev_with"
WORKDIR_FIELD = "workdir"
INSTALL_FIELD = "install"
TEST_FIELD = "test"
QUALITY_GATE_FIELD = "quality_gate"
OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {
    STORIES_KIND: (DONE_CHECKPOINT_FIELD, SPEC_CHECKPOINT_FIELD, INVOKE_DEV_WITH_FIELD),
    EPICS_KIND: (
        DONE_CHECKPOINT_FIELD,
        WORKDIR_FIELD,
        INSTALL_FIELD,
        TEST_FIELD,
        QUALITY_GATE_FIELD,
    ),
}

#: The fence a story file's YAML frontmatter opens and closes with.
FRONTMATTER_FENCE = "---"
#: The frontmatter key FR-10 reads, and the one value that means the Story is finished.
STATUS_KEY = "status"
DONE_STATUS = "done"

#: Names other modules import from here; the rules and vocabulary are `spec_folder`'s (AD-35).
__all__ = [
    "EPICS_KIND",
    "ID_KEY",
    "REQUIRED_FIELDS",
    "STORIES_KIND",
    "list_kind",
    "stories_directory",
]


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
    found = check_spec_folder({} if text is None else {path: text}, expected=(path,))
    if found:
        raise _refuse(frame, found[0], line)
    assert text is not None  # a missing file is a finding
    entries = read_entries(text)
    assert entries is not None  # so is a file that is not a list
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


def filter_only(
    items: Sequence[Entry], only: str | None, frame: Frame, *, line: int
) -> Sequence[Entry]:
    """The entries a loop's `only:` keeps — all of them when it declares none (story 4-8).

    A resolved `only` id that matches no entry is a refusal rather than an empty loop: the
    Operator named a Story the list does not hold, and zero rows would read as "already
    done". Lives here beside `read_list` rather than in `rows.py` on line
    count alone (the 400-line module limit).
    """
    if only is None:
        return items
    filtered = [entry for entry in items if entry.get(ID_KEY) == only]
    if not filtered:
        raise _refuse(frame, PlanError(reason=ONLY_NOT_IN_LIST, item=only), line)
    return filtered


def story_done(reader: PlanReader, frame: Frame, directory: str, story_id: str, line: int) -> bool:
    """Whether this Story's file already states `status: done` at the frame's ref (FR-10).

    Read at `frame.ref` — the commit the frame's own list file was read at — so a Story's
    state and the list that named it always come from the same tree. Two files matching
    `{id}-*.md` is a refusal rather than a guess: the plan would otherwise call a Story
    finished on the strength of whichever file happened to sort first.
    """
    listing = reader.listing(frame.ref, directory)
    found = story_file_findings(listing, directory, story_id)
    if found:
        raise _refuse(frame, found[0], line)
    matches = story_files(listing, directory, story_id)
    if not matches:
        return False
    text = reader.read(frame.ref, matches[0])
    return text is not None and _states_done(text)


# --- reading one file -------------------------------------------------------------------------


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


def _refuse(frame: Frame, finding: PlanError, line: int) -> PlanError:
    """A refusal that names the Template, the line and the entry (`ProblemError`)."""
    return PlanError(
        reason=finding.reason,
        template=frame.template.name,
        version=frame.template.version,
        line=line,
        item=finding.item,
        file=finding.file,
    )


#: What one loop item is called in a label: the Story by its own id, the epic by its place.
STORY_LABEL = "story"
EPIC_LABEL = "epic"


def item_label(kind: str | None, as_name: str, entry: Mapping[str, Any], index: int) -> str:
    """`story {id}` names the Story an Operator knows; the rest count from one."""
    if kind == STORIES_KIND:
        return f"{STORY_LABEL} {entry[ID_KEY]}"
    if kind == EPICS_KIND:
        return f"{EPIC_LABEL} {index + 1}"
    return f"{as_name} {index + 1}"
