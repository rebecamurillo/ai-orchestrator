"""Fixture values the initiative tests own (AD-36)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from orchestrator.domain.entities.initiative import FrozenSequence, FrozenWorkflow, Initiative
from orchestrator.domain.entities.project_package import GateWords, StepDecl
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id

AT = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)


def a_sequence(package: str = "p") -> FrozenSequence:
    step = StepDecl(
        id="spec", kind="conversation", skill="s", persona=None, file="a.md", writes=("SPEC.md",)
    )
    return FrozenSequence(
        package=package,
        sha="abc123",
        workflows=(
            FrozenWorkflow(
                workflow="spec",
                template="p/spec",
                version=2,
                type="interactive",
                shown_as="workflow",
                steps=(step,),
            ),
            FrozenWorkflow(
                workflow="build",
                template="p/build",
                version=1,
                type="auto",
                shown_as="step",
                steps=(),
            ),
        ),
        gate=GateWords(pass_words=("pass",), fail_words=("fail",), owners_key="owners"),
        status_map={"done": "done"},
    )


def an_initiative(**overrides: Any) -> Initiative:
    values: dict[str, Any] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "slug": "snake",
        "name": "Snake",
        "first_message": "make a snake game",
        "sequence": a_sequence(),
        "created_at": AT,
    }
    values.update(overrides)
    return Initiative(**values)


def a_run(*, project_id: UUID | None = None, minutes: int = 0, **overrides: Any) -> Run:
    values: dict[str, Any] = {
        "id": new_id(),
        "project_id": project_id or new_id(),
        "repository_id": new_id(),
        "template_name": "t",
        "template_version": 1,
        "pinned_versions": (),
        "inputs": {},
        "status": "queued",
        "plan_ref": None,
        "plan_refs": {},
        "engine_ref": {},
        "budget_usd": None,
        "spend_usd": Decimal("0"),
        "re_review_done": False,
        "created_at": AT + timedelta(minutes=minutes),
    }
    values.update(overrides)
    return Run(**values)
