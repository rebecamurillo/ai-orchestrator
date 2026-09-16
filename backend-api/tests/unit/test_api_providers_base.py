"""The `app.state` accessors every provider module reads adapters through.

Split out of `api/providers.py` at the 400-line cap (`test_source_limits.py`), so the
accessor claims move with the code: `from_state` answers the stored adapter or refuses
naming the missing attribute; `git_adapter` is the one tolerant read; `required_git` is
the loud one, naming who needed the port. The names `api/providers.py` re-exports stay
importable from there — `test_api_providers.py` and the frozen router tests already hold
that side.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request

from orchestrator.api.providers_base import (
    CRYPTO,
    ENGINE,
    GIT,
    SESSION_FACTORY,
    SETTINGS,
    from_state,
    git_adapter,
    required_git,
)


def request_for(app: FastAPI) -> Request:
    """A bare request whose only capability is reaching `app.state`."""
    return Request({"type": "http", "app": app})


def test_the_state_attribute_names_are_the_wiring_contract() -> None:
    """`main.py` stores adapters under these exact names; a rename is a wiring break."""
    assert (SESSION_FACTORY, CRYPTO, GIT, ENGINE, SETTINGS) == (
        "session_factory",
        "crypto",
        "git",
        "engine",
        "settings",
    )


def test_from_state_answers_the_stored_adapter() -> None:
    app = FastAPI()
    adapter = object()
    setattr(app.state, ENGINE, adapter)

    assert from_state(request_for(app), ENGINE) is adapter


def test_from_state_refuses_a_missing_adapter_naming_the_attribute() -> None:
    with pytest.raises(RuntimeError, match=r"app\.state\.engine is not set"):
        from_state(request_for(FastAPI()), ENGINE)


def test_git_adapter_reads_tolerantly_and_answers_none_when_unwired() -> None:
    assert git_adapter(request_for(FastAPI())) is None


def test_git_adapter_answers_the_stored_adapter() -> None:
    app = FastAPI()
    adapter = object()
    setattr(app.state, GIT, adapter)

    assert git_adapter(request_for(app)) is adapter


def test_required_git_refuses_loudly_naming_who_needed_it() -> None:
    with pytest.raises(RuntimeError, match=r"pre-flight needs a git port"):
        required_git(request_for(FastAPI()), "pre-flight")


def test_required_git_answers_the_stored_adapter() -> None:
    app = FastAPI()
    adapter = object()
    setattr(app.state, GIT, adapter)

    assert required_git(request_for(app), "create_run") is adapter
