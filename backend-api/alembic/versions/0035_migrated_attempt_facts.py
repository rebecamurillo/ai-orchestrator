"""migrated attempt facts: the figures attempts already carry, copied into facts.

Revision ID: 0035_migrated_attempt_facts
Revises: 0034_run_spend_figures
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic import op

from orchestrator.application.use_cases.spend_figures import (
    AttemptRows,
    SpendFigures,
    StoredRead,
    figures_of,
)
from orchestrator.domain.entities.facts import GatewayRead, UsageFact
from orchestrator.domain.ids import new_id

revision: str = "0035_migrated_attempt_facts"
down_revision: str | None = "0034_run_spend_figures"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

EXTRACTOR = "migrated"
EXTRACTOR_VERSION = 1
REASON = "migrated from attempt record"

_attempt = sa.table(
    "attempt",
    sa.column("id", sa.Uuid()),
    sa.column("run_id", sa.Uuid()),
    sa.column("model", sa.Text()),
    sa.column("ended_at", sa.DateTime(timezone=True)),
    sa.column("cost_usd", sa.Numeric(12, 6)),
    sa.column("cost_provisional", sa.Boolean()),
    sa.column("tokens_in", sa.BigInteger()),
    sa.column("tokens_out", sa.BigInteger()),
)
_fact_set = sa.table(
    "fact_set",
    sa.column("id", sa.Uuid()),
    sa.column("attempt_id", sa.Uuid()),
    sa.column("run_id", sa.Uuid()),
    sa.column("extractor", sa.Text()),
    sa.column("extractor_version", sa.Integer()),
    sa.column("read_at", sa.DateTime(timezone=True)),
    sa.column("status", sa.Text()),
    sa.column("reason", sa.Text()),
)
_gateway_read = sa.table(
    "gateway_read",
    sa.column("id", sa.Uuid()),
    sa.column("attempt_id", sa.Uuid()),
    sa.column("run_id", sa.Uuid()),
    sa.column("read_at", sa.DateTime(timezone=True)),
    sa.column("trigger", sa.Text()),
    sa.column("rows", sa.BigInteger()),
    sa.column("calls", sa.BigInteger()),
    sa.column("provisional", sa.Boolean()),
    sa.column("capped", sa.Boolean()),
    sa.column("usd", sa.Numeric(12, 6)),
    sa.column("prompt", sa.BigInteger()),
    sa.column("completion", sa.BigInteger()),
)
_usage_fact = sa.table(
    "usage_fact",
    sa.column("id", sa.Uuid()),
    sa.column("fact_set_id", sa.Uuid()),
    sa.column("gateway_read_id", sa.Uuid()),
    sa.column("source", sa.Text()),
    sa.column("model", sa.Text()),
    sa.column("class", sa.Text()),
    sa.column("usd", sa.Numeric(12, 6)),
)
_run = sa.table(
    "run",
    sa.column("id", sa.Uuid()),
    sa.column("gateway_spend_usd", sa.Numeric(12, 6)),
    sa.column("harness_spend_usd", sa.Numeric(12, 6)),
    sa.column("gate_spend_usd", sa.Numeric(12, 6)),
    sa.column("gateway_reported", sa.Boolean()),
    sa.column("harness_reported", sa.Boolean()),
)


def plan_attempt(
    attempt: Mapping[str, Any], now: datetime, new_id: Callable[[], UUID]
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    """The rows one attempt's stored figures become; nothing is inferred beyond them."""
    fact_set = {
        "id": new_id(),
        "attempt_id": attempt["id"],
        "run_id": attempt["run_id"],
        "extractor": EXTRACTOR,
        "extractor_version": EXTRACTOR_VERSION,
        "read_at": now,
        "status": "partial",
        "reason": REASON,
    }
    cost = attempt["cost_usd"]
    if cost is None:
        return fact_set, None, []
    usage = {
        "id": new_id(),
        "fact_set_id": None,
        "gateway_read_id": None,
        "source": "harness",
        "model": attempt["model"],
        "class": "money",
        "usd": cost,
    }
    if attempt["cost_provisional"]:
        usage["fact_set_id"] = fact_set["id"]
        return fact_set, None, [usage]
    read = {
        "id": new_id(),
        "attempt_id": attempt["id"],
        "run_id": attempt["run_id"],
        "read_at": attempt["ended_at"] or now,
        "trigger": "attempt_end",
        "rows": None,
        "calls": None,
        "provisional": False,
        "capped": False,
        "usd": cost,
        "prompt": attempt["tokens_in"],
        "completion": attempt["tokens_out"],
    }
    usage.update({"gateway_read_id": read["id"], "source": "gateway"})
    return fact_set, read, [usage]


