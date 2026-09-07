"""The Run aggregate round-trips through the migrated schema — what only Postgres settles.

`tests/unit/test_run_repository_adapter.py` drives the four adapters over a recording
session, so it proves the SQL they build and the mapping they apply, but never that
`0005_run.py` created the columns those adapters name: the model and the migration are two
files, and a divergence between them is invisible from the unit side. This module writes a
Project, a Repository, a Run, two `step_run` rows, one `attempt` and one `gate_record`
through their adapters, commits, and reads them back in a **fresh session** — so the
comparison is against what the database holds, not against what the identity map cached.

Entity equality is the assertion, which is what makes `Decimal` money and tz-aware
timestamps part of it: a `numeric` read back as a float or a `timestamp` that lost its zone
would fail here and nowhere else.

The three unique indexes are read from `pg_index` the way
`tests/e2e/test_repositories.py::repository_indexes` reads the Repository's, for the same
reason: the unit suite asserts them against `Base.metadata`, which the model populates,
never against what the migration actually built.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Worktree
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings

AT = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
EXPECTED_ROWS = 2
ATTEMPT_N = 2


@pytest.fixture(scope="module")
def sessions(stack: str) -> Iterator[Any]:
    """A session factory over the migrated database. `stack` first, so a down stack is
    reported once, by the readiness fixture, rather than as a connection error here."""
    engine = create_engine_from(Settings())
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


def a_project() -> Project:
    unique = uuid4()
    return Project(
        id=new_id(),
        slug=f"e2e-run-{unique}",
        name=f"e2e run persistence {unique}",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=AT,
        updated_at=AT,
    )


def a_repository(project: Project) -> Repository:
    unique = uuid4()
    return Repository(
        id=new_id(),
        project_id=project.id,
        slug=f"e2e-repo-{unique}",
        url=f"https://example.invalid/{unique}.git",
        default_branch="main",
        install_command="make install",
        quality_gate_command="make lint test",
        unit_test_command="make test",
        test_globs=("tests/**",),
        package_manager="uv",
        clone_check=CloneCheck.pending(),
        created_at=AT,
        updated_at=AT,
    )


def a_run(project: Project, repository: Repository) -> Run:
    """A Run with every optional column filled: the round trip has to survive all of them."""
    return Run(
        id=new_id(),
        project_id=project.id,
        repository_id=repository.id,
        template_name="story",
        template_version=1,
        pinned_versions=(TemplateRef(name="story", version=1), TemplateRef(name="epic", version=2)),
        inputs={"base_branch": "main", "harness": "claude", "model": "sonnet"},
        status="needs_you",
        plan_ref="a" * 40,
        plan_refs={"docs/stories.yaml": "b" * 40},
        engine_ref={"workflow_id": "w-1"},
        budget_usd=Decimal("10.000000"),
        spend_usd=Decimal("1.234567"),
        manual_estimate_h=Decimal("2.50"),
        re_review_done=True,
        park_kind="checkpoint",
        park_path="steps[1]",
        park_reason="review the diff",
        accepted_paths=("tests/unit/a.py",),
        worktree_path="/work/wt/a",
        worktrees=(
            Worktree(branch="story/4-1", path="/work/wt/a", created_branch=True, pushed=False),
        ),
        compare_urls=("https://example.invalid/compare/a...b",),
        trace_id="trace-1",
        terminal_session=True,
        active_seconds=120,
        last_opened_at=AT,
        created_at=AT,
        started_at=AT,
        ended_at=None,
    )


def step_rows(run: Run) -> list[StepRun]:
    return [
        StepRun(
            id=new_id(),
            run_id=run.id,
            seq=0,
            path="steps[0]",
            label="plan check",
            kind="plan.check",
            gate="deterministic",
            status="done",
            with_resolved={},
        ),
        StepRun(
            id=new_id(),
            run_id=run.id,
            seq=1,
            path="steps[1]",
            label="build",
            kind="agent",
            gate="unvalidated",
            status="checkpoint",
            reason="review the diff",
            with_resolved={"harness": "claude"},
            retry_count=1,
            redispatch_count=0,
            frame="steps[1].stories[0]",
            story_id="4-1",
        ),
    ]


def an_attempt(run: Run, row: StepRun) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=row.id,
        n=ATTEMPT_N,
        status="checkpoint",
        started_at=AT,
        ended_at=AT,
        engine_ref={"step": "agent"},
        start_sha="c" * 40,
        end_sha="d" * 40,
        frozen_test_files=("tests/unit/a.py", "tests/unit/b.py"),
        log_path="/work/logs/1.log",
        exit_code=0,
        output_ref="/work/logs/1.log",
        harness="claude",
        model="sonnet",
        session_id="s-1",
        pgid=4321,
        tokens_in=100,
        tokens_out=200,
        cost_usd=Decimal("0.012345"),
        cost_provisional=True,
    )


def a_gate_record(run: Run) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=run.id,
        at=AT,
        path="steps[1]",
        event="checkpoint",
        actor="machine",
        text="stopped for review",
        attempt_n=ATTEMPT_N,
        payload={"accepted": ["tests/unit/a.py"]},
    )


@pytest.fixture(scope="module")
def written(sessions: Any) -> tuple[Run, list[StepRun], Attempt, GateRecord]:
    """Write the whole aggregate in one transaction and commit it."""
    project = a_project()
    repository = a_repository(project)
    run = a_run(project, repository)
    rows = step_rows(run)
    attempt = an_attempt(run, rows[1])
    record = a_gate_record(run)

    session: Session = sessions()
    try:
        SQLAlchemyProjectRepository(session).add(project)
        SQLAlchemyRepositoryRepository(session).add(repository)
        SQLAlchemyRunRepository(session).add(run)
        SQLAlchemyStepRunRepository(session).add_many(rows)
        SQLAlchemyAttemptRepository(session).add(attempt)
        SQLAlchemyGateRecordRepository(session).add(record)
        session.commit()
    finally:
        session.close()
    return run, rows, attempt, record


@pytest.fixture
def reader(sessions: Any) -> Iterator[Session]:
    """A session that never saw the write — so a read is a read, not a cache hit."""
    session: Session = sessions()
    try:
        yield session
    finally:
        session.close()


def test_the_run_reads_back_equal_to_what_was_written(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], reader: Session
) -> None:
    run, _, _, _ = written

    assert SQLAlchemyRunRepository(reader).get(run.id) == run


def test_the_planned_rows_read_back_in_seq_order(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], reader: Session
) -> None:
    run, rows, _, _ = written

    stored = SQLAlchemyStepRunRepository(reader).list_for_run(run.id)

    assert stored == rows
    assert len(stored) == EXPECTED_ROWS


def test_a_row_reads_back_by_its_seq(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], reader: Session
) -> None:
    run, rows, _, _ = written

    assert SQLAlchemyStepRunRepository(reader).get_by_seq(run.id, 1) == rows[1]


def test_the_attempt_reads_back_equal_including_its_money_and_its_frozen_files(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], reader: Session
) -> None:
    _, rows, attempt, _ = written

    stored = SQLAlchemyAttemptRepository(reader).get_latest(rows[1].id)

    assert stored == attempt
    assert stored is not None
    assert stored.cost_usd == Decimal("0.012345")
    assert stored.frozen_test_files == ("tests/unit/a.py", "tests/unit/b.py")


def test_the_gate_record_reads_back_equal(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], reader: Session
) -> None:
    run, _, _, record = written

    assert SQLAlchemyGateRecordRepository(reader).list_for_run(run.id) == [record]


def test_the_stored_run_keeps_its_decimal_money_and_its_zone(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], reader: Session
) -> None:
    run, _, _, _ = written

    stored = SQLAlchemyRunRepository(reader).get(run.id)

    assert stored is not None
    assert stored.budget_usd == Decimal("10.000000")
    assert stored.spend_usd == Decimal("1.234567")
    assert stored.manual_estimate_h == Decimal("2.50")
    assert stored.created_at.tzinfo is not None
    assert stored.created_at == AT


def test_the_run_is_listed_under_its_project_and_not_under_another(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], reader: Session
) -> None:
    run, _, _, _ = written
    runs = SQLAlchemyRunRepository(reader)

    assert run in runs.list(project_id=run.project_id)
    assert run not in runs.list(project_id=new_id())


def test_a_parked_run_is_listed_as_non_terminal_against_its_repository(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], reader: Session
) -> None:
    run, _, _, _ = written

    assert run in SQLAlchemyRunRepository(reader).list_by_repository_non_terminal(run.repository_id)


def test_the_run_is_listed_by_its_status(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], reader: Session
) -> None:
    run, _, _, _ = written

    assert run in SQLAlchemyRunRepository(reader).list_by_status("needs_you")


def test_an_update_through_the_adapter_lands_in_the_database(
    written: tuple[Run, list[StepRun], Attempt, GateRecord], sessions: Any, reader: Session
) -> None:
    run, _, _, _ = written
    # `status` is left alone: the fixture is module-scoped, and a test that changed it
    # would decide what the status assertions above see.
    raised = run.model_copy(
        update={"spend_usd": Decimal("2.500000"), "park_reason": "budget raised"}
    )

    writer: Session = sessions()
    try:
        SQLAlchemyRunRepository(writer).update(raised)
        writer.commit()
    finally:
        writer.close()

    assert SQLAlchemyRunRepository(reader).get(run.id) == raised


# ── the schema the migration was written to create ───────────────────────────


def indexes_of(settings: Settings, table: str) -> dict[str, bool]:
    engine = create_engine_from(settings)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "select i.relname, x.indisunique from pg_index x "
                    "join pg_class i on i.oid = x.indexrelid "
                    "join pg_class t on t.oid = x.indrelid "
                    "join pg_namespace n on n.oid = t.relnamespace "
                    "where t.relname = :table and n.nspname = 'public'"
                ),
                {"table": table},
            )
            return {name: bool(unique) for name, unique in rows}
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def run_indexes(stack: str) -> dict[str, bool]:
    return indexes_of(Settings(), "run")


@pytest.fixture(scope="module")
def step_run_indexes(stack: str) -> dict[str, bool]:
    return indexes_of(Settings(), "step_run")


@pytest.fixture(scope="module")
def attempt_indexes(stack: str) -> dict[str, bool]:
    return indexes_of(Settings(), "attempt")


@pytest.fixture(scope="module")
def gate_record_indexes(stack: str) -> dict[str, bool]:
    return indexes_of(Settings(), "gate_record")


@pytest.mark.parametrize("index", ["ix_step_run_run_id_seq", "ix_step_run_run_id_path"])
def test_the_migration_created_the_step_run_unique_indexes(
    step_run_indexes: dict[str, bool], index: str
) -> None:
    assert step_run_indexes.get(index) is True, sorted(step_run_indexes)


def test_the_migration_created_the_attempt_unique_index(
    attempt_indexes: dict[str, bool],
) -> None:
    assert attempt_indexes.get("ix_attempt_step_run_id_n") is True, sorted(attempt_indexes)


@pytest.mark.parametrize(
    "index", ["ix_run_project_id", "ix_run_status", "ix_run_repository_id_status"]
)
def test_the_migration_created_the_run_read_indexes(
    run_indexes: dict[str, bool], index: str
) -> None:
    assert index in run_indexes, sorted(run_indexes)
    assert run_indexes[index] is False, f"{index} is unique; a Run list would be refused"


def test_the_migration_created_the_gate_record_read_index(
    gate_record_indexes: dict[str, bool],
) -> None:
    assert gate_record_indexes.get("ix_gate_record_run_id_at") is False, sorted(gate_record_indexes)
