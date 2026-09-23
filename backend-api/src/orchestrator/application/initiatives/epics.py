"""One initiative's `epics.yaml`: parsed into entries, and checked as a graph.

The operator-facing contract, as the hub repository documents it — an entry carries

    id, title, repo, branch, spec_folder,
    depends_on: [epic ids],
    done_checkpoint: bool?, checkpoint: block_merge | go_live?,
    baseline_sha?

— and `done_checkpoint: true` on its own means `block_merge`.

Everything here is pure: text in, entries and refusal lines out. Nothing raises. A
dispatcher has to be able to show the Operator *every* thing wrong with the file at once,
and an exception can only carry the first, which is why this module's currency is the same
`Line` pre-flight already speaks (`fail` refuses, `warn` and `ok` inform).

**Order is the file's own.** `topological_order` is a Kahn walk that always takes the
earliest still-ready entry in file order, so two independent epics come out in the order the
Operator wrote them and a dispatch of the same file twice creates its Runs in the same
sequence. A stable order is not cosmetic here: it is what makes "created in topological
order" (AD-12) a checkable property rather than a coin toss.

**A cycle is reported, not broken.** Kahn's walk simply stops when nothing is ready; what is
left is exactly the entries inside or downstream of a cycle, and naming them is more use to
the Operator than naming one arbitrary back-edge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from orchestrator.application.preflight.model import Line
from orchestrator.application.templates.lines import load_sequence

#: The file every initiative folder holds, and the check name its refusals carry.
EPICS_FILE = "epics.yaml"
CHECK_EPICS = "initiative epics.yaml"
#: The graph the entries describe — `depends_on`, cycles, and the per-repository branch.
CHECK_GRAPH = "initiative graph"

#: What an entry has to state. `depends_on` is optional (an epic in wave 0 declares none),
#: and so is every checkpoint key.
REQUIRED_FIELDS = ("id", "title", "repo", "branch", "spec_folder")

#: The two stops an entry can declare, and the key that is shorthand for the first of them.
BLOCK_MERGE = "block_merge"
GO_LIVE = "go_live"
CHECKPOINTS = (BLOCK_MERGE, GO_LIVE)
DONE_CHECKPOINT_KEY = "done_checkpoint"
CHECKPOINT_KEY = "checkpoint"

#: The refusal texts, each naming the entry the Operator has to go and fix.
NOT_A_LIST = f"{EPICS_FILE} is not a list of entries"
NO_ENTRIES = f"{EPICS_FILE} holds no entries"
MISSING_FIELD = "epic {item}: missing {field}"
DUPLICATE_ID = "epic {item}: duplicate id"
UNKNOWN_DEPENDENCY = "epic {item}: depends_on names no epic: {dep}"
CYCLE = "epics depend on each other in a cycle: {items}"
BAD_CHECKPOINT = "epic {item}: checkpoint must be {choices}"
REPO_TWO_BRANCHES = "repo {item}: two integration branches declared: {branches}"

#: How an entry with no readable id is named, so a refusal still points somewhere.
POSITIONAL = "entry {index}"


@dataclass(frozen=True)
class Epic:
    """One `epics.yaml` entry, after parsing. Nothing here has met a Repository yet."""

    id: str
    title: str
    repo: str
    branch: str
    spec_folder: str
    depends_on: tuple[str, ...] = ()
    #: `block_merge`, `go_live`, or `None`. Normalised: an entry that said only
    #: `done_checkpoint: true` arrives here as `block_merge`, which is what the contract
    #: says that shorthand means.
    checkpoint: str | None = None
    #: Where this epic's integration branch is created from when the remote does not hold it
    #: yet. `None` leaves the choice to the repository's own default branch.
    baseline_sha: str | None = None

    @property
    def blocks_merge(self) -> bool:
        """Whether the epic Run ends on a human stop before its merge Run may run."""
        return self.checkpoint == BLOCK_MERGE

    @property
    def goes_live(self) -> bool:
        """Whether this epic is one the initiative's single go-live checkpoint holds for."""
        return self.checkpoint == GO_LIVE


