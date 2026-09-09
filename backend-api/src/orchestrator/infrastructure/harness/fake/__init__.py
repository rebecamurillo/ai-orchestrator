"""The scripted `fake` harness (AR-14), registered only under `ORCH_TEST_MODE`.

Laid out the way `claude/` is — `adapter.py` beside the parsing it needs — so the registry
names one class here and nothing else has to know the package has two modules.
"""

from orchestrator.infrastructure.harness.fake.adapter import NAME, FakeHarness

__all__ = ["NAME", "FakeHarness"]
