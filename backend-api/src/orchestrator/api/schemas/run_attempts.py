"""Response schemas for the attempt-log endpoint (story 1-1)."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class LogPageOut(BaseModel):
    """One page of an attempt's log, addressed by byte cursor.

    `next_cursor` is the byte offset immediately after the last `\\n` in `lines`.
    Pass it as `?cursor=` on the next poll to receive only newly appended content.
    `eof=True` means no bytes follow `next_cursor` at the time this page was read.
    """

    lines: list[str]
    next_cursor: Annotated[int, Field(ge=0)]
    eof: bool
