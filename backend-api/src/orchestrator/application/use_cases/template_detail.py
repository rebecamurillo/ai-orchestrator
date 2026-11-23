"""The read model of one stored Template version."""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.application.templates.model import InputDecl, TemplateType
from orchestrator.domain.entities.template import TemplateCaller, TemplateVersion


@dataclass(frozen=True)
class TemplateVersionDetail:
    """The read model `GET /templates/{name}/{version}` renders.

    `pinned_by` defaults to `0` so a fixture built before 4.4 (3.1's own, and
    `test_template_version_out_of_a_detail_hardcodes_pinned_by_zero`) still constructs one
    without naming it; `get_version` in `use_cases/templates.py` is the only caller that
    fills it with a real count.
    """

    template: TemplateVersion
    called_by: tuple[TemplateCaller, ...]
    inputs: tuple[InputDecl, ...]
    pinned_by: int = 0
    type: TemplateType = "auto"
