"""The reopen wire shapes (epic 9 story 2): the body, the answer and the new detail fields."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.initiative_detail import DetailWorkflowOut, ReopenedAfterOut
from orchestrator.api.schemas.initiatives import ReopenIn, ReopenOut
from orchestrator.application.use_cases.initiative_view_types import DetailWorkflow, ReopenedAfter

ID = UUID("01960000-0000-7000-8000-000000000009")


@pytest.mark.parametrize(
    "body", [{"step": "tech"}, {"reason": "r"}, {"step": "tech", "reason": "r", "x": 1}]
)
def test_the_body_refuses_a_missing_or_extra_field(body: dict[str, str | int]) -> None:
    with pytest.raises(ValidationError):
        ReopenIn.model_validate(body)


@pytest.mark.parametrize("reason", ["x\x00", "x\ud800"])
def test_the_body_refuses_a_reason_no_column_can_store(reason: str) -> None:
    with pytest.raises(ValidationError, match="reason"):
        ReopenIn.model_validate({"step": "tech", "reason": reason})


def test_the_body_and_the_answer_hold_their_fields() -> None:
    assert ReopenIn(step="tech", reason="r").model_dump() == {"step": "tech", "reason": "r"}
    assert ReopenOut(run_id=ID, round=2).model_dump(mode="json") == {"run_id": str(ID), "round": 2}


def test_reopened_after_maps_field_for_field() -> None:
    out = ReopenedAfterOut.of(ReopenedAfter("build", "attached"))

    assert out.model_dump() == {"workflow": "build", "branch": "attached"}


@pytest.mark.parametrize("token", [None, "BLK"])
def test_a_workflow_maps_its_token(token: str | None) -> None:
    workflow = DetailWorkflow(1, "build", "p/build", 1, "auto", None, None, [], token=token)  # type: ignore[arg-type]

    assert DetailWorkflowOut.of(workflow).model_dump(mode="json")["token"] == token


def test_a_step_maps_its_reopened_after() -> None:
    from orchestrator.api.schemas.initiative_detail import DetailStepOut  # noqa: PLC0415
    from orchestrator.application.use_cases.initiative_view_types import DetailStep  # noqa: PLC0415

    step = DetailStep(
        "tech", "conversation", None, None, None, "planned", "", [], [],
        reopened_after=ReopenedAfter("build", "created"),
    )  # fmt: skip

    out = DetailStepOut.of(step).model_dump(mode="json")

    assert out["reopened_after"] == {"workflow": "build", "branch": "created"}
