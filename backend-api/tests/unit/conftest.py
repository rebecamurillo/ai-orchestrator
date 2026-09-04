"""Shared unit-test fixtures.

The environment every test runs against is derived from the committed `.env.example`
contract (AD-20), never hand-written here: if a variable is added to the contract, the
tests pick it up. Values are the placeholders from the contract — no real secret.

The contract parser is imported from `scripts/check_env_contract.py` rather than
re-implemented, so the gate and the fixture can never disagree about what the file says.
That import needs the repo-root `scripts/` directory on `sys.path`; doing it here means it
happens once, at conftest load, instead of as a side effect of collecting a test module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_env_contract import parse_env_example  # noqa: E402 — needs the path above

__all__ = ["ENV_EXAMPLE", "REPO_ROOT", "parse_env_example"]


@pytest.fixture(scope="session")
def env_example() -> dict[str, str]:
    pairs = parse_env_example(ENV_EXAMPLE)
    assert pairs, f"no variables parsed from {ENV_EXAMPLE}"
    return pairs


@pytest.fixture
def env(env_example: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Put every contract variable in the process environment for the test's duration.

    Settings is case-insensitive, so a differently-cased host variable (`log_level`) would
    otherwise shadow the fixture value. Clear by upper-cased name, then set.
    """
    contract_names = set(env_example)
    for name in list(os.environ):
        if name.upper() in contract_names:
            monkeypatch.delenv(name, raising=False)
    for name, value in env_example.items():
        monkeypatch.setenv(name, value)
    return dict(env_example)
