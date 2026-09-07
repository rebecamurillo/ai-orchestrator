"""`TemplateVersionRepository.pinned_by` (SPEC CAP-4, AD-15): counting a pin across `run`.

Three layers, three tests: the fake (`tests/unit/fakes/templates.py`) counts a live
`FakeRunRepository`; the adapter issues a real `jsonb` containment query rather than a
Python scan (unlike `callers_of`, which scans `template_version` in Python because that
table is short — `run` is not); `get_version` (3.3/4.4) wires the count into the read
model. `tests/e2e/test_run_creation.py` proves the containment query for real, against
Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from orchestrator.application.use_cases.templates import TemplatePorts, get_version
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db import SQLAlchemyTemplateVersionRepository
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def a_run(pinned: tuple[TemplateRef, ...]) -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        pinned_versions=pinned,
        status="queued",
        budget_usd=Decimal("1"),
        created_at=AT,
    )


def a_version(name: str = "story", version: int = 1) -> TemplateVersion:
    return TemplateVersion(
        name=name,
        version=version,
        yaml=f"name: {name}\nversion: {version}\nsteps: []\n",
        hash="sha",
        calls=(),
        created_at=AT,
    )


# ── the fake: live against `FakeRunRepository` ──────────────────────────────────────────


def test_the_fake_answers_zero_with_no_runs_wired() -> None:
    templates = FakeTemplateVersionRepository([a_version()])

    assert templates.pinned_by("story", 1) == 0


def test_the_fake_counts_a_run_that_pins_it_as_a_callee() -> None:
    runs = FakeRunRepository()
    templates = FakeTemplateVersionRepository([a_version()], runs=runs)
    runs.add(a_run((TemplateRef(name="epic", version=1), TemplateRef(name="story", version=1))))

    assert templates.pinned_by("story", 1) == 1
    assert templates.pinned_by("epic", 1) == 1
    assert templates.pinned_by("story", 2) == 0


#: Every `RunStatus` there is (AD-15: "any status" pins).
ALL_RUN_STATUSES = ("queued", "running", "needs_you", "done", "failed", "cancelled")


def test_the_fake_counts_every_status_a_run_can_be_in() -> None:
    """AD-15: "any status" — a `done`/`failed`/`cancelled` Run still pins its Version."""
    runs = FakeRunRepository()
    templates = FakeTemplateVersionRepository([a_version()], runs=runs)
    for status in ALL_RUN_STATUSES:
        runs.add(
            a_run((TemplateRef(name="story", version=1),)).model_copy(
                update={
                    "id": new_id(),
                    "status": status,
                }
            )
        )

    assert templates.pinned_by("story", 1) == len(ALL_RUN_STATUSES)


def test_get_version_reads_pinned_by_off_the_port() -> None:
    runs = FakeRunRepository()
    templates = FakeTemplateVersionRepository([a_version()], runs=runs)
    runs.add(a_run((TemplateRef(name="story", version=1),)))
    ports = TemplatePorts(uow=FakeUnitOfWork(), templates=templates, clock=FakeClock())

    detail = get_version(ports, "story", 1)

    assert detail.pinned_by == 1


# ── the adapter: a real `jsonb` containment query, not a Python scan ────────────────────


class RecordingResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class RecordingSession:
    """Records the statement `pinned_by` builds; answers a canned count."""

    def __init__(self, count: int) -> None:
        self.statements: list[Any] = []
        self._count = count

    def scalars(self, statement: Any) -> RecordingResult:
        self.statements.append(statement)
        return RecordingResult([self._count])


SCRIPTED_COUNT = 3


def test_the_adapter_issues_one_jsonb_containment_query() -> None:
    session = RecordingSession(count=SCRIPTED_COUNT)
    repo = SQLAlchemyTemplateVersionRepository(session)  # type: ignore[arg-type]

    count = repo.pinned_by("story", 1)

    assert count == SCRIPTED_COUNT
    (statement,) = session.statements
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "run" in compiled.lower()
    assert "@>" in compiled or "contains" in compiled.lower() or "jsonb" in compiled.lower()


def test_the_adapter_answers_zero_rather_than_none() -> None:
    session = RecordingSession(count=0)
    repo = SQLAlchemyTemplateVersionRepository(session)  # type: ignore[arg-type]

    assert repo.pinned_by("story", 1) == 0
