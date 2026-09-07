"""The durability proof refuses to run without a container, and never skips instead.

`tests/e2e/test_durability.py` is the one module in this repository that needs more than a
reachable backend: it needs a backend it may `SIGKILL` and bring back, which means a compose
container. `tests/e2e/conftest.py`'s own docstring states the rule that follows — "an e2e gate
that skips when the stack is missing reports success for a suite that ran nothing" — and this
module holds that module to it, here, where it costs no stack to check.

Importing the e2e module is deliberate and cheap: it opens nothing. Its imports are
`orchestrator.infrastructure.db` (models the unit suite already imports elsewhere), the typed
settings, and two sibling e2e modules that define fixtures and constants and run no I/O at
import time. `make test` still needs no Postgres and no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e import test_durability

SERVICE = "backend-api"
TARGET = "make durability"

#: What `pytest.fail` raises. `pytest.skip` raises `Skipped`, a different class — and telling
#: the two apart is the whole point of the second test below.
Failed = pytest.fail.Exception


def answering(output: str) -> object:
    """A `compose` stand-in that answers `output` whatever it is asked."""
    return lambda *arguments, **keywords: output


def test_no_container_is_a_failure_naming_the_service_and_the_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`docker compose ps --quiet` answers nothing at all when the project has no container."""
    monkeypatch.setattr(test_durability, "compose", answering(""))

    with pytest.raises(Failed) as refusal:
        test_durability.container_id()

    assert SERVICE in str(refusal.value)
    assert TARGET in str(refusal.value)


def test_the_refusal_is_a_failure_and_not_a_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """A skipped durability marker would report success for a proof that never ran, so the
    refusal must raise `Failed` — `Skipped` would be caught by this and by nothing else."""
    monkeypatch.setattr(test_durability, "compose", answering("\n  \n"))

    with pytest.raises(Failed) as refusal:
        test_durability.container_id()

    assert not isinstance(refusal.value, pytest.skip.Exception)


def test_more_than_one_container_is_refused_rather_than_picked_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Killing one and inspecting another would prove nothing, quietly."""
    monkeypatch.setattr(test_durability, "compose", answering("abc123\ndef456\n"))

    with pytest.raises(Failed) as refusal:
        test_durability.container_id()

    assert "2" in str(refusal.value)


def test_a_named_container_is_handed_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(test_durability, "compose", answering("abc123\n"))

    assert test_durability.container_id() == "abc123"


def test_the_module_skips_nowhere_at_all() -> None:
    """`container_id` is only the first of the module's refusals — `compose`, `wait_healthy`,
    `wait_for_process`, `wait_for_row` and `wait_for` each have one too. Rather than drive
    every one of them, this asserts the property they share, over the whole file."""
    source = Path(test_durability.__file__).read_text()

    assert "pytest.skip" not in source
    assert "skipif" not in source
