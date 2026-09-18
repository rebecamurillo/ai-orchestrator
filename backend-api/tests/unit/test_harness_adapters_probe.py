"""Each harness adapter's `probe()` (story 2-1): which script it shells, and the one that
shells none.

`GET /harnesses/{name}/probe` is only as true as this delegation: the route, the use case and
the registry all address a harness by the name a Template writes (`claude`, `codex`, `local`),
while the script that answers for it is named after the *CLI* — `local` is `opencode.sh`.
Nothing else in the suite would notice two adapters pointed at the same script, or at the
right file under the wrong directory, because every other probe test runs on
`tests/unit/fakes/harness.py`.

So the registry is built the way `main.py` builds it and each adapter is asked for its probe
against a scripts directory this test wrote, where every script reports its own name. Parsing
and the adapter faults are `tests/unit/test_harness_probe_script_runner.py`'s; the shipped
scripts are `tests/unit/test_harness_scripts_probe.py`'s.

`fake` (AR-14) is the one adapter that shells nothing: it is dev-mode only and always ready,
so its answer is a constant and its scripts directory is never read.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from orchestrator.infrastructure.harness.registry import build_harnesses
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

#: The registry name each adapter is looked up by, and the script file it must shell for it.
SCRIPTS = {"claude": "claude.sh", "codex": "codex.sh", "local": "opencode.sh"}
FAKE_VERSION = "0.0.0-fake"


@pytest.fixture
def scripts_dir(tmp_path: Path) -> Path:
    """One executable script per harness, each reporting the file it was read from."""
    for filename in SCRIPTS.values():
        script = tmp_path / filename
        script.write_text(f'#!/bin/sh\nprintf \'{{"ok":true,"version":"{filename}"}}\\n\'\n')
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return tmp_path


@pytest.fixture
def harnesses(env: dict[str, str], scripts_dir: Path) -> dict[str, object]:
    settings = Settings(harness_scripts_dir=scripts_dir, orch_test_mode=True)
    return dict(build_harnesses(settings, FakeProcessRunner()))


@pytest.mark.parametrize(("name", "filename"), sorted(SCRIPTS.items()))
def test_each_adapter_shells_the_script_named_for_its_own_cli(
    harnesses: dict, name: str, filename: str
) -> None:
    result = harnesses[name].probe()

    assert result.ok is True
    assert result.version == filename


def test_the_fake_harness_answers_without_a_script(harnesses: dict, tmp_path: Path) -> None:
    (tmp_path / "fake.sh").unlink(missing_ok=True)

    result = harnesses["fake"].probe()

    assert (result.ok, result.failing_reason, result.version) == (True, None, FAKE_VERSION)
    assert result.models == ["fake-model"]


def test_no_two_adapters_answer_from_the_same_script(harnesses: dict) -> None:
    """The failure this module exists to catch: a copied line leaves two harnesses probing
    one CLI and both report whatever that one installed."""
    reported = [harnesses[name].probe().version for name in SCRIPTS]

    assert len(set(reported)) == len(SCRIPTS)