def _as_usage_fact(row: Mapping[str, Any]) -> UsageFact:
    return UsageFact(
        source=row["source"], model=row.get("model"), usage_class=row["class"], usd=row["usd"]
    )


def run_totals(
    attempt_ids: Sequence[UUID],
    reads: Sequence[Mapping[str, Any]],
    read_usage: Mapping[UUID, Sequence[Mapping[str, Any]]],
    fact_money: Mapping[UUID, Sequence[Mapping[str, Any]]],
) -> SpendFigures:
    """One Run's totals through the rule `record_attempt_spend` uses, not a copy of it."""
    by_attempt: dict[UUID, list[StoredRead]] = defaultdict(list)
    for row in sorted(reads, key=lambda r: (r["read_at"], r["id"]), reverse=True):
        read = GatewayRead(
            id=row["id"],
            attempt_id=row["attempt_id"],
            run_id=row.get("run_id") or attempt_ids[0],
            read_at=row["read_at"],
            trigger=row["trigger"],
            provisional=row["provisional"],
            usd=row["usd"],
        )
        usage = tuple(_as_usage_fact(u) for u in read_usage.get(row["id"], ()))
        by_attempt[row["attempt_id"]].append((read, usage))
    return figures_of(
        AttemptRows(
            reads=by_attempt[attempt_id],
            fact_money=tuple(_as_usage_fact(u) for u in fact_money.get(attempt_id, ())),
        )
        for attempt_id in attempt_ids
    )


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)
    migrated = (
        sa.select(_fact_set.c.id)
        .where(
            _fact_set.c.attempt_id == _attempt.c.id,
            _fact_set.c.extractor == EXTRACTOR,
            _fact_set.c.extractor_version == EXTRACTOR_VERSION,
        )
        .exists()
    )
    attempts = conn.execute(sa.select(_attempt).where(~migrated)).mappings().all()
    planned = [plan_attempt(row, now, new_id) for row in attempts]
    if planned:
        conn.execute(sa.insert(_fact_set), [p[0] for p in planned])
        read_rows = [p[1] for p in planned if p[1] is not None]
        if read_rows:
            conn.execute(sa.insert(_gateway_read), read_rows)
        usage_rows = [u for p in planned for u in p[2]]
        if usage_rows:
            conn.execute(sa.insert(_usage_fact), usage_rows)
    _rewrite_run_totals(conn)


def _rewrite_run_totals(conn: sa.Connection) -> None:
    attempts_by_run: dict[UUID, list[UUID]] = defaultdict(list)
    for row in conn.execute(sa.select(_attempt.c.id, _attempt.c.run_id)).all():
        attempts_by_run[row.run_id].append(row.id)
    reads_by_run: dict[UUID, list[Mapping[str, Any]]] = defaultdict(list)
    for read in conn.execute(sa.select(_gateway_read)).mappings():
        reads_by_run[read["run_id"]].append(dict(read))
    read_usage: dict[UUID, list[Mapping[str, Any]]] = defaultdict(list)
    for usage in conn.execute(
        sa.select(_usage_fact).where(_usage_fact.c.gateway_read_id.is_not(None))
    ).mappings():
        read_usage[usage["gateway_read_id"]].append(dict(usage))
    fact_money: dict[UUID, list[Mapping[str, Any]]] = {}
    first_set: dict[UUID, UUID] = {}
    money = (
        sa.select(_usage_fact, _fact_set.c.attempt_id)
        .join(_fact_set, _fact_set.c.id == _usage_fact.c.fact_set_id)
        .where(_usage_fact.c.source == "harness", _usage_fact.c["class"] == "money")
        .order_by(_fact_set.c.read_at, _fact_set.c.id)
    )
    for usage in conn.execute(money).mappings():
        attempt_id = usage["attempt_id"]
        if first_set.setdefault(attempt_id, usage["fact_set_id"]) == usage["fact_set_id"]:
            fact_money.setdefault(attempt_id, []).append(dict(usage))
    for run_id in [row.id for row in conn.execute(sa.select(_run.c.id))]:
        totals = run_totals(
            attempts_by_run.get(run_id, []), reads_by_run.get(run_id, []), read_usage, fact_money
        )
        conn.execute(
            sa.update(_run)
            .where(_run.c.id == run_id)
            .values(
                gateway_spend_usd=totals.gateway_usd,
                harness_spend_usd=totals.harness_usd,
                gate_spend_usd=totals.gate_usd,
                gateway_reported=totals.gateway_reported,
                harness_reported=totals.harness_reported,
            )
        )


def downgrade() -> None:
    raise NotImplementedError(
        "0035_migrated_attempt_facts is a data migration; downgrade is not supported"
    )
