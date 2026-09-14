"""The planner's vocabulary: what it can refuse, what it can skip, and what it returns.

Everything the walker, the list reader and the public `plan_run` share is named once here,
so the three of them cannot spell a path separator, a skipped reason or a refusal two ways.

**`PlanError` is an `Invalid`.** `api/errors.py::DOMAIN_STATUS` already maps `Invalid` to
422 and `ProblemError` already carries `{template, version, line, path, reason}`, so a plan
that cannot be built reaches the Operator as a problem document naming the file, the line
and the entry, with no new mapping to add in 4.3 or 4.4.

**`INSERTED_GATE` is not a fallback for a missing `gate`.** A Template step that declared
none is `unvalidated` and stays `unvalidated` (NFR-2). The two rows the *planner* inserts —
the `plan` row and an item checkpoint — are the exception, because nobody left them
ungated: they carry their kind's own `gate_default`, read out of `KIND_META` rather than
written down again, exactly as `application/graph.py::_item_checkpoint` reads it.

**`Plan.plan_refs` holds list files.** `Run.plan_refs` is documented as "the commit each
list file was read at, so a plan can be called stale", so it has one entry per list file
and not one per file read; a story file is read at its frame's ref and adds nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from orchestrator.application.steps import KIND_META, WORKTREE_KIND
from orchestrator.application.templates.model import ForEach, ParsedTemplate
from orchestrator.application.templates.substitute import resolve
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.errors import Invalid
from orchestrator.domain.statuses import Gate
from orchestrator.domain.values import PlannedRow

# --- what a plan can refuse ----------------------------------------------------------------

#: The `for_each` named a file no candidate ref holds.
LIST_FILE_NOT_FOUND = "list file not found"
#: The file is there, but it is not a YAML sequence of mappings.
LIST_FILE_NOT_A_LIST = "list file is not a list"
#: An entry of a `stories.yaml` or an `epics.yaml` left out a field the loop needs.
ENTRY_MISSING_FIELDS = "entry is missing a required field"
#: Two entries claim the same id, so a row could not say which one it belongs to.
DUPLICATE_ENTRY_ID = "duplicate entry id"
#: One id is another id plus `-…`, so `{id}-*.md` would match both stories' files.
ID_NOT_PREFIX_FREE = "entry ids are not prefix-free"
#: Two files match one Story's `{id}-*.md`, so "is it done" has two answers.
AMBIGUOUS_STORY_FILE = "ambiguous story file"
#: A `uses: template` step names a version the resolved tree does not hold.
CALLEE_NOT_RESOLVED = "callee not resolved"
#: The Run has no commit to plan from: the remote holds no such base branch.
BASE_BRANCH_NOT_FOUND = "base branch not found"
#: Every ordinal a declared branch could take is already a branch on the origin, so this
#: Run has no name of its own to work on (`branches.py`).
NO_FREE_BRANCH = "no free branch name"
#: A row routes its failure back to a step that is not a row of its own frame. The
#: validator only checks that the target is an earlier `agent` step *somewhere in the file*
#: (`keys.py` keeps one flat set), so a step inside a loop may name one outside it — and
#: there is no such row to go back to.
REDISPATCH_TARGET_NOT_PLANNED = "redispatch target is not a row of this frame"
#: Two rows expanded to one path, so neither the walker nor `step_run`'s unique
#: `(run_id, path)` index could tell them apart. A step id that collides with an inserted
#: row's — `plan`, `before`, `after` — is the way a Template reaches this.
DUPLICATE_ROW_PATH = "duplicate row path"

# --- how a row's failure is routed (4.7 reads exactly this) ------------------------------

#: Where a row's routing lives in `with_resolved`. Absent on a row that declared none,
#: which the executor reads as `escalate` — the default the DSL gives it.
ON_FAIL_KEY = "on_fail"

#: The two keys a resolved redispatch carries. They are `domain.values.Redispatch`'s own
#: field names on purpose: the executor builds one with `Redispatch(**on_fail)` and needs
#: nothing else, which is what makes the row a complete instruction (AD-7).
REDISPATCH_TARGET_SEQ = "target_seq"
REDISPATCH_MAX = "max"


@dataclass(frozen=True)
class Redispatched:
    """A backwards route the walker found and `plan_run` has not numbered yet.

    The target is a **path** here because `seq` is dense over the finished plan: a row that
    routes backwards cannot know its target's number until the walk is over. `plan_run`
    replaces this object with `{target_seq, max}` before any caller sees a `Plan`, so the
    two shapes never both exist outside one function.

    The provenance fields are carried because the refusal happens after the walk, by which
    point the frame that declared the route is gone; without them a plan error would name
    the root Template for a step written in a callee.

    `max` is `int | None` only because `Step.redispatch_max` is: the key table requires
    `max` alongside `redispatch`, so a `None` here means a tree that never went through
    `validate()`.
    """

    target_path: str
    max: int | None
    template: str
    version: int
    line: int


# --- what a plan can skip, and say why -------------------------------------------------------

#: FR-10: the Story's file already states `status: done`, and this is not a re-review.
REASON_ALREADY_DONE = "already done"
#: The row's command resolved to nothing and named no Repository command on the way.
REASON_NO_COMMAND = "no command"


#: What every `reason_no_field` answer begins with, and the bare fallback does too — which
#: is why `names_a_field` excludes it explicitly rather than by prefix alone.
NO_FIELD_PREFIX = "no "


def reason_no_field(field: str) -> str:
    """`skipped · no <field>` — the row asked a Repository for a command it does not state.

    One function rather than one constant per field, because a Repository states three
    commands (`install_command`, `unit_test_command`, `quality_gate_command`) and every
    one of them can be the reason a shell row has nothing to run. Naming the field is the
    whole value of the reason: `skipped · no command` tells an Operator that something is
    unset, `skipped · no unit_test_command` tells them which box to fill in.
    """
    return f"no {field}"


def names_a_field(reason: str) -> bool:
    """Whether a reason is one of `reason_no_field`'s, rather than the bare fallback.

    The question `_verify_line` asks: was this row skipped because the Repository declares
    no command for it — which is an honest "there was nothing to prove" — or for some
    other reason, which is a readiness failure.
    """
    return reason.startswith(NO_FIELD_PREFIX) and reason != REASON_NO_COMMAND


#: The row's command was `{{repository.quality_gate_command}}` and the Repository has none.
#: Kept as a name because it is the one field the readiness fixture's own docstring reasons
#: about; derived, so the wording can never drift from `reason_no_field`'s.
REASON_NO_QUALITY_GATE = reason_no_field("quality_gate_command")

# --- how a row is named -----------------------------------------------------------------------

#: The first row of every plan: its path and its label are the same word (AD-7).
PLAN_PATH = "plan"
#: What joins the segments of a row's `path`.
PATH_SEPARATOR = "."
#: What joins the segments of a row's `label`. A middle dot, with spaces: the Operator reads
#: this, and `epic 1 . story 4-1 . build` reads as a path rather than as a sentence.
LABEL_SEPARATOR = " · "
#: The last segment of each item checkpoint a `pause_*_item_when` declares.
BEFORE_ITEM = "before"
AFTER_ITEM = "after"
#: What an `after` checkpoint is called on screen. The `before` one is called `before`,
#: because a stop before the item has nothing to be done with yet.
AFTER_LABEL = "done checkpoint"

#: The `with` key a `git.*` step names its branch in.
BRANCH_KEY = "branch"


def working_branch(template: ParsedTemplate, scope: Mapping[str, Any]) -> str | None:
    """The branch a Run of this Template works on: the one its worktree checks out.

    The kind is named in the one place kinds are named (AD-9). It has to be the kind rather
    than the first step that mentions a `branch`, because `git.push` and `pr.link` name one
    too and a Template that pushed somewhere else would move the whole plan's commit. A
    Template that checks nothing out itself — `initiative@1`, whose worktree is inside the
    epic frame — works from the base branch instead.
    """
    for entry in template.steps:
        if isinstance(entry, ForEach) or entry.uses != WORKTREE_KIND:
            continue
        return _branch_name(resolve(dict(entry.params).get(BRANCH_KEY), scope))
    return None


def _branch_name(value: Any) -> str | None:
    """A branch a Run could actually check out, or `None` for one nobody named."""
    return value if isinstance(value, str) and value else None


#: The gate a row the *planner* inserted carries: its kind's own, never `unvalidated`.
#: Derived from the one enumeration of kinds (AD-9); a kind with no gate of its own — the
#: `template` call, which is a path segment rather than a row — is simply not in the table.
INSERTED_GATE: dict[str, Gate] = {
    kind: meta.gate_default for kind, meta in KIND_META.items() if meta.gate_default is not None
}


class PlanError(Invalid):
    """A Run that cannot be planned, named by file, line and entry.

    Keyword-only, because five optional positions in one call is how a `line` ends up in
    the `item`. Every field but `reason` is absent when the refusal has no position of its
    own — a base branch that is not on the remote is about the Run, not about a line.
    """

    def __init__(
        self,
        *,
        reason: str,
        template: str | None = None,
        version: int | None = None,
        line: int | None = None,
        item: str | None = None,
    ) -> None:
        super().__init__(_sentence(reason, template, version, line, item))
        self.reason = reason
        self.template = template
        self.version = version
        self.line = line
        self.item = item


def _sentence(
    reason: str, template: str | None, version: int | None, line: int | None, item: str | None
) -> str:
    """`epic@1 line 27: entry is missing a required field: 4-1` — as much as is known."""
    where = f"{template}@{version}" if template is not None else ""
    where += f" line {line}" if line is not None else ""
    what = f"{reason}: {item}" if item is not None else reason
    return f"{where.strip()}: {what}" if where.strip() else what


@dataclass(frozen=True)
class ResolvedTree:
    """The pinned tree a Run is planned from: the root, and every callee it reaches.

    Resolved once, by the use case, before anything pure begins (AD-7). A planner that
    could look a Template up could look one up twice and plan two versions of it.
    """

    root: ParsedTemplate
    callees: tuple[ParsedTemplate, ...] = ()

    def callee(self, name: str, version: int) -> ParsedTemplate | None:
        """The callee a `uses: template` step names, or `None` when the tree lacks it."""
        for parsed in self.callees:
            if (parsed.name, parsed.version) == (name, version):
                return parsed
        return None

    def pinned_versions(self) -> tuple[TemplateRef, ...]:
        """Root first, then the callees in walk order — what 4.4 writes to the Run (AD-15)."""
        return tuple(
            TemplateRef(name=parsed.name, version=parsed.version)
            for parsed in (self.root, *self.callees)
        )


@dataclass(frozen=True)
class Plan:
    """What `plan_run` returns: the commit, the list files' commits, and every row."""

    plan_ref: str
    #: `{path: sha}` — one entry per list file the plan read (see the module docstring).
    plan_refs: dict[str, str] = field(default_factory=dict)
    rows: tuple[PlannedRow, ...] = ()
    #: `{declared: created}` — the branch each Template named, and the fresh name this Run
    #: works on instead (`branches.py`). The rows carry only the created name, so this is
    #: where pre-flight reads the declared one back: AD-14 refuses a Run whose branch
    #: another Run is holding, and after allocation no two Runs can ever name one branch.
    branches: dict[str, str] = field(default_factory=dict)
