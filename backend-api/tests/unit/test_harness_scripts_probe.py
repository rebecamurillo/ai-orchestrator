"""The probe verb in each harness script — probe-specific counterpart to test_harness_scripts.py.

Does NOT import from test_harness_scripts.py (the anchor file; never modify it).
Helpers are re-stated here rather than imported from the anchor.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS_DIR = REPO_ROOT / "scripts" / "harness"
HARNESSES = ("claude", "codex", "opencode")


def _text(name: str) -> str:
    path = HARNESS_DIR / f"{name}.sh"
    assert path.is_file(), f"{path} is missing"
    return path.read_text()


pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")


@pytest.mark.parametrize("name", HARNESSES)
def test_probe_function_is_defined(name: str) -> None:
    """Each script must contain `probe() {` at the start of a line."""
    assert re.search(r"^probe\(\) \{", _text(name), re.MULTILINE), f"{name}.sh: no probe() function"


@pytest.mark.parametrize("name", HARNESSES)
def test_probe_dispatcher_case_entry(name: str) -> None:
    """Each script's case dispatcher must have a `probe)` entry."""
    assert "probe)" in _text(name), f"{name}.sh: no probe) in dispatcher case"
