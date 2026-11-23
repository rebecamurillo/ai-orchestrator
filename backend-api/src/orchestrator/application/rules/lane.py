"""Which engine queue a Run waits in (AD-6, AD-12 amended)."""

from __future__ import annotations

from collections.abc import Collection

from orchestrator.application.templates.model import TemplateType
from orchestrator.domain.statuses import Lane

#: The row kind that makes a Run a conversation. Epic 4 story 3 replaces this with its
#: `CONVERSATION_KIND`.
CONVERSATION_KIND_NAME = "conversation"


def lane_of(template_type: TemplateType, row_kinds: Collection[str]) -> Lane:
    """`interactive` only for an `interactive` template whose plan holds a conversation row."""
    if template_type == "interactive" and CONVERSATION_KIND_NAME in row_kinds:
        return "interactive"
    return "walk"
