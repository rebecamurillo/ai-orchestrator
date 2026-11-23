"""What a `uses: conversation` step declares beside its `with` (AD-15 amended).

Its own module: `model.py` is at its length limit and `conversation.py` imports `model`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ConversationExtras(BaseModel):
    """The step-level siblings of `with` only a `uses: conversation` step carries."""

    model_config = ConfigDict(frozen=True)

    line: int
    expect_files: tuple[str, ...] = ()
    expect_success: tuple[str, ...] = ()
    expect_blocked: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    prompt_open: str = ""
    prompt_close: str = ""
