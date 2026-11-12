"""`available_models` (epic 2 story 4, AC1-AC3, AC5)."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.harness_models import (
    EMPTY_NOTE,
    LITELLM_NOTE,
    available_models,
)
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.gateway import GatewayUnreachable
from tests.unit.fakes.gateway import FakeGatewayModels

KNOWN = {"claude", "codex", "local"}


def test_litellm_equals_the_fakes_list() -> None:
    answer = available_models("claude", FakeGatewayModels(("claude-sonnet", "gpt-5")), (), KNOWN)
    assert (answer.source, answer.models, answer.note) == (
        "litellm",
        ("claude-sonnet", "gpt-5"),
        LITELLM_NOTE,
    )
    assert (answer.code, answer.guide) == (None, None)


def test_an_empty_list_stays_litellm_with_its_note() -> None:
    answer = available_models("claude", FakeGatewayModels(()), (), KNOWN)
    assert (answer.source, answer.models, answer.note) == ("litellm", (), EMPTY_NOTE)


def test_no_gateway_is_none_with_the_code_naming_the_harness() -> None:
    answer = available_models("codex", None, (), KNOWN)
    assert answer.source == "none"
    assert answer.models == ()
    assert answer.note is not None
    assert answer.note.startswith("codex cannot list its models here")
    assert answer.code == "refusal-models-unlisted"
    assert answer.guide == "errors/refusal-models-unlisted"


def test_local_is_configured_and_never_calls_the_gateway() -> None:
    fake = FakeGatewayModels(("x",))
    answer = available_models("local", fake, ("local-coder", "local-general"), KNOWN)
    assert (answer.source, answer.models, answer.note) == (
        "configured",
        ("local-coder", "local-general"),
        None,
    )
    assert fake.calls == 0


def test_an_unreachable_gateway_propagates() -> None:
    with pytest.raises(GatewayUnreachable):
        available_models("claude", FakeGatewayModels(error=GatewayUnreachable("x")), (), KNOWN)


def test_an_unknown_harness_is_not_found() -> None:
    with pytest.raises(NotFound):
        available_models("nosuch", None, (), KNOWN)
