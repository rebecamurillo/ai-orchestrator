"""The HTTP shape of `POST /runs/{id}/signals` (SPEC CAP-9, FR-20, AD-13).

`SignalIn` is the body every kind shares — `signal_run` (4.5) is what tells a well-formed
one from an admitted one, not this schema. The response is `RunSummaryOut`
(`api/schemas/runs.py`): the Run this signal left, with the `admitted_signals` list its own
`.of()` now computes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orchestrator.domain.statuses import SignalKind
from orchestrator.domain.values import Signal


class SignalIn(BaseModel):
    """`POST /runs/{id}/signals`'s body: one signal kind, and whatever it carries."""

    kind: SignalKind
    payload: dict[str, Any] = Field(default_factory=dict)

    def as_signal(self) -> Signal:
        return Signal(kind=self.kind, payload=self.payload)
