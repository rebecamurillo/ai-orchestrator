"""The Story file a coding agent leaves behind: reading it, and handing it back rewritten.

FR-16 routes on one thing — `{spec_folder}/stories/{id}-*.md` — and this module is the only
place that knows what is inside it. `route` (`application/rules/routing.py`) sees a
`StoryFile` or `None`, never markdown, so every way a file can be unreadable is decided
once, here: no frontmatter fence, a fence that never closes, YAML that does not load, a
document that is not a mapping, or a `status` that is missing, empty or not text. All five
are the same answer — `None`, which the rule reports as `no story file: frontmatter
unreadable in {name}`. Nothing here raises: a Run parks on a bad file, it never 500s.

**The fence convention is `application/templates/lists.py`'s, matched rather than imported.**
That module is a *plan-time* reader: it reads Story files at a git ref through `PlanReader`
to answer "is this Story already done", while this one reads the worktree the executor is
standing in through `Workspace`. Two readers of the same convention on two sources; sharing
the private helper would tie a dispatch-time decision to a planning-time port. The YAML
loader *is* shared, because `templates/lines.py` is the one `yaml` import site (AD-2).

**Two writers live here for the same reason the reader does.** A verify redispatch hands the
agent its own file back with the frontmatter at `in-progress` and a `## Verify Failure`
section appended (FR-10). What that file may look like — with frontmatter, without, with a
`status:` line or without — is this module's knowledge, not the executor's; `agent.py`
decides *when* to rewrite and this decides *how*.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from orchestrator.application.templates.lines import load_with_lines

#: The fence a Story file's YAML frontmatter opens and closes with.
FRONTMATTER_FENCE = "---"
#: The one frontmatter key FR-16 routes on.
STATUS_KEY = "status"

#: The section `bmad-build-auto`'s HALT protocol writes its outcome under, and what the
#: Operator is shown verbatim as the Question when a Story blocks (PRD §4.6).
AUTO_RUN_RESULT = "## Auto Run Result"
#: What ends a section: the next heading at the same level. A deeper one (`### `) does not.
HEADING_PREFIX = "## "
#: The line inside that section naming why the agent stopped.
BLOCKING_CONDITION = "Blocking condition:"

#: FR-10's own section, and the status a Story file a `verify` row sent back goes back to:
#: `bmad-build-auto` routes `in-progress` straight to implementation rather than re-planning.
IN_PROGRESS = "in-progress"
VERIFY_FAILURE = "## Verify Failure\n\nCommand: {command}\nExit code: {code}\n\n{tail}"
#: What the exit code reads when the `verify` row recorded none — a stated fact rather than
#: a Python repr of `None`, because the agent reads this file and so does the Operator
#: (PRD NFR-8: product copy states facts).
NO_EXIT_CODE = "not recorded"


@dataclass(frozen=True)
class StoryFile:
    """One parsed Story file: everything `route` is allowed to know about it."""

    #: The worktree-relative path the glob matched, as the stop reason names it.
    path: str
    #: The frontmatter `status`, stripped. Never empty — an empty one is no file at all.
    status: str
    #: The whole `## Auto Run Result` section, heading included; `""` when there is none.
    auto_run_result: str
    #: The `Blocking condition:` line's own text, or `None` when the section states none.
    blocking_condition: str | None


def parse(path: str, text: str) -> StoryFile | None:
    """The file as `route` reads it, or `None` for every way it can be unreadable."""
    body = frontmatter(text)
    if body is None:
        return None
    loaded = load_with_lines(body)
    if loaded.root is None:
        return None
    status = loaded.root.get(STATUS_KEY)
    if not isinstance(status, str) or not status.strip():
        return None
    result = section(text, AUTO_RUN_RESULT)
    return StoryFile(
        path=path,
        status=status.strip(),
        auto_run_result=result,
        blocking_condition=blocking_condition(result),
    )


def frontmatter(text: str) -> str | None:
    """The text between the opening `---` and the next one, or `None` when there is none."""
    lines = text.splitlines()
    span = _fence(lines)
    return None if span is None else "\n".join(lines[span[0] : span[1]])


def section(text: str, heading: str) -> str:
    """One `## ` section whole, heading included, or `""` when the file has no such heading."""
    lines = text.splitlines()
    start = next((n for n, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return ""
    end = next(
        (n for n in range(start + 1, len(lines)) if lines[n].startswith(HEADING_PREFIX)),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip()


def blocking_condition(text: str) -> str | None:
    """The first `Blocking condition:` line's own text, or `None` when it says nothing."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(BLOCKING_CONDITION):
            return stripped[len(BLOCKING_CONDITION) :].strip() or None
    return None


def with_status(text: str, status: str) -> str:
    """`text` with its frontmatter `status` set to `status`, and the rest of it untouched.

    A file with no frontmatter is given one rather than left alone: the caller is about to
    dispatch on this file, and a Story file the harness cannot route on is the failure this
    call exists to prevent.
    """
    lines = text.splitlines()
    span = _fence(lines)
    line = f"{STATUS_KEY}: {status}"
    if span is None:
        return "\n".join([FRONTMATTER_FENCE, line, FRONTMATTER_FENCE, "", *lines]) + "\n"
    start, end = span
    kept = [entry for entry in lines[start:end] if not entry.startswith(f"{STATUS_KEY}:")]
    head = [FRONTMATTER_FENCE, line, *kept, FRONTMATTER_FENCE]
    return "\n".join([*head, *lines[end + 1 :]]) + "\n"


def after_verify(text: str, command: str, code: int | None, tail: Sequence[str]) -> str:
    """The Story file a `verify` row sent back: the frontmatter at `in-progress`, and what
    failed appended under `## Verify Failure` (FR-10). What the agent wrote is untouched."""
    stated = NO_EXIT_CODE if code is None else str(code)
    block = VERIFY_FAILURE.format(command=command, code=stated, tail="\n".join(tail))
    return appended(with_status(text, IN_PROGRESS), block)


def appended(text: str, block: str) -> str:
    """`text` with `block` after it, one blank line between them, one newline at the end."""
    body = text.rstrip("\n")
    return f"{body}\n\n{block.rstrip()}\n" if body else f"{block.rstrip()}\n"


def _fence(lines: list[str]) -> tuple[int, int] | None:
    """The half-open span of the frontmatter's *contents*, or `None` when there is none —
    which is both "no opening fence" and "a fence that never closes"."""
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_FENCE:
            return 1, index
    return None
