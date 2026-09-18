"""Shared probe helper for harness adapters (story 2-1).

Each concrete harness adapter delegates `probe()` to `run_probe_script`, which shells the
harness script's `probe` verb and parses its one-line JSON stdout.  `subprocess.run` is used
directly — not `ProcessRunner` — because probe is a short synchronous one-shot check, not a
coding-agent dispatch (Design Notes, story 2-1).

`ProbeResult` is re-exported here so each adapter imports from one place rather than mixing
domain-port and infrastructure paths for the same feature.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from orchestrator.domain.ports.harness import ProbeResult

__all__ = ["ProbeResult", "run_probe_script"]


def run_probe_script(script: Path) -> ProbeResult:
    """Shell `<script> probe`, parse the one-line JSON stdout.

    Raises on adapter faults (timeout, empty stdout, JSON parse error) — these are not probe
    failures and must not be swallowed into a `ProbeResult`.
    """
    try:
        completed = subprocess.run(
            [str(script), "probe"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"probe timed out after {exc.timeout}s: {script}") from exc
    if not completed.stdout.strip():
        raise RuntimeError(
            f"probe emitted no output (exit {completed.returncode}): {script}"
            f"\nstderr: {completed.stderr!r}"
        )
    data = json.loads(completed.stdout.strip())
    return ProbeResult(
        ok=data["ok"],
        failing_reason=data.get("failing_reason"),
        version=data.get("version", ""),
        models=data.get("models", []),
    )