@dataclass(frozen=True)
class ParsedEpics:
    """What the file said, and every reason it could not be used.

    `epics` is what parsed; `lines` is every refusal. A caller checks the lines, never the
    emptiness of `epics`: a file with one good entry and one broken one yields both.
    """

    epics: tuple[Epic, ...]
    lines: tuple[Line, ...]
    #: The entries in dependency order, file order breaking every tie. Empty when the graph
    #: could not be ordered — which is exactly when a `fail` line says why.
    order: tuple[str, ...] = ()

    @property
    def failed(self) -> bool:
        """Whether anything here refuses the dispatch."""
        return any(line.status == "fail" for line in self.lines)


def _fail(check: str, text: str) -> Line:
    return Line(check=check, status="fail", text=text)


def parse_epics(text: str | None) -> ParsedEpics:
    """The file's entries and every refusal in it, including the graph's own.

    `None` is "the hub does not hold the file", which is a refusal like any other rather
    than an exception: the Operator typed an `initiative_folder` and this says what is not
    there.
    """
    if text is None:
        return ParsedEpics((), (_fail(CHECK_EPICS, f"{EPICS_FILE} not found"),))
    document = load_sequence(text)
    if document is None:
        return ParsedEpics((), (_fail(CHECK_EPICS, NOT_A_LIST),))
    entries = [entry for entry in document if isinstance(entry, Mapping)]
    if len(entries) != len(document):
        return ParsedEpics((), (_fail(CHECK_EPICS, NOT_A_LIST),))
    if not entries:
        return ParsedEpics((), (_fail(CHECK_EPICS, NO_ENTRIES),))
    epics, lines = _entries(entries)
    lines += check_graph(epics)
    order = topological_order(epics) if not any(line.status == "fail" for line in lines) else ()
    return ParsedEpics(epics=epics, lines=tuple(lines), order=order)


def _entries(entries: Sequence[Mapping[str, Any]]) -> tuple[tuple[Epic, ...], list[Line]]:
    """Every entry that reads as one, and a `fail` line per entry that does not."""
    epics: list[Epic] = []
    lines: list[Line] = []
    for index, entry in enumerate(entries):
        name = str(entry["id"]) if entry.get("id") else POSITIONAL.format(index=index)
        missing = [field for field in REQUIRED_FIELDS if not entry.get(field)]
        if missing:
            lines += [
                _fail(CHECK_EPICS, MISSING_FIELD.format(item=name, field=field))
                for field in missing
            ]
            continue
        checkpoint, problem = _checkpoint(entry, name)
        if problem is not None:
            lines.append(problem)
            continue
        epics.append(
            Epic(
                id=str(entry["id"]),
                title=str(entry["title"]),
                repo=str(entry["repo"]),
                branch=str(entry["branch"]),
                spec_folder=str(entry["spec_folder"]),
                depends_on=_dependencies(entry),
                checkpoint=checkpoint,
                baseline_sha=_optional(entry, "baseline_sha"),
            )
        )
    return tuple(epics), lines


def _dependencies(entry: Mapping[str, Any]) -> tuple[str, ...]:
    """`depends_on` as a tuple of ids; anything that is not a list is no dependency at all.

    A scalar is accepted as the one id it names — the mistake an Operator makes most often
    writing `depends_on: s1` — because reading it as "no dependencies" would silently
    dispatch the epic in wave 0, and that is the failure mode this whole module exists to
    prevent.
    """
    declared = entry.get("depends_on")
    if declared is None:
        return ()
    if isinstance(declared, str):
        return (declared,)
    if isinstance(declared, Sequence):
        return tuple(str(item) for item in declared)
    return (str(declared),)


def _optional(entry: Mapping[str, Any], key: str) -> str | None:
    """One optional string field, `None` when it is absent or empty."""
    value = entry.get(key)
    return str(value) if value else None


