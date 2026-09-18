"""`probe`: run a readiness check against one harness (story 2-1).

Looks up the harness by name from the registry; raises `NotFound` (404) on miss; delegates
to `harness.probe()` and returns the result verbatim.  A probe that found problems — wrong
CLI version, gateway unreachable, bad credentials — returns `ProbeResult(ok=False, …)`
rather than raising: HTTP errors belong to unknown names (404) and adapter faults (500),
not to a probe that ran to completion and reported a finding.

The registry is a plain `dict[str, Harness]` built by
`infrastructure/harness/registry.build_harnesses`; passing it as a port keeps this module
free of any infrastructure import (AD-2).
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.harness import Harness, ProbeResult


@dataclass(frozen=True)
class HarnessProbePorts:
    """Everything the probe use case reaches the outside world through."""

    #: Harness registry keyed by name — the same mapping `build_harnesses` produces.
    harnesses: dict[str, Harness]


def probe(ports: HarnessProbePorts, name: str) -> ProbeResult:
    """Run the named harness's probe verb and return the result.

    `NotFound` (404) when `name` is not in the registry.  Any other exception is an adapter
    fault and surfaces as a 500 — there is no partial-success case to swallow.
    """
    harness = ports.harnesses.get(name)
    if harness is None:
        raise NotFound(f"no harness named {name!r}")
    return harness.probe()
