"""Tests for the harness_probe use case.

ok probe → ProbeResult(ok=True); failing probe → ProbeResult(ok=False, non-empty reason);
unknown harness name → NotFound (translates to 404 at the API layer).
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.harness_probe import HarnessProbePorts, probe
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.harness import ProbeResult
from tests.unit.fakes.harness import FakeHarness


def _ok_result() -> ProbeResult:
    return ProbeResult(ok=True, failing_reason=None, version="2.1.258", models=["claude-sonnet"])


def _failing_result() -> ProbeResult:
    return ProbeResult(ok=False, failing_reason="gateway unreachable", version="2.1.258", models=[])


def _ports(harness_name: str, result: ProbeResult) -> HarnessProbePorts:
    harness = FakeHarness(name=harness_name, probe_results=[result])
    return HarnessProbePorts(harnesses={harness_name: harness})


def test_ok_probe_returns_result_with_ok_true() -> None:
    result = probe(_ports("claude", _ok_result()), "claude")

    assert result.ok is True


def test_failing_probe_returns_result_with_non_empty_failing_reason() -> None:
    result = probe(_ports("claude", _failing_result()), "claude")

    assert result.ok is False
    assert result.failing_reason is not None
    assert len(result.failing_reason) > 0


def test_failing_probe_does_not_raise() -> None:
    """A probe that found issues returns 200 with ok=false — never raises (never HTTP 4xx/5xx)."""
    result = probe(_ports("claude", _failing_result()), "claude")

    assert isinstance(result, ProbeResult)


def test_unknown_harness_name_raises_not_found() -> None:
    ports = HarnessProbePorts(harnesses={"claude": FakeHarness(name="claude", probe_results=[])})

    with pytest.raises(NotFound):
        probe(ports, "unknown-harness")