def _checkpoint(entry: Mapping[str, Any], name: str) -> tuple[str | None, Line | None]:
    """The entry's normalised stop, or the line refusing the token it used.

    An explicit `checkpoint` wins over `done_checkpoint`: the shorthand is defined as what
    `done_checkpoint: true` means *on its own*, so an entry that states both is read as
    having said the longer thing.
    """
    declared = entry.get(CHECKPOINT_KEY)
    if declared is not None:
        if declared not in CHECKPOINTS:
            choices = " | ".join(CHECKPOINTS)
            return None, _fail(CHECK_EPICS, BAD_CHECKPOINT.format(item=name, choices=choices))
        return str(declared), None
    return (BLOCK_MERGE if entry.get(DONE_CHECKPOINT_KEY) is True else None), None


def check_graph(epics: Sequence[Epic]) -> list[Line]:
    """Duplicate ids, unknown dependencies, cycles, and one branch per repository."""
    lines = _duplicate_ids(epics)
    known = {epic.id for epic in epics}
    for epic in epics:
        lines += [
            _fail(CHECK_GRAPH, UNKNOWN_DEPENDENCY.format(item=epic.id, dep=dep))
            for dep in epic.depends_on
            if dep not in known
        ]
    lines += _branch_per_repo(epics)
    if not lines:
        lines += _cycle(epics)
    return lines


def _duplicate_ids(epics: Sequence[Epic]) -> list[Line]:
    """One `fail` per id claimed twice, named at its second appearance."""
    seen: set[str] = set()
    lines: list[Line] = []
    for epic in epics:
        if epic.id in seen:
            lines.append(_fail(CHECK_GRAPH, DUPLICATE_ID.format(item=epic.id)))
        seen.add(epic.id)
    return lines


def _branch_per_repo(epics: Sequence[Epic]) -> list[Line]:
    """A repository has exactly one integration branch across the whole initiative.

    Two epics on one repository naming two branches is not two integration branches — it is
    one of them being wrong. Their merge Runs would land on different branches and the
    go-live checkpoint would hold for a tree nothing was merged into.
    """
    branches: dict[str, list[str]] = {}
    for epic in epics:
        declared = branches.setdefault(epic.repo, [])
        if epic.branch not in declared:
            declared.append(epic.branch)
    return [
        _fail(CHECK_GRAPH, REPO_TWO_BRANCHES.format(item=repo, branches=", ".join(declared)))
        for repo, declared in branches.items()
        if len(declared) > 1
    ]


def _cycle(epics: Sequence[Epic]) -> list[Line]:
    """The `fail` line naming every entry a cycle swallowed, or nothing at all."""
    ordered = topological_order(epics)
    if len(ordered) == len(epics):
        return []
    stuck = [epic.id for epic in epics if epic.id not in set(ordered)]
    return [_fail(CHECK_GRAPH, CYCLE.format(items=", ".join(stuck)))]


def topological_order(epics: Sequence[Epic]) -> tuple[str, ...]:
    """Epic ids in dependency order, file order breaking every tie.

    Shorter than the whole list exactly when a cycle stopped the walk — `_cycle` is what
    turns that into the Operator's sentence.
    """
    known = {epic.id for epic in epics}
    waiting = {epic.id: {dep for dep in epic.depends_on if dep in known} for epic in epics}
    ordered: list[str] = []
    done: set[str] = set()
    remaining = [epic.id for epic in epics]
    while True:
        ready = next((item for item in remaining if not (waiting[item] - done)), None)
        if ready is None:
            return tuple(ordered)
        remaining.remove(ready)
        ordered.append(ready)
        done.add(ready)


def wavefront(epics: Sequence[Epic]) -> tuple[str, ...]:
    """The epics that start at once: every entry with no dependency of its own (AD-12)."""
    return tuple(epic.id for epic in epics if not epic.depends_on)
