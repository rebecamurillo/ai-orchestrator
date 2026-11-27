"""Which engine queue a Run waits in (AD-6, AD-12 amended)."""

from __future__ import annotations

from collections.abc import Collection

from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.templates.model import TemplateType
from orchestrator.domain.statuses import Lane


def lane_of(template_type: TemplateType, row_kinds: Collection[str]) -> Lane:
    """`interactive` only for an `interactive` template whose plan holds a conversation row."""
    if template_type == "interactive" and CONVERSATION_KIND in row_kinds:
        return "interactive"
    return "walk"
