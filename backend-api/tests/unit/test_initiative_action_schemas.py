"""The initiative action bodies (story 5, epic 7, AC4 and AC9)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.initiatives import InitiativeIn, StartNextIn

CREATE = {"project_id": str(uuid4()), "name": "Snake", "first_message": "hi"}


def test_the_create_body_is_read() -> None:
    assert InitiativeIn.model_validate(CREATE).name == "Snake"


@pytest.mark.parametrize(
    "body",
    [
        {**CREATE, "extra": 1},
        {"project_id": CREATE["project_id"], "name": "Snake"},
        {**CREATE, "project_id": "nope"},
    ],
)
def test_the_create_body_refuses_what_it_does_not_declare(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        InitiativeIn.model_validate(body)


@pytest.mark.parametrize("seq", [0, 3])
def test_start_next_accepts_a_stop_number(seq: int) -> None:
    assert StartNextIn.model_validate({"park_seq": seq}).park_seq == seq


@pytest.mark.parametrize(
    "body",
    [{"park_seq": "1"}, {"park_seq": True}, {"park_seq": -1}, {"park_seq": 1, "extra": 1}, {}],
)
def test_start_next_refuses_anything_else(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        StartNextIn.model_validate(body)
