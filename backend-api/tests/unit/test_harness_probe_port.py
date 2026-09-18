"""Assert ProbeResult shape and FakeHarness protocol compliance (AD-18).

All assertions here are about the *port contract* — that ProbeResult has the four fields,
that FakeHarness satisfies the Harness protocol after probe() is added, and that the scripted
queue pops in order and raises on empty.
"""

from __future__ import annotations

import pytest

from orchestrator.domain.ports.harness import Harness, ProbeResult
from tests.unit.fakes.harness import FakeHarness


def test_probe_result_ok_field() -> None:
    result = ProbeResult(ok=True, failing_reason=None, version="2.1.258", models=[])
    assert result.ok is True

    failing = ProbeResult(
        ok=False, failing_reason="gateway unreachable", version="2.1.258", models=[]
    )
    assert failing.ok is False


def test_probe_result_failing_reason_field() -> None:
    result = ProbeResult(ok=True, failing_reason=None, version="2.1.258", models=[])
    assert result.failing_reason is None

    result2 = ProbeResult(ok=False, failing_reason="not logged in", version="2.1.258", models=[])
    assert result2.failing_reason == "not logged in"


def test_probe_result_version_field() -> None:
    result = ProbeResult(ok=True, failing_reason=None, version="2.1.258", models=[])
    assert result.version == "2.1.258"


def test_probe_result_models_field() -> None:
    result = ProbeResult(ok=True, failing_reason=None, version="2.1.258", models=["m1", "m2"])
    assert result.models == ["m1", "m2"]

    empty = ProbeResult(ok=True, failing_reason=None, version="2.1.258", models=[])
    assert empty.models == []


def test_fake_harness_satisfies_harness_protocol() -> None:
    """FakeHarness must be a structural match for the Harness Protocol (runtime check)."""
    harness = FakeHarness(
        probe_results=[ProbeResult(ok=True, failing_reason=None, version="0.0.0", models=[])]
    )
    assert isinstance(harness, Harness)


def test_fake_harness_probe_pops_in_order() -> None:
    r1 = ProbeResult(ok=True, failing_reason=None, version="1.0", models=[])
    r2 = ProbeResult(ok=False, failing_reason="gateway unreachable", version="1.0", models=[])
    harness = FakeHarness(probe_results=[r1, r2])

    assert harness.probe() is r1
    assert harness.probe() is r2


def test_fake_harness_probe_raises_on_empty_queue() -> None:
    harness = FakeHarness()

    with pytest.raises(AssertionError, match="probe queue empty"):
        harness.probe()
