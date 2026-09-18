"""`run_probe_script` (`infrastructure/harness/probe.py`, story 2-1): shell it, parse it.

Every adapter's `probe()` is one line delegating here, so this is where the parsing and the
two adapter faults are settled — `tests/unit/test_harness_adapters_probe.py` pins the
delegation, and `tests/unit/test_harness_scripts_probe.py` pins the scripts themselves.

The happy paths run a real script, because what is under test is a shell-out: a double for
`subprocess.run` would prove the call was built and never that the process's stdout parses.
The timeout is the one case that cannot be staged that way — the bound is thirty seconds, and
a test that waited for it would cost more than the suite it is in — so it is the one case
that replaces `subprocess.run` with a raise.

`ok=False` is not a fault: a probe that ran and found a problem reports it as data, which is
what lets `GET /harnesses/{name}/probe` serve it as a 200 (`domain/ports/harness.py`).
"""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from orchestrator.infrastructure.harness.probe import ProbeResult, run_probe_script

#: What the shell verb promises: exactly one JSON line on stdout, whatever the outcome.
READY = {
    "ok": True,
    "failing_reason": None,
    "version": "2.1.258",
    "models": ["sonnet", "opus"],
}
NOT_READY = {"ok": False, "failing_reason": "no credentials", "version": "2.1.258", "models": []}


def a_script(directory: Path, body: str) -> Path:
    """An executable script of `body`, the way the image installs one."""
    script = directory / "harness.sh"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def emitting(line: object) -> str:
    """A body that answers `probe` with one JSON line and nothing else."""
    return f"printf '%s\\n' '{json.dumps(line)}'"


def test_the_one_json_line_becomes_the_probe_result(tmp_path: Path) -> None:
    result = run_probe_script(a_script(tmp_path, emitting(READY)))

    assert result == ProbeResult(
        ok=True, failing_reason=None, version="2.1.258", models=["sonnet", "opus"]
    )


def test_a_probe_that_ran_and_found_a_problem_is_data_not_a_raise(tmp_path: Path) -> None:
    result = run_probe_script(a_script(tmp_path, emitting(NOT_READY)))

    assert result.ok is False
    assert result.failing_reason == "no credentials"


def test_the_verb_the_script_is_asked_for_is_probe(tmp_path: Path) -> None:
    """The one argument, echoed back through the field the script controls."""
    script = a_script(tmp_path, 'printf \'{"ok":true,"version":"%s","models":[]}\\n\' "$1"')

    assert run_probe_script(script).version == "probe"


def test_the_optional_fields_fall_back_rather_than_raise(tmp_path: Path) -> None:
    """A script that names only `ok` still parses: `failing_reason`, `version` and `models`
    are what a probe may leave out, and `ok` is what it may not."""
    result = run_probe_script(a_script(tmp_path, emitting({"ok": True})))

    assert result == ProbeResult(ok=True, failing_reason=None, version="", models=[])


def test_a_script_that_emitted_nothing_is_an_adapter_fault(tmp_path: Path) -> None:
    """Not a `ProbeResult`: there is nothing to report, and swallowing it would publish a
    harness as failing when what failed was the probe itself."""
    script = a_script(tmp_path, "printf 'boom\\n' >&2\nexit 3")

    with pytest.raises(RuntimeError) as raised:
        run_probe_script(script)

    assert "no output" in str(raised.value)
    assert "exit 3" in str(raised.value)
    assert "boom" in str(raised.value)


def test_output_that_is_not_json_is_an_adapter_fault(tmp_path: Path) -> None:
    with pytest.raises(json.JSONDecodeError):
        run_probe_script(a_script(tmp_path, "printf 'not json\\n'"))


def test_a_probe_that_never_answered_names_the_bound_it_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = a_script(tmp_path, emitting(READY))

    def timing_out(*_: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd=[str(script), "probe"], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timing_out)

    with pytest.raises(RuntimeError) as raised:
        run_probe_script(script)

    assert "timed out after 30s" in str(raised.value)
    assert str(script) in str(raised.value)
