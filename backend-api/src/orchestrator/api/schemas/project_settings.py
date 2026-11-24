"""The bodies of the run-defaults and initiative-folder `PUT`s."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.api.schemas.common import StorableText
from orchestrator.api.schemas.runs import BudgetUsd
from orchestrator.application.use_cases.project_run_defaults import RunDefaults


class RunDefaultsIn(BaseModel):
    """Replaces all five run defaults together; `null` clears one, an omitted key is refused."""

    model_config = ConfigDict(extra="forbid")

    default_budget_usd: BudgetUsd | None
    default_harness: Annotated[str, Field(pattern=r"^[a-z0-9-]+$")] | None
    default_model: Annotated[StorableText, Field(min_length=1)] | None
    default_autonomy: Literal["auto", "checkpoints"] | None
    default_senior_model: Annotated[StorableText, Field(min_length=1)] | None

    def as_defaults(self) -> RunDefaults:
        return RunDefaults(
            default_budget_usd=self.default_budget_usd,
            default_harness=self.default_harness,
            default_model=self.default_model,
            default_autonomy=self.default_autonomy,
            default_senior_model=self.default_senior_model,
        )


class InitiativeFolderIn(BaseModel):
    """The folder rule is the use case's, so a bad folder is a 422 from `Invalid`."""

    model_config = ConfigDict(extra="forbid")

    initiative_folder: str
