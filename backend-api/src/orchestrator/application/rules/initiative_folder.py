"""Bind a Run's `initiative_folder` input to its repository's initiative folder (SPEC CAP-4)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.application.templates.plan_model import PlanError
from orchestrator.domain.entities.repository import is_valid_folder

INITIATIVE_FOLDER_INPUT = "initiative_folder"


def bind_initiative_folder(
    *, declared: bool, folder: str, inputs: Mapping[str, Any]
) -> dict[str, Any]:
    """The inputs a Run is planned and stored with.

    Undeclared: unchanged. Absent or `None`: the repository's folder. A value equal to or
    under the folder: kept. Anything else is a `PlanError`.
    """
    bound = dict(inputs)
    if not declared:
        return bound
    value = bound.get(INITIATIVE_FOLDER_INPUT)
    if value is None:
        bound[INITIATIVE_FOLDER_INPUT] = folder
        return bound
    if (
        isinstance(value, str)
        and is_valid_folder(value)
        and (value == folder or value.startswith(f"{folder}/"))
    ):
        return bound
    raise PlanError(
        reason=f"initiative_folder {value} is not under the repository's initiative folder {folder}"
    )
