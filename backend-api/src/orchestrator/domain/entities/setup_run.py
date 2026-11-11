"""The last setup run's record, as the setup runner writes it (C6, AD-29).

The backend only reads it; extra keys are ignored so the runner may add some, and a missing
required key is a validation error.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, Field


def _utc(value: datetime) -> datetime:
    try:
        return value.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError("timestamp out of range in UTC") from exc


#: Converted here so a stamp `UtcTimestamp` would refuse (naive, or out of range once in UTC)
#: makes the record unreadable rather than the route a 500.
UtcStamp = Annotated[AwareDatetime, AfterValidator(_utc)]


class BmadPhase(BaseModel):
    choice: str
    version: str | None = None
    ok: bool
    reason: str | None = None


class ScriptRun(BaseModel):
    name: str
    exit: int
    ok: bool
    clashes: list[str] = Field(default_factory=list)
    seconds: float
    log: str


class OperatorPhase(BaseModel):
    ok: bool


class SetupCatalog(BaseModel):
    claude: int
    codex: int
    opencode: int


class SetupRun(BaseModel):
    at: UtcStamp
    trigger: str
    release: str
    bmad: BmadPhase
    scripts: list[ScriptRun]
    operator: OperatorPhase
    catalog: SetupCatalog
