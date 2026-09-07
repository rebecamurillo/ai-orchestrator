"""In-memory `Gateway` — the one fake for that port (AD-18). Reuse it; do not write another.

Scripted per `(run_id, attempt_id)`, the same shape `FakeTracer.observed` scripts its own
pair-keyed answers with. An unscripted pair answers a provisional zero — the same thing the
real adapter answers for an attempt the spend log has no rows for yet — so a test never has
to script the "nothing happened" case explicitly.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from orchestrator.domain.ports.gateway import AttemptSpend

#: What every unscripted `(run_id, attempt_id)` pair answers — the real adapter's own
#: "empty rows" and "connection error" outcomes collapse to this same shape.
PROVISIONAL_ZERO = AttemptSpend(
    usd=Decimal("0"), tokens_in=0, tokens_out=0, by_model=(), calls=0, provisional=True
)


class FakeGateway:
    """Scripted `AttemptSpend` per `(run_id, attempt_id)`, and a call log."""

    def __init__(self) -> None:
        self._scripted: dict[tuple[UUID, UUID], AttemptSpend] = {}
        self.calls: list[tuple[UUID, UUID]] = []

    def script(self, run_id: UUID, attempt_id: UUID, spend: AttemptSpend) -> None:
        """What `spend_for_attempt(run_id, attempt_id)` answers from now on."""
        self._scripted[(run_id, attempt_id)] = spend

    def spend_for_attempt(self, run_id: UUID, attempt_id: UUID) -> AttemptSpend:
        self.calls.append((run_id, attempt_id))
        return self._scripted.get((run_id, attempt_id), PROVISIONAL_ZERO)
