"""A command's process group goes with it when its leader exits on its own (issue #25).

A harness or a verify command leaves processes behind in its group — a background shell,
test workers, a detached `git maintenance`. In a container whose PID 1 reaps nothing, each
held its PID until a restart: 97,046 of them parked a Run on 2026-11-24.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from orchestrator.infrastructure.process.runner import RealProcessRunner

#: Long enough to outlive the test by far if nothing kills it.
LEFT_BEHIND = "sleep 300 & exit 0"
#: The leader has gone by the time `wait` returns; its child must have gone too, at once.
GONE_WITHIN_SECONDS = 5.0


def _group_gone(pgid: int) -> bool:
    deadline = time.monotonic() + GONE_WITHIN_SECONDS
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            # Darwin answers EPERM for a group whose last member is a zombie of another parent
            return True
        time.sleep(0.05)
    return False


@pytest.mark.parametrize("stall_min", [None, 5.0], ids=["plain wait", "stall watch"])
def test_a_natural_exit_takes_what_the_leader_left_in_its_group(
    tmp_path: Path, stall_min: float | None
) -> None:
    runner = RealProcessRunner()
    handle = runner.start(
        ["sh", "-c", LEFT_BEHIND],
        cwd=tmp_path,
        env={},
        timeout_min=None,
        log_path=tmp_path / "a.log",
        stall_min=stall_min,
    )

    outcome = runner.wait(handle)

    assert (outcome.exit_code, outcome.timed_out, outcome.stalled) == (0, False, False)
    assert _group_gone(handle.pgid)
