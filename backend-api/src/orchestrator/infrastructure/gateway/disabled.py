"""`DisabledGateway`: the no-op `Gateway` adapter for instances with no LiteLLM proxy.

When `LITELLM_BASE_URL` is blank, `build_gateway` returns this adapter instead of
`LiteLLMSpend`.  It holds no HTTP client and makes no network request — so budget
parking and `record_attempt_spend` keep working on whatever the harness itself
reported, and an unpriced attempt is never written down as $0.00.

`spend_for_attempt` always returns `_DISABLED_ANSWER` — the same shape that
`LiteLLMSpend` returns on any degraded answer and that `tests/unit/fakes/gateway.py
::PROVISIONAL_ZERO` gives — so every downstream caller (`application/use_cases/spend
.py::_priced_attempt`) treats "gateway off" identically to "gateway unreachable".
One `log.info` at construction; nothing per attempt — a long Run must not log the
same fact on every attempt.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import structlog

from orchestrator.domain.ports.gateway import AttemptSpend

log = structlog.get_logger(__name__)

#: The answer every `spend_for_attempt` call returns — provisional zero, the same
#: shape `LiteLLMSpend` returns on any degraded answer and `PROVISIONAL_ZERO` in
#: `tests/unit/fakes/gateway.py` gives.
_DISABLED_ANSWER = AttemptSpend(
    usd=Decimal("0"),
    tokens_in=0,
    tokens_out=0,
    by_model=(),
    calls=0,
    provisional=True,
)


class DisabledGateway:
    """Gateway port implementation for instances with no LiteLLM proxy (AD-11).

    Holds no `httpx.Client` and makes no network request.  Logs once at
    construction so the operator knows the mode; nothing per attempt so the log
    is not repeated on every Run.
    """

    def __init__(self) -> None:
        log.info("gateway disabled, spend unknown")

    def spend_for_attempt(self, run_id: UUID, attempt_id: UUID) -> AttemptSpend:
        """Always returns a provisional zero — spend is unknown when the gateway is off."""
        return _DISABLED_ANSWER
