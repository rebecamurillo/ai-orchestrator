"""The HTTP shape of `POST /runs/{id}/signals` (`api/schemas/signals.py`, SPEC CAP-9).

The router tests (`test_signals_router.py`) prove this renders correctly through a real
request; this module exercises `SignalIn.as_signal()` directly, the way `test_runs_schemas.py`
does for `RunIn.as_request()`.
"""

from __future__ import annotations

from orchestrator.api.schemas.signals import SignalIn
from orchestrator.domain.values import Signal


def test_as_signal_carries_the_kind_and_the_payload() -> None:
    payload = SignalIn(kind="retry", payload={"note": "syncs first"})

    signal = payload.as_signal()

    assert isinstance(signal, Signal)
    assert signal.kind == "retry"
    assert signal.payload == {"note": "syncs first"}


def test_the_payload_defaults_to_empty() -> None:
    payload = SignalIn(kind="cancel")

    assert payload.as_signal().payload == {}
