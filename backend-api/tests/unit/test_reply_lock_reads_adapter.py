"""The fresh reads the reply lock takes (story 4-1 review, 2026-11-03), without a database.

A chat fire shares one session with `expire_on_commit=False`, so its identity map outlives a
commit: `session.get`, or a `SELECT` without `populate_existing`, hands back the object it
already holds even when the row changed meanwhile. `IdentityMapSession` models exactly that
rule over one stored table, so the tests below show a plain read staying stale and the fresh
read seeing the change, and the compiled statement pins the option the real session obeys.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatUser
from orchestrator.infrastructure.db import (
    ProjectChannelRow,
    SQLAlchemyProjectChannelRepository,
    SQLAlchemyStepRunRepository,
)
from orchestrator.infrastructure.db.models.run import StepRunRow
from orchestrator.infrastructure.db.repositories.project_channel import allowed_users_json
from orchestrator.infrastructure.db.repositories.step_runs import row_values

AT = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
ALICE = ChatUser(id="u1", handle="alice")


class IdentityMapSession:
    """One table's rows in `stored`, and the objects this session already loaded in `held`.

    Without `populate_existing` a loaded row comes back as the held object; with it, the
    held object is replaced by what is stored now, as SQLAlchemy refreshes it in place."""

    def __init__(self, entity: type, key: str) -> None:
        self.entity = entity
        self.key = key
        self.stored: dict[Any, Any] = {}
        self.held: dict[Any, Any] = {}
        self.statements: list[Any] = []

    def get(self, entity: type, ident: Any) -> Any:
        if ident not in self.held and ident in self.stored:
            self.held[ident] = self.stored[ident]
        return self.held.get(ident)

    def scalars(self, statement: Any) -> SimpleNamespace:
        self.statements.append(statement)
        fresh = statement.get_execution_options().get("populate_existing", False)
        rows = []
        for ident, row in self.stored.items():
            if fresh or ident not in self.held:
                self.held[ident] = row
            rows.append(self.held[ident])
        return SimpleNamespace(all=lambda: list(rows), first=lambda: rows[0] if rows else None)


def a_channel(**overrides: Any) -> ProjectChannel:
    fields: dict[str, Any] = {
        "project_id": new_id(),
        "provider": "mattermost",
        "base_url": "https://chat.example.com",
        "channel_id": "c1",
        "token_enc": "enc",
        "allowed_users": (ALICE,),
        "metadata_only": False,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return ProjectChannel(**fields)


def channel_row(channel: ProjectChannel) -> ProjectChannelRow:
    return ProjectChannelRow(
        project_id=channel.project_id,
        provider=channel.provider,
        base_url=channel.base_url,
        channel_id=channel.channel_id,
        token_enc=channel.token_enc,
        allowed_users=allowed_users_json(channel),
        metadata_only=channel.metadata_only,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


def a_step(run_id: UUID, status: str = "blocked") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=1,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="deterministic",
        status=status,  # type: ignore[arg-type]
    )


# ── the channel ─────────────────────────────────────────────────────────────────────────


def test_a_channel_changed_after_the_first_read_is_seen_by_get_current() -> None:
    first = a_channel()
    session = IdentityMapSession(ProjectChannelRow, "project_id")
    session.stored[first.project_id] = channel_row(first)
    channels = SQLAlchemyProjectChannelRepository(session)  # type: ignore[arg-type]
    assert channels.get(first.project_id) == first

    changed = a_channel(project_id=first.project_id, allowed_users=(), channel_id="c2")
    session.stored[first.project_id] = channel_row(changed)

    assert channels.get(first.project_id) == first
    assert channels.get_current(first.project_id) == changed


def test_get_current_refreshes_the_row_by_project() -> None:
    channel = a_channel()
    session = IdentityMapSession(ProjectChannelRow, "project_id")
    session.stored[channel.project_id] = channel_row(channel)

    SQLAlchemyProjectChannelRepository(session).get_current(channel.project_id)  # type: ignore[arg-type]

    (statement,) = session.statements
    assert statement.get_execution_options()["populate_existing"] is True
    assert "WHERE project_channel.project_id = " in str(statement)


def test_get_current_answers_none_when_no_channel_is_stored() -> None:
    session = IdentityMapSession(ProjectChannelRow, "project_id")

    assert SQLAlchemyProjectChannelRepository(session).get_current(new_id()) is None  # type: ignore[arg-type]


# ── the step rows ───────────────────────────────────────────────────────────────────────


def test_a_row_changed_after_the_first_read_is_seen_by_list_for_run_current() -> None:
    run_id = new_id()
    first = a_step(run_id)
    session = IdentityMapSession(StepRunRow, "id")
    session.stored[first.id] = StepRunRow(**row_values(first))
    steps = SQLAlchemyStepRunRepository(session)  # type: ignore[arg-type]
    assert steps.list_for_run(run_id) == [first]

    changed = first.model_copy(update={"status": "queued"})
    session.stored[first.id] = StepRunRow(**row_values(changed))

    assert steps.list_for_run(run_id) == [first]
    assert steps.list_for_run_current(run_id) == [changed]


def test_list_for_run_current_refreshes_the_runs_rows_in_seq_order() -> None:
    session = IdentityMapSession(StepRunRow, "id")

    SQLAlchemyStepRunRepository(session).list_for_run_current(new_id())  # type: ignore[arg-type]

    (statement,) = session.statements
    assert statement.get_execution_options()["populate_existing"] is True
    text = str(statement)
    assert "WHERE step_run.run_id = " in text
    assert text.endswith("ORDER BY step_run.seq")
