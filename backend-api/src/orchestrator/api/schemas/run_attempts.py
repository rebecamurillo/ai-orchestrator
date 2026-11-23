"""Response schemas for the attempt-log endpoint (story 1-1)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.application.use_cases.attempt_log import LogPage


def _drop_default(schema: dict[str, Any]) -> None:
    """Strip the JSON-schema `default` so `openapi-typescript` still emits the field optional."""
    schema.pop("default", None)


class LogPageOut(BaseModel):
    """One page of an attempt's log, addressed by byte cursor.

    `next_cursor` is the byte offset immediately after the last `\\n` in `lines`.
    Pass it as `?cursor=` on the next poll to receive only newly appended content.
    `eof=True` means no bytes follow `next_cursor` at the time this page was read.

    `state` says why a page is empty or gone (AD-40): `text` (the lines are the log),
    `no_output` (the attempt produced none; `reason` when nothing was recorded) or
    `removed` (the file is gone; `removed_at` when the sweep stamped it).
    """

    lines: list[str]
    next_cursor: Annotated[int, Field(ge=0)]
    eof: bool
    state: Literal["text", "no_output", "removed"] = Field(
        default="text", json_schema_extra=_drop_default
    )
    removed_at: UtcTimestamp | None = Field(default=None, json_schema_extra=_drop_default)
    reason: str | None = Field(default=None, json_schema_extra=_drop_default)

    @classmethod
    def of(cls, page: LogPage) -> LogPageOut:
        return cls(
            lines=page.lines,
            next_cursor=page.next_cursor,
            eof=page.eof,
            state=page.state,
            removed_at=page.removed_at,
            reason=page.reason,
        )
