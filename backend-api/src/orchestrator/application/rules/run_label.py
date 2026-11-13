"""The Run label rules: computed default and operator text (story 3; ARCHITECTURE.md §6.2)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from orchestrator.domain.errors import Invalid

MAX_LABEL = 120


def _folder(inputs: Mapping[str, Any]) -> str:
    for key in ("initiative_folder", "spec_folder"):
        value = inputs.get(key)
        if isinstance(value, str) and value:
            return PurePosixPath(value.rstrip("/")).name
    return ""


def default_label(
    project_name: str, inputs: Mapping[str, Any], template_name: str, created_at: datetime
) -> str:
    words = [
        project_name,
        _folder(inputs),
        template_name,
        created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M"),
    ]
    return " ".join(word for word in words if word)


def clean_label(text: str) -> str:
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_LABEL:
        raise Invalid("label must be 1-120 characters")
    return cleaned


def initial_label(
    given: str | None,
    project_name: str,
    inputs: Mapping[str, Any],
    template_name: str,
    created_at: datetime,
) -> tuple[str, bool]:
    if given is not None:
        return clean_label(given), True
    return default_label(project_name, inputs, template_name, created_at), False
