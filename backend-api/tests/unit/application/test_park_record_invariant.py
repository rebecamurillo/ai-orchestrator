"""The count-back's guard (story 4-2): `rules/chat_close.py::ending_record` finds a stop's
park record by counting park-kind records back from the end, which holds only while every
`park_seq` increment writes exactly one record whose event is a park kind.

Three things are pinned: the three park writers each do exactly that; an `ast` scan of
`application/` finds no other place that sets `park_seq` to anything but a plain read or
writes a park-kind record, so a new park writer fails here until it joins (1); and the park
alphabet shares no token with the other record alphabets.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from orchestrator.application.use_cases.apply_step_result import budget_second_record
from orchestrator.application.use_cases.writers import _write_dependency_park, park_run
from orchestrator.domain.statuses import (
    LIFECYCLE_EVENTS,
    MACHINE_EVENTS,
    PARK_KINDS,
    SIGNAL_KINDS,
    WRITE_EVENTS,
)
from orchestrator.domain.values import Park, StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.conftest import REPO_ROOT

APPLICATION = REPO_ROOT / "backend-api" / "src" / "orchestrator" / "application"
BUILD = "stories[0].build"
SEQ = 4
#: Every `park_seq` increment in `application/` at `afb565a`, by file and function.
PARK_WRITERS = frozenset(
    {
        ("use_cases/writers.py", "park_run"),
        ("use_cases/writers.py", "_write_dependency_park"),
        ("use_cases/apply_step_result.py", "budget_second_record"),
    }
)


def park_records(world: World) -> int:
    return sum(1 for event in world.events() if event in PARK_KINDS)


# ── (1) the writers ────────────────────────────────────────────────────────────────────


def test_park_run_raises_park_seq_by_one_with_one_park_record() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"}, park_seq=SEQ)
    before = park_records(world)

    with world.ports.uow:
        park_run(world.ports, world.stored_run(), Park(kind="blocked", reason="why", path=BUILD))
        world.ports.uow.commit()

    assert world.stored_run().park_seq == SEQ + 1
    assert park_records(world) == before + 1


def test_the_budget_second_record_raises_park_seq_by_one_with_one_park_record() -> None:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="why",
        park_seq=SEQ,
    )
    before = park_records(world)
    result = StepResult(
        status="blocked", gate="liveness", budget_park=Park(kind="budget", reason="over")
    )

    budget_second_record(world.ports, world.stored_run(), world.row(BUILD), result)

    assert world.stored_run().park_seq == SEQ + 1
    assert park_records(world) == before + 1


def test_the_dependency_park_raises_park_seq_by_one_with_one_park_record() -> None:
    world = a_world("queued", EPIC_PLAN, {}, park_seq=SEQ)
    before = park_records(world)

    _write_dependency_park(world.ports, world.stored_run(), "the run it waits on failed")

    assert world.stored_run().park_seq == SEQ + 1
    assert park_records(world) == before + 1


# ── (2) the scan ───────────────────────────────────────────────────────────────────────


def _is_park_seq_read(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "park_seq"


def _is_park_event(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return node.value in PARK_KINDS
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "kind"
        and isinstance(node.value, ast.Name)
        and node.value.id == "park"
    )


def _is_entry(node: ast.Call) -> bool:
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "Entry") or (
        isinstance(func, ast.Attribute) and func.attr == "Entry"
    )


def _flags(node: ast.AST) -> Iterator[int]:
    """The line of every flagged site directly under `node`."""
    if isinstance(node, ast.keyword) and node.arg == "park_seq":
        if not _is_park_seq_read(node.value):
            yield node.value.lineno
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=True):
            if isinstance(key, ast.Constant) and key.value == "park_seq":
                if not _is_park_seq_read(value):
                    yield value.lineno
    if isinstance(node, ast.Call) and _is_entry(node):
        for keyword in node.keywords:
            if keyword.arg == "event" and _is_park_event(keyword.value):
                yield keyword.value.lineno


def scan(source: str) -> list[tuple[str | None, int]]:
    """Each flagged site in `source`, with the name of the function that holds it."""
    found: list[tuple[str | None, int]] = []

    def visit(node: ast.AST, function: str | None) -> None:
        found.extend((function, line) for line in _flags(node))
        inner = node.name if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) else function
        for child in ast.iter_child_nodes(node):
            visit(child, inner)

    visit(ast.parse(source), None)
    return found


def scan_application() -> set[tuple[str, str | None]]:
    flagged: set[tuple[str, str | None]] = set()
    for path in sorted(APPLICATION.rglob("*.py")):
        name = path.relative_to(APPLICATION).as_posix()
        flagged |= {(name, function) for function, _ in scan(path.read_text(encoding="utf-8"))}
    return flagged


def test_only_the_three_park_writers_raise_park_seq_or_write_a_park_record() -> None:
    assert scan_application() == PARK_WRITERS


@pytest.mark.parametrize(
    "source",
    [
        "def new_park(run):\n    set_run(ports, run, park_seq=run.park_seq + 2)\n",
        "def new_park(run):\n    run.model_copy(update={'park_seq': 9})\n",
        "def new_park(run):\n    record(ports, run, Entry(event='blocked', actor='machine'))\n",
        "def new_park(run, park):\n    record(ports, run, writers.Entry(event=park.kind))\n",
    ],
)
def test_the_scan_flags_a_new_park_writer(source: str) -> None:
    assert scan(source) == [("new_park", 2)]


@pytest.mark.parametrize(
    "source",
    [
        "def view(run):\n    return RunEvent(park_seq=run.park_seq)\n",
        "def view(run):\n    return {'park_seq': thread.park_seq}\n",
        "def view(run):\n    return Entry(event='failed', actor='machine')\n",
        "def view(run, row):\n    return Entry(event=row.kind)\n",
        "def view(run):\n    return Other(event='blocked')\n",
        "def view(run):\n    return {**extra, 'kind': 'blocked'}\n",
    ],
)
def test_the_scan_passes_plain_reads_and_other_records(source: str) -> None:
    assert scan(source) == []


# ── (3) the alphabets ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("alphabet", [SIGNAL_KINDS, LIFECYCLE_EVENTS, MACHINE_EVENTS, WRITE_EVENTS])
def test_the_park_kinds_share_no_token_with_another_alphabet(alphabet: tuple[str, ...]) -> None:
    assert set(PARK_KINDS).isdisjoint(alphabet)


def test_the_application_tree_is_where_the_scan_looks() -> None:
    assert Path(APPLICATION / "use_cases" / "writers.py").is_file()
