"""The `Gateway` port (AD-11): one attempt's real spend, as LiteLLM's own spend log answers.

`Attempt.cost_usd`/`tokens_in`/`tokens_out`/`cost_provisional` (4.1) exist but nothing fills
them until this story. `spend_for_attempt` is the one read that fills them: it answers what
`GET /spend/logs/v2` knows about one `(run_id, attempt_id)` pair, summed and broken down by
model — never raising, because a gateway outage must degrade an attempt's cost to
"provisional zero", not fail the row that earned it (this port's own docstring on the real
adapter, `infrastructure/gateway/litellm_spend.py`, says why in detail).

Nothing here is wired to a call site yet (5.7's own scope): this story is the port, the
real adapter, and the one fake — nothing calls `spend_for_attempt` from the walker or an
executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class ModelSpend:
    """One model's own share of an attempt's spend."""

    model: str
    usd: Decimal
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class AttemptSpend:
    """What one attempt cost, as the Gateway's spend log answers.

    `provisional` is `True` for every outcome that is not "the log answered real rows":
    empty rows, an HTTP error, a bad body. A caller reading `provisional=True` never learns
    *why* — only the real adapter's own log line does — because the two are handled
    identically everywhere else in this system (`application/use_cases/spend.py`).
    """

    usd: Decimal
    tokens_in: int
    tokens_out: int
    by_model: tuple[ModelSpend, ...]
    #: How many spend-log rows this figure was summed from.
    calls: int
    provisional: bool


@runtime_checkable
class Gateway(Protocol):
    """The Gateway's own spend log, read per attempt. One method: no other query is needed."""

    def spend_for_attempt(self, run_id: UUID, attempt_id: UUID) -> AttemptSpend:
        """What `(run_id, attempt_id)` cost — the exact ids `env_for`'s headers send (5.1).

        Never raises: every failure this port's adapters can hit answers a provisional
        zero instead (this port's docstring, and the real adapter's own).
        """
        ...
